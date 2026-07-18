# BatikCraft Studio desktop installers

BatikCraft Studio is compiled with PyInstaller on each native operating system and then wrapped in the platform's normal installation format. The public artifacts are installers, not portable application folders.

## Installer artifacts

| Platform | Workflow artifact | Installer file |
| --- | --- | --- |
| Windows x64 | `BatikCraftStudio-Installer-Windows-x64` | `BatikCraftStudio-Setup-Windows-x64.exe` |
| Linux x64 | `BatikCraftStudio-Installer-Linux-x64` | `BatikCraftStudio-Installer-Linux-x64.deb` |
| macOS Intel | `BatikCraftStudio-Installer-macOS-x64` | `BatikCraftStudio-Installer-macOS-x64.dmg` |
| macOS Apple Silicon | `BatikCraftStudio-Installer-macOS-arm64` | `BatikCraftStudio-Installer-macOS-arm64.dmg` |

The workflow can be started from **Actions → Build desktop applications → Run workflow**. A manual run without a release version stores installer artifacts for 14 days.

To build all targets and publish a permanent GitHub Release, provide a version such as `v0.1.3` in the `release_tag` input:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" workflow run 315390261 `
  --ref main `
  --repo balyaapik/BatikCraftStudio `
  -f release_tag=v0.1.3
```

Pushing a Git tag matching `v*` also builds and publishes all installers.

## Local builds

Install the build profile:

```bash
python -m pip install -e ".[desktop-build]"
```

Build the installer for the current operating system:

```bash
python scripts/build_desktop.py
```

The resulting installer is written to `release/`.

### Additional Windows requirement

Windows installer compilation uses Inno Setup 6. Install it first or set `INNO_SETUP_COMPILER` to `ISCC.exe`:

```powershell
choco install innosetup -y
python scripts/build_desktop.py
```

## Windows installer

`BatikCraftStudio-Setup-Windows-x64.exe` is an Inno Setup installer. It:

- installs BatikCraft Studio under `%LOCALAPPDATA%\Programs\BatikCraft Studio`;
- creates a Start Menu entry;
- optionally creates a Desktop shortcut;
- registers BatikCraft Studio in Windows Installed Apps;
- provides a normal uninstaller;
- requires no administrator permission.

The installed application still uses one self-contained PyInstaller executable internally. Windows builds are currently unsigned, so SmartScreen may warn until code signing is configured.

The build process regenerates a square BMP-backed multi-resolution ICO before embedding the icon, preventing `UpdateResourceW` failures caused by malformed source ICO frames.

## macOS installer

Each macOS target is distributed as a DMG. Opening the DMG shows `BatikCraftStudio.app` and an `Applications` shortcut. Drag the application into Applications to install it.

The app receives an ad-hoc signature for bundle consistency. Public distribution without Gatekeeper warnings still requires an Apple Developer ID signature and notarization. Intel and Apple Silicon installers are separate.

## Linux installer

Ubuntu and Debian users install the DEB with:

```bash
sudo apt install ./BatikCraftStudio-Installer-Linux-x64.deb
```

The package installs:

- the application under `/opt/batikcraft-studio`;
- the launcher `/usr/bin/batikcraft-studio`;
- a desktop-menu entry;
- the BatikCraft Studio icon;
- package-manager uninstall support.

Remove it normally with:

```bash
sudo apt remove batikcraft-studio
```

The Linux installer is built on Ubuntu 22.04 for x64 Debian/Ubuntu-compatible distributions.

## Managed dependencies

The installed application contains the internal dependency bootstrap and Hugging Face downloader. Large platform- and GPU-sensitive packages such as Torch, Diffusers, Transformers, Accelerate, and PEFT are installed on demand through **Dependencies → Instal Semua AI + BatikBrew SDXL**.

On Windows, everything downloaded by the dependency manager is grouped beside the installed application:

```text
%LOCALAPPDATA%\Programs\BatikCraft Studio\dependencies\
├── python\site-packages\
├── models\runtime\
├── cache\pip\
└── logs\dependency-install.log
```

This location is writable because the Windows installer is per-user. Existing packages from the previous `%LOCALAPPDATA%\BatikCraftStudio\ai-runtime` layout are migrated on a best-effort basis when the new application starts.

A signed macOS `.app` must not be modified after installation, and Linux `/opt` is normally root-owned. On those systems the same `dependencies` structure is stored in the BatikCraft Studio per-user application-data directory instead of inside the signed or system-owned program directory.

## Download progress and cancellation

Stable Diffusion downloads read repository file sizes from Hugging Face metadata and display:

- an actual percentage;
- downloaded bytes and total bytes;
- the file currently being downloaded.

The model downloader uses a cancellation-aware progress callback for every received chunk. Pressing **Batal** sets the cancellation signal immediately; the active transfer raises a cancellation exception on its next chunk, stops the remaining files, and preserves partial data so a later installation can resume.

Dependency installation runs in its own process group. Pressing **Hentikan Instalasi** terminates the pip child process and its descendants rather than merely closing the GUI. Pip wheel cache and already downloaded files remain under `dependencies` for repair or resume.

No system Python or manual terminal dependency installation is required.
