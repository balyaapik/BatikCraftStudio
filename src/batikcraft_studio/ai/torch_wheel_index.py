"""Pemilihan wheel PyTorch: CUDA bila ada GPU NVIDIA, selain itu CPU.

Wheel ``torch`` default di PyPI untuk Windows adalah build CPU-only. Tanpa
index khusus, pengguna dengan GPU NVIDIA tetap menjalankan SDXL di CPU —
lambat dan boros RAM sampai proses dimatikan Windows (force close).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

_LOGGER = logging.getLogger(__name__)

# Index resmi PyTorch. cu121 kompatibel dengan driver NVIDIA modern (>=527).
CUDA_WHEEL_INDEX = "https://download.pytorch.org/whl/cu121"
# Build CPU resmi: unduhan jauh lebih kecil daripada wheel default PyPI.
CPU_WHEEL_INDEX = "https://download.pytorch.org/whl/cpu"


def nvidia_gpu_present() -> bool:
    """True bila driver CUDA NVIDIA tersedia di sistem.

    Pemeriksaan utama memuat pustaka driver (``nvcuda.dll`` / ``libcuda.so``)
    lewat ctypes: tanpa proses anak, tanpa jendela, dan tidak terpengaruh PATH
    aplikasi beku. Peluncuran ``nvidia-smi.exe`` sempat memunculkan dialog
    Windows "0xc0000142" karena inisialisasi DLL gagal di lingkungan beku.
    """

    import ctypes

    candidates = (
        ["nvcuda.dll"] if os.name == "nt" else ["libcuda.so.1", "libcuda.so"]
    )
    for library in candidates:
        try:
            handle = (
                ctypes.WinDLL(library)  # type: ignore[attr-defined]
                if os.name == "nt"
                else ctypes.CDLL(library)
            )
        except OSError:
            continue
        try:
            # cuInit(0) memastikan benar-benar ada perangkat yang dapat dipakai.
            if int(handle.cuInit(0)) == 0:
                count = ctypes.c_int(0)
                if int(handle.cuDeviceGetCount(ctypes.byref(count))) == 0:
                    return count.value > 0
        except (AttributeError, OSError):
            continue
    return _nvidia_smi_reports_gpu()


def _nvidia_smi_reports_gpu() -> bool:
    """Fallback: tanya nvidia-smi tanpa jendela dan tanpa dialog kesalahan."""

    executable = shutil.which("nvidia-smi")
    if executable is None:
        return False
    creation = 0
    if os.name == "nt":
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(  # noqa: S603 - biner sistem tepercaya
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=creation,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def torch_index_arguments(force_cuda: bool | None = None) -> list[str]:
    """Argumen pip tambahan agar torch terpasang sesuai perangkat keras."""

    use_cuda = nvidia_gpu_present() if force_cuda is None else bool(force_cuda)
    if not use_cuda:
        return []
    _LOGGER.info("GPU NVIDIA terdeteksi; memakai wheel PyTorch CUDA (cu121).")
    return ["--extra-index-url", CUDA_WHEEL_INDEX]


__all__ = [
    "CPU_WHEEL_INDEX",
    "CUDA_WHEEL_INDEX",
    "nvidia_gpu_present",
    "torch_index_arguments",
]
