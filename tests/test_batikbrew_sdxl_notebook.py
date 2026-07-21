"""Notebook pelatihan LoRA SDXL untuk BatikBrew harus konsisten dengan aplikasi."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "kaggle_train_batikbrew_sdxl_style_lora.ipynb"


def _sources() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def test_notebook_code_cells_are_valid_python() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code":
            continue
        compile("".join(cell["source"]), f"cell-{index}", "exec")


def test_notebook_trains_sdxl_not_sd15() -> None:
    source = _sources()
    assert "stabilityai/stable-diffusion-xl-base-1.0" in source
    assert "StableDiffusionXLPipeline.save_lora_weights" in source
    # SDXL memerlukan dua text encoder dan add_time_ids.
    assert "text_encoder_2" in source
    assert "time_ids" in source


def test_exported_package_matches_application_format() -> None:
    """Paket harus dapat dipasang lewat 'Pasang .batikmodel…'."""

    source = _sources()
    assert '"format": "batikcraft-model-pack"' in source
    assert '"base_model_family": "sdxl"' in source
    assert '"lora_file": "model/pytorch_lora_weights.safetensors"' in source
    assert "trigger_words" in source and "recommended_weight" in source


def test_documentation_explains_family_requirement() -> None:
    doc = (ROOT / "docs" / "KAGGLE_BATIKBREW_SDXL_STYLE_LORA.md").read_text(
        encoding="utf-8"
    )
    assert "BatikBrew" in doc
    assert "sdxl" in doc
    assert "Pasang .batikmodel" in doc


def test_notebook_locks_silhouette_with_controlnet() -> None:
    """'Botol tetap botol' berasal dari ControlNet Canny + strength rendah,
    bukan dari pasangan gambar di dataset."""

    source = _sources()
    assert "controlnet-canny-sdxl-1.0" in source
    assert "StableDiffusionXLControlNetImg2ImgPipeline" in source
    assert "controlnet_conditioning_scale" in source
    assert "cv2.Canny" in source


def test_notebook_explains_absence_of_paired_dataset() -> None:
    source = _sources()
    assert "style transfer" in source.lower()
    assert "tidak ada pasangan" in source.lower()
    # Tersedia pembangun pasangan asli<->batik untuk kurasi (opsional).
    assert "pairs.json" in source
    assert "perbandingan" in source
