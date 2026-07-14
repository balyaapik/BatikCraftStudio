# Milestone 4E — Canvas Rulers and Object-First Layer Containers

Milestone 4E clarifies the BatikCraft document hierarchy and removes the remaining shape workflow
that created one layer for every geometric object.

## Document hierarchy

The editor now follows this hierarchy:

```text
Project
├── Folder Layer
│   ├── Layer Komposisi
│   │   ├── Rectangle
│   │   ├── Ellipse
│   │   ├── Motif
│   │   └── Imported Asset
│   └── Layer Canting
│       ├── Stroke 1
│       └── Stroke 2
└── Layer Latar
    └── Polygon
```

Rules:

- a layer is a container for zero or more objects;
- a folder contains layers and nested folders;
- objects do not become folders;
- drawing multiple shapes while one layer is active adds multiple objects to that layer;
- drawing while a folder is active creates a child layer inside that folder, then inserts the object;
- legacy shape layers remain readable and editable for backward compatibility.

## Canvas rulers

A horizontal and vertical pixel ruler surround the canvas. Tick intervals use a dynamic 1/2/5
sequence so labels remain readable at different preview scales. The ruler origin matches project
coordinate `(0, 0)`, not the application window. Moving the pointer over the canvas shows blue
position guides on both rulers.

## Right-click canvas menu

The Select tool context menu now contains:

```text
Group
Ungroup
New Layer
New Layer Folder
Move to Layer
Fill Color…
Open Batik Process Studio
```

Marquee selection remains passive. Grouping only occurs after the explicit Group command.

`Move to Layer` lists user-facing layers using their full folder path. Moving several selected
objects is one Undo transaction.

## Closed-shape fill

`Fill Color…` is enabled only when the selection contains one or more closed shape objects:

- rectangle;
- ellipse;
- polygon.

Lines are open geometry and are never filled. Applying a fill to several closed shapes is one Undo
transaction and preserves each object's stroke, transform, layer membership, and group metadata.

## Compatibility

The project schema remains `1.1`. Shape objects use the existing `LayerObject` representation with:

```text
kind = shape
source_format = VECTOR_SHAPE_OBJECT
shape_type = rectangle | ellipse | polygon | line
closed_shape = true | false
```

Folders continue to use `LayerNodeKind.GROUP`; regular layers continue to use
`LayerNodeKind.LAYER` and store their objects in `layer.objects`.
