"""Strict integrity checks for the managed BatikBrew SDXL runtime.

The original installer considered a runtime complete when component folders
existed and heavyweight folders contained any weight file.  Interrupted or
older downloads could therefore be reported as installed even when
``model_index.json`` declared ``tokenizer_2``/``text_encoder_2`` as null or the
second tokenizer lacked its vocabulary files.  Diffusers then loaded a partial
pipeline and failed later during prompt encoding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from batikcraft_studio.ai import runtime_model_installer

_INSTALLED = False
_REQUIRED_COMPONENTS = (
    "scheduler",
    "text_encoder",
    "text_encoder_2",
    "tokenizer",
    "tokenizer_2",
    "unet",
    "vae",
)
_WEIGHT_SUFFIXES = {".bin", ".safetensors"}


def inspect_batikbrew_runtime(base_model: str | Path) -> tuple[str, ...]:
    """Return every actionable integrity problem found in one SDXL folder."""

    base = Path(base_model).expanduser()
    issues: list[str] = []
    model_index = base / "model_index.json"
    payload: dict[str, Any] | None = None

    if not model_index.is_file():
        issues.append("model_index.json tidak tersedia")
    else:
        try:
            decoded = json.loads(model_index.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(f"model_index.json tidak dapat dibaca: {exc}")
        else:
            if isinstance(decoded, dict):
                payload = decoded
            else:
                issues.append("model_index.json bukan object JSON")

    for component in _REQUIRED_COMPONENTS:
        folder = base / component
        if not folder.is_dir():
            issues.append(f"folder {component}/ tidak tersedia")
            continue
        if payload is not None and not _component_declared(payload.get(component)):
            issues.append(f"model_index.json tidak mengaktifkan {component}")

        if component == "scheduler":
            if not (folder / "scheduler_config.json").is_file():
                issues.append("scheduler/scheduler_config.json tidak tersedia")
        elif component.startswith("tokenizer"):
            issues.extend(_inspect_tokenizer(folder, component))
        else:
            if not (folder / "config.json").is_file():
                issues.append(f"{component}/config.json tidak tersedia")
            if not _contains_weight(folder):
                issues.append(f"bobot model {component} tidak tersedia")

    return tuple(dict.fromkeys(issues))


def validate_batikbrew_runtime_strict(paths: Any) -> None:
    """Raise the installer's public error when a runtime is incomplete."""

    issues = inspect_batikbrew_runtime(paths.base_model)
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        raise runtime_model_installer.RuntimeModelInstallError(
            "Runtime BatikBrew SDXL belum lengkap:\n" + details
        )


def install_sdxl_runtime_integrity() -> None:
    """Install strict checks into all existing installer/status entry points."""

    global _INSTALLED
    if _INSTALLED:
        return

    runtime_model_installer.validate_batikbrew_runtime = (  # type: ignore[assignment]
        validate_batikbrew_runtime_strict
    )
    runtime_model_installer._sdxl_model_is_complete = (  # type: ignore[attr-defined]
        lambda path: not inspect_batikbrew_runtime(path)
    )
    _INSTALLED = True


def _component_declared(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    library, class_name = value[0], value[1]
    return bool(str(library or "").strip() and str(class_name or "").strip())


def _inspect_tokenizer(folder: Path, component: str) -> list[str]:
    issues: list[str] = []
    if not (folder / "tokenizer_config.json").is_file():
        issues.append(f"{component}/tokenizer_config.json tidak tersedia")

    tokenizer_json = (folder / "tokenizer.json").is_file()
    vocab_json = (folder / "vocab.json").is_file()
    merges_txt = (folder / "merges.txt").is_file()
    sentencepiece = any(
        (folder / filename).is_file()
        for filename in ("spiece.model", "sentencepiece.bpe.model", "tokenizer.model")
    )
    if not tokenizer_json and not sentencepiece and not (vocab_json and merges_txt):
        issues.append(
            f"vocabulary {component} tidak lengkap "
            "(butuh tokenizer.json atau vocab.json + merges.txt)"
        )
    return issues


def _contains_weight(folder: Path) -> bool:
    try:
        return any(
            item.is_file() and item.suffix.casefold() in _WEIGHT_SUFFIXES
            for item in folder.rglob("*")
        )
    except OSError:
        return False


__all__ = [
    "inspect_batikbrew_runtime",
    "install_sdxl_runtime_integrity",
    "validate_batikbrew_runtime_strict",
]
