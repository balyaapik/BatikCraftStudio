from __future__ import annotations

import tkinter as tk
from pathlib import Path

import batikcraft_studio.app_icon as app_icon
from batikcraft_studio.app_icon import (
    APP_USER_MODEL_ID,
    app_icon_resource,
    apply_app_icon,
    prepare_windows_app_identity,
)


class RecordingWindow:
    def __init__(self) -> None:
        self.icon_paths: list[Path] = []

    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> None:
        value = default or bitmap
        assert value is not None
        icon_path = Path(value)
        assert icon_path.is_file()
        self.icon_paths.append(icon_path)

    def update_idletasks(self) -> None:
        return None

    def winfo_id(self) -> int:
        return 77


class RejectingWindow:
    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> None:
        raise tk.TclError("ICO files are not supported by this Tk build")

    def update_idletasks(self) -> None:
        return None

    def winfo_id(self) -> int:
        return 0


class RecordingShell32:
    def __init__(self) -> None:
        self.app_ids: list[str] = []

    def SetCurrentProcessExplicitAppUserModelID(self, value: str) -> int:
        self.app_ids.append(value)
        return 0


class RecordingUser32:
    def __init__(self) -> None:
        self.messages: list[tuple[int, int, int, int]] = []
        self.loaded_sizes: list[tuple[int, int]] = []

    def GetParent(self, hwnd: int) -> int:
        assert hwnd == 77
        return 88

    def GetSystemMetrics(self, metric: int) -> int:
        return 32 if metric in {11, 12} else 16

    def LoadImageW(
        self,
        instance: object,
        path: str,
        image_type: int,
        width: int,
        height: int,
        flags: int,
    ) -> int:
        assert instance is None
        assert Path(path).is_file()
        assert image_type == 1
        assert flags == 0x0010
        self.loaded_sizes.append((width, height))
        return 100 + len(self.loaded_sizes)

    def SendMessageW(self, hwnd: int, message: int, kind: int, handle: int) -> int:
        self.messages.append((hwnd, message, kind, handle))
        return 0


class RecordingWindll:
    def __init__(self) -> None:
        self.shell32 = RecordingShell32()
        self.user32 = RecordingUser32()


def test_packaged_icon_is_a_valid_ico_resource() -> None:
    resource = app_icon_resource()

    assert resource.name == "logo-app.ico"
    with resource.open("rb") as stream:
        assert stream.read(4) == b"\x00\x00\x01\x00"


def test_apply_app_icon_uses_packaged_resource() -> None:
    window = RecordingWindow()

    assert apply_app_icon(window) is True
    assert len(window.icon_paths) == 2
    assert {path.name for path in window.icon_paths} == {"logo-app.ico"}


def test_apply_app_icon_does_not_break_non_windows_startup() -> None:
    assert apply_app_icon(RejectingWindow()) is False


def test_windows_identity_uses_stable_app_user_model_id(monkeypatch) -> None:
    windll = RecordingWindll()
    monkeypatch.setattr(app_icon.sys, "platform", "win32")
    monkeypatch.setattr(app_icon.ctypes, "windll", windll, raising=False)

    assert prepare_windows_app_identity() is True
    assert windll.shell32.app_ids == [APP_USER_MODEL_ID]


def test_windows_taskbar_receives_small_and_large_icons(monkeypatch) -> None:
    windll = RecordingWindll()
    window = RecordingWindow()
    monkeypatch.setattr(app_icon.sys, "platform", "win32")
    monkeypatch.setattr(app_icon.ctypes, "windll", windll, raising=False)

    assert apply_app_icon(window) is True
    assert windll.user32.loaded_sizes == [(32, 32), (16, 16)]
    assert windll.user32.messages == [
        (88, 0x0080, 1, 101),
        (88, 0x0080, 0, 102),
    ]
    assert window._batikcraft_taskbar_icon_handles == (101, 102)


def test_icon_is_included_in_package_configuration() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.setuptools.package-data]" in pyproject
    assert "resources/*.ico" in pyproject


def test_final_application_prepares_identity_before_creating_tk_root() -> None:
    source = Path("src/batikcraft_studio/integrated_market_app.py").read_text(
        encoding="utf-8"
    )

    assert source.index("prepare_windows_app_identity()") < source.index("super().__init__()")
    assert "apply_app_icon(self.root)" in source
