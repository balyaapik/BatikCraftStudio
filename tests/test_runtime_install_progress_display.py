from __future__ import annotations

from batikcraft_studio.ui.ai_runtime_model_install_dialog import RuntimeModelInstallDialog


def test_runtime_installer_exposes_percentage_feedback() -> None:
    names = RuntimeModelInstallDialog._handle_event.__code__.co_names
    assert "percent" in names
    assert "completed" in names
    assert "total" in names
