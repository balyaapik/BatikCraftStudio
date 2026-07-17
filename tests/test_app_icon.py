from __future__ import annotations

import tkinter as tk
from pathlib import Path

from batikcraft_studio.app_icon import app_icon_resource, apply_app_icon


class RecordingWindow:
    def __init__(self) -> None:
        self.icon_path: Path | None = None

    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> None:
        value = default or bitmap
        assert value is not None
        self.icon_path = Path(value)
        assert self.icon_path.is_file()


class RejectingWindow:
    def iconbitmap(self, bitmap: str | None = None, default: str | None = None) -> None:
        raise tk.TclError("ICO files are not supported by this Tk build")


def test_packaged_icon_is_a_valid_ico_resource() -> None:
    resource = app_icon_resource()

    assert resource.name == "logo-app.ico"
    with resource.open("rb") as stream:
        assert stream.read(4) == b"\x00\x00\x01\x00"


def test_apply_app_icon_uses_packaged_resource() -> None:
    window = RecordingWindow()

    assert apply_app_icon(window) is True
    assert window.icon_path is not None
    assert window.icon_path.name == "logo-app.ico"


def test_apply_app_icon_does_not_break_non_windows_startup() -> None:
    assert apply_app_icon(RejectingWindow()) is False


def test_icon_is_included_in_package_configuration() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '[tool.setuptools.package-data]' in pyproject
    assert 'resources/*.ico' in pyproject


def test_final_application_applies_the_icon() -> None:
    source = Path("src/batikcraft_studio/integrated_market_app.py").read_text(
        encoding="utf-8"
    )

    assert "apply_app_icon(self.root)" in source
