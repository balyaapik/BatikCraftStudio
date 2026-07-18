"""Build native BatikCraft Studio installers for Windows, macOS, and Linux."""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = ROOT / "packaging" / "desktop_entry.py"
ICON_ICO = ROOT / "src" / "batikcraft_studio" / "resources" / "logo-app.ico"
PYPROJECT = ROOT / "pyproject.toml"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"
APP_NAME = "BatikCraftStudio"
DISPLAY_NAME = "BatikCraft Studio"
BUNDLE_ID = "com.batikcraft.studio"
WINDOWS_APP_ID = "{{2DB51FA7-DF8E-4E9D-A6DF-B239902B374E}}"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
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


def _project_version() -> str:
    with PYPROJECT.open("rb") as stream:
        value = tomllib.load(stream)["project"]["version"]
    version = str(value).strip()
    if not version:
        raise RuntimeError("Project version is empty.")
    return version


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine.replace(" ", "-") or "unknown"


def _debian_architecture() -> str:
    architecture = _architecture()
    if architecture == "x64":
        return "amd64"
    if architecture == "arm64":
        return "arm64"
    return architecture


def _read_ico_frames(path: Path) -> list[Image.Image]:
    """Recover individually valid frames even when the ICO container is malformed."""

    data = path.read_bytes()
    if len(data) < 6:
        return []
    try:
        reserved, icon_type, frame_count = struct.unpack_from("<HHH", data, 0)
    except struct.error:
        return []
    if reserved != 0 or icon_type != 1 or frame_count < 1:
        return []

    frames: list[Image.Image] = []
    for index in range(frame_count):
        entry_offset = 6 + index * 16
        if entry_offset + 16 > len(data):
            break
        entry = data[entry_offset : entry_offset + 16]
        try:
            payload_size, payload_offset = struct.unpack_from("<II", entry, 8)
        except struct.error:
            continue
        payload_end = payload_offset + payload_size
        if payload_size < 1 or payload_offset < 0 or payload_end > len(data):
            continue
        payload = data[payload_offset:payload_end]

        try:
            if payload.startswith(PNG_SIGNATURE):
                source = io.BytesIO(payload)
            else:
                single_entry = bytearray(entry)
                struct.pack_into("<I", single_entry, 12, 22)
                source = io.BytesIO(b"\x00\x00\x01\x00\x01\x00" + single_entry + payload)
            with Image.open(source) as frame:
                frame.load()
                frames.append(frame.convert("RGBA"))
        except (OSError, ValueError, struct.error):
            continue
    return frames


def _largest_icon_image() -> Image.Image:
    """Read the largest recoverable image from the application ICO."""

    frames = _read_ico_frames(ICON_ICO)
    if frames:
        return max(frames, key=lambda image: image.width * image.height)

    try:
        with Image.open(ICON_ICO) as icon:
            icon.load()
            return icon.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError(f"No usable image frame found in {ICON_ICO}") from exc


def _square_icon_image(size: int = 256) -> Image.Image:
    """Center the source icon on a square transparent canvas without distortion."""

    image = _largest_icon_image()
    side = max(image.width, image.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(
        image,
        dest=((side - image.width) // 2, (side - image.height) // 2),
    )
    if square.size != (size, size):
        square = square.resize((size, size), Image.Resampling.LANCZOS)
    return square


def _prepare_build_icon(directory: Path, platform_name: str | None = None) -> Path:
    """Create a platform-safe icon for PyInstaller and installer packaging."""

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
    package_mode = "--onefile" if sys.platform == "win32" else "--onedir"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        package_mode,
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
            "pip",
            "--collect-all",
            "huggingface_hub",
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


def _find_inno_setup_compiler() -> Path:
    configured = os.environ.get("INNO_SETUP_COMPILER")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))

    discovered = shutil.which("ISCC.exe") or shutil.which("iscc")
    if discovered:
        candidates.append(Path(discovered))

    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Inno Setup 6" / "ISCC.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise RuntimeError(
        "Inno Setup 6 tidak ditemukan. Instal Inno Setup atau set "
        "INNO_SETUP_COMPILER ke lokasi ISCC.exe."
    )


def _windows_installer_script(
    *,
    source_executable: Path,
    output_directory: Path,
    icon_path: Path,
    version: str,
) -> str:
    output_base = f"{APP_NAME}-Setup-Windows-{_architecture()}"
    lines = [
        f'#define MyAppVersion "{version}"',
        f'#define SourceExe "{source_executable.resolve()}"',
        f'#define OutputDirectory "{output_directory.resolve()}"',
        f'#define SetupIcon "{icon_path.resolve()}"',
        "",
        "[Setup]",
        f"AppId={WINDOWS_APP_ID}",
        f"AppName={DISPLAY_NAME}",
        "AppVersion={#MyAppVersion}",
        f"AppPublisher={DISPLAY_NAME}",
        f"DefaultDirName={{localappdata}}\\Programs\\{DISPLAY_NAME}",
        f"DefaultGroupName={DISPLAY_NAME}",
        "DisableProgramGroupPage=yes",
        "OutputDir={#OutputDirectory}",
        f"OutputBaseFilename={output_base}",
        "SetupIconFile={#SetupIcon}",
        "UninstallDisplayIcon={app}\\BatikCraftStudio.exe",
        "Compression=lzma2",
        "SolidCompression=yes",
        "WizardStyle=modern",
        "PrivilegesRequired=lowest",
        "ArchitecturesAllowed=x64compatible",
        "ArchitecturesInstallIn64BitMode=x64compatible",
        "CloseApplications=yes",
        "RestartApplications=no",
        "",
        "[Languages]",
        'Name: "indonesian"; MessagesFile: "compiler:Languages\\Indonesian.isl"',
        'Name: "english"; MessagesFile: "compiler:Default.isl"',
        "",
        "[Tasks]",
        'Name: "desktopicon"; Description: "Buat shortcut di Desktop"; '
        'GroupDescription: "Shortcut tambahan:"; Flags: unchecked',
        "",
        "[Files]",
        'Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "BatikCraftStudio.exe"; '
        "Flags: ignoreversion",
        "",
        "[Icons]",
        f'Name: "{{autoprograms}}\\{DISPLAY_NAME}"; '
        'Filename: "{app}\\BatikCraftStudio.exe"; WorkingDir: "{app}"',
        f'Name: "{{autodesktop}}\\{DISPLAY_NAME}"; '
        'Filename: "{app}\\BatikCraftStudio.exe"; WorkingDir: "{app}"; '
        "Tasks: desktopicon",
        "",
        "[Run]",
        'Filename: "{app}\\BatikCraftStudio.exe"; '
        f'Description: "Jalankan {DISPLAY_NAME}"; '
        "Flags: nowait postinstall skipifsilent",
        "",
    ]
    return "\n".join(lines)


def _package_windows(icon_path: Path) -> Path:
    source_executable = DIST_DIR / f"{APP_NAME}.exe"
    if not source_executable.is_file():
        raise FileNotFoundError(f"Windows executable was not created: {source_executable}")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    artifact = RELEASE_DIR / f"{APP_NAME}-Setup-Windows-{_architecture()}.exe"
    script_path = BUILD_DIR / "BatikCraftStudio-installer.iss"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        _windows_installer_script(
            source_executable=source_executable,
            output_directory=RELEASE_DIR,
            icon_path=icon_path,
            version=_project_version(),
        ),
        encoding="utf-8",
    )
    _run([str(_find_inno_setup_compiler()), str(script_path)])
    if not artifact.is_file():
        raise FileNotFoundError(f"Windows installer was not created: {artifact}")
    return artifact


def _package_macos() -> Path:
    application = DIST_DIR / f"{APP_NAME}.app"
    if not application.is_dir():
        raise FileNotFoundError(f"macOS app bundle was not created: {application}")

    _run(["codesign", "--force", "--deep", "--sign", "-", str(application)])
    artifact = RELEASE_DIR / f"{APP_NAME}-Installer-macOS-{_architecture()}.dmg"
    if artifact.exists():
        artifact.unlink()

    with tempfile.TemporaryDirectory(prefix="batikcraft-dmg-") as temp_directory:
        staging = Path(temp_directory) / DISPLAY_NAME
        staging.mkdir(parents=True)
        shutil.copytree(
            application,
            staging / application.name,
            symlinks=True,
        )
        os.symlink("/Applications", staging / "Applications")
        _run(
            [
                "hdiutil",
                "create",
                "-volname",
                DISPLAY_NAME,
                "-srcfolder",
                str(staging),
                "-ov",
                "-format",
                "UDZO",
                str(artifact),
            ]
        )

    if not artifact.is_file():
        raise FileNotFoundError(f"macOS installer was not created: {artifact}")
    return artifact


def _linux_desktop_entry() -> str:
    return """[Desktop Entry]
Type=Application
Name=BatikCraft Studio
Comment=Manual and AI-assisted batik motif studio
Exec=/usr/bin/batikcraft-studio
Icon=batikcraft-studio
Terminal=false
Categories=Graphics;2DGraphics;
StartupWMClass=BatikCraftStudio
Keywords=batik;design;graphics;AI;
"""


def _linux_control_file(version: str, architecture: str) -> str:
    return (
        "Package: batikcraft-studio\n"
        f"Version: {version}\n"
        "Section: graphics\n"
        "Priority: optional\n"
        f"Architecture: {architecture}\n"
        "Maintainer: Balya Rochmadi\n"
        "Depends: libc6 (>= 2.35), libx11-6, libxext6, libxrender1, libgl1\n"
        "Description: BatikCraft Studio\n"
        " Native desktop studio for manual and AI-assisted batik motif creation.\n"
    )


def _package_linux() -> Path:
    application = DIST_DIR / APP_NAME
    executable = application / APP_NAME
    if not executable.is_file():
        raise FileNotFoundError(f"Linux executable was not created: {executable}")

    version = _project_version()
    architecture = _debian_architecture()
    artifact = RELEASE_DIR / f"{APP_NAME}-Installer-Linux-{_architecture()}.deb"

    with tempfile.TemporaryDirectory(prefix="batikcraft-deb-") as temp_directory:
        package_root = Path(temp_directory) / "batikcraft-studio"
        app_dir = package_root / "opt" / "batikcraft-studio"
        bin_dir = package_root / "usr" / "bin"
        desktop_dir = package_root / "usr" / "share" / "applications"
        icon_dir = package_root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        debian_dir = package_root / "DEBIAN"

        shutil.copytree(application, app_dir, symlinks=True)
        (app_dir / APP_NAME).chmod(0o755)
        bin_dir.mkdir(parents=True)
        desktop_dir.mkdir(parents=True)
        icon_dir.mkdir(parents=True)
        debian_dir.mkdir(parents=True)

        launcher = bin_dir / "batikcraft-studio"
        launcher.write_text(
            '#!/usr/bin/env sh\nexec /opt/batikcraft-studio/BatikCraftStudio "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        launcher.chmod(0o755)

        (desktop_dir / "batikcraft-studio.desktop").write_text(
            _linux_desktop_entry(),
            encoding="utf-8",
            newline="\n",
        )
        _largest_icon_png(icon_dir / "batikcraft-studio.png")
        (debian_dir / "control").write_text(
            _linux_control_file(version, architecture),
            encoding="utf-8",
            newline="\n",
        )

        postinst = debian_dir / "postinst"
        postinst.write_text(
            """#!/usr/bin/env sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
""",
            encoding="utf-8",
            newline="\n",
        )
        postinst.chmod(0o755)

        postrm = debian_dir / "postrm"
        postrm.write_text(
            """#!/usr/bin/env sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
""",
            encoding="utf-8",
            newline="\n",
        )
        postrm.chmod(0o755)

        _run(
            [
                "dpkg-deb",
                "--build",
                "--root-owner-group",
                str(package_root),
                str(artifact),
            ]
        )

    if not artifact.is_file():
        raise FileNotFoundError(f"Linux installer was not created: {artifact}")
    return artifact


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
            assert icon_path is not None
            return _package_windows(icon_path)
        if sys.platform == "darwin":
            return _package_macos()
        return _package_linux()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    artifact = build()
    print(f"Created desktop installer: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
