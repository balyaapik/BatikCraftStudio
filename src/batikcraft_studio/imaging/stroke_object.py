"""Create tightly cropped editable brush and eraser stroke assets."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from batikcraft_studio.imaging.paint import (
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
)


@dataclass(frozen=True, slots=True)
class CroppedStroke:
    """PNG bytes and project-space bounds for one completed stroke."""

    content: bytes
    left: int
    top: int
    width: int
    height: int

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.width / 2, self.top + self.height / 2)


def render_cropped_stroke(
    *,
    canvas_width: int,
    canvas_height: int,
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
    brush_size: float,
    color: str,
    opacity: float,
    hardness: float,
    smoothing: float,
    eraser: bool = False,
) -> CroppedStroke:
    """Render one stroke and crop transparent padding around its actual marks."""

    transparent = create_transparent_canvas_png(canvas_width, canvas_height)
    # Erasers are stored as positive alpha masks. The layer renderer subtracts this
    # alpha from earlier paint objects, preserving non-destructive editability.
    rendered = apply_paint_stroke(
        transparent,
        width=canvas_width,
        height=canvas_height,
        points=points,
        brush_size=brush_size,
        color="#FFFFFF" if eraser else color,
        erase=False,
        opacity=opacity,
        hardness=hardness,
        smoothing=smoothing,
    )
    with Image.open(BytesIO(rendered)) as source:
        source.load()
        image = source.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise PaintStrokeError("Stroke does not intersect the project canvas.")
    left, top, right, bottom = bbox
    cropped = image.crop(bbox)
    output = BytesIO()
    cropped.save(output, format="PNG", optimize=True)
    return CroppedStroke(
        content=output.getvalue(),
        left=left,
        top=top,
        width=right - left,
        height=bottom - top,
    )


__all__ = ["CroppedStroke", "render_cropped_stroke"]
