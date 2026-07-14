"""Semi-automatic Kaggle pipeline for extracting modular Batik asset candidates.

This module intentionally lives outside the application package because OpenCV, NumPy,
and pandas are notebook-time dependencies, not desktop runtime dependencies.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from batikcraft_studio.assets import (
    AssetLibrary,
    AssetPackMetadata,
    build_asset_pack,
    discover_images,
    read_review_csv,
    safe_identifier,
)

_CATEGORY_KEYWORDS = {
    "isen-isen": {
        "isen",
        "cecek",
        "sawut",
        "ukel",
        "galaran",
        "sisik",
        "cacah",
        "titik",
    },
    "tekstur": {
        "texture",
        "tekstur",
        "fabric",
        "kain",
        "serat",
        "noise",
        "malam",
    },
    "ornamen": {
        "border",
        "pinggir",
        "tumpal",
        "frame",
        "hias",
        "ornamen",
        "sulur",
    },
}


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    """Paths, thresholds, and pack metadata for one Kaggle run."""

    dataset_root: Path
    work_root: Path
    pack_id: str = "batikcraft-default-library-v1"
    pack_name: str = "BatikCraft Default Library"
    pack_version: str = "1.0.0"
    pack_author: str = "Balya Rochmadi"
    pack_description: str = "Asset modular hasil ekstraksi dan kurasi dataset batik."
    extraction_modes: tuple[str, ...] = ("full", "components", "grid")
    max_source_side: int = 1800
    grid_size: int = 512
    grid_overlap: float = 0.25
    min_component_area_ratio: float = 0.008
    max_component_area_ratio: float = 0.72
    min_component_side: int = 48
    component_padding_ratio: float = 0.08
    max_candidates_per_image: int = 40
    auto_accept_confidence: float = 0.86
    master_asset_size: int = 1024
    thumbnail_size: int = 192

    @property
    def candidate_root(self) -> Path:
        return self.work_root / "candidates"

    @property
    def contact_sheet_root(self) -> Path:
        return self.work_root / "contact-sheets"

    @property
    def review_csv(self) -> Path:
        return self.work_root / "review.csv"

    @property
    def output_pack(self) -> Path:
        return self.work_root / f"{self.pack_id}.batikpack"


@dataclass(frozen=True, slots=True)
class ExtractedCandidate:
    """One generated PNG candidate awaiting human curation."""

    asset_id: str
    name: str
    category: str
    tags: tuple[str, ...]
    png_path: Path
    source_path: str
    source_sha256: str
    extraction_mode: str
    bbox: tuple[int, int, int, int]
    confidence: float


def prepare_workdirs(config: ExtractionConfig) -> None:
    """Create all writable Kaggle output directories."""

    for path in (
        config.work_root,
        config.candidate_root,
        config.contact_sheet_root,
    ):
        path.mkdir(parents=True, exist_ok=True)


def extract_dataset(config: ExtractionConfig) -> tuple[ExtractedCandidate, ...]:
    """Discover, de-duplicate, segment, and save candidate PNG files."""

    prepare_workdirs(config)
    sources = discover_images(config.dataset_root)
    unique_sources: list[tuple[Path, str]] = []
    seen_hashes: set[str] = set()
    for path in sources:
        digest = _source_hash(path)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        unique_sources.append((path, digest))

    extracted: list[ExtractedCandidate] = []
    visual_hashes: list[int] = []
    for source_index, (path, digest) in enumerate(unique_sources, start=1):
        try:
            image = _read_image(path, config.max_source_side)
            mask, mask_confidence = _foreground_mask(image)
        except (OSError, ValueError, cv2.error):
            continue
        category = infer_category(path)
        tags = infer_tags(path)
        boxes = _candidate_boxes(image, mask, mask_confidence, config)
        for candidate_index, (mode, bbox, confidence) in enumerate(boxes, start=1):
            active_mask = (
                mask
                if mode != "grid"
                else np.full(mask.shape, 255, dtype=np.uint8)
            )
            rgba = _rgba_crop(image, active_mask, bbox)
            alpha_ratio = float(np.count_nonzero(rgba[:, :, 3])) / rgba[:, :, 3].size
            if alpha_ratio < 0.025:
                continue
            fingerprint = _dhash(rgba)
            if any(_hamming(fingerprint, previous) <= 5 for previous in visual_hashes[-5000:]):
                continue
            visual_hashes.append(fingerprint)
            stem = safe_identifier(path.stem)[:45]
            asset_id = safe_identifier(
                f"{category}-{stem}-{source_index:05d}-{mode}-{candidate_index:02d}"
            )
            output = config.candidate_root / f"{asset_id}.png"
            _save_rgba(output, rgba)
            extracted.append(
                ExtractedCandidate(
                    asset_id=asset_id,
                    name=(
                        f"{path.stem.replace('_', ' ').replace('-', ' ').title()} "
                        f"{candidate_index}"
                    ),
                    category=category,
                    tags=tuple(dict.fromkeys((*tags, mode))),
                    png_path=output,
                    source_path=str(path.relative_to(config.dataset_root)),
                    source_sha256=digest,
                    extraction_mode=mode,
                    bbox=bbox,
                    confidence=round(float(np.clip(confidence, 0, 1)), 4),
                )
            )
    return tuple(extracted)


def write_review_files(
    candidates: tuple[ExtractedCandidate, ...] | list[ExtractedCandidate],
    config: ExtractionConfig,
) -> pd.DataFrame:
    """Write review.csv plus visual contact sheets for human curation."""

    rows = [
        {
            "keep": int(item.confidence >= config.auto_accept_confidence),
            "asset_id": item.asset_id,
            "name": item.name,
            "category": item.category,
            "tags": "|".join(item.tags),
            "source_path": item.source_path,
            "confidence": item.confidence,
            "notes": "",
            "extraction_mode": item.extraction_mode,
            "bbox": ",".join(map(str, item.bbox)),
            "source_sha256": item.source_sha256,
        }
        for item in candidates
    ]
    review = pd.DataFrame(rows)
    review.to_csv(config.review_csv, index=False)
    make_contact_sheets(candidates, config.contact_sheet_root)
    return review


def make_contact_sheets(
    candidates: tuple[ExtractedCandidate, ...] | list[ExtractedCandidate],
    output_dir: Path,
    *,
    columns: int = 6,
    rows: int = 5,
    tile_size: int = 190,
) -> tuple[Path, ...]:
    """Create paginated JPEG contact sheets for rapid visual review."""

    output_dir.mkdir(parents=True, exist_ok=True)
    per_page = columns * rows
    outputs: list[Path] = []
    for page_index in range(math.ceil(len(candidates) / per_page)):
        items = candidates[page_index * per_page : (page_index + 1) * per_page]
        sheet = Image.new(
            "RGB",
            (columns * tile_size, rows * (tile_size + 42)),
            (245, 239, 229),
        )
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(items):
            row, column = divmod(index, columns)
            left = column * tile_size
            top = row * (tile_size + 42)
            with Image.open(item.png_path) as source:
                preview = source.convert("RGBA")
            preview.thumbnail(
                (tile_size - 16, tile_size - 16),
                Image.Resampling.LANCZOS,
            )
            holder = Image.new(
                "RGBA",
                (tile_size, tile_size),
                (255, 255, 255, 255),
            )
            holder.alpha_composite(
                preview,
                dest=(
                    (tile_size - preview.width) // 2,
                    (tile_size - preview.height) // 2,
                ),
            )
            sheet.paste(holder.convert("RGB"), (left, top))
            draw.text(
                (left + 5, top + tile_size + 2),
                f"{item.asset_id[:25]}\n{item.category} · {item.confidence:.2f}",
                fill=(42, 34, 29),
            )
        output = output_dir / f"contact-sheet-{page_index + 1:03d}.jpg"
        sheet.save(output, quality=90, optimize=True)
        outputs.append(output)
    return tuple(outputs)


def build_curated_pack(
    config: ExtractionConfig,
    *,
    curated_review_csv: Path | None = None,
) -> Path:
    """Build and validate a `.batikpack` from approved review rows."""

    review_path = curated_review_csv or config.review_csv
    accepted = read_review_csv(review_path, config.candidate_root)
    if not accepted:
        raise RuntimeError("Belum ada candidate dengan keep=1 pada review CSV.")
    metadata = AssetPackMetadata(
        pack_id=config.pack_id,
        name=config.pack_name,
        version=config.pack_version,
        author=config.pack_author,
        description=config.pack_description,
    )
    pack_path = build_asset_pack(
        accepted,
        metadata,
        config.output_pack,
        master_size=config.master_asset_size,
        padding_ratio=0.06,
        thumbnail_size=config.thumbnail_size,
    )
    validation_root = config.work_root / "validation-library"
    library = AssetLibrary(validation_root)
    library.install_pack(pack_path, replace=True)
    return pack_path


def infer_category(path: Path) -> str:
    """Infer a broad initial category from folder and filename keywords."""

    tokens = set(re.split(r"[^a-z0-9]+", path.as_posix().casefold()))
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if tokens.intersection(keywords):
            return category
    return "motif-pokok"


def infer_tags(path: Path) -> tuple[str, ...]:
    """Create conservative initial tags from the final path components."""

    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", path.as_posix().casefold())
        if len(token) >= 3
        and token not in {"kaggle", "input", "dataset", "datasets", "images"}
    ]
    return tuple(dict.fromkeys(tokens[-6:]))


def _candidate_boxes(
    image: np.ndarray,
    mask: np.ndarray,
    mask_confidence: float,
    config: ExtractionConfig,
) -> list[tuple[str, tuple[int, int, int, int], float]]:
    boxes: list[tuple[str, tuple[int, int, int, int], float]] = []
    height, width = image.shape[:2]
    if "full" in config.extraction_modes:
        boxes.append(("full", (0, 0, width, height), 0.62))
    if "components" in config.extraction_modes:
        boxes.extend(
            ("components", bbox, confidence * mask_confidence)
            for bbox, confidence in _component_boxes(mask, config)
        )
    foreground_ratio = float(np.count_nonzero(mask)) / mask.size
    if "grid" in config.extraction_modes and foreground_ratio > 0.65:
        boxes.extend(
            ("grid", bbox, confidence)
            for bbox, confidence in _grid_boxes(image, config)
        )
    return boxes[: config.max_candidates_per_image]


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_image(path: Path, max_side: int) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Tidak dapat membaca {path}")
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(width, height))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    return image


def _foreground_mask(image: np.ndarray) -> tuple[np.ndarray, float]:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]], axis=0)
    background = np.median(border.astype(np.float32), axis=0)
    distance = np.linalg.norm(lab.astype(np.float32) - background, axis=2)
    normalized = np.clip(
        distance / max(float(distance.max()), 1) * 255,
        0,
        255,
    ).astype(np.uint8)
    _, mask = cv2.threshold(
        normalized,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.bitwise_or(mask, edges)
    kernel_size = max(3, round(min(image.shape[:2]) * 0.006) | 1)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    foreground_ratio = float(np.count_nonzero(mask)) / mask.size
    confidence = max(0.05, 1.0 - abs(foreground_ratio - 0.35))
    return mask, confidence


def _component_boxes(
    mask: np.ndarray,
    config: ExtractionConfig,
) -> list[tuple[tuple[int, int, int, int], float]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    image_area = mask.shape[0] * mask.shape[1]
    boxes: list[tuple[tuple[int, int, int, int], float]] = []
    for index in range(1, count):
        x, y, width, height, area = stats[index]
        area_ratio = area / image_area
        if (
            width < config.min_component_side
            or height < config.min_component_side
            or area_ratio < config.min_component_area_ratio
            or area_ratio > config.max_component_area_ratio
        ):
            continue
        padding = round(max(width, height) * config.component_padding_ratio)
        left = max(0, x - padding)
        top = max(0, y - padding)
        right = min(mask.shape[1], x + width + padding)
        bottom = min(mask.shape[0], y + height + padding)
        solidity = area / max(width * height, 1)
        confidence = min(
            0.99,
            0.45 + 0.45 * solidity + 0.1 * min(area_ratio / 0.2, 1),
        )
        boxes.append(((left, top, right - left, bottom - top), confidence))
    boxes.sort(key=lambda item: item[0][2] * item[0][3], reverse=True)
    return boxes[: config.max_candidates_per_image]


def _grid_boxes(
    image: np.ndarray,
    config: ExtractionConfig,
) -> list[tuple[tuple[int, int, int, int], float]]:
    height, width = image.shape[:2]
    tile = min(config.grid_size, width, height)
    if tile < config.min_component_side:
        return [((0, 0, width, height), 0.55)]
    step = max(1, round(tile * (1 - config.grid_overlap)))
    xs = list(range(0, max(1, width - tile + 1), step))
    ys = list(range(0, max(1, height - tile + 1), step))
    if xs[-1] != width - tile:
        xs.append(width - tile)
    if ys[-1] != height - tile:
        ys.append(height - tile)
    return [
        ((x, y, tile, tile), 0.58)
        for y in ys
        for x in xs
    ][: config.max_candidates_per_image]


def _rgba_crop(
    image: np.ndarray,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    x, y, width, height = bbox
    crop = image[y : y + height, x : x + width]
    alpha = mask[y : y + height, x : x + width]
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    rgba = cv2.cvtColor(crop, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    return rgba


def _save_rgba(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(
        ".png",
        cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA),
    )
    if not success:
        raise RuntimeError(f"Gagal menulis candidate {path}")
    encoded.tofile(path)


def _dhash(rgba: np.ndarray, hash_size: int = 16) -> int:
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
    small = cv2.resize(
        gray,
        (hash_size + 1, hash_size),
        interpolation=cv2.INTER_AREA,
    )
    differences = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in differences.flatten():
        value = (value << 1) | int(bit)
    return value


def _hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


__all__ = [
    "ExtractedCandidate",
    "ExtractionConfig",
    "build_curated_pack",
    "extract_dataset",
    "infer_category",
    "infer_tags",
    "make_contact_sheets",
    "prepare_workdirs",
    "write_review_files",
]
