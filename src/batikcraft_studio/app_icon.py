"""Application icon loading for BatikCraft Studio windows."""

from __future__ import annotations

import tkinter as tk
from importlib import resources
from pathlib import Path
from typing import Protocol

_ICON_PARTS = ("resources", "logo-app.ico")


class _IconWindow(Protocol):
    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> object: ...


def app_icon_resource() -> resources.abc.Traversable:
    """Return the packaged BatikCraft Studio ICO resource."""

    return resources.files("batikcraft_studio").joinpath(*_ICON_PARTS)


def apply_app_icon(window: _IconWindow) -> bool:
    """Apply the packaged icon to a Tk window and its future child windows.

    Tk on non-Windows platforms may not support ICO files. In that case the
    application continues without failing startup.
    """

    try:
        with resources.as_file(app_icon_resource()) as icon_path:
            window.iconbitmap(default=str(Path(icon_path)))
    except (FileNotFoundError, OSError, TypeError, tk.TclError):
        return False
    return True


__all__ = ["app_icon_resource", "apply_app_icon"]
