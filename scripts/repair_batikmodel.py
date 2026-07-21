"""Perbaiki paket LoRA agar manifestnya valid untuk BatikCraft Studio.

Dipakai bila Anda sudah memiliki hasil pelatihan tetapi paketnya ditolak
("Manifest model tidak valid") atau terlanjur terunduh sebagai ``.zip``.
Bobot LoRA yang sudah ada dipakai kembali — tidak ada pelatihan ulang.

Contoh::

    python scripts/repair_batikmodel.py hasil.zip
    python scripts/repair_batikmodel.py pytorch_lora_weights.safetensors --family sdxl
    python scripts/repair_batikmodel.py paket-lama.batikmodel -o diperbaiki.batikmodel

Hanya memakai pustaka standar Python 3.11+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

FORMAT = "batikcraft-model-pack"
SCHEMA_VERSION = "1.0"
LORA_ENTRY = "model/pytorch_lora_weights.safetensors"
MODEL_FIELDS = (
    "id", "name", "version", "type", "base_model_family", "trigger_words",
    "recommended_weight", "resolution", "capabilities", "lora_file", "author",
    "description", "license", "controlnet_family", "negative_prompt", "metadata",
)
_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_family(weights: Path) -> str:
    """Tebak keluarga LoRA dari header safetensors (2048 = SDXL, 768 = SD 1.5)."""

    try:
        with weights.open("rb") as stream:
            size = int.from_bytes(stream.read(8), "little")
            if not 0 < size <= 32 * 1024 * 1024:
                return "sdxl"
            header = json.loads(stream.read(size).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return "sdxl"

    keys = [key for key in header if key != "__metadata__"]
    if any("text_encoder_2" in key or "te2" in key for key in keys):
        return "sdxl"
    for key in keys:
        entry = header.get(key)
        shape = entry.get("shape") if isinstance(entry, dict) else None
        if shape and 2048 in shape:
            return "sdxl"
        if shape and 768 in shape and "text" in key:
            return "sd15"
    return "sdxl"


def find_weights(source: Path, workdir: Path) -> tuple[Path, dict]:
    """Kembalikan (berkas bobot, manifest lama bila ada)."""

    if source.suffix.casefold() == ".safetensors":
        return source, {}

    if not zipfile.is_zipfile(source):
        raise SystemExit(f"Bukan arsip maupun .safetensors: {source}")

    extracted = workdir / "isi"
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            name = Path(member.filename).name
            if member.is_dir() or not name or name.startswith("."):
                continue
            target = extracted / Path(member.filename).name
            with archive.open(member) as reader, target.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
            # Arsip berisi paket lain (kasus "Download All" Kaggle).
            if target.suffix.casefold() == ".batikmodel":
                return find_weights(target, workdir / "dalam")

    old_manifest: dict = {}
    manifest_path = extracted / "manifest.json"
    if manifest_path.is_file():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            old_manifest = {}

    candidates = sorted(extracted.glob("*.safetensors"), key=lambda p: p.stat().st_size)
    if not candidates:
        raise SystemExit("Tidak menemukan berkas .safetensors di dalam arsip.")
    return candidates[-1], old_manifest


def build_manifest(weights: Path, old: dict, args: argparse.Namespace) -> dict:
    previous = old.get("model", {}) if isinstance(old, dict) else {}

    def inherit(field: str, fallback):
        value = previous.get(field)
        return value if value not in (None, "", [], {}) else fallback

    family = args.family or inherit("base_model_family", None) or detect_family(weights)
    default_id = _ID_PATTERN.sub("-", weights.parent.name.casefold()).strip("-")
    model_id = args.id or inherit("id", None) or default_id or "batikcraft-lora"
    resolution = int(args.resolution or inherit("resolution", 1024 if family == "sdxl" else 512))
    trigger = args.trigger or (inherit("trigger_words", ["bcr_batikstyle"]) or ["bcr_batikstyle"])
    if isinstance(trigger, str):
        trigger = [trigger]

    metadata = inherit("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.setdefault("repaired_by", "scripts/repair_batikmodel.py")

    return {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "model": {
            "id": model_id,
            "name": args.name or inherit("name", model_id),
            "version": inherit("version", "1.0.0"),
            "type": "lora",
            "base_model_family": family,
            "trigger_words": list(trigger),
            "recommended_weight": float(inherit("recommended_weight", 0.85)),
            "resolution": resolution,
            "capabilities": list(
                inherit("capabilities", ["object-batification", "img2img", "preserve-silhouette"])
            ),
            "lora_file": LORA_ENTRY,
            "author": args.author or inherit("author", "BatikCraft User"),
            "description": inherit(
                "description", "LoRA gaya batik untuk membatikkan objek apa pun."
            ),
            "license": inherit("license", ""),
            "controlnet_family": inherit("controlnet_family", "canny"),
            "negative_prompt": inherit(
                "negative_prompt",
                "photograph, 3d render, text, watermark, changed silhouette, extra object",
            ),
            "metadata": metadata,
        },
        "files": [
            {
                "path": LORA_ENTRY,
                "role": "lora",
                "sha256": sha256_of(weights),
                "size": weights.stat().st_size,
            }
        ],
    }


def validate(manifest: dict) -> None:
    """Periksa persis seperti validator aplikasi sebelum berkas ditulis."""

    if set(manifest) != {"format", "schema_version", "model", "files"}:
        raise SystemExit("Kunci root manifest tidak sesuai.")
    missing = set(MODEL_FIELDS) - set(manifest["model"])
    extra = set(manifest["model"]) - set(MODEL_FIELDS)
    if missing or extra:
        raise SystemExit(f"Field model salah — kurang: {missing}, berlebih: {extra}")
    if not 256 <= int(manifest["model"]["resolution"]) <= 2048:
        raise SystemExit("resolution harus antara 256 dan 2048.")
    if not 0 <= float(manifest["model"]["recommended_weight"]) <= 2:
        raise SystemExit("recommended_weight harus antara 0 dan 2.")
    for entry in manifest["files"]:
        if set(entry) != {"path", "role", "sha256", "size"}:
            raise SystemExit("Struktur files tidak sesuai.")
        if len(entry["sha256"]) != 64 or entry["size"] < 1:
            raise SystemExit("Checksum atau ukuran file tidak valid.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Perbaiki paket LoRA menjadi .batikmodel yang valid."
    )
    parser.add_argument("source", help="berkas .zip, .batikmodel, atau .safetensors")
    parser.add_argument("-o", "--output", help="nama berkas keluaran (.batikmodel)")
    parser.add_argument("--family", choices=("sdxl", "sd15"), help="keluarga base model")
    parser.add_argument("--id", help="model id")
    parser.add_argument("--name", help="nama tampilan model")
    parser.add_argument("--trigger", help="kata pemicu")
    parser.add_argument("--resolution", type=int, help="resolusi model")
    parser.add_argument("--author", help="nama pembuat")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Berkas tidak ditemukan: {source}")

    with tempfile.TemporaryDirectory() as temporary:
        workdir = Path(temporary)
        weights, old_manifest = find_weights(source, workdir)
        manifest = build_manifest(weights, old_manifest, args)
        validate(manifest)

        output = Path(args.output).expanduser() if args.output else (
            source.with_name(f"{manifest['model']['id']}.batikmodel")
        )
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False)
            )
            archive.write(weights, LORA_ENTRY)

    model = manifest["model"]
    print("Paket valid dibuat:", output)
    print(f"  id          : {model['id']}")
    print(f"  keluarga    : {model['base_model_family']}")
    print(f"  resolusi    : {model['resolution']}")
    print(f"  kata pemicu : {', '.join(model['trigger_words'])}")
    print(f"  ukuran      : {output.stat().st_size / 1024**2:.1f} MB")
    print()
    print("Pasang lewat: Pusat Dependensi → Model AI Offline & LoRA → Pasang .batikmodel…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
