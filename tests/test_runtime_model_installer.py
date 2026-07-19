from __future__ import annotations

import threading
from pathlib import Path

import pytest

from batikcraft_studio.ai import runtime_model_installer
from batikcraft_studio.ai.runtime_model_installer import (
    BASE_MODEL_REPO_ID,
    CONTROLNET_REPO_ID,
    RuntimeModelInstallCancelled,
    RuntimeModelInstallProgress,
    find_installed_runtime_models,
    install_default_runtime_models,
    runtime_model_paths,
)


def _write_base_model(destination: Path) -> None:
    (destination / "model_index.json").write_text("{}", encoding="utf-8")
    for folder_name in ("scheduler", "text_encoder", "tokenizer", "unet", "vae"):
        folder = destination / folder_name
        folder.mkdir(parents=True, exist_ok=True)
    for folder_name in ("text_encoder", "unet", "vae"):
        (destination / folder_name / "model.safetensors").write_bytes(b"weights")


def _write_controlnet(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "config.json").write_text("{}", encoding="utf-8")
    (destination / "diffusion_pytorch_model.safetensors").write_bytes(b"weights")


def test_installer_downloads_and_discovers_managed_runtime(tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []
    progress: list[RuntimeModelInstallProgress] = []

    def fake_snapshot_download(**kwargs: object) -> str:
        repo_id = str(kwargs["repo_id"])
        destination = Path(str(kwargs["local_dir"]))
        calls.append((repo_id, destination))
        if repo_id == BASE_MODEL_REPO_ID:
            _write_base_model(destination)
        elif repo_id == CONTROLNET_REPO_ID:
            _write_controlnet(destination)
        else:
            raise AssertionError(f"Repo tidak terduga: {repo_id}")
        return str(destination)

    paths = install_default_runtime_models(
        tmp_path,
        progress=progress.append,
        snapshot_download_func=fake_snapshot_download,
    )

    assert paths == runtime_model_paths(tmp_path)
    assert [repo_id for repo_id, _ in calls] == [
        BASE_MODEL_REPO_ID,
        CONTROLNET_REPO_ID,
    ]
    assert find_installed_runtime_models(tmp_path) == paths
    assert progress[-1].stage == "complete"
    assert progress[-1].completed == progress[-1].total


def test_installer_reuses_complete_runtime_without_network(tmp_path: Path) -> None:
    paths = runtime_model_paths(tmp_path)
    paths.base_model.mkdir(parents=True)
    _write_base_model(paths.base_model)
    _write_controlnet(paths.controlnet)

    def unexpected_download(**kwargs: object) -> str:
        raise AssertionError(f"Tidak boleh mengunduh ulang: {kwargs}")

    installed = install_default_runtime_models(
        tmp_path,
        snapshot_download_func=unexpected_download,
    )

    assert installed == paths


def test_cancellation_preserves_completed_base_download(tmp_path: Path) -> None:
    cancel_event = threading.Event()
    downloaded: list[str] = []

    def fake_snapshot_download(**kwargs: object) -> str:
        repo_id = str(kwargs["repo_id"])
        destination = Path(str(kwargs["local_dir"]))
        downloaded.append(repo_id)
        if repo_id == BASE_MODEL_REPO_ID:
            _write_base_model(destination)
            cancel_event.set()
        else:
            _write_controlnet(destination)
        return str(destination)

    with pytest.raises(RuntimeModelInstallCancelled):
        install_default_runtime_models(
            tmp_path,
            cancel_event=cancel_event,
            snapshot_download_func=fake_snapshot_download,
        )

    paths = runtime_model_paths(tmp_path)
    assert downloaded == [BASE_MODEL_REPO_ID]
    assert (paths.base_model / "model_index.json").is_file()
    assert not paths.controlnet.exists()


def test_download_progress_exposes_real_byte_percentage() -> None:
    event = RuntimeModelInstallProgress(
        stage="sdxl",
        message="Mengunduh SDXL",
        completed=1,
        total=3,
        downloaded_bytes=3_500_000_000,
        total_bytes=7_000_000_000,
        current_file="unet/model.safetensors",
    )

    assert event.download_percent == 50.0
    assert event.current_file == "unet/model.safetensors"


def test_tqdm_tracker_stops_active_download_when_cancelled() -> None:
    events: list[RuntimeModelInstallProgress] = []
    cancel_event = threading.Event()
    tracker = runtime_model_installer._SnapshotProgressTracker(
        progress=events.append,
        cancel_event=cancel_event,
        stage="sdxl",
        message="Mengunduh SDXL",
        completed=1,
        stage_total=3,
        total_bytes=100,
    )
    progress_type = tracker.tqdm_class("unet/model.safetensors")
    bar = progress_type(total=100)
    bar.update(25)
    tracker._emit(force=True)

    assert events[-1].downloaded_bytes == 25
    assert events[-1].total_bytes == 100
    assert events[-1].download_percent == 25.0

    cancel_event.set()
    with pytest.raises(RuntimeModelInstallCancelled):
        bar.update(1)


def test_repository_weight_files_are_deduplicated() -> None:
    from batikcraft_studio.ai.runtime_model_installer import (
        _dedupe_weight_files,
        _RepositoryFile,
    )

    files = [
        _RepositoryFile("model_index.json", 100),
        _RepositoryFile("unet/config.json", 10),
        _RepositoryFile("unet/diffusion_pytorch_model.bin", 3_400),
        _RepositoryFile("unet/diffusion_pytorch_model.safetensors", 3_400),
        _RepositoryFile("unet/diffusion_pytorch_model.fp16.bin", 1_700),
        _RepositoryFile("unet/diffusion_pytorch_model.fp16.safetensors", 1_700),
        _RepositoryFile("unet/diffusion_pytorch_model.non_ema.safetensors", 3_400),
        _RepositoryFile("text_encoder/model.safetensors", 490),
        _RepositoryFile("text_encoder/pytorch_model.bin", 490),
        _RepositoryFile("vae/diffusion_pytorch_model.fp16.safetensors", 160),
    ]

    result = {item.name for item in _dedupe_weight_files(files)}

    assert result == {
        "model_index.json",
        "unet/config.json",
        # satu format per bobot: safetensors fp32 menang atas duplikatnya
        "unet/diffusion_pytorch_model.safetensors",
        "text_encoder/model.safetensors",
        # hanya fp16 yang tersedia -> tetap diunduh
        "vae/diffusion_pytorch_model.fp16.safetensors",
    }
