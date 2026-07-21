"""Pengaman terhadap crash tingkat driver CUDA (mis. ``0xC0000409`` di
``nvcuda64.dll``).

Crash semacam ini terjadi *di dalam driver NVIDIA*, bukan di Python. Proses
langsung dimatikan Windows tanpa exception, tanpa traceback, dan tanpa
kesempatan menyimpan apa pun -- dari sisi pengguna aplikasi "menutup sendiri".
Karena tidak bisa ditangkap, satu-satunya cara bertahan adalah *mendeteksi
setelahnya*:

1. Sebelum generasi GPU dimulai, tulis penanda (sentinel) berisi konteks.
2. Setelah generasi selesai (sukses maupun error Python biasa), hapus penanda.
3. Kalau penanda masih ada saat generasi berikutnya dimulai, berarti proses
   sebelumnya mati di tengah pekerjaan GPU. Setelah beberapa kali, perangkat
   diturunkan otomatis ke CPU supaya aplikasi tetap bisa dipakai.

Selain itu modul ini mematikan jalur autotune/JIT yang paling sering memicu
fast-fail driver pada build frozen (cuDNN benchmark, TF32 reduksi).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Jumlah crash GPU beruntun sebelum perangkat diturunkan paksa ke CPU.
MAX_GPU_CRASHES = 2

_SENTINEL_NAME = "gpu-generation.active"
_CRASH_NAME = "gpu-generation.crash.json"

_CPU_FALLBACK_MESSAGE = (
    "Generasi GPU sebelumnya membuat aplikasi tertutup paksa (crash driver "
    "NVIDIA). Untuk kali ini generasi dijalankan di CPU supaya aman. Perbarui "
    "driver NVIDIA lalu pilih GPU kembali di pengaturan runtime AI."
)


@dataclass(frozen=True)
class GpuCrashRecord:
    """Catatan crash GPU yang terdeteksi dari sesi sebelumnya."""

    count: int
    device: str
    model: str
    started_at: float

    @property
    def should_force_cpu(self) -> bool:
        return self.count >= MAX_GPU_CRASHES


def _state_dir() -> Path:
    from batikcraft_studio.logging_setup import default_log_dir

    directory = default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sentinel_path() -> Path:
    return _state_dir() / _SENTINEL_NAME


def crash_record_path() -> Path:
    return _state_dir() / _CRASH_NAME


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:  # pragma: no cover - disk penuh / read-only
        logger.debug("Gagal menulis %s", path, exc_info=True)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def detect_previous_gpu_crash() -> GpuCrashRecord | None:
    """Periksa sentinel yang tertinggal; kalau ada, catat sebagai crash.

    Dipanggil sekali sebelum generasi. Sentinel yang tersisa berarti proses
    sebelumnya tidak pernah sampai ke ``end_gpu_attempt``.
    """

    sentinel = sentinel_path()
    if not sentinel.exists():
        stored = _read_json(crash_record_path())
        if not stored:
            return None
        return GpuCrashRecord(
            count=int(stored.get("count", 0)),
            device=str(stored.get("device", "cuda")),
            model=str(stored.get("model", "")),
            started_at=float(stored.get("started_at", 0.0)),
        )

    context = _read_json(sentinel)
    _unlink(sentinel)
    previous = _read_json(crash_record_path())
    count = int(previous.get("count", 0)) + 1
    record = GpuCrashRecord(
        count=count,
        device=str(context.get("device", "cuda")),
        model=str(context.get("model", "")),
        started_at=float(context.get("started_at", 0.0)),
    )
    _write_json(
        crash_record_path(),
        {
            "count": record.count,
            "device": record.device,
            "model": record.model,
            "started_at": record.started_at,
            "detected_at": time.time(),
        },
    )
    logger.warning(
        "Terdeteksi crash generasi GPU sebelumnya (ke-%d) pada perangkat %s.",
        record.count,
        record.device,
    )
    return record


def clear_gpu_crash_history() -> None:
    """Reset riwayat setelah generasi GPU berhasil."""

    _unlink(crash_record_path())


def begin_gpu_attempt(device: str, model: str = "") -> None:
    if device != "cuda":
        return
    _write_json(
        sentinel_path(),
        {"device": device, "model": model, "started_at": time.time()},
    )


def end_gpu_attempt(device: str, *, succeeded: bool) -> None:
    if device != "cuda":
        return
    _unlink(sentinel_path())
    if succeeded:
        clear_gpu_crash_history()


def guard_device(device: str) -> tuple[str, str | None]:
    """Turunkan ``cuda`` ke ``cpu`` bila GPU sudah berulang kali crash.

    Mengembalikan ``(perangkat_efektif, peringatan_atau_None)``.
    """

    if device != "cuda":
        return device, None
    record = detect_previous_gpu_crash()
    if record is None or not record.should_force_cpu:
        return device, None
    return "cpu", _CPU_FALLBACK_MESSAGE


def apply_cuda_safety(torch: Any) -> tuple[str, ...]:
    """Matikan jalur autotune/JIT yang rawan memicu fast-fail driver."""

    applied: list[str] = []
    backends = getattr(torch, "backends", None)
    cudnn = getattr(backends, "cudnn", None) if backends is not None else None
    if cudnn is not None:
        try:
            # Autotune cuDNN menjalankan banyak kernel eksperimental saat
            # panggilan pertama -- sumber crash driver paling umum.
            cudnn.benchmark = False
            cudnn.allow_tf32 = False
            applied.append("cudnn.benchmark=False")
        except Exception:  # noqa: BLE001
            pass
    cuda_backend = getattr(backends, "cuda", None) if backends is not None else None
    matmul = getattr(cuda_backend, "matmul", None) if cuda_backend is not None else None
    if matmul is not None:
        try:
            matmul.allow_tf32 = False
            applied.append("matmul.allow_tf32=False")
        except Exception:  # noqa: BLE001
            pass
    # Alokator dengan segmen yang bisa dimekarkan mempercepat fragmentasi tapi
    # menekan driver lebih keras; matikan bila belum diatur pengguna.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:False")
    applied.append("PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False")
    return tuple(applied)


__all__ = [
    "GpuCrashRecord",
    "MAX_GPU_CRASHES",
    "apply_cuda_safety",
    "begin_gpu_attempt",
    "clear_gpu_crash_history",
    "crash_record_path",
    "detect_previous_gpu_crash",
    "end_gpu_attempt",
    "guard_device",
    "sentinel_path",
]
