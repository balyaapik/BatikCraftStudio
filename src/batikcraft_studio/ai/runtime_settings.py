"""Persistent global AI/GPU settings and dependency-free runtime diagnosis."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

AI_SETTINGS_SCHEMA_VERSION = 1
DEFAULT_MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
_DEVICE_VALUES = {"auto", "cpu", "cuda", "mps"}
_PRECISION_VALUES = {"auto", "float16", "float32", "bfloat16"}


def default_ai_settings_path() -> Path:
    """Return a stable per-user configuration path without extra dependencies."""

    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata)
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "BatikCraftStudio" / "ai_runtime.json"


def default_ai_cache_dir() -> Path:
    """Return a persistent model-cache directory that survives application updates."""

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        root = Path(local_appdata)
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "BatikCraftStudio" / "models" / "huggingface"


@dataclass(frozen=True, slots=True)
class AIRuntimeSettings:
    """Global runtime choices shared by every Stable Diffusion workflow."""

    schema_version: int = AI_SETTINGS_SCHEMA_VERSION
    device: str = "auto"
    precision: str = "auto"
    cpu_offload: bool = True
    low_vram_mode: bool = False
    attention_slicing: bool = True
    vae_slicing: bool = True
    vae_tiling: bool = False
    cache_dir: str = field(default_factory=lambda: str(default_ai_cache_dir()))
    default_model: str = field(
        default_factory=lambda: os.environ.get("BATIKCRAFT_PRETRAINED_MODEL", DEFAULT_MODEL_ID)
    )
    local_files_only: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != AI_SETTINGS_SCHEMA_VERSION:
            raise ValueError("Versi konfigurasi AI tidak didukung.")
        device = str(self.device).strip().casefold()
        if device not in _DEVICE_VALUES:
            raise ValueError("Device AI harus auto, cuda, cpu, atau mps.")
        precision = str(self.precision).strip().casefold()
        if precision not in _PRECISION_VALUES:
            raise ValueError("Precision AI harus auto, float16, float32, atau bfloat16.")
        flags = (
            self.cpu_offload,
            self.low_vram_mode,
            self.attention_slicing,
            self.vae_slicing,
            self.vae_tiling,
            self.local_files_only,
        )
        if any(not isinstance(value, bool) for value in flags):
            raise ValueError("Pengaturan optimasi AI harus berupa boolean.")
        model = str(self.default_model).strip()
        if not model or len(model) > 1_000:
            raise ValueError("Model Stable Diffusion global tidak valid.")
        cache = str(Path(str(self.cache_dir).strip() or default_ai_cache_dir()).expanduser())
        object.__setattr__(self, "device", device)
        object.__setattr__(self, "precision", precision)
        object.__setattr__(self, "default_model", model)
        object.__setattr__(self, "cache_dir", cache)

    @property
    def effective_cpu_offload(self) -> bool:
        return self.cpu_offload or self.low_vram_mode

    @property
    def effective_attention_slicing(self) -> bool:
        return self.attention_slicing or self.low_vram_mode

    @property
    def effective_vae_slicing(self) -> bool:
        return self.vae_slicing or self.low_vram_mode

    @property
    def effective_vae_tiling(self) -> bool:
        return self.vae_tiling or self.low_vram_mode

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> AIRuntimeSettings:
        allowed = set(cls.__dataclass_fields__)
        payload = {key: item for key, item in value.items() if key in allowed}
        payload.setdefault("schema_version", AI_SETTINGS_SCHEMA_VERSION)
        return cls(**payload)


class AIRuntimeSettingsStore:
    """Read and atomically persist one global AI settings document."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_ai_settings_path()
        self.last_error: str | None = None

    def load(self) -> AIRuntimeSettings:
        self.last_error = None
        if not self.path.is_file():
            return AIRuntimeSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Akar konfigurasi harus berupa object JSON.")
            return AIRuntimeSettings.from_mapping(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.last_error = f"Konfigurasi AI rusak; default aman digunakan. Detail: {exc}"
            return AIRuntimeSettings()

    def save(self, settings: AIRuntimeSettings) -> Path:
        if not isinstance(settings, AIRuntimeSettings):
            raise TypeError("settings harus berupa AIRuntimeSettings.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        Path(settings.cache_dir).expanduser().mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        encoded = json.dumps(
            settings.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            temporary.write_text(encoded + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        self.last_error = None
        return self.path

    def reset(self) -> AIRuntimeSettings:
        settings = AIRuntimeSettings()
        self.save(settings)
        return settings


@dataclass(frozen=True, slots=True)
class AIRuntimeRecommendation:
    device: str
    precision: str
    cpu_offload: bool
    low_vram_mode: bool
    reason: str


@dataclass(frozen=True, slots=True)
class AIRuntimeReport:
    """Hardware/runtime diagnosis produced without downloading a model."""

    torch_available: bool
    torch_version: str | None
    cuda_build: str | None
    cuda_available: bool
    mps_available: bool
    gpu_name: str | None
    gpu_vram_gb: float | None
    requested_device: str
    effective_device: str | None
    requested_precision: str
    effective_precision: str | None
    tensor_test_ok: bool | None
    tensor_test_ms: float | None
    recommendation: AIRuntimeRecommendation
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def format_text(self) -> str:
        lines = [
            f"PyTorch: {self.torch_version or 'tidak tersedia'}",
            f"CUDA build: {self.cuda_build or '-'}",
            f"CUDA tersedia: {'Ya' if self.cuda_available else 'Tidak'}",
            f"MPS tersedia: {'Ya' if self.mps_available else 'Tidak'}",
            f"GPU: {self.gpu_name or '-'}",
        ]
        if self.gpu_vram_gb is not None:
            lines.append(f"VRAM: {self.gpu_vram_gb:.1f} GB")
        lines.extend(
            [
                f"Device efektif: {self.effective_device or '-'}",
                f"Precision efektif: {self.effective_precision or '-'}",
            ]
        )
        if self.tensor_test_ok is not None:
            state = "Berhasil" if self.tensor_test_ok else "Gagal"
            timing = "" if self.tensor_test_ms is None else f" ({self.tensor_test_ms:.1f} ms)"
            lines.append(f"Tes tensor: {state}{timing}")
        if self.error:
            lines.append(f"ERROR: {self.error}")
        lines.extend(f"Peringatan: {warning}" for warning in self.warnings)
        recommendation = self.recommendation
        lines.append(
            "Rekomendasi: "
            f"{recommendation.device} + {recommendation.precision} · "
            f"CPU offload {'aktif' if recommendation.cpu_offload else 'nonaktif'} · "
            recommendation.reason
        )
        return "\n".join(lines)


_GLOBAL_STORE = AIRuntimeSettingsStore()


def get_ai_runtime_store() -> AIRuntimeSettingsStore:
    return _GLOBAL_STORE


def load_ai_runtime_settings() -> AIRuntimeSettings:
    return _GLOBAL_STORE.load()


def save_ai_runtime_settings(settings: AIRuntimeSettings) -> Path:
    return _GLOBAL_STORE.save(settings)


def diagnose_ai_runtime(
    settings: AIRuntimeSettings,
    *,
    run_tensor_test: bool = True,
    torch_module: Any | None = None,
) -> AIRuntimeReport:
    """Inspect Torch/CUDA/MPS and optionally execute one tiny tensor operation."""

    try:
        torch = torch_module
        if torch is None:
            import torch as imported_torch

            torch = imported_torch
    except ImportError:
        recommendation = AIRuntimeRecommendation(
            device="cpu",
            precision="float32",
            cpu_offload=False,
            low_vram_mode=False,
            reason="Instal extra paket [ai] untuk menggunakan Stable Diffusion.",
        )
        return AIRuntimeReport(
            torch_available=False,
            torch_version=None,
            cuda_build=None,
            cuda_available=False,
            mps_available=False,
            gpu_name=None,
            gpu_vram_gb=None,
            requested_device=settings.device,
            effective_device=None,
            requested_precision=settings.precision,
            effective_precision=None,
            tensor_test_ok=None,
            tensor_test_ms=None,
            recommendation=recommendation,
            error='PyTorch belum terpasang. Jalankan: python -m pip install -e ".[ai]"',
        )

    cuda = getattr(torch, "cuda", None)
    cuda_available = bool(cuda is not None and cuda.is_available())
    backends = getattr(torch, "backends", None)
    mps_backend = getattr(backends, "mps", None)
    mps_available = bool(mps_backend is not None and mps_backend.is_available())
    gpu_name: str | None = None
    gpu_vram_gb: float | None = None
    if cuda_available:
        try:
            gpu_name = str(cuda.get_device_name(0))
            properties = cuda.get_device_properties(0)
            gpu_vram_gb = float(properties.total_memory) / (1024**3)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            gpu_name = "NVIDIA CUDA GPU"

    warnings: list[str] = []
    error: str | None = None
    effective_device = _effective_device(settings.device, cuda_available, mps_available)
    if effective_device is None:
        error = (
            "CUDA dipilih tetapi GPU/PyTorch CUDA tidak tersedia."
            if settings.device == "cuda"
            else "MPS dipilih tetapi backend Apple MPS tidak tersedia."
        )
    effective_precision = (
        None
        if effective_device is None
        else _effective_precision(settings.precision, effective_device, warnings)
    )
    recommendation = _recommendation(cuda_available, mps_available, gpu_vram_gb)

    tensor_ok: bool | None = None
    tensor_ms: float | None = None
    if run_tensor_test and error is None and effective_device and effective_precision:
        started = time.perf_counter()
        try:
            dtype = getattr(torch, effective_precision)
            left = torch.ones((128, 128), device=effective_device, dtype=dtype)
            result = left @ left
            _ = result[0, 0].item()
            if effective_device == "cuda" and cuda is not None:
                cuda.synchronize()
            tensor_ok = True
        except Exception as exc:  # noqa: BLE001 - diagnosis must report arbitrary backend errors
            tensor_ok = False
            error = f"Tes tensor pada {effective_device} gagal: {exc}"
        tensor_ms = (time.perf_counter() - started) * 1_000

    version = getattr(torch, "__version__", None)
    version_info = getattr(torch, "version", None)
    cuda_build = getattr(version_info, "cuda", None)
    return AIRuntimeReport(
        torch_available=True,
        torch_version=None if version is None else str(version),
        cuda_build=None if cuda_build is None else str(cuda_build),
        cuda_available=cuda_available,
        mps_available=mps_available,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        requested_device=settings.device,
        effective_device=effective_device,
        requested_precision=settings.precision,
        effective_precision=effective_precision,
        tensor_test_ok=tensor_ok,
        tensor_test_ms=tensor_ms,
        recommendation=recommendation,
        warnings=tuple(warnings),
        error=error,
    )


def _effective_device(requested: str, cuda_available: bool, mps_available: bool) -> str | None:
    if requested == "cuda":
        return "cuda" if cuda_available else None
    if requested == "mps":
        return "mps" if mps_available else None
    if requested == "cpu":
        return "cpu"
    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    return "cpu"


def _effective_precision(requested: str, device: str, warnings: list[str]) -> str:
    if requested == "auto":
        return "float16" if device in {"cuda", "mps"} else "float32"
    if device == "cpu" and requested in {"float16", "bfloat16"}:
        warnings.append(f"{requested} tidak aman pada CPU; float32 akan digunakan.")
        return "float32"
    if device == "mps" and requested == "bfloat16":
        warnings.append("bfloat16 pada MPS diganti menjadi float16.")
        return "float16"
    return requested


def _recommendation(
    cuda_available: bool,
    mps_available: bool,
    gpu_vram_gb: float | None,
) -> AIRuntimeRecommendation:
    if cuda_available:
        limited = gpu_vram_gb is not None and gpu_vram_gb < 7.0
        return AIRuntimeRecommendation(
            device="cuda",
            precision="float16",
            cpu_offload=limited,
            low_vram_mode=limited,
            reason=(
                "VRAM terbatas; gunakan resolusi 512–640."
                if limited
                else "GPU CUDA terdeteksi; jalankan model langsung di VRAM."
            ),
        )
    if mps_available:
        return AIRuntimeRecommendation(
            device="mps",
            precision="float16",
            cpu_offload=False,
            low_vram_mode=False,
            reason="Apple MPS terdeteksi.",
        )
    return AIRuntimeRecommendation(
        device="cpu",
        precision="float32",
        cpu_offload=False,
        low_vram_mode=False,
        reason="Tidak ada akselerator; gunakan resolusi 512 dan steps rendah.",
    )


__all__ = [
    "AI_SETTINGS_SCHEMA_VERSION",
    "DEFAULT_MODEL_ID",
    "AIRuntimeRecommendation",
    "AIRuntimeReport",
    "AIRuntimeSettings",
    "AIRuntimeSettingsStore",
    "default_ai_cache_dir",
    "default_ai_settings_path",
    "diagnose_ai_runtime",
    "get_ai_runtime_store",
    "load_ai_runtime_settings",
    "save_ai_runtime_settings",
]
