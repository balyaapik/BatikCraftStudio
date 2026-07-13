"""Small monochrome icons rendered in code for native Tkinter toolbars."""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image, ImageDraw, ImageTk

IconDrawer = Callable[[ImageDraw.ImageDraw, int, str], None]


def render_icon(
    name: str,
    *,
    size: int = 20,
    color: str = "#2B2B2B",
) -> Image.Image:
    """Render one transparent RGBA icon without external asset files."""

    if size < 12:
        raise ValueError("Icon size must be at least 12 pixels.")
    try:
        drawer = _DRAWERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown icon: {name}") from exc

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    drawer(ImageDraw.Draw(image), size, color)
    return image


def create_icon(
    master: object,
    name: str,
    *,
    size: int = 20,
    color: str = "#2B2B2B",
) -> ImageTk.PhotoImage:
    """Create a Tk-compatible icon and bind it to ``master``."""

    rendered = render_icon(name, size=size, color=color)
    return ImageTk.PhotoImage(rendered, master=master)


def _line_width(size: int) -> int:
    return max(2, round(size / 10))


def _new(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.rectangle(
        (s * 0.22, s * 0.16, s * 0.72, s * 0.84),
        outline=c,
        width=w,
    )
    draw.line((s * 0.52, s * 0.38, s * 0.52, s * 0.68), fill=c, width=w)
    draw.line((s * 0.37, s * 0.53, s * 0.67, s * 0.53), fill=c, width=w)


def _open(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line(
        (
            s * 0.12,
            s * 0.34,
            s * 0.38,
            s * 0.34,
            s * 0.46,
            s * 0.22,
            s * 0.82,
            s * 0.22,
        ),
        fill=c,
        width=w,
    )
    draw.polygon(
        (
            (s * 0.14, s * 0.40),
            (s * 0.88, s * 0.40),
            (s * 0.72, s * 0.82),
            (s * 0.18, s * 0.82),
        ),
        outline=c,
    )
    draw.line(
        (
            s * 0.14,
            s * 0.40,
            s * 0.18,
            s * 0.82,
            s * 0.72,
            s * 0.82,
            s * 0.88,
            s * 0.40,
        ),
        fill=c,
        width=w,
    )


def _save(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.rectangle(
        (s * 0.18, s * 0.14, s * 0.82, s * 0.86),
        outline=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.30, s * 0.18, s * 0.68, s * 0.42),
        outline=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.30, s * 0.58, s * 0.70, s * 0.82),
        outline=c,
        width=w,
    )


def _import(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.rectangle(
        (s * 0.16, s * 0.20, s * 0.82, s * 0.78),
        outline=c,
        width=w,
    )
    draw.ellipse(
        (s * 0.28, s * 0.29, s * 0.40, s * 0.41),
        outline=c,
        width=w,
    )
    draw.line(
        (
            s * 0.22,
            s * 0.70,
            s * 0.42,
            s * 0.50,
            s * 0.54,
            s * 0.62,
            s * 0.70,
            s * 0.46,
            s * 0.82,
            s * 0.58,
        ),
        fill=c,
        width=w,
    )
    draw.line((s * 0.68, s * 0.10, s * 0.68, s * 0.38), fill=c, width=w)
    draw.line(
        (s * 0.56, s * 0.26, s * 0.68, s * 0.38, s * 0.80, s * 0.26),
        fill=c,
        width=w,
    )


def _undo(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.arc(
        (s * 0.18, s * 0.22, s * 0.86, s * 0.84),
        start=190,
        end=355,
        fill=c,
        width=w,
    )
    draw.polygon(
        (
            (s * 0.15, s * 0.48),
            (s * 0.38, s * 0.25),
            (s * 0.38, s * 0.56),
        ),
        fill=c,
    )


def _redo(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.arc(
        (s * 0.14, s * 0.22, s * 0.82, s * 0.84),
        start=185,
        end=350,
        fill=c,
        width=w,
    )
    draw.polygon(
        (
            (s * 0.85, s * 0.48),
            (s * 0.62, s * 0.25),
            (s * 0.62, s * 0.56),
        ),
        fill=c,
    )


def _duplicate(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.rectangle(
        (s * 0.18, s * 0.18, s * 0.66, s * 0.66),
        outline=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.34, s * 0.34, s * 0.82, s * 0.82),
        outline=c,
        width=w,
    )


def _delete(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line((s * 0.24, s * 0.28, s * 0.76, s * 0.28), fill=c, width=w)
    draw.line((s * 0.36, s * 0.18, s * 0.64, s * 0.18), fill=c, width=w)
    draw.rectangle(
        (s * 0.30, s * 0.32, s * 0.70, s * 0.84),
        outline=c,
        width=w,
    )
    draw.line((s * 0.43, s * 0.40, s * 0.43, s * 0.74), fill=c, width=w)
    draw.line((s * 0.57, s * 0.40, s * 0.57, s * 0.74), fill=c, width=w)


def _home(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line(
        (s * 0.16, s * 0.48, s * 0.50, s * 0.18, s * 0.84, s * 0.48),
        fill=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.26, s * 0.46, s * 0.74, s * 0.82),
        outline=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.44, s * 0.60, s * 0.56, s * 0.82),
        outline=c,
        width=w,
    )


def _editor(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line(
        (s * 0.22, s * 0.78, s * 0.68, s * 0.32),
        fill=c,
        width=w + 1,
    )
    draw.polygon(
        (
            (s * 0.68, s * 0.32),
            (s * 0.80, s * 0.20),
            (s * 0.84, s * 0.36),
            (s * 0.76, s * 0.44),
        ),
        outline=c,
    )
    draw.line((s * 0.18, s * 0.82, s * 0.36, s * 0.76), fill=c, width=w)


def _spark(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line((s * 0.50, s * 0.12, s * 0.50, s * 0.88), fill=c, width=w)
    draw.line((s * 0.12, s * 0.50, s * 0.88, s * 0.50), fill=c, width=w)
    draw.line((s * 0.24, s * 0.24, s * 0.76, s * 0.76), fill=c, width=w)
    draw.line((s * 0.76, s * 0.24, s * 0.24, s * 0.76), fill=c, width=w)


def _grid(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    for x in (0.18, 0.52):
        for y in (0.18, 0.52):
            draw.rectangle(
                (s * x, s * y, s * (x + 0.28), s * (y + 0.28)),
                outline=c,
                width=w,
            )


def _publish(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.rectangle(
        (s * 0.20, s * 0.48, s * 0.80, s * 0.84),
        outline=c,
        width=w,
    )
    draw.line((s * 0.50, s * 0.12, s * 0.50, s * 0.64), fill=c, width=w)
    draw.line(
        (s * 0.34, s * 0.28, s * 0.50, s * 0.12, s * 0.66, s * 0.28),
        fill=c,
        width=w,
    )


def _eye(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.arc(
        (s * 0.12, s * 0.30, s * 0.88, s * 0.72),
        start=190,
        end=350,
        fill=c,
        width=w,
    )
    draw.arc(
        (s * 0.12, s * 0.28, s * 0.88, s * 0.70),
        start=10,
        end=170,
        fill=c,
        width=w,
    )
    draw.ellipse((s * 0.42, s * 0.40, s * 0.58, s * 0.56), fill=c)


def _lock(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.arc(
        (s * 0.30, s * 0.12, s * 0.70, s * 0.54),
        start=180,
        end=360,
        fill=c,
        width=w,
    )
    draw.rectangle(
        (s * 0.24, s * 0.42, s * 0.76, s * 0.84),
        outline=c,
        width=w,
    )


def _up(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line((s * 0.50, s * 0.18, s * 0.50, s * 0.82), fill=c, width=w)
    draw.line(
        (s * 0.30, s * 0.38, s * 0.50, s * 0.18, s * 0.70, s * 0.38),
        fill=c,
        width=w,
    )


def _down(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line((s * 0.50, s * 0.18, s * 0.50, s * 0.82), fill=c, width=w)
    draw.line(
        (s * 0.30, s * 0.62, s * 0.50, s * 0.82, s * 0.70, s * 0.62),
        fill=c,
        width=w,
    )


def _apply(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.line(
        (s * 0.18, s * 0.52, s * 0.40, s * 0.74, s * 0.82, s * 0.28),
        fill=c,
        width=w + 1,
    )


def _select(draw: ImageDraw.ImageDraw, s: int, c: str) -> None:
    w = _line_width(s)
    draw.polygon(
        (
            (s * 0.20, s * 0.14),
            (s * 0.76, s * 0.52),
            (s * 0.52, s * 0.58),
            (s * 0.66, s * 0.84),
            (s * 0.54, s * 0.90),
            (s * 0.40, s * 0.62),
            (s * 0.22, s * 0.80),
        ),
        outline=c,
    )
    draw.line(
        (s * 0.20, s * 0.14, s * 0.76, s * 0.52, s * 0.52, s * 0.58),
        fill=c,
        width=w,
    )
    draw.line(
        (s * 0.40, s * 0.62, s * 0.22, s * 0.80, s * 0.20, s * 0.14),
        fill=c,
        width=w,
    )


_DRAWERS: dict[str, IconDrawer] = {
    "new": _new,
    "open": _open,
    "save": _save,
    "import": _import,
    "undo": _undo,
    "redo": _redo,
    "duplicate": _duplicate,
    "delete": _delete,
    "dashboard": _home,
    "editor": _editor,
    "batikification": _spark,
    "preview": _grid,
    "publish": _publish,
    "visibility": _eye,
    "lock": _lock,
    "up": _up,
    "down": _down,
    "apply": _apply,
    "select": _select,
}
