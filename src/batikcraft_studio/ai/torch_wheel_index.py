"""Pemilihan wheel PyTorch: CUDA bila ada GPU NVIDIA, selain itu CPU.

Wheel ``torch`` default di PyPI untuk Windows adalah build CPU-only. Tanpa
index khusus, pengguna dengan GPU NVIDIA tetap menjalankan SDXL di CPU —
lambat dan boros RAM sampai proses dimatikan Windows (force close).
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_LOGGER = logging.getLogger(__name__)

# Index resmi PyTorch. cu121 kompatibel dengan driver NVIDIA modern (>=527).
CUDA_WHEEL_INDEX = "https://download.pytorch.org/whl/cu121"


def nvidia_gpu_present() -> bool:
    """True bila ``nvidia-smi`` melaporkan minimal satu GPU."""

    executable = shutil.which("nvidia-smi")
    if executable is None:
        return False
    try:
        completed = subprocess.run(  # noqa: S603 - biner sistem tepercaya
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    return bool(completed.stdout.strip())


def torch_index_arguments(force_cuda: bool | None = None) -> list[str]:
    """Argumen pip tambahan agar torch terpasang sesuai perangkat keras."""

    use_cuda = nvidia_gpu_present() if force_cuda is None else bool(force_cuda)
    if not use_cuda:
        return []
    _LOGGER.info("GPU NVIDIA terdeteksi; memakai wheel PyTorch CUDA (cu121).")
    return ["--extra-index-url", CUDA_WHEEL_INDEX]


__all__ = ["CUDA_WHEEL_INDEX", "nvidia_gpu_present", "torch_index_arguments"]
