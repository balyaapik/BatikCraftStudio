"""Installable offline LoRA model packs for BatikCraft Studio."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

BATIK_MODEL_FORMAT = "batikcraft-model-pack"
BATIK_MODEL_SCHEMA_VERSION = "1.0"
BATIK_MODEL_EXTENSION = ".batikmodel"
_MANIFEST = "manifest.json"
_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}")


class BatikModelError(RuntimeError):
    """Raised when an offline model pack is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class BatikModelManifest:
    model_id: str
    name: str
    version: str
    model_type: str
    base_model_family: str
    trigger_words: tuple[str, ...]
    recommended_weight: float
    resolution: int
    capabilities: tuple[str, ...]
    lora_file: str
    author: str = ""
    description: str = ""
    license_name: str = ""
    controlnet_family: str = "lineart"
    negative_prompt: str = ""
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", safe_model_id(self.model_id))
        object.__setattr__(self, "name", _text(self.name, "model name", 160))
        object.__setattr__(self, "version", _text(self.version, "model version", 40))
        model_type = _text(self.model_type, "model type", 40).casefold()
        if model_type != "lora":
            raise BatikModelError("Milestone 4B hanya mendukung model_type 'lora'.")
        object.__setattr__(self, "model_type", model_type)
        object.__setattr__(
            self,
            "base_model_family",
            _text(self.base_model_family, "base model family", 80),
        )
        triggers = tuple(dict.fromkeys(_text(word, "trigger word", 80) for word in self.trigger_words))
        if not triggers:
            raise BatikModelError("Model harus memiliki trigger word.")
        object.__setattr__(self, "trigger_words", triggers)
        weight = float(self.recommended_weight)
        if not 0 <= weight <= 2:
            raise BatikModelError("recommended_weight harus berada antara 0 dan 2.")
        object.__setattr__(self, "recommended_weight", weight)
        if isinstance(self.resolution, bool) or not isinstance(self.resolution, int):
            raise BatikModelError("resolution harus berupa bilangan bulat.")
        if not 256 <= self.resolution <= 2048:
            raise BatikModelError("resolution harus berada antara 256 dan 2048.")
        capabilities = tuple(
            dict.fromkeys(_text(item, "capability", 80) for item in self.capabilities)
        )
        if not capabilities:
            raise BatikModelError("Model harus memiliki capability.")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "lora_file", _safe_path(self.lora_file))
        object.__setattr__(self, "author", _optional(self.author, 160))
        object.__setattr__(self, "description", _optional(self.description, 2_000))
        object.__setattr__(self, "license_name", _optional(self.license_name, 160))
        object.__setattr__(
            self,
            "controlnet_family",
            _text(self.controlnet_family, "controlnet family", 80),
        )
        object.__setattr__(self, "negative_prompt", _optional(self.negative_prompt, 1_000))
        metadata = {} if self.metadata is None else self.metadata
        if not isinstance(metadata, dict):
            raise BatikModelError("metadata model harus berupa dictionary.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(metadata)))


@dataclass(frozen=True, slots=True)
class InstalledBatikModel:
    manifest: BatikModelManifest
    root: Path
    lora_path: Path
    preview_paths: tuple[Path, ...]

    @property
    def model_id(self) -> str:
        return self.manifest.model_id


class OfflineModelLibrary:
    """Filesystem-backed registry that never resolves remote identifiers."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_model_library_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, InstalledBatikModel] = {}
        self.refresh()

    @property
    def models(self) -> tuple[InstalledBatikModel, ...]:
        return tuple(sorted(self._models.values(), key=lambda item: item.manifest.name.casefold()))

    def refresh(self) -> tuple[InstalledBatikModel, ...]:
        models: dict[str, InstalledBatikModel] = {}
        for child in self.root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                model = _load_installed(child)
            except (BatikModelError, OSError, json.JSONDecodeError):
                continue
            models[model.model_id] = model
        self._models = models
        return self.models

    def get(self, model_id: str) -> InstalledBatikModel:
        try:
            return self._models[safe_model_id(model_id)]
        except KeyError as exc:
            raise BatikModelError(f"Model offline {model_id!r} belum terpasang.") from exc

    def install(self, archive_path: Path | str, *, replace: bool = False) -> InstalledBatikModel:
        source = Path(archive_path)
        if source.suffix.casefold() != BATIK_MODEL_EXTENSION:
            raise BatikModelError(f"Model harus memakai ekstensi {BATIK_MODEL_EXTENSION}.")
        if not source.is_file():
            raise BatikModelError(f"File model tidak ditemukan: {source}")
        try:
            with zipfile.ZipFile(source, "r") as archive:
                names = [_safe_path(item.filename, allow_directory=True) for item in archive.infolist()]
                if len(names) != len(set(name.casefold() for name in names)):
                    raise BatikModelError("Model pack memiliki path ganda.")
                if names.count(_MANIFEST) != 1:
                    raise BatikModelError("Model pack harus memiliki satu manifest.json.")
                manifest, files = _parse_manifest(
                    json.loads(archive.read(_MANIFEST).decode("utf-8"))
                )
                destination = self.root / manifest.model_id
                if destination.exists() and not replace:
                    raise BatikModelError(f"Model {manifest.model_id!r} sudah terpasang.")
                with tempfile.TemporaryDirectory(dir=self.root, prefix=f".{manifest.model_id}-") as temp:
                    staging = Path(temp) / "model"
                    staging.mkdir()
                    for member in archive.infolist():
                        relative = _safe_path(member.filename, allow_directory=True)
                        if member.is_dir():
                            (staging / relative).mkdir(parents=True, exist_ok=True)
                            continue
                        output = _safe_join(staging, relative)
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as src, output.open("wb") as dst:
                            shutil.copyfileobj(src, dst, length=1024 * 1024)
                    _validate_files(staging, files)
                    _load_installed(staging)
                    backup = self.root / f".{manifest.model_id}.backup"
                    if backup.exists():
                        shutil.rmtree(backup)
                    if destination.exists():
                        destination.replace(backup)
                    try:
                        staging.replace(destination)
                    except Exception:
                        if backup.exists() and not destination.exists():
                            backup.replace(destination)
                        raise
                    finally:
                        if backup.exists():
                            shutil.rmtree(backup)
        except BatikModelError:
            raise
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BatikModelError("Model pack rusak atau tidak dapat dibaca.") from exc
        self.refresh()
        return self.get(manifest.model_id)

    def uninstall(self, model_id: str) -> None:
        installed = self.get(model_id)
        shutil.rmtree(installed.root)
        self.refresh()


def build_batik_model_pack(
    manifest: BatikModelManifest,
    lora_weights: Path | str,
    destination: Path | str,
    *,
    previews: tuple[Path | str, ...] | list[Path | str] = (),
    training_report: Path | str | None = None,
) -> Path:
    weights_path = Path(lora_weights)
    if not weights_path.is_file() or not weights_path.stat().st_size:
        raise BatikModelError(f"Bobot LoRA tidak ditemukan atau kosong: {weights_path}")
    output = Path(destination)
    if output.suffix.casefold() != BATIK_MODEL_EXTENSION:
        output = output.with_suffix(BATIK_MODEL_EXTENSION)
    output.parent.mkdir(parents=True, exist_ok=True)
    lora_member = f"lora/{weights_path.name}"
    normalized = BatikModelManifest(
        model_id=manifest.model_id,
        name=manifest.name,
        version=manifest.version,
        model_type=manifest.model_type,
        base_model_family=manifest.base_model_family,
        trigger_words=manifest.trigger_words,
        recommended_weight=manifest.recommended_weight,
        resolution=manifest.resolution,
        capabilities=manifest.capabilities,
        lora_file=lora_member,
        author=manifest.author,
        description=manifest.description,
        license_name=manifest.license_name,
        controlnet_family=manifest.controlnet_family,
        negative_prompt=manifest.negative_prompt,
        metadata=dict(manifest.metadata or {}),
    )
    payloads: list[tuple[str, str, bytes]] = [(lora_member, "lora", weights_path.read_bytes())]
    for index, value in enumerate(previews, start=1):
        path = Path(value)
        if not path.is_file():
            raise BatikModelError(f"Preview tidak ditemukan: {path}")
        payloads.append((f"previews/preview-{index:02d}{path.suffix or '.png'}", "preview", path.read_bytes()))
    if training_report is not None:
        report = Path(training_report)
        if not report.is_file():
            raise BatikModelError(f"Training report tidak ditemukan: {report}")
        payloads.append(("training-report.json", "training-report", report.read_bytes()))
    files = [
        {
            "path": path,
            "role": role,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        for path, role, content in payloads
    ]
    data = {
        "format": BATIK_MODEL_FORMAT,
        "schema_version": BATIK_MODEL_SCHEMA_VERSION,
        "model": _manifest_dict(normalized),
        "files": files,
    }
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(_MANIFEST, json.dumps(data, ensure_ascii=False, indent=2))
            for path, _role, content in payloads:
                archive.writestr(path, content)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output


def default_model_library_root() -> Path:
    override = os.environ.get("BATIKCRAFT_MODEL_LIBRARY")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BatikCraftStudio" / "models"


def discover_bundled_model_packs(root: Path | str) -> tuple[Path, ...]:
    directory = Path(root)
    if not directory.is_dir():
        return ()
    return tuple(sorted(directory.rglob(f"*{BATIK_MODEL_EXTENSION}")))


def safe_model_id(value: object) -> str:
    text = str(value).strip().casefold().replace(" ", "-")
    text = _ID_PATTERN.sub("-", text).strip("-.")
    if not text:
        raise BatikModelError("model_id tidak boleh kosong.")
    return text[:120]


def _load_installed(root: Path) -> InstalledBatikModel:
    manifest, files = _parse_manifest(json.loads((root / _MANIFEST).read_text(encoding="utf-8")))
    _validate_files(root, files)
    previews = tuple(_safe_join(root, item["path"]) for item in files if item["role"] == "preview")
    return InstalledBatikModel(manifest, root, _safe_join(root, manifest.lora_file), previews)


def _parse_manifest(data: object) -> tuple[BatikModelManifest, tuple[dict[str, Any], ...]]:
    if not isinstance(data, dict) or set(data) != {"format", "schema_version", "model", "files"}:
        raise BatikModelError("Manifest model tidak valid.")
    if data["format"] != BATIK_MODEL_FORMAT or data["schema_version"] != BATIK_MODEL_SCHEMA_VERSION:
        raise BatikModelError("Format atau versi model pack tidak didukung.")
    raw = data["model"]
    required = {
        "id", "name", "version", "type", "base_model_family", "trigger_words",
        "recommended_weight", "resolution", "capabilities", "lora_file", "author",
        "description", "license", "controlnet_family", "negative_prompt", "metadata",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise BatikModelError("Metadata model tidak lengkap.")
    manifest = BatikModelManifest(
        model_id=raw["id"], name=raw["name"], version=raw["version"], model_type=raw["type"],
        base_model_family=raw["base_model_family"], trigger_words=tuple(raw["trigger_words"]),
        recommended_weight=raw["recommended_weight"], resolution=raw["resolution"],
        capabilities=tuple(raw["capabilities"]), lora_file=raw["lora_file"], author=raw["author"],
        description=raw["description"], license_name=raw["license"],
        controlnet_family=raw["controlnet_family"], negative_prompt=raw["negative_prompt"],
        metadata=raw["metadata"],
    )
    if not isinstance(data["files"], list) or not data["files"]:
        raise BatikModelError("Manifest model tidak memiliki file.")
    files: list[dict[str, Any]] = []
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "role", "sha256", "size"}:
            raise BatikModelError("Struktur file model tidak valid.")
        path = _safe_path(item["path"])
        digest = str(item["sha256"]).casefold()
        if not _SHA_PATTERN.fullmatch(digest):
            raise BatikModelError("Checksum file model tidak valid.")
        size = item["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise BatikModelError("Ukuran file model tidak valid.")
        files.append({"path": path, "role": _text(item["role"], "role", 80), "sha256": digest, "size": size})
    if manifest.lora_file not in {item["path"] for item in files if item["role"] == "lora"}:
        raise BatikModelError("lora_file tidak terdaftar sebagai file LoRA.")
    return manifest, tuple(files)


def _validate_files(root: Path, files: tuple[dict[str, Any], ...]) -> None:
    for item in files:
        path = _safe_join(root, item["path"])
        if not path.is_file() or path.stat().st_size != item["size"]:
            raise BatikModelError(f"File model tidak valid: {item['path']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise BatikModelError(f"Checksum file model tidak cocok: {item['path']}")


def _manifest_dict(manifest: BatikModelManifest) -> dict[str, Any]:
    return {
        "id": manifest.model_id, "name": manifest.name, "version": manifest.version,
        "type": manifest.model_type, "base_model_family": manifest.base_model_family,
        "trigger_words": list(manifest.trigger_words),
        "recommended_weight": manifest.recommended_weight, "resolution": manifest.resolution,
        "capabilities": list(manifest.capabilities), "lora_file": manifest.lora_file,
        "author": manifest.author, "description": manifest.description,
        "license": manifest.license_name, "controlnet_family": manifest.controlnet_family,
        "negative_prompt": manifest.negative_prompt, "metadata": dict(manifest.metadata or {}),
    }


def _safe_path(value: object, *, allow_directory: bool = False) -> str:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise BatikModelError(f"Path model tidak aman: {text!r}.")
    return path.as_posix().rstrip("/") if allow_directory else path.as_posix()


def _safe_join(root: Path, relative: str) -> Path:
    destination = (root / _safe_path(relative)).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise BatikModelError("Path model keluar dari directory instalasi.") from exc
    return destination


def _text(value: object, label: str, maximum: int) -> str:
    text = str(value).strip()
    if not text:
        raise BatikModelError(f"{label} tidak boleh kosong.")
    if len(text) > maximum:
        raise BatikModelError(f"{label} terlalu panjang.")
    return text


def _optional(value: object, maximum: int) -> str:
    text = str(value).strip()
    if len(text) > maximum:
        raise BatikModelError("Metadata model terlalu panjang.")
    return text


__all__ = [
    "BATIK_MODEL_EXTENSION", "BATIK_MODEL_FORMAT", "BATIK_MODEL_SCHEMA_VERSION",
    "BatikModelError", "BatikModelManifest", "InstalledBatikModel", "OfflineModelLibrary",
    "build_batik_model_pack", "default_model_library_root", "discover_bundled_model_packs",
    "safe_model_id",
]
