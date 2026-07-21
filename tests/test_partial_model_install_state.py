"""Regression tests for partial model downloads and false success state."""

from __future__ import annotations

import queue

import pytest

from batikcraft_studio.ai import sdxl_runtime_integrity
from batikcraft_studio.ui import dependency_catalog as catalog
from batikcraft_studio.ui import dependency_integrity_patch as integrity_patch
from batikcraft_studio.ui.dependency_center import DependencyCenterWindow


def _sdxl_item() -> catalog.DependencyItem:
    return next(item for item in catalog.CATALOG if item.key == "sdxl")


def _prepare_partial_sdxl(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    folder = runtime_root / "stable-diffusion-xl-base-1.0"
    folder.mkdir(parents=True)
    (folder / "model_index.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(catalog, "managed_runtime_root", lambda: runtime_root)
    monkeypatch.setattr(
        sdxl_runtime_integrity,
        "inspect_batikbrew_runtime",
        lambda _folder: ["Bobot UNet belum lengkap"],
    )
    integrity_patch.install_dependency_integrity_patch()
    return folder


def test_partial_model_is_not_reported_as_installed(monkeypatch, tmp_path) -> None:
    _prepare_partial_sdxl(monkeypatch, tmp_path)
    item = _sdxl_item()

    assert catalog.is_installed(item) is False
    status, detail = catalog.integrity_status(item)
    assert status == "PERLU REPARASI"
    assert "parsial" in detail.casefold()
    assert catalog.installed_fraction(item) < 1.0


def test_validated_model_is_the_only_installed_state(monkeypatch, tmp_path) -> None:
    _prepare_partial_sdxl(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sdxl_runtime_integrity,
        "inspect_batikbrew_runtime",
        lambda _folder: [],
    )
    item = _sdxl_item()

    assert catalog.is_installed(item) is True
    assert catalog.integrity_status(item) == ("Terpasang", "")
    assert catalog.installed_fraction(item) == 1.0


def test_model_install_rechecks_disk_before_download(monkeypatch, tmp_path) -> None:
    _prepare_partial_sdxl(monkeypatch, tmp_path)
    monkeypatch.setattr(catalog, "free_disk_bytes", lambda: 1)
    window = DependencyCenterWindow.__new__(DependencyCenterWindow)

    with pytest.raises(RuntimeError, match="Ruang disk tidak cukup"):
        window._install_model(_sdxl_item())


def test_failed_model_batch_does_not_finish_as_success(monkeypatch, tmp_path) -> None:
    _prepare_partial_sdxl(monkeypatch, tmp_path)
    window = DependencyCenterWindow.__new__(DependencyCenterWindow)
    window._messages = queue.Queue()
    window._install_model = lambda _item: (_ for _ in ()).throw(
        RuntimeError("disk penuh")
    )

    window._install_worker([_sdxl_item()])
    messages = list(window._messages.queue)
    done_payload = next(payload for kind, payload in messages if kind == "done")
    progress_values = [payload for kind, payload in messages if kind == "progress"]

    assert done_payload["succeeded"] == 0
    assert done_payload["failures"] == [_sdxl_item().name]
    assert progress_values
    assert all(float(value[1]) < 1.0 for value in progress_values)
