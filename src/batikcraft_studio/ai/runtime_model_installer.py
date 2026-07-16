"""Download and validate managed Stable Diffusion runtimes.

The legacy object workflow uses SD 1.5 plus Canny ControlNet. BatikBrew generation,
ported from the BatikCraft notebooks, uses the SDXL base model without ControlNet.
Both runtimes are resumable and stored outside the Python package.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .runtime_settings import default_ai_cache_dir

BASE_MODEL_REPO_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
CONTROLNET_REPO_ID = "lllyasviel/control_v11p_sd15_canny"
SDXL_BASE_MODEL_REPO_ID = "stabilityai/stable-diffusion-xl-base-1.0"
_BASE_MODEL_FOLDER = "stable-diffusion-v1-5"
_CONTROLNET_FOLDER = "control_v11p_sd15_canny"
_SDXL_BASE_MODEL_FOLDER = "stable-diffusion-xl-base-1.0"
_MODEL_WEIGHT_SUFFIXES = {".bin", ".safetensors"}

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
    """Raised when the user cancels between download stages."""


@dataclass(frozen=True, slots=True)
class RuntimeModelPaths:
    """Resolved folders consumed by the legacy SD 1.5 provider."""

    base_model: Path
    controlnet: Path


@dataclass(frozen=True, slots=True)
class BatikBrewRuntimePaths:
    """Resolved SDXL folder consumed by the notebook-compatible generator."""

    base_model: Path


@dataclass(frozen=True, slots=True)
class RuntimeModelInstallProgress:
    """Coarse progress update safe to pass from a worker thread to Tk."""

    stage: str
    message: str
    completed: int
    total: int = 4


ProgressCallback = Callable[[RuntimeModelInstallProgress], object]
SnapshotDownload = Callable[..., str]


def default_runtime_model_root() -> Path:
    """Return a stable per-user folder for fully materialized model assets."""

    return default_ai_cache_dir().parent / "runtime"


def runtime_model_paths(root: str | Path | None = None) -> RuntimeModelPaths:
    """Resolve the canonical SD 1.5 and ControlNet installation folders."""

    install_root = Path(root) if root is not None else default_runtime_model_root()
    install_root = install_root.expanduser()
    return RuntimeModelPaths(
        base_model=install_root / _BASE_MODEL_FOLDER,
        controlnet=install_root / _CONTROLNET_FOLDER,
    )


def batikbrew_runtime_model_paths(
    root: str | Path | None = None,
) -> BatikBrewRuntimePaths:
    """Resolve the canonical SDXL installation folder used by BatikBrew."""

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
    """Validate the minimum SD 1.5/ControlNet directory structure."""

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
    """Validate the SDXL structure required by StableDiffusionXLPipeline."""

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
    downloader = snapshot_download_func or _load_snapshot_download()
    _raise_if_cancelled(cancel_event)
    if not _base_model_is_complete(paths.base_model):
        _report(
            progress,
            "base",
            "Mengunduh Stable Diffusion 1.5. Unduhan dapat dilanjutkan jika terputus…",
            1,
            4,
        )
        _download_snapshot(
            downloader,
            repo_id=BASE_MODEL_REPO_ID,
            destination=paths.base_model,
            allow_patterns=_BASE_ALLOW_PATTERNS,
        )
    else:
        _report(progress, "base", "Stable Diffusion 1.5 sudah tersedia.", 2, 4)
    _raise_if_cancelled(cancel_event)
    if not _controlnet_is_complete(paths.controlnet):
        _report(
            progress,
            "controlnet",
            "Mengunduh ControlNet Canny untuk Stable Diffusion 1.5…",
            2,
            4,
        )
        _download_snapshot(
            downloader,
            repo_id=CONTROLNET_REPO_ID,
            destination=paths.controlnet,
            allow_patterns=_CONTROLNET_ALLOW_PATTERNS,
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
    downloader = snapshot_download_func or _load_snapshot_download()
    _raise_if_cancelled(cancel_event)
    if not _sdxl_model_is_complete(paths.base_model):
        _report(
            progress,
            "sdxl",
            "Mengunduh Stable Diffusion XL. Ukuran unduhan sekitar 7 GB dan dapat dilanjutkan…",
            1,
            3,
        )
        _download_snapshot(
            downloader,
            repo_id=SDXL_BASE_MODEL_REPO_ID,
            destination=paths.base_model,
            allow_patterns=_SDXL_ALLOW_PATTERNS,
        )
    else:
        _report(progress, "sdxl", "Stable Diffusion XL sudah tersedia.", 2, 3)
    _raise_if_cancelled(cancel_event)
    _report(progress, "validating", "Memvalidasi dua text encoder, UNet, dan VAE SDXL…", 2, 3)
    validate_batikbrew_runtime(paths)
    _report(progress, "complete", "Runtime BatikBrew SDXL berhasil dipasang.", 3, 3)
    return paths


def _load_snapshot_download() -> SnapshotDownload:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeModelInstallError(
            'Komponen pengunduh model belum terpasang. Instal aplikasi dengan extra AI: '
            'python -m pip install -e ".[ai]"'
        ) from exc
    return snapshot_download


def _download_snapshot(
    downloader: SnapshotDownload,
    *,
    repo_id: str,
    destination: Path,
    allow_patterns: tuple[str, ...],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        downloader(
            repo_id=repo_id,
            local_dir=str(destination),
            allow_patterns=list(allow_patterns),
            ignore_patterns=["*.ckpt", "*.onnx", "*.msgpack", "*.h5"],
            max_workers=4,
        )
    except Exception as exc:  # noqa: BLE001 - normalize third-party network errors
        raise RuntimeModelInstallError(
            f"Gagal mengunduh {repo_id}. Periksa internet dan ruang penyimpanan, "
            f"kemudian tekan instal lagi untuk melanjutkan. Detail: {exc}"
        ) from exc


def _base_model_is_complete(path: Path) -> bool:
    if not (path / "model_index.json").is_file():
        return False
    required_folders = ("scheduler", "text_encoder", "tokenizer", "unet", "vae")
    if any(not (path / name).is_dir() for name in required_folders):
        return False
    return all(_contains_model_weight(path / name) for name in ("text_encoder", "unet", "vae"))


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
    return all(
        _contains_model_weight(path / name)
        for name in ("text_encoder", "text_encoder_2", "unet", "vae")
    )


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
) -> None:
    if callback is not None:
        callback(
            RuntimeModelInstallProgress(
                stage=stage,
                message=message,
                completed=completed,
                total=total,
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
