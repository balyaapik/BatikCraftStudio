from __future__ import annotations

from datetime import datetime

import pytest

from batikcraft_studio.domain import (
    CURRENT_SCHEMA_VERSION,
    CanvasSpec,
    DuplicateLayerError,
    Layer,
    LayerKind,
    LayerNotFoundError,
    Project,
    ProjectMetadata,
    ProjectValidationError,
    Transform,
)


def test_metadata_normalizes_text_and_deduplicates_tags() -> None:
    metadata = ProjectMetadata(
        title="  Flora Otomotif  ",
        creator="  Balya Rochmadi ",
        description="  Motif eksperimental.  ",
        tags=("Modern", "modern", " Mobil "),
    )

    assert metadata.title == "Flora Otomotif"
    assert metadata.creator == "Balya Rochmadi"
    assert metadata.description == "Motif eksperimental."
    assert metadata.tags == ("Modern", "Mobil")


@pytest.mark.parametrize("field", ["title", "creator"])
def test_metadata_rejects_blank_required_fields(field: str) -> None:
    values = {"title": "Motif", "creator": "Creator"}
    values[field] = "   "

    with pytest.raises(ProjectValidationError):
        ProjectMetadata(**values)


def test_canvas_validates_dimensions_and_normalizes_color() -> None:
    canvas = CanvasSpec(width=1024, height=768, background_color="#a1b2c3")

    assert canvas.width == 1024
    assert canvas.height == 768
    assert canvas.background_color == "#A1B2C3"


@pytest.mark.parametrize(
    ("width", "height", "color"),
    [
        (0, 100, "#FFFFFF"),
        (100, 20_000, "#FFFFFF"),
        (100.5, 100, "#FFFFFF"),
        (100, 100, "white"),
    ],
)
def test_canvas_rejects_invalid_values(width: object, height: object, color: str) -> None:
    with pytest.raises(ProjectValidationError):
        CanvasSpec(width=width, height=height, background_color=color)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "transform",
    [
        {"scale_x": 0},
        {"scale_y": 0},
        {"x": float("nan")},
        {"rotation_degrees": float("inf")},
    ],
)
def test_transform_rejects_invalid_numeric_values(transform: dict[str, float]) -> None:
    with pytest.raises(ProjectValidationError):
        Transform(**transform)


def test_layer_is_validated_and_properties_are_immutable() -> None:
    layer = Layer(
        name=" Main Flower ",
        kind=LayerKind.BATIKIFIED_OBJECT,
        opacity=0.75,
        asset_ref=" assets/flower.png ",
        properties={"style_id": "kawung_geometry"},
    )

    assert layer.name == "Main Flower"
    assert layer.asset_ref == "assets/flower.png"
    assert layer.properties["style_id"] == "kawung_geometry"
    with pytest.raises(TypeError):
        layer.properties["style_id"] = "parang"  # type: ignore[index]


@pytest.mark.parametrize("opacity", [-0.1, 1.1, float("nan")])
def test_layer_rejects_invalid_opacity(opacity: float) -> None:
    with pytest.raises(ProjectValidationError):
        Layer(name="Layer", opacity=opacity)


def test_layer_update_preserves_identity() -> None:
    layer = Layer(name="Object")
    updated = layer.with_updates(name="Batik Object", visible=False)

    assert updated.layer_id == layer.layer_id
    assert updated.name == "Batik Object"
    assert updated.visible is False
    with pytest.raises(ProjectValidationError):
        layer.with_updates(layer_id="replacement")


def test_new_project_is_valid_and_unsaved() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")

    assert project.schema_version == CURRENT_SCHEMA_VERSION
    assert project.metadata.title == "Motif Baru"
    assert project.layers == ()
    assert project.revision == 0
    assert project.saved_revision == -1
    assert project.is_dirty is True
    assert project.validate() == ()


def test_mark_saved_and_no_op_updates_do_not_create_revision() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    project.mark_saved()

    assert project.is_dirty is False
    project.update_metadata(title="Motif Baru")
    project.update_canvas(width=project.canvas.width)

    assert project.revision == 0
    assert project.is_dirty is False


def test_metadata_and_canvas_updates_increment_revision() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    project.mark_saved()
    original_updated_at = project.updated_at

    project.update_metadata(title="Motif Flora")
    project.update_canvas(width=1024, height=1024)

    assert project.metadata.title == "Motif Flora"
    assert project.canvas.width == 1024
    assert project.revision == 2
    assert project.is_dirty is True
    assert project.updated_at >= original_updated_at


def test_layer_lifecycle_tracks_order_selection_and_dirty_state() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    first = Layer(name="Background")
    second = Layer(name="Main Object")

    project.add_layer(first)
    project.add_layer(second, index=0)

    assert project.layers == (second, first)
    assert project.active_layer_id == second.layer_id
    assert project.revision == 2

    project.reorder_layer(first.layer_id, 0)
    assert project.layers == (first, second)
    assert project.revision == 3

    removed = project.remove_layer(first.layer_id)
    assert removed == first
    assert project.layers == (second,)
    assert project.active_layer_id == second.layer_id
    assert project.revision == 4


def test_removing_active_layer_selects_neighbor_then_none() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    first = Layer(name="First")
    second = Layer(name="Second")
    project.add_layer(first)
    project.add_layer(second)

    project.remove_layer(second.layer_id)
    assert project.active_layer_id == first.layer_id

    project.remove_layer(first.layer_id)
    assert project.active_layer_id is None


def test_duplicate_layer_id_is_rejected() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    original = Layer(name="Original")
    duplicate = Layer(name="Duplicate", layer_id=original.layer_id)
    project.add_layer(original)

    with pytest.raises(DuplicateLayerError):
        project.add_layer(duplicate)


def test_update_layer_returns_validated_replacement() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    layer = Layer(name="Object")
    project.add_layer(layer)

    updated = project.update_layer(layer.layer_id, opacity=0.5, locked=True)

    assert updated.opacity == 0.5
    assert updated.locked is True
    assert project.get_layer(layer.layer_id) == updated


def test_selection_is_transient_and_does_not_change_revision() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    first = Layer(name="First")
    second = Layer(name="Second")
    project.add_layer(first)
    project.add_layer(second)
    project.mark_saved()

    project.set_active_layer(first.layer_id)

    assert project.active_layer_id == first.layer_id
    assert project.is_dirty is False
    assert project.revision == project.saved_revision


def test_unknown_layer_and_invalid_indices_are_rejected() -> None:
    project = Project.create("Motif Baru", "Balya Rochmadi")
    layer = Layer(name="Layer")
    project.add_layer(layer)

    with pytest.raises(LayerNotFoundError):
        project.get_layer("00000000-0000-0000-0000-000000000000")
    with pytest.raises(ProjectValidationError):
        project.add_layer(Layer(name="Other"), index=99)
    with pytest.raises(ProjectValidationError):
        project.reorder_layer(layer.layer_id, 2)


def test_constructor_rejects_unsupported_schema_and_naive_time() -> None:
    metadata = ProjectMetadata(title="Motif", creator="Creator")

    with pytest.raises(ProjectValidationError, match="Unsupported schema_version"):
        Project(metadata=metadata, schema_version="99.0")
    with pytest.raises(ProjectValidationError, match="timezone-aware"):
        Project(metadata=metadata, created_at=datetime(2026, 7, 14))


def test_constructor_rejects_active_layer_that_does_not_exist() -> None:
    metadata = ProjectMetadata(title="Motif", creator="Creator")

    with pytest.raises(ProjectValidationError, match="active_layer_id"):
        Project(
            metadata=metadata,
            active_layer_id="00000000-0000-0000-0000-000000000000",
        )
