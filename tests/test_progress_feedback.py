from __future__ import annotations

from pathlib import Path

import pytest
from batikcraft_studio.progress import (
    OperationCancelledError,
    ProgressUpdate,
    ensure_not_cancelled,
    format_byte_progress,
)


ROOT = Path(__file__).resolve().parents[1]


def test_progress_update_supports_determinate_and_indeterminate_modes() -> None:
    determinate = ProgressUpdate("download", "Mengunduh", 25, 100)
    indeterminate = ProgressUpdate("model", "Memuat model")
    clamped = ProgressUpdate("write", "Menulis", 150, 100)

    assert determinate.determinate is True
    assert determinate.fraction == pytest.approx(0.25)
    assert determinate.percent == 25
    assert indeterminate.determinate is False
    assert indeterminate.percent is None
    assert clamped.completed == 100
    assert clamped.percent == 100


def test_progress_byte_format_and_cooperative_cancellation() -> None:
    assert format_byte_progress(1024, 4096) == "1.0 KB / 4.0 KB"
    ensure_not_cancelled(lambda: False)
    with pytest.raises(OperationCancelledError, match="dibatalkan"):
        ensure_not_cancelled(lambda: True)


def test_desktop_entrypoint_and_editor_use_progress_aware_layers() -> None:
    entrypoint = (ROOT / "src/batikcraft_studio/__main__.py").read_text(encoding="utf-8")
    views = (ROOT / "src/batikcraft_studio/ui/views.py").read_text(encoding="utf-8")
    editor = (
        ROOT / "src/batikcraft_studio/ui/context_tool_editor_hotfix_v12.py"
    ).read_text(encoding="utf-8")
    app = (ROOT / "src/batikcraft_studio/progress_context_tool_app.py").read_text(
        encoding="utf-8"
    )

    assert "ProgressContextToolApplication" in entrypoint
    assert "context_tool_editor_hotfix_v12" in views
    assert "Batifikasi AI — Stable Diffusion + LoRA" in editor
    assert "run_modal_progress" in editor
    assert "Ekspor Paket BatikCraft NFT" in app
    assert "Membuka Project BatikCraft" in app


def test_long_running_model_and_dataset_workflows_are_progress_wrapped() -> None:
    source = (
        ROOT / "src/batikcraft_studio/ui/offline_ai_dialogs_progress.py"
    ).read_text(encoding="utf-8")

    assert "ProgressOfflineModelManagerWindow" in source
    assert "ProgressDatasetStudioWindow" in source
    assert "checksum" in source
    assert "run_modal_progress" in source
