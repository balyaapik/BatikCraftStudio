"""Pengaman memori generasi AI: cegah proses dimatikan sistem (force close).

SDXL di CPU memuat bobot fp32 dan tensor aktivasi besar. Bila RAM bebas tidak
mencukupi, Windows/Linux membunuh proses tanpa dialog — pengguna melihatnya
sebagai aplikasi "tiba-tiba tertutup". Modul ini memberi peringatan dini dan
menurunkan beban secara otomatis, bukan membiarkan proses mati.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Perkiraan konservatif kebutuhan RAM puncak generasi SDXL di CPU (fp32 +
# aktivasi + VAE decode), dengan slicing aktif.
_CPU_MINIMUM_FREE_GB = 9.0
_CPU_COMFORTABLE_FREE_GB = 14.0
_CPU_SAFE_RESOLUTION = 768


def available_memory_gb() -> float | None:
    """RAM bebas dalam GB; None bila tidak dapat dideteksi."""

    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:  # noqa: BLE001 - psutil opsional
        pass
    try:  # fallback Linux tanpa psutil
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / (1024**2)
    except OSError:
        pass
    return None


def guard_cpu_generation(resolution: int) -> tuple[int, str | None]:
    """Kembalikan (resolusi_aman, catatan) untuk generasi di CPU.

    Menaikkan peluang berhasil dengan menurunkan resolusi bila RAM menipis,
    dan menolak dengan pesan jelas bila jelas-jelas tidak cukup — jauh lebih
    baik daripada aplikasi mati mendadak di tengah proses.
    """

    free_gb = available_memory_gb()
    if free_gb is None:
        return resolution, None

    _LOGGER.info("RAM bebas sebelum generasi CPU: %.1f GB", free_gb)
    if free_gb < _CPU_MINIMUM_FREE_GB:
        raise MemoryError(
            f"RAM bebas hanya {free_gb:.1f} GB, sedangkan generasi SDXL di CPU "
            f"membutuhkan sekitar {_CPU_MINIMUM_FREE_GB:.0f} GB. Tutup aplikasi "
            "lain lalu coba lagi, atau gunakan provider cloud (OpenAI/Gemini/"
            "watsonx) yang tidak memakai memori komputer."
        )
    if free_gb < _CPU_COMFORTABLE_FREE_GB and resolution > _CPU_SAFE_RESOLUTION:
        note = (
            f"RAM bebas {free_gb:.1f} GB; resolusi diturunkan {resolution}→"
            f"{_CPU_SAFE_RESOLUTION} px agar proses tidak dimatikan sistem."
        )
        _LOGGER.warning(note)
        return _CPU_SAFE_RESOLUTION, note
    return resolution, None


__all__ = ["available_memory_gb", "guard_cpu_generation"]
