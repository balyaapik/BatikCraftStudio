"""Windows installer policy for machine-wide BatikCraft Studio installations."""

from __future__ import annotations

from pathlib import Path


def build_inno_setup_script(
    *,
    app_name: str,
    display_name: str,
    app_id: str,
    architecture: str,
    source_executable: Path,
    output_directory: Path,
    icon_path: Path,
    version: str,
) -> str:
    """Return an Inno Setup script that installs into Program Files.

    The application itself stays protected under Program Files. Only the
    ``dependencies`` subtree is writable by standard users because BatikCraft
    downloads AI packages and model files there after installation.
    """

    output_base = f"{app_name}-Setup-Windows-{architecture}"
    lines = [
        f'#define MyAppVersion "{version}"',
        f'#define SourceExe "{source_executable.resolve()}"',
        f'#define OutputDirectory "{output_directory.resolve()}"',
        f'#define SetupIcon "{icon_path.resolve()}"',
        "",
        "[Setup]",
        f"AppId={app_id}",
        f"AppName={display_name}",
        "AppVersion={#MyAppVersion}",
        f"AppPublisher={display_name}",
        f"DefaultDirName={{autopf}}\\{display_name}",
        f"DefaultGroupName={display_name}",
        "DisableProgramGroupPage=yes",
        "UsePreviousAppDir=no",
        "OutputDir={#OutputDirectory}",
        f"OutputBaseFilename={output_base}",
        "SetupIconFile={#SetupIcon}",
        "UninstallDisplayIcon={app}\\BatikCraftStudio.exe",
        "Compression=lzma2",
        "SolidCompression=yes",
        "WizardStyle=modern",
        "PrivilegesRequired=admin",
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
        "[Dirs]",
        'Name: "{app}\\dependencies"; Permissions: users-modify; '
        "Flags: uninsneveruninstall",
        "",
        "[Files]",
        'Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "BatikCraftStudio.exe"; '
        "Flags: ignoreversion",
        "",
        "[Icons]",
        f'Name: "{{autoprograms}}\\{display_name}"; '
        'Filename: "{app}\\BatikCraftStudio.exe"; WorkingDir: "{app}"',
        f'Name: "{{autodesktop}}\\{display_name}"; '
        'Filename: "{app}\\BatikCraftStudio.exe"; WorkingDir: "{app}"; '
        "Tasks: desktopicon",
        "",
        "[Run]",
        'Filename: "{app}\\BatikCraftStudio.exe"; '
        f'Description: "Jalankan {display_name}"; '
        "Flags: nowait postinstall skipifsilent",
        "",
    ]
    return "\n".join(lines)
