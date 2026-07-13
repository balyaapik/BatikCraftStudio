"""Conversion between project domain objects and ``project.json`` data."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from batikcraft_studio.domain import (
    CURRENT_SCHEMA_VERSION,
    CanvasSpec,
    Layer,
    LayerKind,
    Project,
    ProjectMetadata,
    ProjectValidationError,
    Transform,
)
from batikcraft_studio.persistence.errors import (
    ArchiveValidationError,
    UnsupportedSchemaVersionError,
)
from batikcraft_studio.persistence.paths import normalize_archive_path

FORMAT_NAME = "batikcraft-project"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """Integrity metadata for one binary member in a project archive."""

    path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        normalized = normalize_archive_path(self.path)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ArchiveValidationError("Asset size must be a non-negative integer.")
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ArchiveValidationError("Asset sha256 must be 64 lowercase hexadecimal characters.")
        object.__setattr__(self, "path", normalized)


def project_to_manifest(project: Project, assets: Sequence[AssetRecord]) -> dict[str, Any]:
    """Create deterministic JSON-compatible data for a validated project."""

    if not isinstance(project, Project):
        raise ArchiveValidationError("project must be a Project aggregate.")
    project.assert_valid()
    records = _validate_asset_records(assets)
    asset_paths = {record.path for record in records}
    for layer in project.layers:
        if layer.asset_ref is not None:
            normalized_ref = normalize_archive_path(layer.asset_ref)
            if normalized_ref not in asset_paths:
                raise ArchiveValidationError(
                    f"Layer {layer.layer_id} references missing asset {normalized_ref!r}."
                )

    return {
        "format": FORMAT_NAME,
        "schema_version": project.schema_version,
        "project": {
            "id": project.project_id,
            "metadata": {
                "title": project.metadata.title,
                "creator": project.metadata.creator,
                "description": project.metadata.description,
                "tags": list(project.metadata.tags),
            },
            "canvas": {
                "width": project.canvas.width,
                "height": project.canvas.height,
                "background_color": project.canvas.background_color,
            },
            "active_layer_id": project.active_layer_id,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "revision": project.revision,
            "layers": [_layer_to_data(layer) for layer in project.layers],
        },
        "assets": [
            {"path": record.path, "size": record.size, "sha256": record.sha256}
            for record in sorted(records, key=lambda item: item.path)
        ],
    }


def project_from_manifest(data: object) -> tuple[Project, tuple[AssetRecord, ...]]:
    """Build a validated, clean project and its declared asset records."""

    root = _expect_mapping(data, "manifest")
    _expect_keys(root, {"format", "schema_version", "project", "assets"}, "manifest")
    if root["format"] != FORMAT_NAME:
        raise ArchiveValidationError(f"Unsupported project format: {root['format']!r}.")
    schema_version = root["schema_version"]
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Unsupported schema_version {schema_version!r}; expected {CURRENT_SCHEMA_VERSION!r}."
        )

    asset_items = _expect_sequence(root["assets"], "assets")
    records = tuple(_asset_record_from_data(item, index) for index, item in enumerate(asset_items))
    records = _validate_asset_records(records)

    project_data = _expect_mapping(root["project"], "project")
    _expect_keys(
        project_data,
        {
            "id",
            "metadata",
            "canvas",
            "active_layer_id",
            "created_at",
            "updated_at",
            "revision",
            "layers",
        },
        "project",
    )
    metadata_data = _expect_mapping(project_data["metadata"], "project.metadata")
    _expect_keys(
        metadata_data,
        {"title", "creator", "description", "tags"},
        "project.metadata",
    )
    canvas_data = _expect_mapping(project_data["canvas"], "project.canvas")
    _expect_keys(
        canvas_data,
        {"width", "height", "background_color"},
        "project.canvas",
    )
    layer_items = _expect_sequence(project_data["layers"], "project.layers")

    try:
        metadata = ProjectMetadata(
            title=metadata_data["title"],
            creator=metadata_data["creator"],
            description=metadata_data["description"],
            tags=tuple(_expect_sequence(metadata_data["tags"], "project.metadata.tags")),
        )
        canvas = CanvasSpec(
            width=canvas_data["width"],
            height=canvas_data["height"],
            background_color=canvas_data["background_color"],
        )
        layers = tuple(_layer_from_data(item, index) for index, item in enumerate(layer_items))
        revision = project_data["revision"]
        project = Project(
            metadata=metadata,
            canvas=canvas,
            layers=layers,
            project_id=project_data["id"],
            schema_version=schema_version,
            active_layer_id=project_data["active_layer_id"],
            created_at=_parse_datetime(project_data["created_at"], "project.created_at"),
            updated_at=_parse_datetime(project_data["updated_at"], "project.updated_at"),
            revision=revision,
            saved_revision=revision,
        )
    except ProjectValidationError as exc:
        raise ArchiveValidationError(f"Invalid project domain data: {exc}") from exc

    declared_paths = {record.path for record in records}
    for layer in project.layers:
        if layer.asset_ref is not None:
            normalized_ref = normalize_archive_path(layer.asset_ref)
            if normalized_ref not in declared_paths:
                raise ArchiveValidationError(
                    f"Layer {layer.layer_id} references undeclared asset {normalized_ref!r}."
                )
    return project, records


def _layer_to_data(layer: Layer) -> dict[str, Any]:
    return {
        "id": layer.layer_id,
        "name": layer.name,
        "kind": layer.kind.value,
        "asset_ref": layer.asset_ref,
        "visible": layer.visible,
        "locked": layer.locked,
        "opacity": layer.opacity,
        "transform": {
            "x": layer.transform.x,
            "y": layer.transform.y,
            "rotation_degrees": layer.transform.rotation_degrees,
            "scale_x": layer.transform.scale_x,
            "scale_y": layer.transform.scale_y,
        },
        "properties": _json_value(layer.properties, f"layer {layer.layer_id} properties"),
    }


def _layer_from_data(data: object, index: int) -> Layer:
    location = f"project.layers[{index}]"
    item = _expect_mapping(data, location)
    _expect_keys(
        item,
        {
            "id",
            "name",
            "kind",
            "asset_ref",
            "visible",
            "locked",
            "opacity",
            "transform",
            "properties",
        },
        location,
    )
    transform_data = _expect_mapping(item["transform"], f"{location}.transform")
    _expect_keys(
        transform_data,
        {"x", "y", "rotation_degrees", "scale_x", "scale_y"},
        f"{location}.transform",
    )
    properties = _expect_mapping(item["properties"], f"{location}.properties")
    try:
        return Layer(
            layer_id=item["id"],
            name=item["name"],
            kind=LayerKind(item["kind"]),
            asset_ref=item["asset_ref"],
            visible=item["visible"],
            locked=item["locked"],
            opacity=item["opacity"],
            transform=Transform(
                x=transform_data["x"],
                y=transform_data["y"],
                rotation_degrees=transform_data["rotation_degrees"],
                scale_x=transform_data["scale_x"],
                scale_y=transform_data["scale_y"],
            ),
            properties=dict(properties),
        )
    except (ProjectValidationError, TypeError, ValueError) as exc:
        raise ArchiveValidationError(f"Invalid {location}: {exc}") from exc


def _asset_record_from_data(data: object, index: int) -> AssetRecord:
    location = f"assets[{index}]"
    item = _expect_mapping(data, location)
    _expect_keys(item, {"path", "size", "sha256"}, location)
    return AssetRecord(path=item["path"], size=item["size"], sha256=item["sha256"])


def _validate_asset_records(assets: Sequence[AssetRecord]) -> tuple[AssetRecord, ...]:
    if isinstance(assets, (str, bytes, bytearray)) or not isinstance(assets, Sequence):
        raise ArchiveValidationError("assets must be a sequence of AssetRecord values.")
    records: list[AssetRecord] = []
    seen: set[str] = set()
    for item in assets:
        if not isinstance(item, AssetRecord):
            raise ArchiveValidationError("assets must contain only AssetRecord values.")
        collision_key = item.path.casefold()
        if collision_key in seen:
            raise ArchiveValidationError(f"Duplicate asset path: {item.path!r}.")
        seen.add(collision_key)
        records.append(item)
    return tuple(records)


def _json_value(value: object, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArchiveValidationError(f"{location} contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ArchiveValidationError(f"{location} contains an invalid property key.")
            converted[key] = _json_value(item, f"{location}.{key}")
        return converted
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{location}[]") for item in value]
    raise ArchiveValidationError(
        f"{location} contains unsupported value type {type(value).__name__}."
    )


def _expect_mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArchiveValidationError(f"{location} must be an object.")
    if any(not isinstance(key, str) for key in value):
        raise ArchiveValidationError(f"{location} keys must be strings.")
    return value


def _expect_sequence(value: object, location: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ArchiveValidationError(f"{location} must be an array.")
    return value


def _expect_keys(data: Mapping[str, Any], expected: set[str], location: str) -> None:
    actual = set(data)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unexpected {', '.join(sorted(extra))}")
        raise ArchiveValidationError(f"{location} has invalid fields: {'; '.join(details)}.")


def _parse_datetime(value: object, location: str) -> datetime:
    if not isinstance(value, str):
        raise ArchiveValidationError(f"{location} must be an ISO-8601 string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveValidationError(f"{location} is not a valid ISO-8601 datetime.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArchiveValidationError(f"{location} must include a timezone offset.")
    return parsed
