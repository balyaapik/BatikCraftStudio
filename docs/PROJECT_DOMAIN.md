# Project Domain — Milestone 2A

Milestone 2A introduces the non-GUI document model used by the future canvas,
serializer, Object Batikfication, and publishing workflows.

## Package Boundary

The public API is exposed from:

```python
from batikcraft_studio.domain import Project, Layer, CanvasSpec
```

The domain package does not import Tkinter, Pillow, OpenCV, PyTorch, networking,
or file-dialog modules.

## Aggregate Root

`Project` owns:

- a stable UUID;
- schema version;
- immutable `ProjectMetadata`;
- immutable `CanvasSpec`;
- ordered immutable `Layer` descriptors;
- transient active-layer selection;
- creation/update timestamps;
- revision and saved-revision counters.

All content mutations pass through `Project`. This prevents the UI from changing
layer order, metadata, or canvas configuration without validation and dirty-state
tracking.

## Dirty-State Rules

A newly created project is unsaved:

```python
project = Project.create("Flora Otomotif", "Balya Rochmadi")
assert project.is_dirty
```

After persistence, the serializer must call:

```python
project.mark_saved()
```

Meaningful metadata, canvas, or layer changes increment `revision`. No-op updates
and active-layer selection do not increment it. Selection is treated as transient
UI state rather than document content.

## Value Objects

### `ProjectMetadata`

Validates and normalizes:

- title and creator;
- description length;
- up to 20 tags;
- duplicate tags case-insensitively.

### `CanvasSpec`

Validates:

- integer width and height;
- dimensions from 1 to 16,384 pixels;
- `#RRGGBB` background color.

### `Transform`

Stores finite non-destructive placement values:

- x/y position;
- rotation in degrees;
- x/y scale.

Zero scale is rejected. Negative scale remains valid so later tools can represent
horizontal or vertical mirroring without destructively modifying pixels.

### `Layer`

Stores project-level layer metadata only. It does not render images.

Supported kinds:

- `raster`;
- `paint`;
- `shape`;
- `batikified_object`.

`asset_ref` is only a logical reference in Milestone 2A. Actual asset storage and
path-security rules belong to Milestone 2B.

## Layer Operations

`Project` provides validated operations for:

- add;
- get;
- update;
- remove;
- reorder;
- select.

Layer IDs are immutable UUIDs and must be unique within a project. Layer values are
immutable; updates produce a replacement while preserving the original ID.

## Error Model

- `ProjectValidationError` — one or more invariant violations;
- `DuplicateLayerError` — duplicate layer UUID;
- `LayerNotFoundError` — unknown layer UUID;
- `ProjectDomainError` — common base exception.

## Deferred to Milestone 2B

Milestone 2A intentionally does not implement:

- JSON conversion;
- `.batikcraft` ZIP creation;
- atomic save/open;
- asset hashing;
- archive path validation;
- schema migration.

Those features must consume this domain API rather than duplicating document
validation in the persistence layer.
