"""Cetak dan Cetak Sebagai."""

from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.domain import (
    Layer,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.printing import PrintError, render_for_print, save_print_file


def _session():
    session = ProjectSession()
    project = session.new_project(title="Cetak", creator="B", width=800, height=600)
    buffer = BytesIO()
    Image.new("RGBA", (120, 120), (120, 70, 40, 255)).save(buffer, format="PNG")
    session._assets["assets/o.png"] = buffer.getvalue()
    project.add_layer(
        Layer(
            name="L",
            objects=(
                LayerObject(
                    name="O",
                    kind=ObjectKind.RASTER,
                    asset_ref="assets/o.png",
                    transform=Transform(x=400, y=300),
                    bounds=ObjectBounds(120, 120),
                ),
            ),
        )
    )
    return session, project


def test_render_for_print_is_flattened_on_white() -> None:
    session, project = _session()

    image = render_for_print(project, session.assets)

    assert image.mode == "RGB"  # tanpa alpha agar tidak tercetak hitam
    assert image.size == (800, 600)
    assert image.getpixel((5, 5)) == (255, 255, 255)


def test_print_as_writes_pdf_and_images(tmp_path: Path) -> None:
    session, project = _session()

    pdf = save_print_file(project, session.assets, tmp_path / "hasil.pdf")
    png = save_print_file(project, session.assets, tmp_path / "hasil.png")

    assert pdf.suffix == ".pdf" and pdf.stat().st_size > 0
    assert png.suffix == ".png" and png.stat().st_size > 0
    with Image.open(png) as image:
        assert image.size == (800, 600)


def test_unknown_extension_falls_back_to_pdf(tmp_path: Path) -> None:
    session, project = _session()

    written = save_print_file(project, session.assets, tmp_path / "tanpa-ekstensi")

    assert written.suffix == ".pdf"
    assert written.is_file()


def test_menu_exposes_print_entries() -> None:
    from batikcraft_studio import app

    source = inspect.getsource(app)
    assert 'tr("file.print")' in source
    assert 'tr("file.print_as")' in source
    assert '("<Control-p>", self.print_project)' in source
    assert '("<Control-Shift-P>", self.print_project_as)' in source


def test_translations_exist() -> None:
    from batikcraft_studio.i18n import tr

    assert tr("file.print")
    assert tr("file.print_as")
    assert tr("status.print_saved", name="x")


def test_broken_project_reports_print_error(tmp_path: Path) -> None:
    session, project = _session()
    # Aset hilang -> render gagal dan harus menjadi PrintError yang jelas.
    session._assets.clear()
    with pytest.raises(PrintError):
        save_print_file(project, session.assets, tmp_path / "gagal.pdf")


def test_print_as_png_atomik_bisa_dibuka(tmp_path):
    """Regresi: Print As -> PNG dulu memakai save() langsung, berkas bisa rusak."""

    from PIL import Image

    from batikcraft_studio.persistence.raster_archive import write_image_atomic

    saved = write_image_atomic(tmp_path / "rererer.png", Image.new("RGB", (120, 90), (30, 60, 90)))

    assert saved.suffix == ".png"
    assert saved.stat().st_size > 0
    reopened = Image.open(saved)
    reopened.load()
    assert reopened.size == (120, 90)


def test_print_as_jpeg_dari_rgba(tmp_path):
    from PIL import Image

    from batikcraft_studio.persistence.raster_archive import write_image_atomic

    saved = write_image_atomic(tmp_path / "x.jpg", Image.new("RGBA", (50, 50), (200, 0, 0, 255)))

    reopened = Image.open(saved)
    reopened.load()
    assert reopened.mode == "RGB"
