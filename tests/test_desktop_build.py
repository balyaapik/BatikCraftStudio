import importlib.util
import struct
from pathlib import Path
from types import ModuleType

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _load_build_module() -> ModuleType:
    path = ROOT / "scripts" / "build_desktop.py"
    spec = importlib.util.spec_from_file_location("batikcraft_build_desktop", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_build_uses_onefile_and_other_platforms_use_onedir() -> None:
    module = _load_build_module()
    original_platform = module.sys.platform
    try:
        module.sys.platform = "win32"
        windows_command = module._pyinstaller_command(None)
        assert "--onefile" in windows_command
        assert "--onedir" not in windows_command
        assert "--windowed" in windows_command

        module.sys.platform = "darwin"
        macos_command = module._pyinstaller_command(None)
        assert "--onedir" in macos_command
        assert "--onefile" not in macos_command
        assert "--windowed" in macos_command
        assert "--osx-bundle-identifier" in macos_command

        module.sys.platform = "linux"
        linux_command = module._pyinstaller_command(None)
        assert "--onedir" in linux_command
        assert "--onefile" not in linux_command
        assert "--windowed" not in linux_command
    finally:
        module.sys.platform = original_platform


def test_windows_packager_publishes_exactly_one_executable(tmp_path: Path) -> None:
    module = _load_build_module()
    dist_dir = tmp_path / "dist"
    release_dir = tmp_path / "release"
    dist_dir.mkdir()
    release_dir.mkdir()
    source = dist_dir / f"{module.APP_NAME}.exe"
    source.write_bytes(b"single-file-windows-bundle")

    module.DIST_DIR = dist_dir
    module.RELEASE_DIR = release_dir
    module._architecture = lambda: "x64"

    artifact = module._package_windows()

    assert artifact == release_dir / "BatikCraftStudio-Windows-x64.exe"
    assert artifact.read_bytes() == source.read_bytes()
    assert list(release_dir.iterdir()) == [artifact]


def test_windows_build_icon_is_square_and_bmp_backed(tmp_path: Path) -> None:
    module = _load_build_module()
    icon_path = module._prepare_build_icon(tmp_path, "win32")

    with Image.open(icon_path) as icon:
        sizes = icon.ico.sizes()
    assert sizes
    assert (256, 256) in sizes
    assert all(width == height for width, height in sizes)

    data = icon_path.read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, icon_type) == (0, 1)
    assert count == len(module.WINDOWS_ICON_SIZES)
    for index in range(count):
        entry_offset = 6 + index * 16
        width, height, _colors, _reserved, _planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", data, entry_offset
        )
        actual_width = 256 if width == 0 else width
        actual_height = 256 if height == 0 else height
        assert actual_width == actual_height
        assert bits == 32
        assert size > 0
        # BITMAPINFOHEADER signature. This avoids PNG-compressed ICO frames that have
        # caused UpdateResourceW failures in Windows PyInstaller builds.
        assert data[offset : offset + 4] == b"(\x00\x00\x00"


def test_macos_build_icon_is_square_png(tmp_path: Path) -> None:
    module = _load_build_module()
    icon_path = module._prepare_build_icon(tmp_path, "darwin")

    with Image.open(icon_path) as icon:
        assert icon.format == "PNG"
        assert icon.size == (256, 256)


def test_portable_build_excludes_large_local_ai_frameworks() -> None:
    source = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")

    for module in ("torch", "diffusers", "transformers", "accelerate", "peft"):
        assert f'"{module}"' in source


def test_workflow_builds_all_supported_desktop_targets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "windows-2022" in workflow
    assert "ubuntu-22.04" in workflow
    assert "macos-15-intel" in workflow
    assert "macos-15" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "workflow_dispatch:" in workflow


def test_workflow_can_publish_a_manual_github_release() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "release_tag:" in workflow
    assert "Publish GitHub release" in workflow
    assert "inputs.release_tag != ''" in workflow
    assert 'gh release create "${RELEASE_TAG}"' in workflow
    assert '--target "${GITHUB_SHA}"' in workflow


def test_linux_package_registers_a_desktop_icon() -> None:
    source = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")

    assert "batikcraft-studio.desktop.in" in source
    assert "StartupWMClass=BatikCraftStudio" in source
    assert "gtk-update-icon-cache" in source


def test_desktop_build_profile_contains_pyinstaller_and_cloud_clients() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "desktop-build = [" in pyproject
    assert '"pyinstaller>=6.21,<7"' in pyproject
    assert '"openai>=1.0,<3"' in pyproject
    assert '"google-genai>=1.0,<2"' in pyproject
