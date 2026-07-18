from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from batikcraft_studio import managed_storage
from batikcraft_studio.ai.runtime_model_installer import RuntimeModelInstallProgress
from batikcraft_studio.runtime_model_process import run_runtime_model_installer
from batikcraft_studio.ui import cache_directory_guard, runtime_installer_completion_guard


def test_ensure_managed_storage_creates_every_required_directory(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    paths = tuple(tmp_path / name for name in ("dependencies", "cache", "hub", "runtime"))
    monkeypatch.setattr(managed_storage, "managed_storage_directories", lambda: paths)

    created = managed_storage.ensure_managed_storage()

    assert created == paths
    assert all(path.is_dir() for path in paths)


def test_nearest_existing_directory_never_returns_missing_path(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()

    resolved = managed_storage.nearest_existing_directory(existing / "missing" / "child")

    assert resolved == existing.resolve()
    assert resolved.is_dir()


def test_runtime_worker_rejects_incomplete_sdxl_before_complete_event(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    event_file = tmp_path / "events.jsonl"
    incomplete = tmp_path / "runtime" / "stable-diffusion-xl-base-1.0"
    incomplete.mkdir(parents=True)

    # Avoid touching the user's real managed directories during this unit test.
    import batikcraft_studio.managed_storage as storage_module

    monkeypatch.setattr(storage_module, "ensure_managed_storage", lambda: ())

    def incomplete_installer(_root: Path, *, progress: Any) -> object:
        progress(
            RuntimeModelInstallProgress(
                stage="checking",
                message="checking",
                completed=0,
                total=3,
            )
        )
        return SimpleNamespace(base_model=incomplete)

    code = run_runtime_model_installer(
        "sdxl",
        root=tmp_path / "runtime",
        event_file=event_file,
        installer_override=incomplete_installer,
    )
    events = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]

    assert code == 1
    assert any(event["kind"] == "error" for event in events)
    assert not any(event["kind"] == "complete" for event in events)


def test_main_dispatches_dependency_worker_before_desktop_imports(monkeypatch: Any) -> None:
    from batikcraft_studio import __main__ as entrypoint
    from batikcraft_studio import dependency_bootstrap, runtime_model_process

    monkeypatch.setattr(entrypoint, "_configure_logging", lambda: None)
    monkeypatch.setattr(dependency_bootstrap, "maybe_run_dependency_installer", lambda: 17)

    def runtime_must_not_run() -> int | None:
        raise AssertionError("runtime worker must not run after dependency worker matched")

    monkeypatch.setattr(
        runtime_model_process,
        "maybe_run_runtime_model_installer",
        runtime_must_not_run,
    )

    assert entrypoint.main() == 17


def test_main_dispatches_runtime_worker_before_desktop_imports(monkeypatch: Any) -> None:
    from batikcraft_studio import __main__ as entrypoint
    from batikcraft_studio import dependency_bootstrap, runtime_model_process

    monkeypatch.setattr(entrypoint, "_configure_logging", lambda: None)
    monkeypatch.setattr(dependency_bootstrap, "maybe_run_dependency_installer", lambda: None)
    monkeypatch.setattr(runtime_model_process, "maybe_run_runtime_model_installer", lambda: 23)

    assert entrypoint.main() == 23


def test_ui_guards_cover_missing_cache_and_unverified_complete_events() -> None:
    cache_source = inspect.getsource(cache_directory_guard)
    completion_source = inspect.getsource(runtime_installer_completion_guard)

    assert "nearest_existing_directory" in cache_source
    assert "ensure_managed_storage" in cache_source
    assert "_batikcraft_validated_complete_seen" in completion_source
    assert 'payload.get("validated") is True' in completion_source
    assert "Status 100% dibatalkan" in completion_source
    assert "inspect_batikbrew_runtime" in completion_source
