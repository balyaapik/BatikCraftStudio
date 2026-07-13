from __future__ import annotations

from pathlib import Path

import pytest

from batikcraft_studio.domain import Project
from batikcraft_studio.persistence import ProjectArchive


def test_save_reopens_temporary_archive_writable_before_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_modes: list[str] = []
    original_open = Path.open

    def recording_open(
        path: Path,
        mode: str = "r",
        *args: object,
        **kwargs: object,
    ):
        observed_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)

    destination = tmp_path / "windows-fsync.batikcraft"
    ProjectArchive.save(destination, Project.create("Windows", "Creator"))

    assert destination.exists()
    assert "r+b" in observed_modes
