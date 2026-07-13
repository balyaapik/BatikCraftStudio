from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from batikcraft_studio.domain import (
    CanvasSpec,
    Layer,
    Project,
    ProjectMetadata,
    ProjectValidationError,
)


def test_project_rejects_mismatched_timestamp_awareness_without_type_error() -> None:
    metadata = ProjectMetadata(title="Motif", creator="Creator")

    with pytest.raises(ProjectValidationError, match="created_at"):
        Project(
            metadata=metadata,
            created_at=datetime(2026, 7, 14),
            updated_at=datetime(2026, 7, 14, tzinfo=UTC),
        )


def test_project_rejects_updated_time_before_created_time() -> None:
    metadata = ProjectMetadata(title="Motif", creator="Creator")
    created = datetime(2026, 7, 14, 12, tzinfo=UTC)

    with pytest.raises(ProjectValidationError, match="earlier"):
        Project(
            metadata=metadata,
            created_at=created,
            updated_at=created - timedelta(seconds=1),
        )


def test_project_rejects_invalid_aggregate_value_types() -> None:
    metadata = ProjectMetadata(title="Motif", creator="Creator")

    with pytest.raises(ProjectValidationError, match="canvas"):
        Project(metadata=metadata, canvas="2048x2048")  # type: ignore[arg-type]
    with pytest.raises(ProjectValidationError, match=r"layers\[0\]"):
        Project(metadata=metadata, layers=["not-a-layer"])  # type: ignore[list-item]


def test_layer_mutation_no_op_does_not_increment_revision() -> None:
    project = Project.create("Motif", "Creator")
    layer = Layer(name="Layer")
    project.add_layer(layer)
    project.mark_saved()

    returned = project.update_layer(layer.layer_id, opacity=layer.opacity)

    assert returned == layer
    assert project.is_dirty is False
    assert project.revision == project.saved_revision


def test_reordering_to_same_index_is_a_no_op() -> None:
    project = Project.create("Motif", "Creator", canvas=CanvasSpec(512, 512))
    layer = Layer(name="Layer")
    project.add_layer(layer)
    project.mark_saved()

    project.reorder_layer(layer.layer_id, 0)

    assert project.is_dirty is False
