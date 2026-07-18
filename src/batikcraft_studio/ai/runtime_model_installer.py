"""Download, report, cancel, and validate managed Stable Diffusion runtimes."""

from __future__ import annotations

import fnmatch
import io
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from batikcraft_studio.dependency_bootstrap import default_managed_dependency_root

BASE_MODEL_REPO_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
CONTROLNET_REPO_ID = "lllyasviel/control_v11p_sd15_canny"
SDXL_BASE_MODEL_REPO_ID = "stabilityai/stable-diffusion-xl-base-1.0"
_BASE_MODEL_FOLDER = "stable-diffusion-v1-5"
_CONTROLNET_FOLDER = "control_v11p_sd15_canny"
_SDXL_BASE_MODEL_FOLDER = "stable-diffusion-xl-base-1.0"
_MODEL_WEIGHT_SUFFIXES = {".bin", ".safetensors"}
_IGNORE_PATTERNS = ("*.ckpt", "*.onnx", "*.msgpack", "*.h5")

_BASE_ALLOW_PATTERNS = (
    "model_index.json",
    "feature_extractor/*",
    "safety_checker/*",
    "scheduler/*",
    "text_encoder/*",
    "tokenizer/*",
    "unet/*",
    "vae/*",
)
_CONTROLNET_ALLOW_PATTERNS = (
    "config.json",
    "diffusion_pytorch_model.bin",
    "diffusion_pytorch_model.safetensors",
)
_SDXL_ALLOW_PATTERNS = (
    "model_index.json",
    "scheduler/*",
    "text_encoder/*",
    "text_encoder_2/*",
    "tokenizer/*",
    "tokenizer_2/*",
    "unet/*",
    "vae/*",
)


class RuntimeModelInstallError(RuntimeError):
    """Raised when a managed model download or validation fails."""


class RuntimeModelInstallCancelled(RuntimeModelInstallError):
    """Raised when the user cancels a model installation."""


@dataclass(frozen=True, slots=True)
class RuntimeModelPaths:
    """Resolved folders consumed by the legacy SD 1.5 provider."""

    base_model: Path
    controlnet: Path


@dataclass(frozen=True, slots=True)
class BatikBrewRuntimePaths:
    """Resolved SDXL folder consumed by the BatikBrew generator."""

    base_model: Path


@dataclass(frozen=True, slots=True)
class RuntimeModelInstallProgress:
    """Progress update safe to pass from a worker thread to Tk."""

    stage: str
    message: str
    completed: int
    total: int = 4
    downloaded_bytes: int = 0
    total_bytes: int = 0
    current_file: str = ""

    @property
    def download_percent(self) -> float | None:
        if self.total_bytes <= 0:
            return None
        value = self.downloaded_bytes / self.total_bytes * 100.0
        return max(0.0, min(100.0, value))


ProgressCallback = Callable[[RuntimeModelInstallProgress], object]
SnapshotDownload = Callable[..., str]
HubFileDownload = Callable[..., str]


@dataclass(frozen=True, slots=True)
class _RepositoryFile:
    name: str
    size: int


class _SnapshotProgressTracker:
    """Aggregate byte progress from all files in one model repository."""

    def __init__(
        self,
        *,
        progress: ProgressCallback | None,
        cancel_event: threading.Event | None,
        stage: str,
        message: str,
        completed: int,
        stage_total: int,
        total_bytes: int,
        completed_bytes: int = 0,
    ) -> None:
        self.progress = progress
        self.cancel_event = cancel_event
        self.stage = stage
        self.message = message
        self.completed = completed
        self.stage_total = stage_total
        self.total_bytes = max(0, int(total_bytes))
        self._base_completed = max(0, int(completed_bytes))
        self._file_progress: dict[str, int] = {}
        self.current_file = ""
        self._lock = threading.Lock()
        self._last_emit = 0.0

    def raise_if_cancelled(self) -> None:
        _raise_if_cancelled(self.cancel_event)

    def register_file(self, name: str, *, total: int, initial: int) -> None:
        with self._lock:
            self.current_file = name
            self._file_progress[name] = max(
                self._file_progress.get(name, 0),
                min(max(0, int(initial)), max(0, int(total))),
            )
        self._emit(force=True)

    def advance_file(self, name: str, amount: int) -> None:
        if amount <= 0:
            return
        with self._lock:
            self.current_file = name
            current = self._file_progress.get(name, 0)
            self._file_progress[name] = current + int(amount)
        self._emit(force=False)

    def complete_file(self, name: str, size: int) -> None:
        with self._lock:
            self.current_file = name
            self._file_progress[name] = max(0, int(size))
        self._emit(force=True)

    def complete(self) -> None:
        with self._lock:
            self._base_completed = self.total_bytes
            self._file_progress.clear()
        self._emit(force=True)

    def _downloaded_bytes(self) -> int:
        return self._base_completed + sum(self._file_progress.values())

    def _emit(self, *, force: bool) -> None:
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_emit < 0.10:
                return
            self._last_emit = now
            downloaded = self._downloaded_bytes()
            total_bytes = self.total_bytes
            current_file = self.current_file
        _report(
            self.progress,
            self.stage,
            self.message,
            self.completed,
            self.stage_total,
            downloaded_bytes=min(downloaded, total_bytes) if total_bytes else downloaded,
            total_bytes=total_bytes,
            current_file=current_file,
        )

    def tqdm_class(self, current_file: str) -> type:
        """Return a silent tqdm subclass that reports byte updates and cancellation."""

        from tqdm.auto import tqdm as base_tqdm

        tracker = self

        class BatikCraftDownloadTqdm(base_tqdm):  # type: ignore[misc, valid-type]
            def __init__(self, *args: object, **kwargs: object) -> None:
                kwargs["disable"] = False
                kwargs["file"] = io.StringIO()
                kwargs.setdefault("leave", False)
                super().__init__(*args, **kwargs)
                tracker.raise_if_cancelled()
                tracker.register_file(
                    current_file,
                    total=int(getattr(self, "total", 0) or 0),
                    initial=int(getattr(self, "n", 0) or 0),
                )

            def update(self, n: int | float = 1) -> bool | None:
                tracker.raise_if_cancelled()
                previous = int(getattr(self, "n", 0) or 0)
                result = super().update(n)
                current = int(getattr(self, "n", previous) or previous)
                tracker.advance_file(current_file, max(0, current - previous))
                tracker.raise_if_cancelled()
                return result

        BatikCraftDownloadTqdm.__name__ = "BatikCraftDownloadTqdm"
        return BatikCraftDownloadTqdm


def default_runtime_model_root() -> Path:
    """Return the Stable Diffusion folder inside managed dependencies."""

    return default_managed_dependency_root() / "models" / "runtime"


def runtime_model_paths(root: str | Path | None = None) -> RuntimeModelPaths:
    install_root = Path(root) if root is not None else default_runtime_model_root()
    install_root = install_root.expanduser()
    return RuntimeModelPaths(
        base_model=install_root / _BASE_MODEL_FOLDER,
        controlnet=install_root / _CONTROLNET_FOLDER,
    )


def batikbrew_runtime_model_paths(
    root: str | Path | None = None,
) -> BatikBrewRuntimePaths:
    install_root = Path(root) if root is not None else default_runtime_model_root()
    return BatikBrewRuntimePaths(
        base_model=install_root.expanduser() / _SDXL_BASE_MODEL_FOLDER,
    )


def find_installed_runtime_models(
    root: str | Path | None = None,
) -> RuntimeModelPaths | None:
    paths = runtime_model_paths(root)
    try:
        validate_runtime_models(paths)
    except RuntimeModelInstallError:
        return None
    return paths


def find_installed_batikbrew_runtime(
    root: str | Path | None = None,
) -> BatikBrewRuntimePaths | None:
    paths = batikbrew_runtime_model_paths(root)
    try:
        validate_batikbrew_runtime(paths)
    except RuntimeModelInstallError:
        return None
    return paths


def validate_runtime_models(paths: RuntimeModelPaths) -> None:
    errors: list[str] = []
    base = paths.base_model
    controlnet = paths.controlnet
    if not (base / "model_index.json").is_file():
        errors.append(f"Base model belum memiliki model_index.json: {base}")
    for folder_name in ("scheduler", "text_encoder", "tokenizer", "unet", "vae"):
        folder = base / folder_name
        if not folder.is_dir():
            errors.append(f"Folder base model belum lengkap: {folder}")
    for folder_name in ("text_encoder", "unet", "vae"):
        folder = base / folder_name
        if folder.is_dir() and not _contains_model_weight(folder):
            errors.append(f"Bobot model tidak ditemukan di: {folder}")
    if not (controlnet / "config.json").is_file():
        errors.append(f"ControlNet belum memiliki config.json: {controlnet}")
    if controlnet.is_dir() and not _contains_model_weight(controlnet):
        errors.append(f"Bobot ControlNet tidak ditemukan di: {controlnet}")
    if errors:
        raise RuntimeModelInstallError("\n".join(errors))


def validate_batikbrew_runtime(paths: BatikBrewRuntimePaths) -> None:
    base = paths.base_model
    errors: list[str] = []
    if not (base / "model_index.json").is_file():
        errors.append(f"Runtime SDXL belum memiliki model_index.json: {base}")
    required = (
        "scheduler",
        "text_encoder",
        "text_encoder_2",
        "tokenizer",
        "tokenizer_2",
        "unet",
        "vae",
    )
    for folder_name in required:
        folder = base / folder_name
        if not folder.is_dir():
            errors.append(f"Folder SDXL belum lengkap: {folder}")
    for folder_name in ("text_encoder", "text_encoder_2", "unet", "vae"):
        folder = base / folder_name
        if folder.is_dir() and not _contains_model_weight(folder):
            errors.append(f"Bobot SDXL tidak ditemukan di: {folder}")
    if errors:
        raise RuntimeModelInstallError("\n".join(errors))


def install_default_runtime_models(
    root: str | Path | None = None,
    *,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    snapshot_download_func: SnapshotDownload | None = None,
) -> RuntimeModelPaths:
    """Download the legacy SD 1.5 and Canny ControlNet runtime."""

    paths = runtime_model_paths(root)
    paths.base_model.parent.mkdir(parents=True, exist_ok=True)
    _report(progress, "checking", "Memeriksa runtime AI yang sudah ada…", 0, 4)
    if find_installed_runtime_models(root) is not None:
        _report(progress, "complete", "Runtime AI sudah terpasang dan siap digunakan.", 4, 4)
        return paths
    _raise_if_cancelled(cancel_event)
    if not _base_model_is_complete(paths.base_model):
        message = "Mengunduh Stable Diffusion 1.5. File parsial dapat dilanjutkan…"
        _report(progress, "base", message, 1, 4)
        _download_snapshot(
            snapshot_download_func,
            repo_id=BASE_MODEL_REPO_ID,
            destination=paths.base_model,
            allow_patterns=_BASE_ALLOW_PATTERNS,
            progress=progress,
            cancel_event=cancel_event,
            stage="base",
            message=message,
            completed=1,
            stage_total=4,
        )
    else:
        _report(progress, "base", "Stable Diffusion 1.5 sudah tersedia.", 2, 4)
    _raise_if_cancelled(cancel_event)
    if not _controlnet_is_complete(paths.controlnet):
        message = "Mengunduh ControlNet Canny untuk Stable Diffusion 1.5…"
        _report(progress, "controlnet", message, 2, 4)
        _download_snapshot(
            snapshot_download_func,
            repo_id=CONTROLNET_REPO_ID,
            destination=paths.controlnet,
            allow_patterns=_CONTROLNET_ALLOW_PATTERNS,
            progress=progress,
            cancel_event=cancel_event,
            stage="controlnet",
            message=message,
            completed=2,
            stage_total=4,
        )
    else:
        _report(progress, "controlnet", "ControlNet Canny sudah tersedia.", 3, 4)
    _raise_if_cancelled(cancel_event)
    _report(progress, "validating", "Memvalidasi file runtime AI…", 3, 4)
    validate_runtime_models(paths)
    _report(progress, "complete", "Runtime AI berhasil dipasang.", 4, 4)
    return paths


def install_batikbrew_runtime(
    root: str | Path | None = None,
    *,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    snapshot_download_func: SnapshotDownload | None = None,
) -> BatikBrewRuntimePaths:
    """Download the SDXL base model used by the BatikCraft notebooks."""

    paths = batikbrew_runtime_model_paths(root)
    paths.base_model.parent.mkdir(parents=True, exist_ok=True)
    _report(progress, "checking", "Memeriksa runtime BatikBrew SDXL…", 0, 3)
    if find_installed_batikbrew_runtime(root) is not None:
        _report(progress, "complete", "Runtime BatikBrew SDXL sudah siap.", 3, 3)
        return paths
    _raise_if_cancelled(cancel_event)
    if not _sdxl_model_is_complete(paths.base_model):
        message = "Mengunduh Stable Diffusion XL. Ukuran sekitar 7 GB dan dapat dilanjutkan…"
        _report(progress, "sdxl", message, 1, 3)
        _download_snapshot(
            snapshot_download_func,
            repo_id=SDXL_BASE_MODEL_REPO_ID,
            destination=paths.base_model,
            allow_patterns=_SDXL_ALLOW_PATTERNS,
            progress=progress,
            cancel_event=cancel_event,
            stage="sdxl",
            message=message,
            completed=1,
            stage_total=3,
        )
    else:
        _report(progress, "sdxl", "Stable Diffusion XL sudah tersedia.", 2, 3)
    _raise_if_cancelled(cancel_event)
    _report(progress, "validating", "Memvalidasi dua text encoder, UNet, dan VAE SDXL…", 2, 3)
    validate_batikbrew_runtime(paths)
    _report(progress, "complete", "Runtime BatikBrew SDXL berhasil dipasang.", 3, 3)
    return paths


def _load_hub_tools() -> tuple[Any, HubFileDownload]:
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        raise RuntimeModelInstallError(
            "Komponen pengunduh model belum tersedia. Buka Dependencies lalu tekan "
            "Instal Semua AI + BatikBrew SDXL."
        ) from exc
    return HfApi(), hf_hub_download


def _repository_files(api: Any, repo_id: str, patterns: tuple[str, ...]) -> list[_RepositoryFile]:
    try:
        info = api.model_info(repo_id, files_metadata=True)
    except Exception as exc:  # noqa: BLE001 - normalize third-party network errors
        raise RuntimeModelInstallError(
            f"Metadata ukuran model {repo_id} tidak dapat dibaca: {exc}"
        ) from exc

    files: list[_RepositoryFile] = []
    for sibling in info.siblings or ():
        name = str(getattr(sibling, "rfilename", "") or "")
        if not name or not _path_matches(name, patterns):
            continue
        if _path_matches(name, _IGNORE_PATTERNS):
            continue
        size = getattr(sibling, "size", None)
        if size is None:
            lfs = getattr(sibling, "lfs", None)
            size = getattr(lfs, "size", None) if lfs is not None else None
            if size is None and isinstance(lfs, dict):
                size = lfs.get("size")
        try:
            numeric_size = max(0, int(size or 0))
        except (TypeError, ValueError):
            numeric_size = 0
        files.append(_RepositoryFile(name=name, size=numeric_size))
    if not files:
        raise RuntimeModelInstallError(
            f"Tidak ada file model yang cocok pada repository {repo_id}."
        )
    return files


def _download_repository_files(
    *,
    api: Any,
    file_downloader: HubFileDownload,
    repo_id: str,
    destination: Path,
    allow_patterns: tuple[str, ...],
    progress: ProgressCallback | None,
    cancel_event: threading.Event | None,
    stage: str,
    message: str,
    completed: int,
    stage_total: int,
) -> None:
    files = _repository_files(api, repo_id, allow_patterns)
    total_bytes = sum(item.size for item in files)
    completed_files = {
        item.name
        for item in files
        if item.size > 0
        and (destination / item.name).is_file()
        and (destination / item.name).stat().st_size == item.size
    }
    completed_bytes = sum(item.size for item in files if item.name in completed_files)
    tracker = _SnapshotProgressTracker(
        progress=progress,
        cancel_event=cancel_event,
        stage=stage,
        message=message,
        completed=completed,
        stage_total=stage_total,
        total_bytes=total_bytes,
        completed_bytes=completed_bytes,
    )
    tracker._emit(force=True)

    for item in files:
        if item.name in completed_files:
            continue
        tracker.raise_if_cancelled()
        try:
            file_downloader(
                repo_id=repo_id,
                filename=item.name,
                local_dir=str(destination),
                tqdm_class=tracker.tqdm_class(item.name),
            )
        except RuntimeModelInstallCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize network errors
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeModelInstallCancelled(
                    "Unduhan dibatalkan. File parsial disimpan agar dapat dilanjutkan."
                ) from exc
            raise RuntimeModelInstallError(
                f"Gagal mengunduh {repo_id}/{item.name}. Detail: {exc}"
            ) from exc
        tracker.complete_file(item.name, item.size)

    tracker.raise_if_cancelled()
    tracker.complete()


def _download_snapshot(
    snapshot_downloader: SnapshotDownload | None,
    *,
    repo_id: str,
    destination: Path,
    allow_patterns: tuple[str, ...],
    progress: ProgressCallback | None,
    cancel_event: threading.Event | None,
    stage: str,
    message: str,
    completed: int,
    stage_total: int,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    _raise_if_cancelled(cancel_event)
    if snapshot_downloader is not None:
        try:
            snapshot_downloader(
                repo_id=repo_id,
                local_dir=str(destination),
                allow_patterns=list(allow_patterns),
                ignore_patterns=list(_IGNORE_PATTERNS),
                max_workers=2,
            )
        except Exception as exc:  # noqa: BLE001 - normalize test/custom download errors
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeModelInstallCancelled(
                    "Unduhan dibatalkan. File parsial disimpan agar dapat dilanjutkan."
                ) from exc
            raise RuntimeModelInstallError(
                f"Gagal mengunduh {repo_id}. Detail: {exc}"
            ) from exc
        _raise_if_cancelled(cancel_event)
        return

    api, file_downloader = _load_hub_tools()
    _download_repository_files(
        api=api,
        file_downloader=file_downloader,
        repo_id=repo_id,
        destination=destination,
        allow_patterns=allow_patterns,
        progress=progress,
        cancel_event=cancel_event,
        stage=stage,
        message=message,
        completed=completed,
        stage_total=stage_total,
    )


def _path_matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _base_model_is_complete(path: Path) -> bool:
    if not (path / "model_index.json").is_file():
        return False
    required_folders = ("scheduler", "text_encoder", "tokenizer", "unet", "vae")
    if any(not (path / name).is_dir() for name in required_folders):
        return False
    folders = ("text_encoder", "unet", "vae")
    return all(_contains_model_weight(path / name) for name in folders)


def _sdxl_model_is_complete(path: Path) -> bool:
    if not (path / "model_index.json").is_file():
        return False
    required = (
        "scheduler",
        "text_encoder",
        "text_encoder_2",
        "tokenizer",
        "tokenizer_2",
        "unet",
        "vae",
    )
    if any(not (path / name).is_dir() for name in required):
        return False
    folders = ("text_encoder", "text_encoder_2", "unet", "vae")
    return all(_contains_model_weight(path / name) for name in folders)


def _controlnet_is_complete(path: Path) -> bool:
    return (path / "config.json").is_file() and _contains_model_weight(path)


def _contains_model_weight(path: Path) -> bool:
    return any(
        item.is_file() and item.suffix.casefold() in _MODEL_WEIGHT_SUFFIXES
        for item in path.rglob("*")
    )


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeModelInstallCancelled(
            "Instalasi dibatalkan. File yang sudah terunduh disimpan agar dapat dilanjutkan."
        )


def _report(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    completed: int,
    total: int,
    *,
    downloaded_bytes: int = 0,
    total_bytes: int = 0,
    current_file: str = "",
) -> None:
    if callback is not None:
        callback(
            RuntimeModelInstallProgress(
                stage=stage,
                message=message,
                completed=completed,
                total=total,
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
                current_file=current_file,
            )
        )


__all__ = [
    "BASE_MODEL_REPO_ID",
    "CONTROLNET_REPO_ID",
    "SDXL_BASE_MODEL_REPO_ID",
    "BatikBrewRuntimePaths",
    "RuntimeModelInstallCancelled",
    "RuntimeModelInstallError",
    "RuntimeModelInstallProgress",
    "RuntimeModelPaths",
    "batikbrew_runtime_model_paths",
    "default_runtime_model_root",
    "find_installed_batikbrew_runtime",
    "find_installed_runtime_models",
    "install_batikbrew_runtime",
    "install_default_runtime_models",
    "runtime_model_paths",
    "validate_batikbrew_runtime",
    "validate_runtime_models",
]
