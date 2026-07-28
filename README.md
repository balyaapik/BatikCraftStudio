# BatikCraft Studio

<img width="512" height="512" alt="image" src="https://github.com/user-attachments/assets/def188cc-3987-42ec-98a3-c5ba45e939bb" />



A native desktop studio for composing, drawing, and editing Indonesian batik motifs.

BatikCraft Studio is a Python and Tkinter application built around an offline asset
library. It combines a non-destructive object model, raster painting tools, and
optional AI assistance so that a designer can build a complete batik composition
without an internet connection.

**Version 0.9.21** · Python 3.11+ · Windows, macOS, Linux

---

## Table of Contents

- [What It Does](#what-it-does)
- [Screens and Layout](#screens-and-layout)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Document Model](#document-model)
- [Asset Packs](#asset-packs)
- [Kaggle Asset Builder](#kaggle-asset-builder)
- [AI Features](#ai-features)
- [Development](#development)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [Project Team](#project-team)
- [License and Notices](#license-and-notices)

---

## What It Does

The desktop application covers the creative half of the batik workflow. Bidding,
transactions, and licence administration happen on the BatikCraft website; the studio
prepares and packages the work.

Implemented and working today:

- **Native shell** — Tkinter interface with an offline icon toolbar and menu bar.
- **Project format** — `.batikcraft` archives with integrity validation and atomic
  saves. Schema `1.0` projects migrate to `1.1` on open.
- **Asset formats** — `.batikasset` for a single portable asset, `.batikpack` for a
  library pack with manifest, tags, categories, thumbnails, and versioning.
- **Asset library** — install, replace, uninstall, search, filter, preview, and
  double-click placement. Packs live in a per-user global library so thousands of
  assets are never copied into every project.
- **Document structure** — folders, subfolders, sublayers, many objects per layer, and
  object-sized selection.
- **Object editing** — visibility, lock, ordering, duplicate, delete, numeric
  transform, and full undo/redo.
- **Painting** — brush and eraser. Strokes merge into a raster canvas layer, and the
  eraser removes pixels from objects and raster layers alike.
- **Shapes** — rectangle, ellipse, and polygon stay non-destructive vector objects.
  Lines are rasterised on creation so they erase like brush strokes.
- **Procedural motifs** — Kawung, Truntum, Ceplok, and Lereng fallbacks plus automatic
  isen-isen filling.
- **Humanize** — non-destructive irregularity applied to placed objects.
- **Asset pipeline** — Kaggle notebooks for discovery, deduplication, extraction, alpha
  cleaning, review, thumbnails, and validated pack export.

Optional AI features (local SDXL, OpenAI, Gemini) are described in
[AI Features](#ai-features).

---

## Screens and Layout

The main editor keeps only three permanent regions:

```text
Asset Library  |  Canvas  |  Layer Stack
```

Drawing settings never crowd the docks with tabs. The **Draw**, **Edit**, and **Asset**
menus open small windows on demand and close again when the work is done.

---

## Installation

### Requirements

- Python 3.11 or newer
- Tkinter (bundled with most CPython builds; on Debian/Ubuntu install `python3-tk`)

### From source

```bash
git clone https://github.com/balyaapik/BatikCraftStudio.git
cd BatikCraftStudio
python -m venv .venv
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install and run:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m batikcraft_studio
```

### Optional extras

| Extra | Installs | Use it for |
| --- | --- | --- |
| `dev` | pytest, ruff | Running the test suite and linter |
| `model-downloader` | huggingface-hub, tqdm | Downloading AI runtimes from the app |
| `ai-local` | torch, diffusers, transformers, peft | Offline SDXL generation |
| `ai-openai` | openai, keyring | OpenAI image generation |
| `ai-gemini` | google-genai, keyring | Google Gemini image generation |

Install one with, for example, `python -m pip install -e ".[dev,ai-local]"`.

### Desktop builds

Packaged Windows executables are produced by the `build-desktop` GitHub Actions
workflow (`.github/workflows/build-desktop.yml`).

---

## Quick Start

1. Create or open a project.
2. Install a pack through **Asset → Install Asset Pack…**.
3. Search or filter assets in the left panel.
4. Select a destination sublayer in the right panel.
5. Double-click an asset to place it on the canvas.
6. Arrange objects on the canvas or in the tree.
7. Use **Edit → Transform…** for numeric transforms.
8. Use **Asset → Metadata** or **Humanize** as needed.
9. Open **Draw** only when you need to paint or draw a shape.
10. Save as `.batikcraft`.

---

## Document Model

```text
Folder
├── Subfolder
│   └── Sublayer
│       ├── Asset Object 1
│       ├── Asset Object 2
│       └── Asset Object 3
└── Canting Layer
    ├── Canting Stroke 1
    ├── Canting Stroke 2
    └── Erase 3
```

Folders organise the stack. Sublayers hold many objects. An object is the smallest
selectable unit. A library asset is copied into the project only when it is actually
placed on the canvas.

---

## Asset Packs

A pack uses the `.batikpack` extension and this layout:

```text
manifest.json
assets/
  asset-001.batikasset
thumbnails/
  asset-001.png
```

Official categories: `motif-pokok`, `isen-isen`, `ornamen`, `tekstur`, `lainnya`.

Installed packs are stored per user:

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\BatikCraftStudio\asset-library` |
| Linux, macOS | `$XDG_DATA_HOME/BatikCraftStudio/asset-library`, defaulting to `~/.local/share/…` |

Set `BATIKCRAFT_ASSET_LIBRARY` to override the location.

---

## Kaggle Asset Builder

Turning a raw batik photo dataset into a curated pack:

```text
batik dataset
→ exact and visual deduplication
→ full / component / grid candidates
→ alpha cleaning
→ category and tag suggestion
→ contact sheets + review.csv
→ human curation
→ canonical .batikasset + thumbnail
→ manifest.json
→ validated .batikpack
```

| Path | Purpose |
| --- | --- |
| `notebooks/kaggle_batik_asset_pack_builder.ipynb` | The notebook |
| `notebooks/kaggle_asset_pipeline.py` | Extraction module |
| `src/batikcraft_studio/assets/builder.py` | Pack format builder, shared with the tests |

Segmentation is deliberately not treated as fully automatic. Historical motifs,
isen-isen, and interlocking areas of cloth still require human curation.

---

## AI Features

AI is optional and off by default. The application runs completely offline without it.

- **Local SDXL** — install the `ai-local` extra and download a runtime from the
  Dependencies window. Generation runs entirely on your machine.
- **Cloud providers** — OpenAI, Google Gemini, and IBM watsonx.ai. API keys are stored
  in the system keyring.
- **Style LoRA training** — Kaggle notebooks under `notebooks/` train a batik style
  adapter that can be activated for generation. See
  [`docs/KAGGLE_BATIKBREW_SDXL_STYLE_LORA.md`](docs/KAGGLE_BATIKBREW_SDXL_STYLE_LORA.md).

See [`docs/AI_NFT_MARKETPLACE_AUDIT.md`](docs/AI_NFT_MARKETPLACE_AUDIT.md) for the
current state of every provider and the training-to-marketplace flow.

A Settings toggle chooses between online and offline model behaviour, and the runtime
integrity checks refuse to load an incomplete model rather than failing halfway.

---

## Development

```bash
ruff check .
pytest
```

Both run in CI on every push. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the
project layout and [`docs/TESTING.md`](docs/TESTING.md) for how the suite is organised.

Contributions are welcome — read [`CONTRIBUTING.md`](CONTRIBUTING.md) first.

---

## Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| 1 — Application Foundation | Package, Tkinter shell, theme, menus, shortcuts, CI | Done |
| 2 — Project and Workspace Core | Domain, `.batikcraft` serializer, atomic save, undo/redo | Done |
| 3A — Basic Paint Layer | Brush, eraser, colour picker, one stroke per history entry | Done |
| 3B — Brush Refinement | Smoothing, opacity, hardness, presets, circular cursor | Done |
| 3C — Shape and Line Tools | Line, rectangle, ellipse, polygon, fill, stroke, modifiers | Done |
| 3D — Cap Isen and Layout | Procedural isen, batik palette, mirror, rotate, preview | Done |
| 3D.1 — Motif Pokok | Kawung, Truntum, Ceplok, Lereng, automatic isen filling | Done |
| 3E — Object Tree and Humanize | Folders, sublayers, objects, `.batikasset`, metadata | Done |
| 3F — Asset Library | `.batikpack`, pack management, menu-driven tool windows | Done |
| 3G — Kaggle Asset Builder | Discovery, curation, validated pack export | Done |
| 4 — Object Batikfication | Background removal, style selection, editable results | In progress |
| 5 — Pattern Engine | Straight, mirror, half-drop, half-brick, seamless export | Planned |
| 6 — AI Integration | Model loader, conditioning, worker threads, cancellation | In progress |
| 7 — Licensing and Website Bridge | Versioning, hashing, watermark, publish manifest | Planned |

Further manual tooling under consideration: group transform, vector path and node
editing, per-point pressure curves, real-time canting symmetry, asset region recolour,
and an in-application curation manager.

---

## Documentation

Start at [`docs/README.md`](docs/README.md) for the full index.

| Document | Covers |
| --- | --- |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Working in the editor, tool by tool |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, session composition, threading |
| [`docs/CANVAS_RENDERING.md`](docs/CANVAS_RENDERING.md) | Tile cache, zoom, coordinate spaces, hit testing |
| [`docs/PROJECT_FORMAT.md`](docs/PROJECT_FORMAT.md) | The `.batikcraft` archive |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Environment, layout, and conventions |
| [`docs/TESTING.md`](docs/TESTING.md) | Test suite organisation |
| [`docs/EFFICIENCY_REFACTOR.md`](docs/EFFICIENCY_REFACTOR.md) | Performance and consolidation notes |
| [`docs/AI_NFT_MARKETPLACE_AUDIT.md`](docs/AI_NFT_MARKETPLACE_AUDIT.md) | AI providers, training, NFT, marketplace |
| [`docs/WEB_LISTING_FEE.md`](docs/WEB_LISTING_FEE.md) | Listing fees and the publish flow |

---

## Project Team

| Name | Handle |
| --- | --- |
| Hasan Nafi Rais | Balyaapik |
| Siti Fadilah Nur Khasanah | Dila |
| Shabrina Enma | shabrina enma |
| Palupi Fitria Ningrum | Wendy_Son |
| Anindya Nareshwari Nugroho | — |

See [`CONTRIBUTORS.md`](CONTRIBUTORS.md) for roles and contribution details.

Parts of this codebase were written with the help of AI coding assistants. All
AI-assisted output was reviewed, tested, and accepted by the team before it was merged.

---

## License and Notices

Third-party dependency licences are listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Batik motifs carry cultural meaning. Historical motifs such as Kawung, Truntum, and
Parang belong to a living tradition; treat generated and derived work with the respect
that tradition deserves, and credit sources when a design is based on documented
regional patterns.
