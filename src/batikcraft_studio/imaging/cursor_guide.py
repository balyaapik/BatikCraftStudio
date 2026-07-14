"""Shared cursor-guide geometry for brush, canting, pencil, and eraser tools.

A single calculation path converts the tool size (project coordinates) to
viewport-space preview diameter.  The same path is used for:

* the circular guide drawn on the Tk canvas while hovering/dragging;
* the actual stamp radius used by the raster renderer.

This ensures ``preview_diameter == tool_size × zoom_scale`` with no
duplicate formulas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CursorGuide:
    """Viewport-space geometry for one cursor-size overlay circle.

    All values are expressed in *viewport pixels* (i.e. already multiplied
    by the zoom scale and the display DPI factor).

    Attributes
    ----------
    center_x, center_y
        Center of the guide in viewport pixels, relative to the Tk canvas
        widget origin.  These are derived from the raw pointer event
        coordinates with *no* additional scroll offset applied — the guide
        is drawn at the pointer position, not the project position.
    radius
        Preview radius in viewport pixels.  Equal to
        ``(tool_size × zoom_scale × dpi_scale) / 2``.
    project_radius
        Radius in project pixels (unscaled).  Used to drive the raster
        stamp so that preview and actual stroke share the same formula.
    """

    center_x: float
    center_y: float
    radius: float
    project_radius: float

    # Bounding-box helpers (left, top, right, bottom) for ``canvas.create_oval``
    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            self.center_x - self.radius,
            self.center_y - self.radius,
            self.center_x + self.radius,
            self.center_y + self.radius,
        )


def compute_cursor_guide(
    *,
    pointer_x: float,
    pointer_y: float,
    tool_size: float,
    zoom_scale: float,
    dpi_scale: float = 1.0,
) -> CursorGuide:
    """Return the viewport-space guide geometry for a brush/eraser cursor.

    Parameters
    ----------
    pointer_x, pointer_y
        Raw pointer position in the Tk canvas widget (event.x, event.y).
        These are already in viewport pixels — do **not** divide by zoom or
        scroll before passing them here.
    tool_size
        Brush or eraser diameter in *project* pixels (e.g. the value stored
        in ``brush_size_value``).
    zoom_scale
        Current canvas zoom factor (ratio of viewport pixels to project
        pixels).  Typically produced by the viewport manager.
    dpi_scale
        System DPI scaling factor (physical pixels per logical pixel on the
        display).  Pass ``winfo_fpixels('1i') / 96`` or the equivalent.
        Defaults to 1.0 for environments where Tkinter already performs DPI
        scaling internally (e.g. ``tk.call('tk', 'scaling')`` normalized).

    Returns
    -------
    CursorGuide
        Ready-to-use geometry.  The *radius* field drives ``create_oval``;
        the *project_radius* field drives the paint raster engine.
    """
    if not math.isfinite(tool_size) or tool_size <= 0:
        raise ValueError("tool_size must be a positive finite number.")
    if not math.isfinite(zoom_scale) or zoom_scale <= 0:
        raise ValueError("zoom_scale must be a positive finite number.")
    if not math.isfinite(dpi_scale) or dpi_scale <= 0:
        raise ValueError("dpi_scale must be a positive finite number.")

    project_radius = tool_size / 2.0
    # Convert project radius → viewport radius in one step.
    viewport_radius = project_radius * zoom_scale * dpi_scale

    return CursorGuide(
        center_x=pointer_x,
        center_y=pointer_y,
        radius=max(1.0, viewport_radius),
        project_radius=project_radius,
    )


def viewport_to_project(
    viewport_x: float,
    viewport_y: float,
    *,
    zoom_scale: float,
    scroll_x: float = 0.0,
    scroll_y: float = 0.0,
) -> tuple[float, float]:
    """Convert a viewport-space point to project-space coordinates.

    Parameters
    ----------
    viewport_x, viewport_y
        Point in Tk canvas widget pixels.
    zoom_scale
        Viewport-to-project zoom factor.
    scroll_x, scroll_y
        Canvas scroll offset in viewport pixels (positive = canvas scrolled
        right/down).  Typically ``canvas.canvasx(0)`` and
        ``canvas.canvasy(0)``.
    """
    return (
        (viewport_x + scroll_x) / zoom_scale,
        (viewport_y + scroll_y) / zoom_scale,
    )


def project_to_viewport(
    project_x: float,
    project_y: float,
    *,
    zoom_scale: float,
    scroll_x: float = 0.0,
    scroll_y: float = 0.0,
) -> tuple[float, float]:
    """Convert a project-space point to viewport-space coordinates."""
    return (
        project_x * zoom_scale - scroll_x,
        project_y * zoom_scale - scroll_y,
    )


__all__ = [
    "CursorGuide",
    "compute_cursor_guide",
    "project_to_viewport",
    "viewport_to_project",
]
