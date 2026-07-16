from __future__ import annotations

from pathlib import Path

from batikcraft_studio.ai.runtime_model_installer import (
    SDXL_BASE_MODEL_REPO_ID,
    RuntimeModelInstallProgress,
    find_installed_batikbrew_runtime,
    install_batikbrew_runtime,
    validate_batikbrew_runtime,
)


def _fake_sdxl_download(**kwargs: object) -> str:
    assert kwargs["repo_id"] == SDXL_BASE_MODEL_REPO_ID
    root = Path(str(kwargs["local_dir"]))
    root.mkdir(parents=True, exist_ok=True)
    (root / "model_index.json").write_text("{}", encoding="utf-8")
    for name in (
        "scheduler",
        "text_encoder",
        "text_encoder_2",
        "tokenizer",
        "tokenizer_2",
        "unet",
        "vae",
    ):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        if name in {"text_encoder", "text_encoder_2", "unet", "vae"}:
            (folder / "diffusion_pytorch_model.safetensors").write_bytes(b"weights")
    return str(root)


def test_install_and_find_managed_batikbrew_runtime(tmp_path) -> None:
    progress: list[RuntimeModelInstallProgress] = []

    paths = install_batikbrew_runtime(
        tmp_path,
        progress=progress.append,
        snapshot_download_func=_fake_sdxl_download,
    )

    validate_batikbrew_runtime(paths)
    assert paths.base_model.name == "stable-diffusion-xl-base-1.0"
    assert find_installed_batikbrew_runtime(tmp_path) == paths
    assert progress
    assert progress[-1].stage == "complete"
    assert progress[-1].completed == 3
    assert progress[-1].total == 3
