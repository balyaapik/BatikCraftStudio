from __future__ import annotations

import tkinter as tk
from pathlib import Path

import batikcraft_studio.app_icon as app_icon
import batikcraft_studio.windows_identity as windows_identity
from batikcraft_studio.app_icon import app_icon_resource, apply_app_icon
from batikcraft_studio.windows_identity import APP_USER_MODEL_ID


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


class RecordingCallable:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: object) -> int:
        self.calls.append(args)
        return self.result


class RecordingShell32:
    def __init__(self) -> None:
        self.SetCurrentProcessExplicitAppUserModelID = RecordingCallable()


class RecordingUser32:
    def __init__(self) -> None:
        self.messages: list[tuple[int, int, int, int]] = []
        self.loaded_sizes: list[tuple[int, int]] = []
        self.SetClassLongPtrW = RecordingCallable()

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
    shell32 = RecordingShell32()
    monkeypatch.setattr(windows_identity.sys, "platform", "win32")
    monkeypatch.setattr(
        windows_identity.ctypes,
        "WinDLL",
        lambda *args, **kwargs: shell32,
        raising=False,
    )

    assert windows_identity.prepare_windows_app_identity() is True
    assert shell32.SetCurrentProcessExplicitAppUserModelID.calls == [
        (APP_USER_MODEL_ID,)
    ]



def test_windows_taskbar_receives_icons_on_wrapper_and_tk_hwnds(monkeypatch) -> None:
    user32 = RecordingUser32()
    window = RecordingWindow()
    monkeypatch.setattr(app_icon.sys, "platform", "win32")
    monkeypatch.setattr(app_icon, "_configured_user32", lambda: user32)

    assert apply_app_icon(window) is True
    assert user32.loaded_sizes == [(32, 32), (16, 16)]
    assert user32.messages == [
        (88, 0x0080, 1, 101),
        (77, 0x0080, 1, 101),
        (88, 0x0080, 0, 102),
        (77, 0x0080, 0, 102),
    ]
    assert window._batikcraft_taskbar_icon_handles == (101, 102)
    assert len(user32.SetClassLongPtrW.calls) == 4



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



def test_python_module_entrypoint_prepares_identity_before_tk_import() -> None:
    source = Path("src/batikcraft_studio/__main__.py").read_text(encoding="utf-8")

    identity_index = source.index("prepare_windows_app_identity()")
    tkinter_index = source.index("import tkinter as tk")
    application_index = source.index("from .integrated_market_app import")
    assert identity_index < tkinter_index < application_index



def test_python_module_entrypoint_refreshes_mapped_window_icon() -> None:
    source = Path("src/batikcraft_studio/__main__.py").read_text(encoding="utf-8")

    assert "after_idle(lambda: apply_app_icon(application.root))" in source
    assert "after(300, lambda: apply_app_icon(application.root))" in source



def test_win32_functions_use_pointer_safe_signatures() -> None:
    source = Path("src/batikcraft_studio/app_icon.py").read_text(encoding="utf-8")

    assert "LoadImageW.restype = wintypes.HANDLE" in source
    assert "SendMessageW.argtypes" in source
    assert "SetClassLongPtrW" in source
    assert "_native_window_handles" in source



def test_early_identity_module_does_not_import_tkinter() -> None:
    source = Path("src/batikcraft_studio/windows_identity.py").read_text(encoding="utf-8")

    assert "import tkinter" not in source
