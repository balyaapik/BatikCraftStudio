from __future__ import annotations

from pathlib import Path

from batikcraft_studio.runtime_model_process import (
    RUNTIME_INSTALL_FLAG,
    runtime_model_install_command,
)


def test_frozen_runtime_model_command_reuses_application_executable(tmp_path: Path) -> None:
    executable = tmp_path / "BatikCraftStudio.exe"
    command = runtime_model_install_command(
        "sdxl",
        root=tmp_path / "runtime",
        event_file=tmp_path / "progress.jsonl",
        executable=executable,
        frozen=True,
    )

    assert command[0] == str(executable)
    assert command[1] == RUNTIME_INSTALL_FLAG
    assert "--family" in command
    assert "sdxl" in command
    assert "--event-file" in command


def test_frozen_entry_checks_runtime_process_before_gui() -> None:
    source = Path("packaging/desktop_entry.py").read_text(encoding="utf-8")
    assert "maybe_run_runtime_model_installer" in source
    assert source.index("maybe_run_runtime_model_installer") < source.index(
        "from batikcraft_studio.__main__ import main"
    )
