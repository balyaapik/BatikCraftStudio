"""Windows process identity used for taskbar grouping and icon selection."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

APP_USER_MODEL_ID = "BatikCraft.Studio.Desktop"


def prepare_windows_app_identity() -> bool:
    """Assign BatikCraft Studio its own Windows shell identity.

    This must run before the first Tk root window is created. In particular,
    ``python -m batikcraft_studio`` otherwise inherits the identity of
    ``python.exe`` and Windows may keep showing the Python icon in the taskbar.
    """

    if sys.platform != "win32":
        return False

    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        setter = shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [wintypes.LPCWSTR]
        setter.restype = ctypes.c_long
        result = setter(APP_USER_MODEL_ID)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return int(result) == 0


__all__ = ["APP_USER_MODEL_ID", "prepare_windows_app_identity"]
