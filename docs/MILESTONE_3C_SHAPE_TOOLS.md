# Milestone 3C — Shape and Line Tools

Milestone 3C adds non-destructive shape layers to the native editor and extends the
Layers dock with a right-click workflow for creating and managing layers.

## Shape types

The editor provides:

- Line (`L`);
- Rectangle (`R`);
- Ellipse (`O`);
- regular Polygon (`P`).

Click and drag on the project canvas to create a shape. The shape is committed on
mouse release as one undoable operation.

## Modifiers

- `Shift` snaps a line to 45-degree increments;
- `Shift` constrains rectangle, ellipse, and polygon bounds to a square;
- `Alt` treats the initial pointer position as the shape center;
- `Shift+Alt` combines both behaviors.

The modifier state is read when previewing and when committing the shape.

## Non-destructive storage

Shape layers use `LayerKind.SHAPE` and do not require an embedded PNG asset. Their
properties contain validated JSON-compatible data:

- `shape_type`;
- `geometry_width` and `geometry_height`;
- `pixel_width`, `pixel_height`, and renderer padding;
- `fill_enabled` and `fill_color`;
- `stroke_enabled`, `stroke_color`, and `stroke_width`;
- `polygon_sides`;
- line orientation.

The existing layer transform remains responsible for position, rotation, scale, and
mirror operations. Layer opacity applies to the rendered shape as a whole.

## Shape dock

The **Shape** tab edits the selected shape layer:

- width and height;
- fill enabled and fill color;
- stroke enabled and stroke color;
- stroke width;
- polygon side count from 3–12.

Line layers always require a stroke and do not use a fill. Other shape types require
fill, stroke, or both.

## Rendering

Shape geometry is rendered locally with Pillow:

1. validate all stored properties;
2. calculate the requested preview dimensions;
3. draw at a supersampled resolution;
4. downsample with LANCZOS for antialiased edges;
5. apply mirror, rotation, and layer opacity through the common renderer;
6. composite the result according to layer order.

Shape selection uses the same transformed bounds as raster and paint layers.

## Layers right-click menu

Right-clicking the Layers list selects the item under the pointer and opens a native
context menu.

The **New Layer** submenu contains:

- Paint Layer;
- Line;
- Rectangle;
- Ellipse;
- Polygon.

Context actions also include:

- Duplicate Layer;
- Delete Layer;
- Show/Hide Layer;
- Lock/Unlock Layer.

Creating a shape from the context menu places a default-sized shape at the project
center and uses the current Shape dock style settings.

## History and persistence

Shape creation and each property update are one session mutation. Undo/redo restores:

- shape geometry and style;
- transform and selection;
- layer order and visibility;
- project revision and dirty state.

Shape layers survive `.batikcraft` save/reopen without adding binary assets. Existing
raster and paint project files remain compatible because the schema version is
unchanged.

## Offline icons

Line, rectangle, ellipse, polygon, and layer-add controls use crisp Pillow-generated
alpha masks alongside the existing bundled Font Awesome Free icons. No icon download
or installed system icon font is required.

## Deferred

The following remain outside Milestone 3C:

- arbitrary polygon node editing;
- bezier and freeform vector paths;
- boolean path operations;
- snapping guides and alignment distribution;
- motif stamps;
- mirror or radial symmetry drawing;
- AI-assisted shape generation.

## Manual Windows validation

Verify locally:

1. right-click selects the intended layer before opening the menu;
2. **New Layer** creates each listed layer type;
3. Shift and Alt behave correctly at 100–200% display scaling;
4. shape preview matches the committed result;
5. shape layers can be selected and dragged on canvas;
6. shape fill and stroke changes survive save/reopen;
7. one `Ctrl+Z` removes one newly created shape.
