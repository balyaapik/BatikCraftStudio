"""Bungkus karya apa pun menjadi paket .batikcraftnft bersegel sebelum diunggah.

BatikCraftWeb hanya menerima gambar NFT yang datang bersama paket bersegel dan
sidik jarinya cocok dengan ``preview.jpg`` di dalam paket. Studio punya tiga
jalur publish: dari proyek penuh, dari satu aset pustaka, dan dari dokumen
raster. Dua jalur terakhir semula mengirim gambar telanjang, sehingga akan
ditolak server. Modul ini membungkus keduanya memakai pengekspor paket yang sama
dengan jalur proyek, jadi aturan di server tetap seragam dan dapat diverifikasi.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from batikcraft_studio.domain import Project
from batikcraft_studio.domain.models import CanvasSpec, ProjectMetadata
from batikcraft_studio.persistence.nft_package import (
    NFTExportMetadata,
    export_batikcraft_nft,
)

__all__ = ["SealedArtwork", "SealingError", "seal_image_as_nft_package"]

# Preview di dalam paket wajib JPEG; ini kualitas yang dipakai jalur proyek.
_PREVIEW_QUALITY = 92
_MAX_PREVIEW_EDGE = 4096


class SealingError(RuntimeError):
    """Karya tidak dapat dibungkus menjadi paket bersegel."""


@dataclass(frozen=True)
class SealedArtwork:
    """Paket bersegel beserta preview yang harus diunggah sebagai gambar NFT."""

    package_bytes: bytes
    preview_jpeg: bytes
    package_filename: str


def _to_preview_jpeg(image_bytes: bytes) -> tuple[bytes, int, int]:
    """Ubah gambar apa pun menjadi JPEG RGB yang layak jadi preview paket."""
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            source.load()
            rgb = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise SealingError("Gambar karya tidak dapat dibaca.") from exc

    if max(rgb.size) > _MAX_PREVIEW_EDGE:
        rgb.thumbnail((_MAX_PREVIEW_EDGE, _MAX_PREVIEW_EDGE))

    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=_PREVIEW_QUALITY)
    return buffer.getvalue(), rgb.width, rgb.height


def seal_image_as_nft_package(
    image_bytes: bytes,
    *,
    title: str,
    creator_name: str,
    creator_user_id: str,
    description: str = "",
    license_name: str = "All rights reserved",
    project: Project | None = None,
    assets: dict[str, bytes] | None = None,
) -> SealedArtwork:
    """Bungkus satu gambar menjadi paket .batikcraftnft bersegel.

    Bila ``project`` diberikan, proyek itulah yang dikemas sehingga jejak asal
    karya tetap utuh. Bila tidak, dibuat proyek minimal seukuran gambar agar
    dokumen raster tetap dapat dijual tanpa kehilangan segel.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        raise SealingError("Judul karya tidak boleh kosong.")
    if not image_bytes:
        raise SealingError("Gambar karya kosong.")

    preview, width, height = _to_preview_jpeg(image_bytes)

    if project is None:
        try:
            project = Project(
                metadata=ProjectMetadata(
                    title=clean_title[:120],
                    creator=(creator_name or "BatikCraft Creator")[:120],
                    description=(description or "")[:2000],
                ),
                canvas=CanvasSpec(width=width, height=height),
            )
        except Exception as exc:  # noqa: BLE001 - dipetakan ke error domain modul ini
            raise SealingError(f"Proyek pembungkus tidak dapat dibuat: {exc}") from exc

    metadata = NFTExportMetadata(
        creator_user_id=str(creator_user_id),
        # Paket mewajibkan philosophy tidak kosong; deskripsi dipakai bila ada.
        philosophy=(description or "").strip() or clean_title,
        license_name=license_name,
    )

    try:
        with tempfile.TemporaryDirectory(prefix="batikcraft-seal-") as temp:
            target = Path(temp) / "karya.batikcraftnft"
            written = export_batikcraft_nft(
                target,
                project,
                assets or {},
                preview,
                metadata,
            )
            package_bytes = written.read_bytes()
    except Exception as exc:  # noqa: BLE001 - pengekspor melempar beberapa tipe
        raise SealingError(f"Paket tidak dapat dibuat: {exc}") from exc

    return SealedArtwork(
        package_bytes=package_bytes,
        preview_jpeg=preview,
        package_filename=f"{_slug(clean_title)}.batikcraftnft",
    )


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    return "-".join(part for part in cleaned.split("-") if part)[:60] or "karya"
