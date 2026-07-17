"""Application icon loading for BatikCraft Studio windows."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from importlib import resources
from pathlib import Path
from typing import Protocol

from .windows_identity import APP_USER_MODEL_ID, prepare_windows_app_identity

_ICON_PARTS = ("resources", "logo-app.ico")

# Windows constants used to set title-bar, Alt+Tab, and taskbar icons.
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_SM_CXICON = 11
_SM_CYICON = 12
_SM_CXSMICON = 49
_SM_CYSMICON = 50
_GCLP_HICON = -14
_GCLP_HICONSM = -34


class _IconWindow(Protocol):
    _batikcraft_taskbar_icon_handles: tuple[int, ...]

    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> object: ...

    def update_idletasks(self) -> object: ...

    def winfo_id(self) -> int: ...


def app_icon_resource() -> resources.abc.Traversable:
    """Return the packaged BatikCraft Studio ICO resource."""

    return resources.files("batikcraft_studio").joinpath(*_ICON_PARTS)


def apply_app_icon(window: _IconWindow) -> bool:
    """Apply the packaged icon to Tk and the native Windows window handles."""

    try:
        with resources.as_file(app_icon_resource()) as icon_path:
            path = str(Path(icon_path))
            # Apply both to this root and as Tk's default for future Toplevel windows.
            window.iconbitmap(bitmap=path)
            window.iconbitmap(default=path)
            if sys.platform == "win32":
                return _apply_windows_taskbar_icon(window, path)
    except (FileNotFoundError, OSError, TypeError, ValueError, tk.TclError):
        return False
    return True


def _configured_user32() -> object:
    """Return user32 with 64-bit-safe signatures for HWND and HICON values."""

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND

    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int

    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE

    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    return user32


def _native_window_handles(window: _IconWindow, user32: object) -> tuple[int, ...]:
    """Return both the Tk child HWND and its native wrapper HWND when present."""

    child_hwnd = int(window.winfo_id())
    parent_hwnd = int(user32.GetParent(child_hwnd) or 0)
    values = [value for value in (parent_hwnd, child_hwnd) if value]
    return tuple(dict.fromkeys(values))


def _set_class_icons(user32: object, hwnds: tuple[int, ...], big: int, small: int) -> None:
    """Set class-level icons as an additional Windows shell fallback."""

    setter = getattr(user32, "SetClassLongPtrW", None)
    if setter is None:
        setter = getattr(user32, "SetClassLongW", None)
    if setter is None:
        return

    setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    setter.restype = ctypes.c_ssize_t
    for hwnd in hwnds:
        if big:
            setter(hwnd, _GCLP_HICON, big)
        if small:
            setter(hwnd, _GCLP_HICONSM, small)


def _apply_windows_taskbar_icon(window: _IconWindow, icon_path: str) -> bool:
    """Set native icon handles used by the Windows taskbar and Alt+Tab switcher."""

    if sys.platform != "win32":
        return False

    try:
        user32 = _configured_user32()
        window.update_idletasks()
        hwnds = _native_window_handles(window, user32)
        if not hwnds:
            return False

        handles: dict[int, int] = {}
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
            handles[icon_kind] = handle
            for hwnd in hwnds:
                user32.SendMessageW(hwnd, _WM_SETICON, icon_kind, handle)

        if not handles:
            return False
        _set_class_icons(
            user32,
            hwnds,
            handles.get(_ICON_BIG, 0),
            handles.get(_ICON_SMALL, 0),
        )
        # Keep HICON handles alive for the lifetime of the root window.
        window._batikcraft_taskbar_icon_handles = tuple(handles.values())
    except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
        return False
    return True


__all__ = [
    "APP_USER_MODEL_ID",
    "app_icon_resource",
    "apply_app_icon",
    "prepare_windows_app_identity",
]
