"""Deteksi lokasi ekspor tersinkron cloud (penyebab PNG tak bisa dibuka)."""

from __future__ import annotations

import os

from batikcraft_studio.persistence.export_location import (
    is_cloud_synced_path,
    safe_default_export_dir,
)


def test_onedrive_terdeteksi():
    assert is_cloud_synced_path("C:/Users/hp/OneDrive/Downloads/a.png")


def test_dropbox_terdeteksi():
    assert is_cloud_synced_path("/home/x/Dropbox/b.png")


def test_folder_lokal_tidak_terdeteksi():
    assert not is_cloud_synced_path("C:/batiktest/a.png")
    assert not is_cloud_synced_path("/home/x/Pictures/a.png")


def test_variabel_onedrive_terdeteksi(tmp_path, monkeypatch):
    monkeypatch.setenv("OneDrive", str(tmp_path))
    sub = tmp_path / "sub"
    sub.mkdir()

    assert is_cloud_synced_path(sub / "x.png")


def test_default_export_dir_bukan_cloud(monkeypatch):
    # Tanpa OneDrive env, folder default tidak boleh terdeteksi cloud.
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(env, raising=False)
    folder = safe_default_export_dir()
    assert not is_cloud_synced_path(folder)
