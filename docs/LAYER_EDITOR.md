# Milestone 2D — Raster Layer Editor

Milestone 2D turns the Motif Editor shell into a raster composition workspace. It does
not add painting, vector drawing, Object Batikfication, or AI generation.

## Supported imports

- PNG
- JPEG / JPG

Every accepted source image is decoded with Pillow, converted to RGBA, and stored as
a normalized PNG member under `assets/` in the `.batikcraft` archive. The original
filename and source format are retained as layer properties.

Safety limits:

- maximum side length: 16,384 pixels;
- maximum total pixels: 64,000,000;
- unreadable or empty files are rejected;
- normalized content is verified again by the project archive integrity checks.

## Transform convention

`Transform.x` and `Transform.y` identify the center of a layer in project-space pixels.
Positive rotation values appear clockwise in the Tkinter preview. `scale_x` and
`scale_y` may be negative to represent horizontal or vertical mirroring, but neither
may be zero.

Raster layers record these properties:

```json
{
  "pixel_width": 1200,
  "pixel_height": 800,
  "source_format": "JPEG",
  "original_name": "flower.jpg"
}
```

## Layer ordering

Project layer index `0` is the bottom layer. The final project layer is rendered on
top. The layer panel displays the top layer first for familiar editor behavior.

## Editing operations

- click a visible layer to select it;
- drag an unlocked selected layer to move it;
- edit X, Y, rotation, scale, and opacity through the inspector;
- duplicate or delete the selected layer;
- show/hide and lock/unlock layers;
- move layers up or down in the stack;
- undo and redo up to 100 editor mutations.

Locked layers cannot be moved, transformed, have opacity changed, or be deleted.
Visibility and lock state themselves remain editable.

## Asset ownership

Duplicated layers share the same immutable raster asset. Deleting one duplicate does
not remove the asset while another layer still references it. The asset is removed
from the session only after its final referencing layer is deleted. Undo and redo
restore both project metadata and asset bytes.

## Preview rendering

The editor renders a bounded Pillow preview rather than allocating the full project
canvas at screen scale. The renderer preserves project aspect ratio and composites
visible layers over the project background. Selection uses transformed bounding-box
hit testing; transparent pixels are not yet excluded from selection.

## Keyboard shortcuts

- `Ctrl+I`: import image
- `Ctrl+Z`: undo
- `Ctrl+Y` or `Ctrl+Shift+Z`: redo
- `Ctrl+D`: duplicate selected layer

## Deliberate limitations

- corner handles are visual only; scale and rotation use the inspector;
- drag updates the full preview on mouse release;
- selection uses a rotated bounding box, not alpha-aware hit testing;
- no brush, eraser, shape, text, stamp, mask, or crop tools;
- no Object Batikfication, GAN inference, pattern repeat, licensing, or website calls.
