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
# SDXL bfloat16 di CPU: ±7 GB bobot + aktivasi. Angka ini sudah memperhitungkan
# slicing/tiling yang selalu diaktifkan pada jalur CPU.
_CPU_MINIMUM_FREE_GB = 8.0
_CPU_COMFORTABLE_FREE_GB = 12.0
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


# Pemuatan SDXL memerlukan RAM sebesar model walau target akhirnya GPU:
# bobot dibaca ke RAM dulu sebelum dipindah ke VRAM.
_MODEL_LOAD_NEED_GB = {"float16": 7.5, "bfloat16": 7.5, "float32": 14.0}
_MODEL_LOAD_HEADROOM_GB = 1.5


def guard_model_load(
    *,
    device: str,
    dtype_name: str,
    torch_module: object | None = None,
) -> None:
    """Tolak pemuatan model bila RAM jelas tidak cukup.

    Tanpa pemeriksaan ini, OS membunuh proses saat bobot dibaca dan aplikasi
    tampak "tertutup sendiri" tanpa pesan apa pun.
    """

    free_gb = available_memory_gb()
    if free_gb is None:
        return
    key = "float32"
    for name in ("float16", "bfloat16"):
        if name in dtype_name:
            key = name
            break
    needed = _MODEL_LOAD_NEED_GB.get(key, 14.0) + _MODEL_LOAD_HEADROOM_GB
    _LOGGER.info(
        "Pemeriksaan RAM sebelum memuat model: bebas %.1f GB, dibutuhkan ±%.1f GB (%s, %s)",
        free_gb,
        needed,
        device,
        key,
    )
    if free_gb < needed:
        raise MemoryError(
            f"RAM bebas hanya {free_gb:.1f} GB, sedangkan memuat model "
            f"membutuhkan ±{needed:.1f} GB. Tutup aplikasi lain (browser biasanya "
            "paling boros), lalu coba lagi. Alternatif: pakai provider cloud "
            "(OpenAI/Gemini/watsonx) yang tidak memakai memori komputer."
        )


# Ambang mesin "sempit": RAM sistem kecil atau VRAM GPU kecil. Pada kondisi
# ini pipeline dipasang dalam profil paling hemat dan dilepas setelah dipakai.
_LOW_MEMORY_RAM_GB = 12.0
_LOW_MEMORY_VRAM_GB = 8.0


def total_memory_gb() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().total) / (1024**3)
    except Exception:  # noqa: BLE001
        return None


def vram_total_gb(torch_module: object | None) -> float | None:
    torch = torch_module
    if torch is None:
        return None
    try:
        properties = torch.cuda.get_device_properties(0)  # type: ignore[union-attr]
        return float(properties.total_memory) / (1024**3)
    except Exception:  # noqa: BLE001
        return None


def low_memory_profile(device: str, torch_module: object | None = None) -> bool:
    """True bila mesin perlu profil hemat memori agresif."""

    total_ram = total_memory_gb()
    if total_ram is not None and total_ram < _LOW_MEMORY_RAM_GB:
        return True
    free = available_memory_gb()
    if free is not None and free < _LOW_MEMORY_RAM_GB:
        return True
    if device == "cuda":
        vram = vram_total_gb(torch_module)
        if vram is not None and vram < _LOW_MEMORY_VRAM_GB:
            return True
    return False


def release_memory(torch_module: object | None = None) -> None:
    """Kembalikan memori sesegera mungkin setelah generasi selesai."""

    import gc

    gc.collect()
    torch = torch_module
    if torch is None:
        return
    for release in ("empty_cache", "ipc_collect"):
        try:
            getattr(torch.cuda, release)()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "available_memory_gb",
    "guard_cpu_generation",
    "guard_model_load",
    "low_memory_profile",
    "release_memory",
    "total_memory_gb",
    "vram_total_gb",
]
