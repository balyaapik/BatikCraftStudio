# Milestone 3B — Brush Refinement

Milestone 3B improves the raster paint workflow without changing the `.batikcraft`
schema or the one-history-entry-per-stroke contract introduced in Milestone 3A.

## Controls

The Brush dock now provides:

- brush size from 1–256 px;
- presets at 4, 12, 24, 48, and 96 px;
- opacity from 1–100%;
- hardness from 0–100%;
- smoothing from 0–100%;
- the existing offline color picker.

Keyboard shortcuts:

- `B`: Brush;
- `E`: Eraser;
- `V`: Select;
- `[`: previous brush-size step;
- `]`: next brush-size step.

The size-step sequence is bounded and predictable rather than adding or subtracting
an arbitrary fixed value.

## Rendering contract

`apply_paint_stroke()` keeps backward-compatible defaults:

```python
opacity=1.0
hardness=1.0
smoothing=0.0
```

Refined strokes are produced by:

1. validating pointer samples and refinement values;
2. applying endpoint-preserving moving-average smoothing;
3. resampling the polyline at spacing relative to brush diameter;
4. generating an antialiased hard or soft round alpha stamp;
5. combining stamps into one stroke mask;
6. compositing color or reducing alpha for the eraser;
7. encoding the result as deterministic PNG bytes.

Stroke resampling is bounded to prevent accidental unbounded work from malformed
input.

## Opacity and hardness

Opacity controls the maximum alpha contributed by the complete stroke. Separate
strokes may build opacity naturally through normal alpha compositing.

Hardness controls the solid inner radius of the brush:

- `100%`: hard antialiased edge;
- intermediate values: solid center with a feathered edge;
- `0%`: feathering extends through almost the complete radius.

Eraser opacity is supported. A partial-opacity eraser reduces existing alpha rather
than immediately replacing pixels with full transparency.

## Smoothing

Smoothing preserves the first and last pointer samples. Intermediate points are
blended with a bounded local neighborhood. The operation is deterministic and does
not depend on mouse polling frequency after the samples have been collected.

## Brush cursor

Brush and eraser modes display a circular dual-outline cursor matching the on-screen
brush diameter. The two outlines remain visible on light and dark artwork. The cursor
is hidden outside the project canvas and while the Select tool is active.

## History and metadata

Mouse press through mouse release remains one undoable mutation. Paint-layer
properties record the last committed values:

- `last_brush_size`;
- `last_brush_opacity`;
- `last_brush_hardness`;
- `last_brush_smoothing`;
- `last_tool`;
- `stroke_count`.

Undo and redo restore both the PNG asset bytes and these properties.

## Deferred

The following remain outside Milestone 3B:

- pressure sensitivity;
- custom brush-tip images;
- spacing and scatter controls;
- symmetry and mirror drawing;
- motif stamps and isen-isen tools;
- vector paths;
- AI-assisted drawing.

## Manual validation

On Windows, verify:

1. the circular cursor follows the pointer at 100%, 125%, 150%, and 200% display scale;
2. `[` and `]` do not trigger while editing numeric fields;
3. partial-opacity brush strokes and eraser strokes look consistent;
4. hardness changes are visible at larger brush sizes;
5. one `Ctrl+Z` removes one complete stroke.
