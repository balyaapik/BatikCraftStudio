from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from batikcraft_studio.ai.runtime_model_installer import RuntimeModelInstallError
from batikcraft_studio.ai.sdxl_runtime_integrity import (
    inspect_batikbrew_runtime,
    validate_batikbrew_runtime_strict,
)
from batikcraft_studio.ui import dependency_integrity_patch


_COMPONENTS = {
    "scheduler": ["diffusers", "EulerDiscreteScheduler"],
    "text_encoder": ["transformers", "CLIPTextModel"],
    "text_encoder_2": ["transformers", "CLIPTextModelWithProjection"],
    "tokenizer": ["transformers", "CLIPTokenizer"],
    "tokenizer_2": ["transformers", "CLIPTokenizer"],
    "unet": ["diffusers", "UNet2DConditionModel"],
    "vae": ["diffusers", "AutoencoderKL"],
}


def _complete_runtime(base: Path) -> None:
    base.mkdir(parents=True)
    (base / "model_index.json").write_text(
        json.dumps({"_class_name": "StableDiffusionXLPipeline", **_COMPONENTS}),
        encoding="utf-8",
    )

    scheduler = base / "scheduler"
    scheduler.mkdir()
    (scheduler / "scheduler_config.json").write_text("{}", encoding="utf-8")

    for name in ("tokenizer", "tokenizer_2"):
        folder = base / name
        folder.mkdir()
        (folder / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        (folder / "vocab.json").write_text("{}", encoding="utf-8")
        (folder / "merges.txt").write_text("#version: 0.2\n", encoding="utf-8")

    for name in ("text_encoder", "text_encoder_2", "unet", "vae"):
        folder = base / name
        folder.mkdir()
        (folder / "config.json").write_text("{}", encoding="utf-8")
        (folder / "model.safetensors").write_bytes(b"test")


def test_complete_sdxl_runtime_passes_component_level_validation(tmp_path: Path) -> None:
    base = tmp_path / "sdxl"
    _complete_runtime(base)

    assert inspect_batikbrew_runtime(base) == ()
    validate_batikbrew_runtime_strict(SimpleNamespace(base_model=base))


def test_existing_folders_are_not_enough_when_second_tokenizer_is_inactive(
    tmp_path: Path,
) -> None:
    base = tmp_path / "sdxl"
    _complete_runtime(base)
    payload = json.loads((base / "model_index.json").read_text(encoding="utf-8"))
    payload["tokenizer_2"] = [None, None]
    (base / "model_index.json").write_text(json.dumps(payload), encoding="utf-8")
    (base / "tokenizer_2" / "merges.txt").unlink()

    issues = inspect_batikbrew_runtime(base)

    assert "model_index.json tidak mengaktifkan tokenizer_2" in issues
    assert any("vocabulary tokenizer_2 tidak lengkap" in issue for issue in issues)
    with pytest.raises(RuntimeModelInstallError, match="tokenizer_2"):
        validate_batikbrew_runtime_strict(SimpleNamespace(base_model=base))


def test_missing_text_encoder_configuration_requires_repair(tmp_path: Path) -> None:
    base = tmp_path / "sdxl"
    _complete_runtime(base)
    (base / "text_encoder_2" / "config.json").unlink()

    issues = inspect_batikbrew_runtime(base)

    assert "text_encoder_2/config.json tidak tersedia" in issues


def test_dependency_window_reports_repair_instead_of_all_installed() -> None:
    source = inspect.getsource(dependency_integrity_patch)

    assert "PERLU REPARASI" in source
    assert "Periksa & Reparasi Semua AI + BatikBrew SDXL" in source
    assert "inspect_batikbrew_runtime" in source
