# Canvas Rendering

How the main canvas turns a project into pixels, and the constraints that keep it fast.

## Pipeline

```text
wheel event
  ↓ immediately: update the zoom label, scale the last cached image
  ↓ schedule a debounce (100 ms)
debounce fires (one render per zoom burst)
  ↓ CachedViewportRenderer.get_or_render_tile()
      ↓ TileCache hit    → reuse
      ↓ TileCache miss   → ObjectRenderCache → render a single object
  ↓ assemble tiles on a worker thread (Pillow only)
  ↓ return to the Tk main thread → create PhotoImage → place on canvas
```

Each tile is placed as a separate Tk canvas image, so scrolling only renders the tiles
that just became visible.

## Tiles

A tile covers a square block of *project* space, but the block shrinks as zoom grows so
that the tile's size **on screen** stays bounded by `MAX_TILE_SCREEN_PX` (768 px).

This matters more than it sounds. When tiles always covered 512 project pixels, one
tile at 800% zoom was 4096×4096 — 64 MB — and a full screen needed roughly 576 MB. The
cache evicted itself every frame, and past a certain zoom the allocation failed outright
and the canvas went blank. Halving the project area each time the on-screen side crosses
the limit keeps both the per-tile cost and the visible tile count roughly constant at
every zoom level.

## Caches

| Cache | Keyed by | Default budget |
| --- | --- | --- |
| `TileCache` | Project revision, zoom bucket, tile size, tile coordinates, background, visibility revision | 128 MiB |
| `ObjectRenderCache` | Object id, asset digest, bounds, scale, rotation, shear, fill, opacity, scale bucket | 64 MiB |
| Prepared layer images | Layer id, asset, zoom, scale, rotation | 192 MiB |

Both caches are bounded by **bytes**, not entry count, and evict least-recently-used
entries. Selection, cursor position, and tooltip state are deliberately excluded from
the cache keys so that moving the mouse never invalidates artwork.

Tile keys use a **content signature** rather than the global project revision. With a
global revision, a single pen stroke bumped the revision and every tile lost its cache
entry — which is why the canvas used to feel like it re-rendered from scratch on every
stroke.

## Shape Rasterisation

Shapes are drawn supersampled and then scaled down. Three rules keep that affordable:

**The supersample factor follows an area budget, not the longest side.** The old rule
was `4 if max(width, height) <= 2048 else 2`, which ignores area entirely. A diagonal
line with a 6010×4510 bounding box therefore still used factor 2 and allocated a
12020×9020 buffer — 434 MB — to draw one thin line.

| Output area | Factor |
| --- | --- |
| ≤ 4.2 MP | 4 |
| ≤ 48 MP | 2 |
| larger | 1 |

**Downscaling uses `BOX`, not `LANCZOS`.** For an integer factor, box averaging is the
mathematically correct operation for supersampling: no ringing at stroke edges, and
about twice as fast. Measured difference on the alpha channel is 0.04/255 on average.

**Large shapes render in horizontal bands.** Each band is drawn and immediately scaled
down, so peak memory stays near 16 MB instead of hundreds. The pixel output is identical
to a single-pass render; a regression test asserts byte equality.

Measured on a project of 60 line objects on a 3000×2200 canvas, cold tile render:

| Zoom | Before | After |
| --- | --- | --- |
| 0.5× | 1594 ms | 699 ms |
| 1.0× | 6743 ms | 2723 ms |
| 4.0× | 25128 ms | 9283 ms |

## Coordinate Spaces

Three spaces are easy to confuse, and confusing them has caused real bugs:

| Space | Origin | Used by |
| --- | --- | --- |
| Widget | Top-left of the visible canvas widget | `event.x`, `event.y` |
| Canvas | Top-left of the scrollable canvas region | `create_oval`, `create_line`, `create_image` |
| Project | Top-left of the project canvas | Hit testing, sessions, stored geometry |

`canvas.canvasx()` and `canvas.canvasy()` convert widget to canvas. `_project_point()`
converts widget to project; `_screen_point()` converts project back to canvas.

**Drawing an overlay at raw `event.x`/`event.y` is a bug** whenever the canvas can
scroll: the item lands off by exactly the scroll distance. The brush cursor ring is
positioned by round-tripping through `_project_point` then `_screen_point`, which
guarantees it sits exactly where the tool will act regardless of scroll, zoom, or ruler
width.

## Pointer Interaction

Runtime patches installed at startup keep the pointer path cheap:

| Module | Responsibility |
| --- | --- |
| `realtime_canvas_patch` | Coalesces pointer bursts into one preview per frame; one persistent render worker instead of a thread per render |
| `inkscape_canvas_patch` | Retained drag proxy; commits all transforms in one mutation; invalidates only dirty tiles |
| `inkscape_pointer_hotpath` | Reduces mouse motion to three constant-time operations |
| `canvas_selection_semantics` | Selection rules for locked objects and select-all |

These are installed as monkey patches on `MultiObjectEditorWorkspaceView` before the
application imports the editor classes. Subclass overrides therefore still win through
the MRO. Consolidating them into the core editor is a known piece of technical debt.

## Hit Testing

`point_hits_affine_object` tests the object's **bounding box** only. That is enough for
most objects but wrong for lines: a corner-to-corner diagonal has a canvas-sized
bounding box and a few pixels of ink. The consequences were real — a line swallowed
every click inside its box, and when another wide-box object sat on top, the line itself
could never be selected.

`imaging/object_hit_mask.py` adds a second stage: after the bounding box matches, the
object's actual alpha is sampled from a low-resolution, LRU-cached mask (longest side
192 px, dilated by one pixel so thin strokes stay clickable). If a mask cannot be built,
the test falls back to bounding-box behaviour so no object becomes unreachable.
