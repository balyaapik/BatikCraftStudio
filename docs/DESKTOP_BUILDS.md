# BatikCraft Studio desktop builds

BatikCraft Studio is packaged with PyInstaller on each target operating system. PyInstaller is not a cross-compiler, so Windows, macOS, and Linux artifacts are produced by separate native GitHub Actions runners.

## Artifacts

| Platform | Artifact | Output |
| --- | --- | --- |
| Windows x64 | `BatikCraftStudio-Windows-x64` | ZIP containing `BatikCraftStudio.exe` and support files |
| Linux x64 | `BatikCraftStudio-Linux-x64` | TAR.GZ containing the executable, icon, desktop launcher, installer, and uninstaller |
| macOS Intel | `BatikCraftStudio-macOS-x64` | ZIP containing `BatikCraftStudio.app` |
| macOS Apple Silicon | `BatikCraftStudio-macOS-arm64` | ZIP containing `BatikCraftStudio.app` |

The workflow can be started manually from **Actions → Build desktop applications → Run workflow**. Pushing a tag such as `v0.1.0` builds all four packages and publishes them to a GitHub release.

## Local builds

Install the build profile:

```bash
python -m pip install -e ".[desktop-build]"
```

Build for the current operating system:

```bash
python scripts/build_desktop.py
```

The package is written to `release/`.

## Platform notes

### Windows

Run `BatikCraftStudio.exe`, not `python -m batikcraft_studio`. The application logo is embedded in the executable, so Windows taskbar, Alt+Tab, title bar, and shortcuts use the BatikCraft Studio identity. Windows builds are currently unsigned and can trigger SmartScreen.

The build script does not send the repository ICO directly to `UpdateResourceW`. It first reads the largest logo frame, centers it on a 256×256 transparent canvas, and writes a fresh BMP-backed multi-resolution ICO. This prevents `WinError 87` failures caused by non-square or PNG-compressed ICO frames.

After updating an older checkout, remove stale output before retrying when invoking PyInstaller manually:

```powershell
Remove-Item -Recurse -Force build, dist, release -ErrorAction SilentlyContinue
python scripts/build_desktop.py
```

The normal build script already performs this cleanup automatically.

### macOS

The generated `.app` receives an ad-hoc signature so its internal bundle remains consistent. Public distribution without security warnings requires an Apple Developer ID certificate and notarization. Intel and Apple Silicon packages are built separately.

### Linux

Extract the archive and either run `./BatikCraftStudio` directly or execute:

```bash
./install.sh
```

The installer places the application in the user's local data directory, creates `~/.local/bin/batikcraft-studio`, installs the icon, and registers a `.desktop` launcher. Use `./uninstall.sh` from the installed application directory to remove it.

Linux binaries are built on Ubuntu 22.04 to improve compatibility with newer glibc-based distributions. They are x64 builds and are not intended for ARM Linux machines.

## Included feature profile

The native packages include the editor, marketplace integration, NFT and model workflows, cloud generation clients, Gemini/OpenAI support, keyring integration, and all BatikCraft Studio resources.

Torch, Diffusers, Transformers, CUDA, and full local SDXL/LoRA training are intentionally excluded from the portable builds. Those components are large and require platform- and GPU-specific packaging. Development installations can continue to use:

```bash
python -m pip install -e ".[ai]"
python -m batikcraft_studio
```

A dedicated Windows CUDA distribution can be created separately after the portable builds are stable.
