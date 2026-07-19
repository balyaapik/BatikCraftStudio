# BatikCraft Studio desktop installers

BatikCraft Studio is compiled with PyInstaller on each native operating system and then wrapped in the platform's normal installation format. The public artifacts are installers, not portable application folders.

## Installer artifacts

Public installer filenames always include the application release version so downloads from different releases are easy to distinguish. For release `v0.3.0`:

| Platform | Workflow artifact | Installer file |
| --- | --- | --- |
| Windows x64 | `BatikCraftStudio-Installer-Windows-x64` | `BatikCraftStudio-v0.3.0-Setup-Windows-x64.exe` |
| Linux x64 | `BatikCraftStudio-Installer-Linux-x64` | `BatikCraftStudio-v0.3.0-Installer-Linux-x64.deb` |
| macOS Intel | `BatikCraftStudio-Installer-macOS-x64` | `BatikCraftStudio-v0.3.0-Installer-macOS-x64.dmg` |
| macOS Apple Silicon | `BatikCraftStudio-Installer-macOS-arm64` | `BatikCraftStudio-v0.3.0-Installer-macOS-arm64.dmg` |

The installed application keeps the stable internal identity **BatikCraft Studio** so a new release upgrades the same application instead of creating a conflicting second installation. Windows Installed Apps displays the explicit release name, such as **BatikCraft Studio v0.3.0**.

The workflow can be started from **Actions → Build desktop applications → Run workflow**. A manual run without a release version stores installer artifacts for 14 days.

To build all targets and publish a permanent GitHub Release, provide a version such as `v0.3.0` in the `release_tag` input:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" workflow run 315390261 `
  --ref main `
  --repo balyaapik/BatikCraftStudio `
  -f release_tag=v0.3.0
```

Pushing a Git tag matching `v*` also builds and publishes all installers.

## Local builds

Install the build profile:

```bash
python -m pip install -e ".[desktop-build]"
```

Build the installer for the current operating system:

```bash
python scripts/build_installer.py
```

The resulting versioned installer is written to `release/`.

### Additional Windows requirement

Windows installer compilation uses Inno Setup 6. Install it first or set `INNO_SETUP_COMPILER` to `ISCC.exe`:

```powershell
choco install innosetup -y
python scripts/build_installer.py
```

## Windows installer

`BatikCraftStudio-v0.3.0-Setup-Windows-x64.exe` is an Inno Setup installer. It:

- installs BatikCraft Studio under `C:\Program Files\BatikCraft Studio`;
- requests administrator permission during installation;
- creates a Start Menu entry;
- optionally creates a Desktop shortcut;
- registers the versioned display name in Windows Installed Apps;
- makes only the managed `dependencies` directory writable by standard users;
- provides a normal uninstaller.

The installed application still uses one self-contained PyInstaller executable internally. Windows builds are currently unsigned, so SmartScreen may warn until code signing is configured.

The build process regenerates a square BMP-backed multi-resolution ICO before embedding the icon, preventing `UpdateResourceW` failures caused by malformed source ICO frames.

## macOS installer

Each macOS target is distributed as a versioned DMG. Opening the DMG shows `BatikCraftStudio.app` and an `Applications` shortcut. Drag the application into Applications to install it.

The app receives an ad-hoc signature for bundle consistency. Public distribution without Gatekeeper warnings still requires an Apple Developer ID signature and notarization. Intel and Apple Silicon installers are separate.

## Linux installer

Ubuntu and Debian users install the DEB with:

```bash
sudo apt install ./BatikCraftStudio-v0.3.0-Installer-Linux-x64.deb
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

The installed application contains the internal dependency bootstrap and Hugging Face downloader. Large platform- and GPU-sensitive packages such as Torch, Diffusers, Transformers, Accelerate, and PEFT are installed on demand through the application's AI Dependency Manager.

On Windows, everything downloaded by the dependency manager is grouped beside the installed application:

```text
C:\Program Files\BatikCraft Studio\dependencies\
├── python\site-packages\
├── models\runtime\
├── cache\pip\
└── logs\dependency-install.log
```

The installer grants standard users modify permission only to this `dependencies` subtree. Existing packages from the previous `%LOCALAPPDATA%\BatikCraftStudio\ai-runtime` layout are migrated on a best-effort basis when the new application starts.

A signed macOS `.app` must not be modified after installation, and Linux `/opt` is normally root-owned. On those systems the same `dependencies` structure is stored in the BatikCraft Studio per-user application-data directory instead of inside the signed or system-owned program directory.

## Download progress and cancellation

Stable Diffusion downloads read repository file sizes from Hugging Face metadata and display:

- an actual percentage;
- downloaded bytes and total bytes;
- the file currently being downloaded.

The model downloader runs in an isolated child process. Pressing **Batal** terminates the active model-download process tree immediately, stops the remaining files, and preserves partial data so a later installation can resume.

Dependency installation also runs in its own process group. Pressing **Hentikan Instalasi** terminates the pip child process and its descendants rather than merely closing the GUI. Pip wheel cache and already downloaded files remain under `dependencies` for repair or resume.

No system Python or manual terminal dependency installation is required.
