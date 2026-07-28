"""Garis digambar sebagai raster dan harus bisa dihapus."""

from __future__ import annotations

import pytest

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.application.shape_session import ShapeLayerError
from batikcraft_studio.domain import ObjectKind


def _session():
    session = ProjectSession()
    session.new_project(title="Uji Garis", creator="Penguji", width=400, height=300)
    return session


def _active_layer_id(session):
    project = session.require_project()
    for layer in project.layers:
        if layer.asset_ref is None:
            return layer.layer_id
    return None


def _all_objects(session):
    return [item for layer in session.require_project().layers for item in layer.objects]


def test_line_becomes_a_raster_stroke_not_a_vector_shape():
    session = _session()

    session.create_shape_layer("line", (10.0, 10.0), (200.0, 160.0))

    objects = _all_objects(session)
    assert len(objects) == 1
    line = objects[0]
    assert line.kind is ObjectKind.PAINT_STROKE
    assert line.kind is not ObjectKind.SHAPE
    assert line.asset_ref is not None
    assert line.properties["source_format"] == "RASTER_LINE"
    assert line.properties["shape_type"] == "line"


def test_other_shapes_stay_vector():
    """Kotak, elips, dan poligon sengaja tidak diraster."""
    session = _session()

    session.create_shape_layer("rectangle", (10.0, 10.0), (200.0, 160.0))

    shapes = [i for i in _all_objects(session) if i.kind is ObjectKind.SHAPE]
    assert len(shapes) == 1
    assert shapes[0].properties["shape_type"] == "rectangle"


def test_line_can_be_erased_like_a_brush_stroke():
    """Inilah inti permintaannya: penghapus harus mengenai garis."""
    session = _session()
    session.create_shape_layer("line", (20.0, 20.0), (220.0, 180.0))
    layer_id = _active_layer_id(session)

    session.apply_paint_stroke(
        layer_id,
        points=[(100.0, 90.0), (140.0, 120.0)],
        brush_size=30.0,
        color="#000000",
        erase=True,
    )

    kinds = [i.kind for i in _all_objects(session)]
    assert ObjectKind.ERASER_STROKE in kinds
    assert ObjectKind.PAINT_STROKE in kinds


def test_line_has_pixels_and_a_bounding_box():
    session = _session()

    session.create_shape_layer("line", (10.0, 10.0), (200.0, 160.0))

    line = _all_objects(session)[0]
    assert line.bounds.width > 0
    assert line.bounds.height > 0
    content = session.assets[line.asset_ref]
    assert content[:8] == b"\x89PNG\r\n\x1a\n"


def test_line_width_is_honoured():
    """Garis tebal menghasilkan kotak pembatas yang lebih besar."""
    tipis = _session()
    tipis.create_shape_layer("line", (50.0, 50.0), (250.0, 50.0), stroke_width=2.0)
    tebal = _session()
    tebal.create_shape_layer("line", (50.0, 50.0), (250.0, 50.0), stroke_width=40.0)

    assert _all_objects(tebal)[0].bounds.height > _all_objects(tipis)[0].bounds.height


def test_shift_constrains_the_line():
    session = _session()

    session.create_shape_layer(
        "line", (50.0, 50.0), (250.0, 70.0), constrain=True
    )

    line = _all_objects(session)[0]
    # Dengan Shift, garis dipaksa lurus sehingga tingginya hanya setebal goresan.
    assert line.bounds.height < 20.0


def test_line_without_stroke_is_rejected():
    session = _session()

    with pytest.raises(ShapeLayerError):
        session.create_shape_layer(
            "line", (10.0, 10.0), (200.0, 160.0), stroke_enabled=False
        )


def test_degenerate_line_is_rejected():
    session = _session()

    with pytest.raises(ShapeLayerError):
        session.create_shape_layer("line", (10.0, 10.0), (10.0, 10.0))


def test_lines_are_numbered_sequentially():
    session = _session()

    session.create_shape_layer("line", (10.0, 10.0), (100.0, 100.0))
    session.create_shape_layer("line", (20.0, 20.0), (120.0, 120.0))

    names = [i.name for i in _all_objects(session)]
    assert "Garis 1" in names
    assert "Garis 2" in names


def test_line_survives_undo_and_redo():
    session = _session()
    session.create_shape_layer("line", (10.0, 10.0), (200.0, 160.0))
    assert len(_all_objects(session)) == 1

    session.undo()
    after_undo = len(_all_objects(session))
    session.redo()

    assert after_undo == 0
    assert len(_all_objects(session)) == 1


# ---------------------------------------------------------------------------
# Kanvas raster utama: garis harus melebur ke bitmap, bukan mengambang di atasnya
# ---------------------------------------------------------------------------


def _raster_session():
    session = ProjectSession()
    session.new_project(title="Kanvas", creator="Penguji", width=400, height=300)
    session.ensure_active_raster_paint_layer()
    return session


def _raster_layer(session):
    for layer in session.require_project().layers:
        if session._is_raster_paint_layer(layer):
            return layer
    return None


def test_line_on_raster_canvas_melts_into_the_bitmap():
    """Di kanvas utama garis tidak boleh menjadi objek terpisah."""
    session = _raster_session()

    session.create_shape_layer("line", (40.0, 40.0), (300.0, 220.0))

    # Tidak ada objek goresan baru yang mengambang di atas kanvas.
    assert _all_objects(session) == []
    assert _raster_layer(session) is not None


def test_eraser_on_raster_canvas_actually_removes_the_line():
    """Inti laporan: penghapus di kanvas utama harus mengenai garis."""
    from io import BytesIO

    from PIL import Image

    session = _raster_session()
    layer = _raster_layer(session)
    session.create_shape_layer("line", (50.0, 150.0), (350.0, 150.0), stroke_width=20.0)

    def alpha_at(x, y):
        current = _raster_layer(session)
        with Image.open(BytesIO(session.assets[current.asset_ref])) as img:
            img.load()
            return img.convert("RGBA").getpixel((x, y))[3]

    assert alpha_at(200, 150) > 0, "garis harus tergambar dulu"

    session.apply_raster_paint_stroke(
        layer.layer_id,
        points=[(180.0, 150.0), (220.0, 150.0)],
        brush_size=60.0,
        color="#000000",
        erase=True,
    )

    assert alpha_at(200, 150) == 0, "penghapus harus benar-benar menghapus garis"


def test_line_on_raster_canvas_is_one_undo_step():
    session = _raster_session()
    before = len(session.require_project().layers)

    session.create_shape_layer("line", (40.0, 40.0), (300.0, 220.0))
    session.undo()

    assert len(session.require_project().layers) == before


def test_object_layers_still_get_object_lines():
    """Di luar kanvas raster, garis tetap menjadi objek goresan seperti 0.9.17."""
    session = ProjectSession()
    session.new_project(title="Objek", creator="Penguji", width=400, height=300)
    layer = session.create_object_layer("Motif")

    session.create_shape_layer(
        "line", (40.0, 40.0), (300.0, 220.0), target_layer_id=layer.layer_id
    )

    objects = _all_objects(session)
    assert len(objects) == 1
    assert objects[0].properties["source_format"] == "RASTER_LINE"
