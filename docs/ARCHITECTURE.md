# Architecture

## Scope

BatikCraft Studio is the desktop authoring application. It creates and edits batik
motifs, performs object batikfication, prepares patterns, and packages versioned work for
publication.

The BatikCraft website owns marketplace concerns: public listings, bidding, payment,
winners, licensed downloads, and transaction history. The desktop application is never
the source of truth for auction state.

## Package Layout

```text
src/batikcraft_studio/
├── __main__.py      Entry point and ordered startup sequence
├── app.py           Root lifecycle and global menu
├── config.py        Application metadata and workspace definitions
├── domain/          Immutable value objects and the Project aggregate
├── application/     Session classes, one concern per subclass
├── imaging/         Rendering, caches, brushes, shapes, hit masks
├── persistence/     Archives, manifests, export locations
├── ai/              Model runtimes, installers, generation providers
├── assets/          Asset pack builder and per-user store
└── ui/              Tkinter views, editors, dialogs, runtime patches
```

## Dependency Direction

```text
ui  →  application  →  domain
        ↓
      imaging, persistence, ai, assets
```

`domain` imports nothing from the layers above it. `imaging` is pure Pillow work and never
imports Tkinter. AI code never manipulates Tkinter widgets directly. When a rendering
helper appears to need UI state, that state belongs somewhere else.

## Session Composition

Application behaviour is assembled by subclassing rather than by configuration.
`ProjectSession` is an alias for the most derived class in the chain:

```text
ProjectSession = RasterLineProjectSession
    → AIBatikBackgroundProjectSession
        → OutlineCleanupProjectSession
            → … → PaintProjectSession → base session
```

Each subclass adds exactly one concern and delegates the rest through `super()`. To change
how a feature behaves, locate the subclass that owns it instead of editing the base.

One consequence is worth knowing: `RasterLineProjectSession` merges a line into the active
raster canvas layer's bitmap rather than creating an object. A line is therefore not always
an object, and code that scans only objects will miss it.

## Domain Model

```text
Folder
├── Subfolder
│   └── Sublayer
│       ├── Object 1
│       └── Object 2
└── Canting Layer (raster bitmap)
```

Layers organise the stack; objects are the smallest selectable unit. `LayerObject` and its
value objects are frozen dataclasses, which makes them safely hashable as cache keys and
cheap to compare for change detection.

Object kinds: `RASTER`, `PAINT_STROKE`, `ERASER_STROKE`, `SHAPE`, `MOTIF`, `ISEN`.

## Rendering

The canvas renders through a tile cache with byte-bounded LRU eviction. The full design —
tile sizing across zoom levels, cache keys, shape rasterisation budgets, coordinate
spaces, and hit testing — is documented in [`CANVAS_RENDERING.md`](CANVAS_RENDERING.md).

## Threading Rules

- Tkinter widgets are touched only from the main thread.
- Image processing, compression, upload, and AI inference run on worker tasks.
- Workers emit plain data or immutable result objects, never widgets.
- Worker results reach the UI through `after()`.
- Cancellation is cooperative and checked between stages.
- Closing a project must not silently discard an active task or dirty state.

## Startup Order

`__main__.main()` runs a deliberately ordered sequence before any UI exists: dependency
bootstrap, private installer dispatch, managed package activation, storage directories,
runtime compatibility shims, model connectivity, integrity guards, canvas runtime patches,
and finally the application shell.

Several steps must complete before any UI module captures a function through
`from … import`. The comments in that file explain each one; read them before reordering.

## Batikfication Strategy

Two stages, both retained:

1. **Procedural** — segment an object, fill its silhouette with a selected batik pattern,
   preserve the contour, return an RGBA layer.
2. **Generative** — condition a model on image, mask, edge map, style, palette, parameters,
   and seed to produce editable variations.

The procedural path also serves as the pre-processing stage for the model pipeline.

## Security Boundary

- Authentication tokens use the operating system credential service.
- No blockchain private key, payment credential, or bidder secret is stored on the desktop.
- Public previews are watermarked.
- The website validates licence and bidding rules.
