from __future__ import annotations

import pytest

from batikcraft_studio.ui.icons import render_icon


@pytest.mark.parametrize(
    "name",
    (
        "new",
        "open",
        "save",
        "import",
        "undo",
        "redo",
        "duplicate",
        "delete",
        "dashboard",
        "editor",
        "batikification",
        "preview",
        "publish",
        "visibility",
        "lock",
        "up",
        "down",
        "apply",
        "select",
    ),
)
def test_render_icon_produces_transparent_rgba_image(name: str) -> None:
    image = render_icon(name, size=24)

    assert image.mode == "RGBA"
    assert image.size == (24, 24)
    assert image.getbbox() is not None


def test_render_icon_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown icon"):
        render_icon("missing")


def test_render_icon_rejects_too_small_size() -> None:
    with pytest.raises(ValueError, match="at least 12"):
        render_icon("save", size=8)
