# ruff: noqa: I001

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from batikcraft_studio.ai.runtime_model_installer import RuntimeModelInstallError
from batikcraft_studio.ai import sdxl_runtime_integrity
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


def _pretend_weight_sizes_are_complete(monkeypatch: Any) -> None:
    minimums = sdxl_runtime_integrity._MINIMUM_COMPONENT_WEIGHT_BYTES

    def fake_size(path: Path) -> int:
        minimum = minimums.get(path.parent.name)
        return minimum + 1 if minimum is not None else path.stat().st_size

    monkeypatch.setattr(sdxl_runtime_integrity, "_safe_file_size", fake_size)


def test_complete_sdxl_runtime_passes_component_level_validation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    base = tmp_path / "sdxl"
    _complete_runtime(base)
    _pretend_weight_sizes_are_complete(monkeypatch)

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


def test_pointer_and_tiny_weight_files_require_repair(tmp_path: Path) -> None:
    base = tmp_path / "sdxl"
    _complete_runtime(base)
    pointer = base / "unet" / "model.safetensors"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
        encoding="utf-8",
    )

    issues = inspect_batikbrew_runtime(base)

    assert any("pointer/stub" in issue and "unet" in issue for issue in issues)
    assert any("ukuran bobot unet terlalu kecil" in issue for issue in issues)


def test_dependency_table_reports_repair_instead_of_all_installed() -> None:
    """Status integritas kini tampil sebagai kolom Status pada Pusat
    Dependensi (jendela tombol lama sudah dihapus)."""

    from batikcraft_studio.ui import dependency_catalog, dependency_center

    catalog_source = inspect.getsource(dependency_catalog)
    assert "PERLU REPARASI" in catalog_source
    assert "inspect_batikbrew_runtime" in catalog_source

    center_source = inspect.getsource(dependency_center)
    assert "integrity_status" in center_source
    assert "untuk memperbaiki" in center_source
