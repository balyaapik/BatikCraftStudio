from __future__ import annotations

import ast
import base64
import hashlib
import json
import zlib
from pathlib import Path


def _assignment(source: str, name: str) -> object:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Assignment {name!r} tidak ditemukan.")


def test_kaggle_notebook_embeds_repo_independent_pipeline() -> None:
    notebook_path = (
        Path(__file__).parents[1]
        / "notebooks"
        / "kaggle_batik_asset_pack_builder.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    combined = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    bootstrap = "".join(
        next(
            cell["source"]
            for cell in notebook["cells"]
            if cell.get("id") == "standalone-bootstrap"
        )
    )

    assert "Repository BatikCraftStudio belum tersedia" not in combined
    assert "git clone" not in combined
    assert "repo_candidates" not in combined
    assert "EMBEDDED_PIPELINE_B64" in bootstrap

    expected_sha = _assignment(bootstrap, "EMBEDDED_PIPELINE_SHA256")
    payload = _assignment(bootstrap, "EMBEDDED_PIPELINE_B64")
    decoded = zlib.decompress(base64.b64decode(payload))

    assert hashlib.sha256(decoded).hexdigest() == expected_sha
    assert b"batikcraft_studio" not in decoded
    assert b"def extract_dataset" in decoded
    assert b"def build_curated_pack" in decoded
    assert b"def validate_asset_pack" in decoded
    compile(decoded, "embedded_kaggle_asset_pipeline.py", "exec")
