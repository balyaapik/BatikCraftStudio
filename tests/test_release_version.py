from __future__ import annotations

import tomllib
from pathlib import Path

from batikcraft_studio.config import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_application_and_package_versions_are_0_5_7() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project_version = str(tomllib.load(stream)["project"]["version"])

    assert APP_VERSION == "0.9.13"
    assert project_version == APP_VERSION


def test_desktop_workflow_rejects_mismatched_release_tags() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "Verify release tag matches application version" in workflow
    assert "release_tag != expected_tag" in workflow
