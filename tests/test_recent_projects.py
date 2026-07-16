from __future__ import annotations

import json
from pathlib import Path

from batikcraft_studio.recent_projects import RecentProjectStore


def test_recent_projects_are_mru_deduplicated_and_bounded(tmp_path: Path) -> None:
    store = RecentProjectStore(tmp_path / "recent.json", limit=3)
    paths = [tmp_path / f"project-{index}.batikcraft" for index in range(4)]
    for path in paths:
        path.write_bytes(b"project")
        store.remember(path, path.stem)

    entries = store.load()
    assert [Path(entry.path).name for entry in entries] == [
        "project-3.batikcraft",
        "project-2.batikcraft",
        "project-1.batikcraft",
    ]

    store.remember(paths[2], "Judul Baru")
    entries = store.load()
    assert [Path(entry.path).name for entry in entries] == [
        "project-2.batikcraft",
        "project-3.batikcraft",
        "project-1.batikcraft",
    ]
    assert entries[0].title == "Judul Baru"


def test_prune_missing_and_clear_write_valid_registry(tmp_path: Path) -> None:
    store = RecentProjectStore(tmp_path / "recent.json")
    existing = tmp_path / "existing.batikcraft"
    missing = tmp_path / "missing.batikcraft"
    existing.write_bytes(b"project")
    store.remember(missing, "Missing")
    store.remember(existing, "Existing")

    entries = store.prune_missing()
    assert [Path(entry.path).name for entry in entries] == ["existing.batikcraft"]

    store.clear()
    assert store.load() == ()
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload == {"entries": [], "schema_version": 1}


def test_malformed_recent_registry_degrades_to_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "recent.json"
    path.write_text("not-json", encoding="utf-8")
    store = RecentProjectStore(path)

    assert store.load() == ()
    assert store.last_error is not None
