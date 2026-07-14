from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.ai import (
    BatikDatasetError,
    BatikDatasetMetadata,
    BatikModelError,
    BatikModelManifest,
    BatikTrainingSample,
    OfflineLoraBatificationProvider,
    OfflineModelLibrary,
    OfflineRuntimeConfig,
    build_batik_dataset,
    build_batik_model_pack,
    load_batik_dataset,
)


def _png() -> bytes:
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 84, 84), outline=(70, 36, 24, 255), width=8)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_batikdataset_round_trip_preserves_pairs_and_metadata(tmp_path: Path) -> None:
    sample = BatikTrainingSample(
        sample_id="wayang-001",
        caption="bcr_wayang, tokoh wayang batik klasik",
        source_content=_png(),
        target_content=_png(),
        conditioning_content=_png(),
        mask_content=_png(),
        category="wayang",
        style="klasik-jawa",
        target_roles=("main-render", "isen", "ornament"),
    )
    metadata = BatikDatasetMetadata(
        dataset_id="wayang-v1",
        name="Wayang V1",
        author="Balya Rochmadi",
        trigger_word="bcr_wayang",
    )

    path = build_batik_dataset([sample], metadata, tmp_path / "wayang.batikdataset")
    loaded = load_batik_dataset(path)

    assert loaded.metadata.dataset_id == "wayang-v1"
    assert loaded.metadata.trigger_word == "bcr_wayang"
    assert len(loaded.samples) == 1
    assert loaded.samples[0].caption.startswith("bcr_wayang")
    assert loaded.samples[0].target_roles == ("main-render", "isen", "ornament")
    assert loaded.samples[0].target_content.startswith(b"\x89PNG")


def test_batikdataset_rejects_changed_sample_checksum(tmp_path: Path) -> None:
    path = build_batik_dataset(
        [
            BatikTrainingSample(
                sample_id="sample-1",
                caption="bcr_batik, motif",
                target_content=_png(),
            )
        ],
        BatikDatasetMetadata(dataset_id="test", name="Test"),
        tmp_path / "test.batikdataset",
    )
    corrupted = tmp_path / "corrupted.batikdataset"
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        corrupted,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for member in source.infolist():
            content = source.read(member.filename)
            if member.filename.endswith("/target.png"):
                content += b"changed"
            target.writestr(member.filename, content)

    with pytest.raises(BatikDatasetError, match="Checksum"):
        load_batik_dataset(corrupted)


def test_model_pack_installs_and_exposes_local_lora(tmp_path: Path) -> None:
    weights = tmp_path / "weights.safetensors"
    weights.write_bytes(b"not-real-weights-but-checksummed")
    preview = tmp_path / "preview.png"
    preview.write_bytes(_png())
    manifest = BatikModelManifest(
        model_id="wayang-v1",
        name="Wayang V1",
        version="1.0.0",
        model_type="lora",
        base_model_family="sd15",
        trigger_words=("bcr_wayang",),
        recommended_weight=0.85,
        resolution=512,
        capabilities=("selection", "structured-output"),
        lora_file="weights.safetensors",
        author="Balya Rochmadi",
    )

    pack = build_batik_model_pack(
        manifest,
        weights,
        tmp_path / "wayang-v1.batikmodel",
        previews=[preview],
    )
    library = OfflineModelLibrary(tmp_path / "models")
    installed = library.install(pack)

    assert installed.model_id == "wayang-v1"
    assert installed.lora_path.is_file()
    assert installed.preview_paths[0].is_file()
    assert library.get("wayang-v1").manifest.recommended_weight == 0.85

    library.uninstall("wayang-v1")
    assert library.models == ()


def test_model_pack_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.batikmodel"
    manifest = {
        "format": "batikcraft-model-pack",
        "schema_version": "1.0",
        "model": {},
        "files": [],
    }
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("manifest.json", json.dumps(manifest))
        handle.writestr("../escape.txt", "bad")

    with pytest.raises(BatikModelError):
        OfflineModelLibrary(tmp_path / "models").install(archive)


def test_offline_provider_sets_offline_environment_without_loading_weights(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    control = tmp_path / "control"
    model_root = tmp_path / "model"
    base.mkdir()
    control.mkdir()
    (model_root / "lora").mkdir(parents=True)
    weights = model_root / "lora" / "weights.safetensors"
    weights.write_bytes(b"weights")
    manifest = BatikModelManifest(
        model_id="offline",
        name="Offline",
        version="1.0.0",
        model_type="lora",
        base_model_family="sd15",
        trigger_words=("bcr_batik",),
        recommended_weight=0.8,
        resolution=512,
        capabilities=("selection",),
        lora_file="lora/weights.safetensors",
    )
    from batikcraft_studio.ai.model_pack import InstalledBatikModel

    installed = InstalledBatikModel(
        manifest=manifest,
        root=model_root,
        lora_path=weights,
        preview_paths=(),
    )
    provider = OfflineLoraBatificationProvider(
        installed,
        OfflineRuntimeConfig(
            base_model_path=base.resolve(),
            controlnet_path=control.resolve(),
        ),
    )

    assert provider.provider_id == "offline-lora:offline"
    assert not provider.is_loaded
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["DIFFUSERS_OFFLINE"] == "1"


def test_runtime_rejects_relative_or_missing_model_directories(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        OfflineRuntimeConfig(base_model_path=Path("relative/model"))
    with pytest.raises(RuntimeError):
        OfflineRuntimeConfig(base_model_path=(tmp_path / "missing").resolve())
