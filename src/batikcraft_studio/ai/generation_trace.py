"""Pelaporan langkah generasi ke UI dan log aplikasi.

Worker AI memanggil ``trace(...)`` untuk setiap kejadian penting; UI cukup
memberikan satu callback yang menampilkannya di panel log dialog.
"""

from __future__ import annotations

import logging
from typing import Callable

_LOGGER = logging.getLogger("batikcraft_studio.generation")

TraceSink = Callable[[str], None]
_sink: TraceSink | None = None


def set_trace_sink(sink: TraceSink | None) -> None:
    """Pasang tujuan tampilan log (mis. panel dialog). None untuk melepas."""

    global _sink
    _sink = sink


def trace(message: str) -> None:
    """Catat satu baris ke log aplikasi dan panel UI bila tersedia."""

    _LOGGER.info("%s", message)
    sink = _sink
    if sink is None:
        return
    try:
        sink(message)
    except Exception:  # noqa: BLE001 - UI tidak boleh menggagalkan generasi
        pass


def describe_compute_environment(torch_module: object | None = None) -> list[str]:
    """Ringkasan perangkat komputasi untuk ditampilkan sebelum generasi."""

    torch = torch_module
    if torch is None:
        try:
            import torch as torch_import

            torch = torch_import
        except Exception:  # noqa: BLE001
            return ["PyTorch belum tersedia."]

    lines = [f"PyTorch {getattr(torch, '__version__', '?')}"]
    cuda_build = getattr(getattr(torch, "version", None), "cuda", None)
    lines.append(f"Build CUDA: {cuda_build or 'tidak ada (build CPU)'}")
    try:
        available = bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        available = False
    lines.append(f"CUDA tersedia: {'ya' if available else 'tidak'}")
    if available:
        try:
            name = torch.cuda.get_device_name(0)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            lines.append(f"GPU: {name} ({total:.1f} GB VRAM)")
        except Exception:  # noqa: BLE001
            lines.append("GPU: terdeteksi")
    elif cuda_build is None:
        # Kasus paling sering: pengguna punya GPU NVIDIA tetapi memasang
        # PyTorch build CPU, sehingga GPU tidak pernah dipakai.
        try:
            from batikcraft_studio.ai.torch_wheel_index import nvidia_gpu_present

            if nvidia_gpu_present():
                lines.append(
                    "PERINGATAN: GPU NVIDIA terdeteksi tetapi PyTorch yang "
                    "terpasang adalah build CPU. Buka Pusat Dependensi, "
                    "uninstall 'PyTorch CPU', lalu pasang 'PyTorch GPU (CUDA)'."
                )
        except Exception:  # noqa: BLE001
            pass
    return lines


__all__ = ["describe_compute_environment", "set_trace_sink", "trace"]
