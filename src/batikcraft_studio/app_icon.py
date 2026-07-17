"""Application identity and icon loading for BatikCraft Studio windows."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from importlib import resources
from pathlib import Path
from typing import Protocol

APP_USER_MODEL_ID = "BatikCraft.Studio.Desktop"
_ICON_PARTS = ("resources", "logo-app.ico")

# Windows constants used to set both title-bar and taskbar icons explicitly.
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_SM_CXICON = 11
_SM_CYICON = 12
_SM_CXSMICON = 49
_SM_CYSMICON = 50


class _IconWindow(Protocol):
    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> object: ...

    def update_idletasks(self) -> object: ...

    def winfo_id(self) -> int: ...


def app_icon_resource() -> resources.abc.Traversable:
    """Return the packaged BatikCraft Studio ICO resource."""

    return resources.files("batikcraft_studio").joinpath(*_ICON_PARTS)


def prepare_windows_app_identity() -> bool:
    """Give the process a stable Windows application identity.

    Windows groups taskbar buttons by AppUserModelID. Setting it before Tk creates
    the root window prevents BatikCraft Studio from inheriting the generic Python
    or Tcl/Tk taskbar identity.
    """

    if sys.platform != "win32":
        return False
    try:
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        return False
    return int(result) == 0


def apply_app_icon(window: _IconWindow) -> bool:
    """Apply the packaged icon to a Tk window, child windows, and taskbar.

    Tk on non-Windows platforms may not support ICO files. In that case the
    application continues without failing startup.
    """

    try:
        with resources.as_file(app_icon_resource()) as icon_path:
            path = str(Path(icon_path))
            # Set the current root icon as well as Tk's default for future child windows.
            window.iconbitmap(bitmap=path)
            window.iconbitmap(default=path)
            _apply_windows_taskbar_icon(window, path)
    except (FileNotFoundError, OSError, TypeError, ValueError, tk.TclError):
        return False
    return True


def _apply_windows_taskbar_icon(window: _IconWindow, icon_path: str) -> bool:
    """Set small and large native window icons used by the Windows shell."""

    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.windll.user32
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        parent_hwnd = int(user32.GetParent(hwnd))
        if parent_hwnd:
            hwnd = parent_hwnd

        handles: list[int] = []
        icon_specs = (
            (_ICON_BIG, _SM_CXICON, _SM_CYICON),
            (_ICON_SMALL, _SM_CXSMICON, _SM_CYSMICON),
        )
        for icon_kind, width_metric, height_metric in icon_specs:
            width = int(user32.GetSystemMetrics(width_metric))
            height = int(user32.GetSystemMetrics(height_metric))
            handle = int(
                user32.LoadImageW(
                    None,
                    icon_path,
                    _IMAGE_ICON,
                    width,
                    height,
                    _LR_LOADFROMFILE,
                )
                or 0
            )
            if not handle:
                continue
            user32.SendMessageW(hwnd, _WM_SETICON, icon_kind, handle)
            handles.append(handle)

        if not handles:
            return False
        # Keep HICON handles alive for the lifetime of the Tk root.
        setattr(window, "_batikcraft_taskbar_icon_handles", tuple(handles))
    except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
        return False
    return True


__all__ = [
    "APP_USER_MODEL_ID",
    "app_icon_resource",
    "apply_app_icon",
    "prepare_windows_app_identity",
]
