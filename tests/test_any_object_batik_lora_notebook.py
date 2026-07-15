from __future__ import annotations

import ast
import json
from pathlib import Path


def test_any_object_batik_lora_notebook_is_valid_and_complete() -> None:
    root = Path(__file__).parents[1]
    path = root / "notebooks" / "kaggle_train_batik_style_any_object.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))

    assert notebook["nbformat"] == 4
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    assert "git clone" not in source
    assert "LoRA Batik untuk Objek Apa Pun" in source
    assert "object_dataset_required" in source
    assert "StableDiffusionControlNetImg2ImgPipeline" in source
    assert "pytorch_lora_weights.safetensors" in source
    assert ".batikmodel" in source
    assert "preserve exact identity" in source
    assert "mask_of" in source
    assert "outline_strength" in source

    # Dataset preparation must tolerate damaged or mislabeled image files.
    assert "ImageFile.LOAD_TRUNCATED_IMAGES=True" in source
    assert "UnidentifiedImageError" in source
    assert "probe.verify()" in source
    assert "skipped-images.json" in source
    assert "SKIP rusak/tidak valid" in source
    assert "prepared_count" in source

    for cell in notebook["cells"]:
        if cell.get("cell_type") == "code":
            ast.parse("".join(cell.get("source", [])))
