"""Program perbaikan paket LoRA: hasilnya harus diterima aplikasi."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from batikcraft_studio.ai.model_pack import _parse_manifest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_batikmodel.py"


def _fake_lora(path: Path, *, sdxl: bool = True) -> None:
    shape = [2048, 32] if sdxl else [768, 32]
    key = "lora_unet_attn.weight" if sdxl else "lora_te_text_model.weight"
    header = json.dumps({key: {"shape": shape, "dtype": "F16"}, "__metadata__": {}}).encode()
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"\0" * 8192)


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_valid(package: Path) -> object:
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert "model/pytorch_lora_weights.safetensors" in archive.namelist()
    parsed, files = _parse_manifest(manifest)
    assert files[0]["role"] == "lora"
    return parsed


def test_repairs_a_bare_safetensors_file(tmp_path) -> None:
    weights = tmp_path / "pytorch_lora_weights.safetensors"
    _fake_lora(weights)
    output = tmp_path / "hasil.batikmodel"

    _run(str(weights), "-o", str(output))

    parsed = _assert_valid(output)
    assert parsed.base_model_family == "sdxl"  # terdeteksi dari dimensi 2048


def test_repairs_kaggle_download_all_zip(tmp_path) -> None:
    """'Download All' menghasilkan .zip berisi bobot + manifest cacat."""

    weights = tmp_path / "w.safetensors"
    _fake_lora(weights)
    broken = {"format": "batikcraft-model-pack", "schema_version": "1.0",
              "model": {"id": "x", "name": "X", "base_model_family": "sdxl"}}
    archive_path = tmp_path / "output.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(weights, "pytorch_lora_weights.safetensors")
        archive.writestr("manifest.json", json.dumps(broken))
        archive.writestr("preview.png", b"PNG")

    output = tmp_path / "hasil.batikmodel"
    _run(str(archive_path), "-o", str(output), "--name", "Uji", "--trigger", "bcr_batikstyle")

    parsed = _assert_valid(output)
    assert parsed.trigger_words == ("bcr_batikstyle",)
    assert parsed.name == "Uji"


def test_detects_sd15_lora_and_uses_512(tmp_path) -> None:
    weights = tmp_path / "w.safetensors"
    _fake_lora(weights, sdxl=False)
    output = tmp_path / "hasil.batikmodel"

    _run(str(weights), "-o", str(output))

    parsed = _assert_valid(output)
    assert parsed.base_model_family == "sd15"
    assert parsed.resolution == 512


def test_overrides_win_over_detection(tmp_path) -> None:
    weights = tmp_path / "w.safetensors"
    _fake_lora(weights, sdxl=False)
    output = tmp_path / "hasil.batikmodel"

    _run(str(weights), "-o", str(output), "--family", "sdxl", "--resolution", "768",
         "--id", "custom-id", "--author", "Balya")

    parsed = _assert_valid(output)
    assert parsed.base_model_family == "sdxl"
    assert parsed.resolution == 768
    assert parsed.model_id == "custom-id"
    assert parsed.author == "Balya"


def test_rejects_input_without_weights(tmp_path) -> None:
    empty = tmp_path / "kosong.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("catatan.txt", "tidak ada bobot")

    with pytest.raises(subprocess.CalledProcessError):
        _run(str(empty), "-o", str(tmp_path / "hasil.batikmodel"))
