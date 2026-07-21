from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from batikcraft_studio.ai import runtime_model_installer
from batikcraft_studio.ai.runtime_family_resolution import (
    install_runtime_family_resolution,
)
from batikcraft_studio.ai.torch_runtime_integrity import (
    clear_failed_torch_imports,
    inspect_torch_runtime,
    validate_torch_variant,
)


def _write_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_fake_torch(root: Path, *, include_amp: bool = True) -> None:
    files = {
        "torch/__init__.py": b"from torch import amp as amp\n",
        "torch/version.py": b"__version__ = '2.5.1+cu121'\ncuda = '12.1'\n",
        "torch/cuda/__init__.py": b"available = True\n",
        "torch/_C.so": b"native-extension",
    }
    if include_amp:
        files["torch/amp/__init__.py"] = b"class autocast: pass\n"
    for relative, content in files.items():
        _write_file(root / relative, content)

    metadata = root / "torch-2.5.1+cu121.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: torch\nVersion: 2.5.1+cu121\n",
        encoding="utf-8",
    )
    record_lines = [
        f"{relative},,{len(content)}\n" for relative, content in files.items()
    ]
    record_lines.extend(
        [
            "torch-2.5.1+cu121.dist-info/METADATA,,\n",
            "torch-2.5.1+cu121.dist-info/RECORD,,\n",
        ]
    )
    (metadata / "RECORD").write_text("".join(record_lines), encoding="utf-8")


def _write_sd15_runtime(root: Path) -> None:
    base = root / "stable-diffusion-v1-5"
    _write_file(base / "model_index.json", b"{}")
    for folder in ("scheduler", "text_encoder", "tokenizer", "unet", "vae"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    for folder in ("text_encoder", "unet", "vae"):
        _write_file(base / folder / "model.safetensors")
    controlnet = root / "control_v11p_sd15_canny"
    _write_file(controlnet / "config.json", b"{}")
    _write_file(controlnet / "diffusion_pytorch_model.safetensors")


def _write_sdxl_runtime(root: Path) -> None:
    base = root / "stable-diffusion-xl-base-1.0"
    _write_file(base / "model_index.json", b"{}")
    required = (
        "scheduler",
        "text_encoder",
        "text_encoder_2",
        "tokenizer",
        "tokenizer_2",
        "unet",
        "vae",
    )
    for folder in required:
        (base / folder).mkdir(parents=True, exist_ok=True)
    for folder in ("text_encoder", "text_encoder_2", "unet", "vae"):
        _write_file(base / folder / "model.safetensors")


def test_missing_torch_amp_is_not_accepted_as_installed(tmp_path: Path) -> None:
    packages = tmp_path / "site-packages"
    _write_fake_torch(packages, include_amp=False)

    issues = inspect_torch_runtime(packages)

    assert issues
    assert any("torch/amp" in issue for issue in issues)
    with pytest.raises(RuntimeError, match="tidak lengkap|tercampur"):
        validate_torch_variant(packages, "cuda")


def test_complete_torch_inventory_passes_validation(tmp_path: Path) -> None:
    packages = tmp_path / "site-packages"
    _write_fake_torch(packages)

    assert inspect_torch_runtime(packages) == []
    assert validate_torch_variant(packages, "cuda") == "2.5.1+cu121"


def test_failed_torch_modules_are_removed_before_retry(monkeypatch) -> None:
    partial = ModuleType("torch")
    child = ModuleType("torch.cuda")
    monkeypatch.setitem(sys.modules, "torch", partial)
    monkeypatch.setitem(sys.modules, "torch.cuda", child)

    assert clear_failed_torch_imports() == 2
    assert "torch" not in sys.modules
    assert "torch.cuda" not in sys.modules


def test_model_families_resolve_independently_across_roots(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from batikcraft_studio import dependency_bootstrap

    preferred_dependency_root = tmp_path / "per-user" / "dependencies"
    legacy_dependency_root = tmp_path / "Program Files" / "BatikCraft Studio" / "dependencies"
    preferred_runtime = preferred_dependency_root / "models" / "runtime"
    legacy_runtime = legacy_dependency_root / "models" / "runtime"
    _write_sdxl_runtime(preferred_runtime)
    _write_sd15_runtime(legacy_runtime)

    monkeypatch.setattr(
        dependency_bootstrap,
        "default_managed_dependency_root",
        lambda: preferred_dependency_root,
    )
    monkeypatch.setattr(
        dependency_bootstrap,
        "legacy_frozen_dependency_root",
        lambda: legacy_dependency_root,
    )

    install_runtime_family_resolution()

    sd15 = runtime_model_installer.find_installed_runtime_models()
    sdxl = runtime_model_installer.find_installed_batikbrew_runtime()

    assert sd15 is not None
    assert sd15.base_model.parent == legacy_runtime
    assert sdxl is not None
    assert sdxl.base_model.parent == preferred_runtime
