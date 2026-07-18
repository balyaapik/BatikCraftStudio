from __future__ import annotations

from pathlib import Path
from typing import Any

from batikcraft_studio.ai import runtime_model_installer, sdxl_repository_repair


def test_online_repair_bypasses_local_ready_shortcuts(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    observed: dict[str, object] = {}
    sentinel = object()

    monkeypatch.setattr(sdxl_repository_repair, "_INSTALLED", False)
    monkeypatch.setattr(sdxl_repository_repair, "model_online", lambda: True)
    monkeypatch.setattr(
        runtime_model_installer,
        "find_installed_batikbrew_runtime",
        lambda _root=None: "locally-ready",
    )
    monkeypatch.setattr(runtime_model_installer, "_sdxl_model_is_complete", lambda _path: True)

    def fake_original(
        root: str | Path | None = None,
        *,
        progress: Any = None,
        cancel_event: Any = None,
        snapshot_download_func: Any = None,
    ) -> object:
        observed["find"] = runtime_model_installer.find_installed_batikbrew_runtime(root)
        observed["complete"] = runtime_model_installer._sdxl_model_is_complete(tmp_path)
        observed["root"] = root
        return sentinel

    monkeypatch.setattr(runtime_model_installer, "install_batikbrew_runtime", fake_original)

    sdxl_repository_repair.install_sdxl_repository_repair()
    result = runtime_model_installer.install_batikbrew_runtime(tmp_path)

    assert result is sentinel
    assert observed == {"find": None, "complete": False, "root": tmp_path}


def test_offline_repair_keeps_local_shortcuts(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    observed: dict[str, object] = {}

    monkeypatch.setattr(sdxl_repository_repair, "_INSTALLED", False)
    monkeypatch.setattr(sdxl_repository_repair, "model_online", lambda: False)
    monkeypatch.setattr(
        runtime_model_installer,
        "find_installed_batikbrew_runtime",
        lambda _root=None: "locally-ready",
    )
    monkeypatch.setattr(runtime_model_installer, "_sdxl_model_is_complete", lambda _path: True)

    def fake_original(
        root: str | Path | None = None,
        *,
        progress: Any = None,
        cancel_event: Any = None,
        snapshot_download_func: Any = None,
    ) -> object:
        observed["find"] = runtime_model_installer.find_installed_batikbrew_runtime(root)
        observed["complete"] = runtime_model_installer._sdxl_model_is_complete(tmp_path)
        return object()

    monkeypatch.setattr(runtime_model_installer, "install_batikbrew_runtime", fake_original)

    sdxl_repository_repair.install_sdxl_repository_repair()
    runtime_model_installer.install_batikbrew_runtime(tmp_path)

    assert observed == {"find": "locally-ready", "complete": True}
