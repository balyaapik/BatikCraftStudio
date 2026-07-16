from __future__ import annotations

import queue
import threading

from batikcraft_studio.ui.progress_dialog import ProgressReporter, ProgressUpdate


def test_progress_reporter_emits_determinate_and_indeterminate_updates() -> None:
    events: queue.Queue[object] = queue.Queue()
    reporter = ProgressReporter(events, threading.Event())

    reporter.update("Memuat model", 2, 6, detail="Stable Diffusion + LoRA")
    reporter.update("Menjalankan inferensi", detail="24 inference steps")

    first = events.get_nowait()
    second = events.get_nowait()
    assert isinstance(first, ProgressUpdate)
    assert first.percent == 33
    assert first.detail == "Stable Diffusion + LoRA"
    assert isinstance(second, ProgressUpdate)
    assert second.determinate is False


def test_workspace_uses_progress_enabled_ai_hotfix() -> None:
    from batikcraft_studio.ui import views

    assert views.ContextToolEditorWorkspaceView.__module__.endswith(
        "context_tool_editor_hotfix_v12"
    )


def test_runtime_download_dialog_exposes_percentage_label() -> None:
    from batikcraft_studio.ui.ai_runtime_model_install_dialog import (
        RuntimeModelInstallDialog,
    )

    source = RuntimeModelInstallDialog._handle_event.__code__.co_names
    assert "percent" in source
