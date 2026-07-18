from __future__ import annotations

import inspect
from pathlib import Path

from batikcraft_studio import dependency_bootstrap
from batikcraft_studio.ai import runtime_model_installer
from batikcraft_studio.ui import ai_runtime_model_install_dialog


def test_runtime_models_are_stored_below_managed_dependencies(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        dependency_bootstrap.DEPENDENCIES_DIR_ENV,
        str(tmp_path / "dependencies"),
    )

    assert runtime_model_installer.default_runtime_model_root() == (
        tmp_path / "dependencies" / "models" / "runtime"
    )


def test_runtime_dialog_uses_byte_percentage_instead_of_spinner_when_known() -> None:
    source = inspect.getsource(
        ai_runtime_model_install_dialog.RuntimeModelInstallDialog._show_progress
    )

    assert "event.total_bytes > 0" in source
    assert "event.download_percent" in source
    assert "event.downloaded_bytes" in source
    assert "_format_bytes" in source


def test_runtime_dialog_force_stops_child_process_and_becomes_closable() -> None:
    cancel_source = inspect.getsource(
        ai_runtime_model_install_dialog.RuntimeModelInstallDialog._cancel_or_close
    )
    terminate_source = inspect.getsource(
        ai_runtime_model_install_dialog.RuntimeModelInstallDialog._terminate_process_tree
    )
    finish_source = inspect.getsource(
        ai_runtime_model_install_dialog.RuntimeModelInstallDialog._finish
    )

    assert "_terminate_process_tree" in cancel_source
    assert "cancelled=True" in cancel_source
    assert '"taskkill"' in terminate_source
    assert '"/T"' in terminate_source
    assert '"/F"' in terminate_source
    assert 'text="Tutup"' in finish_source or 'else "Tutup"' in finish_source
