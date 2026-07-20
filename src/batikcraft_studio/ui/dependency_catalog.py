"""Katalog dependensi: metadata, kelayakan sistem, status pemasangan.

Dipakai Pusat Dependensi (tabel bercentang) untuk menampilkan nama, ukuran,
persentase terunduh, dan kelayakan tiap komponen tanpa menyentuh Tk.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    default_managed_ai_package_dir,
    default_managed_dependency_root,
)

KIND_PACKAGE = "package"
KIND_MODEL = "model"


@dataclass(frozen=True, slots=True)
class DependencyItem:
    """Satu baris pada tabel dependensi."""

    key: str
    name: str
    kind: str
    size_bytes: int
    requirement: str = ""
    module: str = ""
    folder: str = ""
    note: str = ""
    requires_nvidia: bool = False
    variant: str = ""
    extra_requirements: tuple[str, ...] = field(default_factory=tuple)

    @property
    def size_text(self) -> str:
        gigabytes = self.size_bytes / (1024**3)
        if gigabytes >= 1:
            return f"{gigabytes:.1f} GB"
        return f"{self.size_bytes / (1024**2):.0f} MB"


# Ukuran adalah perkiraan unduhan nyata (setelah deduplikasi bobot).
CATALOG: tuple[DependencyItem, ...] = (
    DependencyItem(
        key="torch_cuda",
        name="PyTorch GPU (CUDA) — untuk GPU NVIDIA",
        kind=KIND_PACKAGE,
        size_bytes=int(2.9 * 1024**3),
        requirement="torch>=2.4",
        module="torch",
        variant="cuda",
        requires_nvidia=True,
        note=(
            "Generasi berjalan di GPU: jauh lebih cepat dan hemat RAM. "
            "Pilih salah satu saja antara versi GPU atau CPU."
        ),
    ),
    DependencyItem(
        key="torch_cpu",
        name="PyTorch CPU — tanpa GPU NVIDIA",
        kind=KIND_PACKAGE,
        size_bytes=int(0.25 * 1024**3),
        requirement="torch>=2.4",
        module="torch",
        variant="cpu",
        note=(
            "Unduhan jauh lebih kecil, tetapi generasi lambat dan butuh RAM "
            "besar. Pilih ini bila komputer tidak punya GPU NVIDIA."
        ),
    ),
    DependencyItem(
        key="diffusers",
        name="Diffusers + Transformers (pipeline SDXL)",
        kind=KIND_PACKAGE,
        size_bytes=int(0.35 * 1024**3),
        requirement="diffusers>=0.39,<0.40",
        module="diffusers",
        extra_requirements=("transformers>=4.48,<5", "tokenizers>=0.20"),
    ),
    DependencyItem(
        key="accelerate",
        name="Accelerate + PEFT (LoRA & optimasi memori)",
        kind=KIND_PACKAGE,
        size_bytes=int(0.05 * 1024**3),
        requirement="accelerate>=1.2",
        module="accelerate",
        extra_requirements=("peft>=0.17", "safetensors>=0.4"),
    ),
    DependencyItem(
        key="huggingface_hub",
        name="Hugging Face Hub (pengunduh model)",
        kind=KIND_PACKAGE,
        size_bytes=int(0.02 * 1024**3),
        requirement="huggingface-hub>=0.27",
        module="huggingface_hub",
        extra_requirements=("numpy>=1.26,<3",),
    ),
    DependencyItem(
        key="cloud_providers",
        name="Provider Cloud (OpenAI, Gemini, keyring)",
        kind=KIND_PACKAGE,
        size_bytes=int(0.03 * 1024**3),
        requirement="openai>=1.0,<3",
        module="openai",
        extra_requirements=("google-genai>=1.0,<2", "keyring>=25,<27"),
        note="Opsional: hanya untuk generasi lewat API cloud.",
    ),
    DependencyItem(
        key="sdxl",
        name="Model BatikBrew SDXL (base model)",
        kind=KIND_MODEL,
        size_bytes=int(13 * 1024**3),
        folder="stable-diffusion-xl-base-1.0",
        note="Wajib untuk Generate Motif/Pola BatikBrew.",
    ),
    DependencyItem(
        key="sd15",
        name="Stable Diffusion 1.5 + ControlNet",
        kind=KIND_MODEL,
        size_bytes=int(6.6 * 1024**3),
        folder="stable-diffusion-v1-5",
        note="Untuk batifikasi objek gaya lama dan ControlNet.",
    ),
)


def managed_runtime_root() -> Path:
    return default_managed_dependency_root() / "models" / "runtime"


def installed_torch_variant() -> str | None:
    """'cuda' / 'cpu' / None — varian torch yang benar-benar terpasang.

    Sumber kebenaran utama adalah string versi (``2.5.1+cu121`` vs
    ``2.13.0+cpu``). Pemeriksaan lama memotong teks sehingga ``None`` terbaca
    ``No`` dan build CPU salah dilaporkan sebagai CUDA.
    """

    import re

    packages = default_managed_ai_package_dir()
    if not (packages / "torch").is_dir():
        return None

    version_text = ""
    version_file = packages / "torch" / "version.py"
    try:
        version_text = version_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        version_text = ""

    match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", version_text)
    if match:
        version = match.group(1).casefold()
        if "+cu" in version or "+rocm" in version:
            return "cuda"
        if "+cpu" in version:
            return "cpu"

    for info in packages.glob("torch-*.dist-info"):
        name = info.name.casefold()
        if "+cu" in name:
            return "cuda"
        if "+cpu" in name:
            return "cpu"

    # Fallback: baris "cuda: Optional[str] = '12.1'" vs "... = None".
    cuda_line = re.search(r"^cuda\s*[:=][^\n]*", version_text, re.MULTILINE)
    if cuda_line and "none" not in cuda_line.group(0).casefold():
        return "cuda"
    return "cpu"


def is_installed(item: DependencyItem) -> bool:
    """True bila komponen sudah tersedia di folder terkelola."""

    if item.kind == KIND_MODEL:
        folder = managed_runtime_root() / item.folder
        return folder.is_dir() and any(folder.iterdir())
    packages = default_managed_ai_package_dir()
    module_root = item.module.split(".")[0]
    if item.variant:
        # Baris CPU dan CUDA berbagi modul yang sama: hanya varian yang
        # benar-benar terpasang yang ditandai "Terpasang".
        return installed_torch_variant() == item.variant
    if (packages / module_root).is_dir():
        return True
    return any(packages.glob(f"{module_root}-*.dist-info")) if packages.is_dir() else False


def installed_fraction(item: DependencyItem) -> float:
    """Perkiraan bagian yang sudah terunduh (0..1)."""

    if item.kind == KIND_MODEL:
        folder = managed_runtime_root() / item.folder
        if not folder.is_dir():
            return 0.0
        total = 0
        for path in folder.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return max(0.0, min(1.0, total / item.size_bytes)) if item.size_bytes else 0.0
    return 1.0 if is_installed(item) else 0.0


def integrity_status(item: DependencyItem) -> tuple[str, str]:
    """(status, detail) — mendeteksi model terpasang yang tidak lengkap/rusak.

    Model SDXL yang terunduh sebagian (mis. koneksi putus) sebelumnya tampak
    "Terpasang" padahal generasi gagal. Status PERLU REPARASI membuat kondisi
    itu terlihat langsung di tabel.
    """

    if not is_installed(item):
        return "Belum terpasang", ""
    if item.key != "sdxl":
        return "Terpasang", ""
    try:
        from batikcraft_studio.ai.runtime_model_installer import (
            batikbrew_runtime_model_paths,
        )
        from batikcraft_studio.ai.sdxl_runtime_integrity import (
            inspect_batikbrew_runtime,
        )

        issues = inspect_batikbrew_runtime(batikbrew_runtime_model_paths().base_model)
    except Exception:  # noqa: BLE001 - jangan gagalkan tabel
        return "Terpasang", ""
    if issues:
        head = "; ".join(issues[:2])
        return "PERLU REPARASI", f"{len(issues)} masalah: {head}"
    return "Terpasang", ""


def free_disk_bytes() -> int:
    root = default_managed_dependency_root()
    probe = root if root.exists() else root.parent
    try:
        return int(shutil.disk_usage(probe).free)
    except OSError:
        return 0


def eligibility(item: DependencyItem) -> tuple[bool, str]:
    """(layak, alasan) — apakah komponen dapat dipasang di sistem ini."""

    free = free_disk_bytes()
    needed = int(item.size_bytes * 1.25)  # ruang kerja ekstraksi
    if free and free < needed:
        return False, (
            f"Ruang disk kurang: butuh ±{needed / 1024**3:.1f} GB, "
            f"tersedia {free / 1024**3:.1f} GB."
        )
    if item.requires_nvidia:
        from batikcraft_studio.ai.torch_wheel_index import nvidia_gpu_present

        if not nvidia_gpu_present():
            return False, "Memerlukan GPU NVIDIA."
    return True, "Kompatibel dengan sistem ini."


def requirements_for(item: DependencyItem) -> list[str]:
    values = [item.requirement, *item.extra_requirements]
    return [value for value in values if value]


def refresh_installed_state() -> None:
    """Pastikan paket terkelola terlihat sebelum memeriksa status."""

    try:
        activate_managed_ai_packages()
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "CATALOG",
    "DependencyItem",
    "KIND_MODEL",
    "KIND_PACKAGE",
    "eligibility",
    "free_disk_bytes",
    "integrity_status",
    "installed_fraction",
    "installed_torch_variant",
    "is_installed",
    "managed_runtime_root",
    "refresh_installed_state",
    "requirements_for",
]
