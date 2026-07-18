# BatikCraft Studio desktop builds

BatikCraft Studio is packaged with PyInstaller on each target operating system. PyInstaller is not a cross-compiler, so Windows, macOS, and Linux artifacts are produced by separate native GitHub Actions runners.

## Artifacts

| Platform | Artifact | Output |
| --- | --- | --- |
| Windows x64 | `BatikCraftStudio-Windows-x64` | One self-contained `BatikCraftStudio-Windows-x64.exe` file |
| Linux x64 | `BatikCraftStudio-Linux-x64` | TAR.GZ containing the executable, icon, desktop launcher, installer, and uninstaller |
| macOS Intel | `BatikCraftStudio-macOS-x64` | ZIP containing `BatikCraftStudio.app` |
| macOS Apple Silicon | `BatikCraftStudio-macOS-arm64` | ZIP containing `BatikCraftStudio.app` |

The workflow can be started manually from **Actions → Build desktop applications → Run workflow**. A manual run without a release version only stores workflow artifacts for 14 days.

To build all four targets and publish them as a permanent GitHub Release, provide a version such as `v0.1.0` in the `release_tag` input. From GitHub CLI on Windows:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" workflow run 315390261 `
  --ref main `
  --repo balyaapik/BatikCraftStudio `
  -f release_tag=v0.1.0
```

Pushing a Git tag matching `v*` also builds all four packages and publishes a release. Release versions must follow forms such as `v0.1.0` or `v0.1.0-beta.1`.

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

The Windows build uses PyInstaller `--onefile --windowed`. The embedded Python interpreter, required desktop packages, DLLs, Tk resources, application resources, model downloader, and AI dependency bootstrap are contained in one executable. End users do not need to install Python or keep an `_internal` directory beside the application.

Run `BatikCraftStudio-Windows-x64.exe`, not `python -m batikcraft_studio`. The application logo is embedded in the executable, so Windows taskbar, Alt+Tab, title bar, and shortcuts use the BatikCraft Studio identity. Windows builds are currently unsigned and can trigger SmartScreen.

A one-file PyInstaller application extracts its bundled runtime into a temporary `_MEI...` directory while running. This can make the first startup slower than an onedir package, especially while Windows Defender scans the executable. The temporary runtime is normally removed when the application exits.

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

## GUI-managed AI runtime

The desktop executable contains `pip` as an internal bootstrap component and contains the Hugging Face model downloader. Heavy, device-sensitive packages such as Torch, Diffusers, Transformers, Accelerate, and PEFT are not inflated into the base EXE. Instead, users open **Dependencies** and press **Instal Semua AI + BatikBrew SDXL**.

The application then:

1. launches its own hidden dependency-installer mode;
2. downloads compatible Python wheels into the per-user BatikCraft AI runtime;
3. activates that folder before AI providers are imported;
4. continues directly to the resumable BatikBrew SDXL model download;
5. keeps installation logs and partial model downloads for repair or resume.

On Windows, packages are stored under:

```text
%LOCALAPPDATA%\BatikCraftStudio\ai-runtime\site-packages
```

Model weights remain under the existing BatikCraft Studio model directory. No system Python installation, terminal command, administrator permission, or manual dependency search is required.

## Included feature profile

The native packages include the editor, marketplace integration, NFT and model workflows, cloud generation clients, Gemini/OpenAI support, keyring integration, the model downloader, the AI bootstrap installer, and all BatikCraft Studio resources.

Torch, Diffusers, Transformers, CUDA, and full local SDXL/LoRA training are installed on demand through the in-app dependency manager because those components are large and platform/GPU-sensitive. Development installations can continue to use:

```bash
python -m pip install -e ".[ai]"
python -m batikcraft_studio
```

A dedicated pre-bundled Windows CUDA distribution can be created separately after the managed runtime is stable.
