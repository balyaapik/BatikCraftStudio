# Milestone 3A — Basic Paint Layer

Milestone 3A adds native freehand brush and eraser tools without changing the `.batikcraft` archive schema.

## User workflow

1. Open or create a project.
2. Choose Brush (`B`) or Eraser (`E`) from the left tool rail.
3. Set brush size and brush color in the **Brush** dock tab.
4. Press and drag inside the project canvas.
5. Release the mouse to commit the complete stroke.
6. Use `Ctrl+Z` or `Ctrl+Y` to undo or redo one complete stroke.
7. Return to Select with `V`.

If the active layer is not an editable paint layer, the first stroke creates a transparent full-canvas paint layer automatically.

## Paint-layer contract

- `LayerKind.PAINT` identifies paint layers.
- Each paint layer owns one RGBA PNG asset with the same pixel dimensions as the project canvas.
- The layer remains centered on the canvas with rotation `0` and scale `1` while drawing.
- Painting a transformed or locked paint layer is rejected; the UI selects or creates a suitable layer instead.
- Brush and eraser operations modify only the paint layer asset.
- `stroke_count` and `last_tool` are stored in layer properties for deterministic revision tracking.

## History behavior

Mouse movement is preview-only. The session snapshots the project and assets once when the mouse button is released, so a complete stroke produces exactly one undo history entry. Undo and redo restore both the PNG bytes and paint-layer metadata.

Creating an automatically required paint layer is a separate history entry from the first stroke.

## Raster behavior

- Brush tips are round.
- Connected points use round joins.
- Eraser strokes replace affected pixels with transparent RGBA pixels.
- Stroke input, brush size, color, image dimensions, and asset readability are validated before mutation.
- PNG output is normalized through Pillow and stored directly in the project asset map.

## Deliberately deferred

- pressure sensitivity;
- custom brush presets and textures;
- opacity and hardness controls;
- smoothing algorithms beyond round line joins;
- symmetry and mirror drawing;
- vector paths;
- motif stamps and isen-isen tools;
- AI-assisted drawing.

These belong to later manual motif and batik-specific tool milestones.
