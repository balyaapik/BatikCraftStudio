# BatikCraft Studio Architecture

## Scope

BatikCraft Studio is the native desktop authoring application. It creates and edits batik motifs, performs object batikfication, prepares seamless patterns, and publishes versioned assets to the BatikCraft website.

The website owns marketplace concerns such as public listings, bidding, payment, winners, downloadable licensed assets, and transaction history.

## Layered Structure

```text
src/batikcraft_studio/
├── app.py                 # root lifecycle and global menu
├── config.py              # application metadata and workspace definitions
├── ui/                    # Tkinter-only presentation layer
├── project/               # project document and .batikcraft serialization
├── workspace/             # editable canvas and layer orchestration
├── imaging/               # masks, contours, palette, and pattern operations
├── batikification/        # object-to-batik application service
├── ai/                    # inference adapters and background jobs
├── licensing/             # design versions and publishing manifests
└── api/                   # BatikCraft website clients
```

Only `app.py`, `config.py`, and `ui/` exist in Milestone 1. Later packages must be added only when their milestone begins.

## Dependency Direction

```text
Tkinter UI
   ↓
Application services
   ↓
Domain models
   ↓
Imaging / project storage / AI adapter / website adapter
```

Domain logic must not import Tkinter. AI code must not directly manipulate Tkinter widgets. UI updates from worker jobs must be scheduled back onto the Tkinter main thread with `after()`.

## Workspace Boundaries

### Dashboard

Project entry, recent files, recovery, and milestone status.

### Motif Editor

Editable canvas, layers, transforms, manual tools, and project state.

### Object Batikfication

Object import, mask correction, style selection, procedural fallback, AI variations, and insertion into the editor.

### Pattern Preview

Non-destructive repeat rendering and seam inspection.

### Publish

Design version freeze, hash, watermark, license configuration, manifest generation, and website upload.

## Project Format Direction

A future `.batikcraft` file will be a ZIP-based editable project containing:

```text
project.batikcraft
├── project.json
├── preview.png
├── assets/
├── masks/
├── renders/
└── metadata/
```

The schema must be versioned and validated before opening. Generated images are caches; source assets, transformations, masks, style identifiers, seeds, and parameters remain the authoritative editable data.

## Object Batikfication Strategy

The feature is introduced in two stages:

1. **Procedural MVP** — segment an object, fill its silhouette using a selected batik pattern, preserve the contour, and return an RGBA layer.
2. **Generative interpretation** — condition the model on image, mask, edge map, style, palette, parameters, and seed to generate several editable variations.

The procedural path is retained as a fallback whenever the model is unavailable.

## Threading Rules

- Tkinter widgets are accessed only from the main thread.
- Image processing, file compression, upload, and AI inference use worker tasks.
- Worker tasks emit plain data or immutable result objects.
- Cancellation is cooperative and checked between processing stages.
- Closing a project must not silently discard an active task or dirty state.

## Security and Marketplace Boundary

- Desktop authentication tokens will be stored using an operating-system credential service when website integration begins.
- No blockchain private key, payment credential, or bidder secret is stored by the desktop application.
- Public previews are watermarked.
- The website validates license and bidding rules; the desktop never becomes the source of truth for auction state.
