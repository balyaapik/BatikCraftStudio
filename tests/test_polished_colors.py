from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.domain import CanvasSpec, LayerObject, ObjectKind
from batikcraft_studio.ui.icons import available_icons, render_icon
from batikcraft_studio.ui.object_colors import (
    declared_object_colors,
    dominant_raster_colors,
)


def _two_color_asset() -> bytes:
    image = Image.new("RGBA", (80, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 43, 43), fill=(255, 0, 0, 255))
    draw.rectangle((44, 4, 75, 43), fill=(0, 0, 255, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_canvas_defaults_to_white() -> None:
    assert CanvasSpec().background_color == "#FFFFFF"

    session = ProjectSession()
    project = session.new_project(title="Putih", creator="Perajin")

    assert project.canvas.background_color == "#FFFFFF"


def test_canvas_background_update_is_undoable() -> None:
    session = ProjectSession()
    session.new_project(title="Warna", creator="Perajin")

    assert session.set_canvas_background("#123456") == "#123456"
    assert session.require_project().canvas.background_color == "#123456"
    assert session.undo() is True
    assert session.require_project().canvas.background_color == "#FFFFFF"
    assert session.redo() is True
    assert session.require_project().canvas.background_color == "#123456"


def test_declared_object_colors_follow_batik_semantics() -> None:
    motif = LayerObject(
        name="Motif",
        kind=ObjectKind.MOTIF,
        properties={"warna_motif": "#4e2a1e", "warna_isen": "#d9a566"},
    )
    stroke = LayerObject(
        name="Canting",
        kind=ObjectKind.PAINT_STROKE,
        properties={"brush_color": "#112233"},
    )
    shape = LayerObject(
        name="Bidang",
        kind=ObjectKind.SHAPE,
        properties={"stroke_color": "#010203", "fill_color": "#AABBCC"},
    )

    assert declared_object_colors(motif) == ("#4E2A1E", "#D9A566")
    assert declared_object_colors(stroke) == ("#112233", None)
    assert declared_object_colors(shape) == ("#010203", "#AABBCC")


def test_raster_palette_ignores_transparency_and_returns_two_colors() -> None:
    primary, secondary = dominant_raster_colors(_two_color_asset())

    assert primary == "#F80808"
    assert secondary == "#0808F8"


def test_all_batik_tool_icons_are_offline_and_renderable() -> None:
    expected = {
        "canting_tool",
        "brush_tool",
        "pencil_tool",
        "eraser_tool",
        "motif_tool",
        "isen_tool",
    }

    assert expected.issubset(available_icons())
    for name in expected:
        image = render_icon(name, size=24)
        assert image.size == (24, 24)
        assert image.getchannel("A").getbbox() is not None
