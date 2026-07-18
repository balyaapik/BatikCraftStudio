"""Build BatikCraft Studio installers using the current platform policy."""

from __future__ import annotations

from pathlib import Path

import build_desktop
from windows_installer_policy import build_inno_setup_script


def _windows_installer_script(
    *,
    source_executable: Path,
    output_directory: Path,
    icon_path: Path,
    version: str,
) -> str:
    return build_inno_setup_script(
        app_name=build_desktop.APP_NAME,
        display_name=build_desktop.DISPLAY_NAME,
        app_id=build_desktop.WINDOWS_APP_ID,
        architecture=build_desktop._architecture(),
        source_executable=source_executable,
        output_directory=output_directory,
        icon_path=icon_path,
        version=version,
    )


def main() -> int:
    build_desktop._windows_installer_script = _windows_installer_script
    return build_desktop.main()


if __name__ == "__main__":
    raise SystemExit(main())
