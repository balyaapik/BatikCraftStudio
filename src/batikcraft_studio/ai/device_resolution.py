"""Resolusi perangkat komputasi yang bekerja untuk semua tipe GPU.

Satu aturan untuk seluruh pipeline AI: pakai perangkat yang DIMINTA bila
tersedia; bila tidak, JANGAN gagal — jatuh secara anggun ke perangkat terbaik
yang benar-benar ada (CUDA → XPU Intel → MPS Apple → CPU). Pengguna dengan GPU
non-NVIDIA atau wheel torch CPU tetap bisa generate (lebih lambat), bukan
disambut error "CUDA dipilih tetapi GPU CUDA tidak tersedia".
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

_DEVICE_LABELS = {
    "cuda": "GPU NVIDIA (CUDA)",
    "xpu": "GPU Intel (XPU)",
    "mps": "GPU Apple (MPS)",
    "cpu": "CPU",
}


def available_torch_devices(torch: Any) -> tuple[str, ...]:
    """Deteksi perangkat yang benar-benar dapat dipakai, urut dari terbaik."""

    devices: list[str] = []
    try:
        if torch.cuda.is_available():
            devices.append("cuda")
    except Exception:  # noqa: BLE001 - build torch tanpa CUDA
        pass
    try:
        xpu = getattr(torch, "xpu", None)
        if xpu is not None and xpu.is_available():
            devices.append("xpu")
    except Exception:  # noqa: BLE001
        pass
    try:
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            devices.append("mps")
    except Exception:  # noqa: BLE001
        pass
    devices.append("cpu")
    return tuple(devices)


def resolve_torch_device(torch: Any, requested: str | None) -> str:
    """Kembalikan perangkat efektif; tidak pernah melempar error."""

    available = available_torch_devices(torch)
    wanted = (requested or "auto").strip().casefold()
    if wanted in available:
        return wanted
    best = available[0]
    if wanted not in ("", "auto"):
        _LOGGER.warning(
            "Perangkat %s diminta tetapi tidak tersedia; memakai %s.",
            wanted,
            _DEVICE_LABELS.get(best, best),
        )
    return best


def describe_device_fallback(requested: str | None, effective: str) -> str | None:
    """Kalimat status singkat bila terjadi fallback perangkat, else None."""

    wanted = (requested or "auto").strip().casefold()
    if wanted in ("", "auto") or wanted == effective:
        return None
    return (
        f"Perangkat {wanted.upper()} tidak tersedia; generasi memakai "
        f"{_DEVICE_LABELS.get(effective, effective)}."
    )


__all__ = [
    "available_torch_devices",
    "describe_device_fallback",
    "resolve_torch_device",
]
