"""Build BatikCraft Studio installers using the current platform policy."""

from __future__ import annotations

from pathlib import Path

import build_desktop
from windows_installer_policy import build_inno_setup_script

_ORIGINAL_BUILD = build_desktop.build


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


def _versioned_artifact_path(artifact: Path, *, version: str) -> Path:
    """Return the public installer path with an explicit release version."""

    prefix = f"{build_desktop.APP_NAME}-"
    versioned_prefix = f"{build_desktop.APP_NAME}-v{version}-"
    if artifact.name.startswith(versioned_prefix):
        return artifact
    if not artifact.name.startswith(prefix):
        raise RuntimeError(f"Unexpected installer filename: {artifact.name}")
    return artifact.with_name(versioned_prefix + artifact.name[len(prefix) :])


def _build_with_versioned_artifact() -> Path:
    artifact = _ORIGINAL_BUILD()
    versioned = _versioned_artifact_path(
        artifact,
        version=build_desktop._project_version(),
    )
    if versioned == artifact:
        return artifact
    if versioned.exists():
        versioned.unlink()
    artifact.replace(versioned)
    return versioned


def main() -> int:
    build_desktop._windows_installer_script = _windows_installer_script
    build_desktop.build = _build_with_versioned_artifact
    return build_desktop.main()


if __name__ == "__main__":
    raise SystemExit(main())
