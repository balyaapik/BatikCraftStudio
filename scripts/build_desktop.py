"""Build and package native BatikCraft Studio desktop applications."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = ROOT / "packaging" / "desktop_entry.py"
ICON_ICO = ROOT / "src" / "batikcraft_studio" / "resources" / "logo-app.ico"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"
APP_NAME = "BatikCraftStudio"
BUNDLE_ID = "com.batikcraft.studio"
WINDOWS_ICON_SIZES = (
    (16, 16),
    (20, 20),
    (24, 24),
    (32, 32),
    (40, 40),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
)


def _run(command: list[str]) -> None:
    print("$", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine.replace(" ", "-") or "unknown"


def _largest_icon_image() -> Image.Image:
    """Read the largest image from an ICO, including Pillow's ICO size variants."""
    with Image.open(ICON_ICO) as icon:
        ico_reader = getattr(icon, "ico", None)
        if ico_reader is not None:
            sizes = ico_reader.sizes()
            if sizes:
                largest = max(sizes, key=lambda size: int(size[0]) * int(size[1]))
                return ico_reader.getimage(largest).convert("RGBA")
        return icon.convert("RGBA")


def _square_icon_image(size: int = 256) -> Image.Image:
    """Center the source icon on a square transparent canvas without distortion."""
    image = _largest_icon_image()
    side = max(image.width, image.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(
        image,
        destination=((side - image.width) // 2, (side - image.height) // 2),
    )
    if square.size != (size, size):
        square = square.resize((size, size), Image.Resampling.LANCZOS)
    return square


def _prepare_build_icon(directory: Path, platform_name: str | None = None) -> Path:
    """Create a platform-safe icon instead of passing the source ICO through unchanged.

    Some icon editors produce non-square or PNG-compressed ICO frames that Windows accepts
    for Tk title bars but that fail when PyInstaller calls UpdateResourceW. Windows builds use
    a freshly generated, square, BMP-backed multi-resolution ICO. macOS receives a square PNG
    that PyInstaller converts to ICNS.
    """
    platform_name = platform_name or sys.platform
    directory.mkdir(parents=True, exist_ok=True)
    image = _square_icon_image()
    if platform_name == "win32":
        destination = directory / "logo-app-windows.ico"
        image.save(
            destination,
            format="ICO",
            sizes=list(WINDOWS_ICON_SIZES),
            bitmap_format="bmp",
        )
        return destination

    destination = directory / "logo-app.png"
    image.save(destination, format="PNG", optimize=True)
    return destination


def _pyinstaller_command(icon_path: Path | None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP_NAME,
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
    ]
    if icon_path is not None:
        command.extend(["--icon", str(icon_path)])
    command.extend(
        [
            "--collect-data",
            "batikcraft_studio",
            "--collect-submodules",
            "batikcraft_studio",
            "--collect-all",
            "tkinterdnd2",
            "--collect-all",
            "keyring",
            "--collect-all",
            "openai",
            "--collect-all",
            "google.genai",
            "--hidden-import",
            "PIL._tkinter_finder",
            "--exclude-module",
            "torch",
            "--exclude-module",
            "torchvision",
            "--exclude-module",
            "diffusers",
            "--exclude-module",
            "transformers",
            "--exclude-module",
            "accelerate",
            "--exclude-module",
            "peft",
        ]
    )
    if sys.platform in {"win32", "darwin"}:
        command.append("--windowed")
    if sys.platform == "darwin":
        command.extend(["--osx-bundle-identifier", BUNDLE_ID])
    command.append(str(ENTRY_POINT))
    return command


def _largest_icon_png(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _square_icon_image().save(destination, format="PNG", optimize=True)


def _package_windows() -> Path:
    application = DIST_DIR / APP_NAME
    executable = application / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"Windows executable was not created: {executable}")
    archive_base = RELEASE_DIR / f"{APP_NAME}-Windows-{_architecture()}"
    archive = Path(shutil.make_archive(str(archive_base), "zip", DIST_DIR, APP_NAME))
    return archive


def _package_macos() -> Path:
    application = DIST_DIR / f"{APP_NAME}.app"
    if not application.is_dir():
        raise FileNotFoundError(f"macOS app bundle was not created: {application}")

    # An ad-hoc signature keeps the bundle internally consistent. Public distribution
    # still requires an Apple Developer ID signature and notarization.
    _run(["codesign", "--force", "--deep", "--sign", "-", str(application)])
    archive = RELEASE_DIR / f"{APP_NAME}-macOS-{_architecture()}.zip"
    if archive.exists():
        archive.unlink()
    _run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(application),
            str(archive),
        ]
    )
    return archive


def _linux_installer_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/batikcraft-studio"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICONS_DIR="$DATA_HOME/icons/hicolor/256x256/apps"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$APPLICATIONS_DIR" "$ICONS_DIR"
cp -a "$SOURCE_DIR/." "$APP_DIR/"
chmod +x "$APP_DIR/BatikCraftStudio"
ln -sfn "$APP_DIR/BatikCraftStudio" "$BIN_DIR/batikcraft-studio"
cp "$APP_DIR/batikcraft-studio.png" "$ICONS_DIR/batikcraft-studio.png"
sed \
  -e "s|@EXEC@|$APP_DIR/BatikCraftStudio|g" \
  -e "s|@ICON@|$ICONS_DIR/batikcraft-studio.png|g" \
  "$APP_DIR/batikcraft-studio.desktop.in" \
  > "$APPLICATIONS_DIR/batikcraft-studio.desktop"
chmod +x "$APPLICATIONS_DIR/batikcraft-studio.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "BatikCraft Studio installed."
echo "Run: $BIN_DIR/batikcraft-studio"
echo "Ensure $BIN_DIR is present in PATH."
"""


def _linux_uninstaller_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA_HOME/batikcraft-studio"
rm -f "$HOME/.local/bin/batikcraft-studio"
rm -f "$DATA_HOME/applications/batikcraft-studio.desktop"
rm -f "$DATA_HOME/icons/hicolor/256x256/apps/batikcraft-studio.png"
echo "BatikCraft Studio removed."
"""


def _package_linux() -> Path:
    application = DIST_DIR / APP_NAME
    executable = application / APP_NAME
    if not executable.is_file():
        raise FileNotFoundError(f"Linux executable was not created: {executable}")
    executable.chmod(executable.stat().st_mode | 0o111)

    _largest_icon_png(application / "batikcraft-studio.png")
    desktop = """[Desktop Entry]
Type=Application
Name=BatikCraft Studio
Comment=Manual and AI-assisted batik motif studio
Exec=@EXEC@
Icon=@ICON@
Terminal=false
Categories=Graphics;2DGraphics;
StartupWMClass=BatikCraftStudio
Keywords=batik;design;graphics;AI;
"""
    (application / "batikcraft-studio.desktop.in").write_text(desktop, encoding="utf-8")
    install_script = application / "install.sh"
    install_script.write_text(_linux_installer_script(), encoding="utf-8", newline="\n")
    install_script.chmod(0o755)
    uninstall_script = application / "uninstall.sh"
    uninstall_script.write_text(_linux_uninstaller_script(), encoding="utf-8", newline="\n")
    uninstall_script.chmod(0o755)
    (application / "README-LINUX.txt").write_text(
        "Run ./BatikCraftStudio directly or execute ./install.sh to add a desktop launcher.\n",
        encoding="utf-8",
    )

    archive = RELEASE_DIR / f"{APP_NAME}-Linux-{_architecture()}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(application, arcname=APP_NAME)
    return archive


def build() -> Path:
    if not ENTRY_POINT.is_file():
        raise FileNotFoundError(ENTRY_POINT)
    if not ICON_ICO.is_file():
        raise FileNotFoundError(ICON_ICO)
    if sys.platform not in {"win32", "darwin"} and not sys.platform.startswith("linux"):
        raise RuntimeError(f"Unsupported build platform: {sys.platform}")

    shutil.rmtree(DIST_DIR, ignore_errors=True)
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    for previous in RELEASE_DIR.glob(f"{APP_NAME}-*"):
        if previous.is_file():
            previous.unlink()

    with tempfile.TemporaryDirectory(prefix="batikcraft-build-icon-") as icon_directory:
        icon_path = None
        if sys.platform in {"win32", "darwin"}:
            icon_path = _prepare_build_icon(Path(icon_directory))
        _run(_pyinstaller_command(icon_path))

    if sys.platform == "win32":
        return _package_windows()
    if sys.platform == "darwin":
        return _package_macos()
    return _package_linux()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    archive = build()
    print(f"Created desktop artifact: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
