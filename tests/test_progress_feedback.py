from __future__ import annotations

import queue
import threading

from batikcraft_studio.progress_context_tool_app import ContextToolApplication
from batikcraft_studio.ui.context_tool_editor_hotfix_v13 import (
    ContextToolEditorWorkspaceView,
)
from batikcraft_studio.ui.offline_ai_dialogs_progress import (
    ProgressDatasetStudioWindow,
    ProgressOfflineModelManagerWindow,
)
from batikcraft_studio.ui.progress_dialog import (
    ProgressDialog,
    ProgressReporter,
    ProgressUpdate,
)
from batikcraft_studio.ui.progress_main_window import ProgressViewportMainWindow


def test_progress_update_reports_clamped_percentage() -> None:
    assert ProgressUpdate("half", 5, 10).percent == 50
    assert ProgressUpdate("over", 12, 10).percent == 100
    assert ProgressUpdate("under", -1, 10).percent == 0
    assert ProgressUpdate("unknown").percent is None


def test_progress_reporter_is_worker_thread_safe() -> None:
    events: queue.Queue[object] = queue.Queue()
    cancelled = threading.Event()
    reporter = ProgressReporter(events, cancelled)

    reporter.update("Rendering", 2, 4, detail="Canvas")
    update = events.get_nowait()

    assert isinstance(update, ProgressUpdate)
    assert update.message == "Rendering"
    assert update.percent == 50
    assert update.detail == "Canvas"
    assert reporter.cancelled is False
    cancelled.set()
    assert reporter.cancelled is True


def test_progress_dialog_close_policy_changes_after_finish() -> None:
    class DialogState:
        def __init__(self, *, finished: bool, cancellable: bool) -> None:
            self._finished = finished
            self._cancellable = cancellable
            self.closed = False
            self.cancelled = False
            self.rang = False

        def close(self) -> None:
            self.closed = True

        def cancel(self) -> None:
            self.cancelled = True

        def bell(self) -> None:
            self.rang = True

    active_locked = DialogState(finished=False, cancellable=False)
    ProgressDialog._request_window_close(active_locked)  # type: ignore[arg-type]
    assert active_locked.rang is True
    assert active_locked.closed is False

    active_cancellable = DialogState(finished=False, cancellable=True)
    ProgressDialog._request_window_close(active_cancellable)  # type: ignore[arg-type]
    assert active_cancellable.cancelled is True

    failed_or_finished = DialogState(finished=True, cancellable=False)
    ProgressDialog._request_window_close(failed_or_finished)  # type: ignore[arg-type]
    assert failed_or_finished.closed is True


def test_progress_aware_entry_points_are_active() -> None:
    assert ContextToolApplication.__module__.endswith("progress_context_tool_app")
    assert ContextToolEditorWorkspaceView.__module__.endswith(
        "context_tool_editor_hotfix_v13"
    )
    assert issubclass(ProgressViewportMainWindow, object)


def test_remaining_long_workflows_use_progress_aware_dialogs() -> None:
    assert ProgressDatasetStudioWindow.__module__.endswith(
        "offline_ai_dialogs_progress"
    )
    assert ProgressOfflineModelManagerWindow.__module__.endswith(
        "offline_ai_dialogs_progress"
    )
    assert "save_project_as" in ContextToolApplication.__dict__
    assert "open_project" in ContextToolApplication.__dict__
    assert "install_asset_pack_dialog" in ContextToolEditorWorkspaceView.__dict__
