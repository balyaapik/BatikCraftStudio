from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path


def test_lora_notebook_is_standalone_and_embeds_compilable_pipeline() -> None:
    root = Path(__file__).parents[1]
    notebook_path = root / "notebooks" / "kaggle_train_batikcraft_lora.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    assert ".batikdataset" in source
    assert ".batikmodel" in source
    assert "BatikCraftStudio belum tersedia" not in source
    assert "git clone" not in source
    sha_match = re.search(r'PIPELINE_SHA256 = "([0-9a-f]{64})"', source)
    payload_match = re.search(
        r"PIPELINE_B64 = \(\n(?P<body>(?:\s+\"[A-Za-z0-9+/=]+\"\n)+)\)",
        source,
    )
    assert sha_match is not None
    assert payload_match is not None
    chunks = re.findall(r'"([A-Za-z0-9+/=]+)"', payload_match.group("body"))
    decoded = zlib.decompress(base64.b64decode("".join(chunks))).decode("utf-8")
    assert hashlib.sha256(decoded.encode("utf-8")).hexdigest() == sha_match.group(1)
    ast.parse(decoded)
    assert "def train_lora" in decoded
    assert "def build_batikmodel" in decoded
