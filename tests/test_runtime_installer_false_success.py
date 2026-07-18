from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from batikcraft_studio import dependency_bootstrap, runtime_compatibility
from batikcraft_studio.ai import model_connectivity, sdxl_runtime_integrity
from batikcraft_studio.runtime_model_process import run_runtime_model_installer
from batikcraft_studio.ui import runtime_installer_completion_guard as completion_guard
from batikcraft_studio.ui.ai_runtime_model_install_dialog import RuntimeModelInstallDialog


def test_child_worker_installs_integrity_before_running_real_installer() -> None:
    source = inspect.getsource(run_runtime_model_installer)

    assert source.index("apply_saved_model_connectivity()") < source.index(
        "installed = installer"
    )
    assert source.index("install_sdxl_runtime_integrity()") < source.index(
        "installed = installer"
    )
    assert source.index("validate_batikbrew_runtime_strict(installed)") < source.index(
        '_write_event(stream, "complete"'
    )


def test_child_worker_refuses_complete_event_for_incomplete_sdxl(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(dependency_bootstrap, "activate_managed_ai_packages", lambda: None)
    monkeypatch.setattr(runtime_compatibility, "install_runtime_compatibility", lambda: None)
    monkeypatch.setattr(model_connectivity, "apply_saved_model_connectivity", lambda: None)
    monkeypatch.setattr(sdxl_runtime_integrity, "install_sdxl_runtime_integrity", lambda: None)

    base = tmp_path / "stable-diffusion-xl-base-1.0"
    base.mkdir()
    (base / "model_index.json").write_text(
        json.dumps(
            {
                "_class_name": "StableDiffusionXLPipeline",
                "tokenizer_2": [None, None],
                "text_encoder_2": [None, None],
            }
        ),
        encoding="utf-8",
    )

    def incomplete_installer(_root: Path, *, progress: object) -> object:
        del progress
        return SimpleNamespace(base_model=base)

    event_file = tmp_path / "events.jsonl"
    code = run_runtime_model_installer(
        "sdxl",
        root=tmp_path,
        event_file=event_file,
        installer_override=incomplete_installer,
    )

    events = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert code == 1
    assert not any(event.get("kind") == "complete" for event in events)
    error = next(event for event in events if event.get("kind") == "error")
    assert "tokenizer_2" in error["message"]
    assert "text_encoder_2" in error["message"]


class _Detail:
    def __init__(self) -> None:
        self.text = ""

    def configure(self, *, text: str) -> None:
        self.text = text


class _FakeDialog:
    family = "sdxl"

    def __init__(self, install_root: Path) -> None:
        self.install_root = install_root
        self.result: object | None = object()
        self.detail = _Detail()
        self.finished: tuple[str, bool] | None = None

    def _finish(self, message: str, *, success: bool) -> None:
        self.finished = (message, success)


def test_dialog_does_not_turn_incomplete_runtime_into_100_percent(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    original_calls: list[object] = []

    def original_handler(_dialog: object, event: object) -> None:
        original_calls.append(event)

    monkeypatch.setattr(completion_guard, "_INSTALLED", False)
    monkeypatch.delattr(
        RuntimeModelInstallDialog,
        "_batikcraft_completion_guard",
        raising=False,
    )
    monkeypatch.setattr(RuntimeModelInstallDialog, "_handle_event", original_handler)
    completion_guard.install_runtime_installer_completion_guard()

    fake = _FakeDialog(tmp_path)
    RuntimeModelInstallDialog._handle_event(fake, ("complete", "sdxl"))

    assert original_calls == []
    assert fake.result is None
    assert fake.finished is not None
    assert fake.finished[1] is False
    assert "Instalasi belum lengkap" in fake.finished[0]
    assert "tokenizer_2" in fake.detail.text
