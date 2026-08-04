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

- [Problem Statement](#problem-statement)
- [Solution Description](#solution-description)
- [Selected Challenge Theme](#selected-challenge-theme)
- [AI Approach and Architecture](#ai-approach-and-architecture)
- [How IBM Bob Was Used](#how-ibm-bob-was-used)
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

## Problem Statement

Batik is a UNESCO-recognised Indonesian heritage craft, and the people who carry it are
running out of successors. The work is slow, the training is long, and a young designer
who wants to explore a Kawung or Truntum variation has no practical way to do it other
than by hand on cloth. Iterating on a motif costs hours and material.

Three specific gaps shaped this project:

**Digital tools do not understand batik.** General illustration software treats a motif
as arbitrary vector art. It has no concept of *motif pokok* and *isen-isen*, no notion of
the controlled irregularity that distinguishes hand-drawn *batik tulis* from a printed
imitation, and no vocabulary a batik artisan would recognise.

**Connectivity cannot be assumed.** Craft communities are concentrated in regional
centres — Pekalongan, Solo, Cirebon, Yogyakarta — where a workshop cannot depend on
reliable broadband, and where cloud subscription pricing is a real barrier. A tool that
stops working offline is a tool that does not get adopted.

**Documentation is scattered and undigitised.** Regional motif knowledge sits in books,
private collections, and photographs of cloth. There is no reusable asset format for a
studio to build on, so every project starts from nothing.

Generative AI adds a fourth problem rather than solving the first three: a model that
emits plausible batik-looking pixels produces an image, not an editable design, and
gives the artisan no authorship over the result.

---

## Solution Description

BatikCraft Studio is a native desktop application that treats batik as structured,
editable design rather than as a flat picture, and runs completely offline.

**A document model built around the craft.** Folders, sublayers, and objects mirror how a
composition is actually assembled. Motif pokok, isen-isen, ornament, and texture are
first-class categories. Humanize applies non-destructive irregularity, so a repeated
stamp reads as hand-drawn rather than mechanically cloned — and it can be adjusted or
removed at any time because it never rewrites the underlying object.

**Offline by default.** The application ships with procedural fallbacks for Kawung,
Truntum, Ceplok, and Lereng, and an asset library that lives on the machine. AI is
optional and switched off until a runtime is installed. Nothing about the core workflow
requires a network.

**A reusable asset economy.** `.batikasset` carries a single portable asset;
`.batikpack` bundles a library with manifest, tags, categories, thumbnails, and
versioning. A Kaggle pipeline turns a raw dataset of cloth photographs into a curated
pack — deduplication, extraction, alpha cleaning, category suggestion, contact sheets for
human review, then validated export.

**Segmentation is deliberately not automatic.** Historical motifs and interlocking areas
of cloth require human curation, and the pipeline is built to route them to a person
rather than guess.

**AI produces editable objects, not final images.** Generated results enter the document
as objects that can be moved, recoloured, and erased like anything else.

**Companion marketplace.** [BatikCraftWeb](https://github.com/balyaapik/BatikCraftWeb)
handles listing, auctions, licensing, and payouts, so creators can sell both finished
motifs and the asset libraries and style models they train.

---

## Selected Challenge Theme

**Culture and heritage preservation.**

Preservation here means keeping the craft *practised*, not archived. A museum photograph
of a Parang motif preserves an artefact; it does not help anyone make the next one.

The design decisions follow from that reading. The document model uses the craft's own
vocabulary so the tool is learnable by someone trained in batik rather than in software.
Humanize exists because mechanical perfection is precisely what separates printed
imitation from *batik tulis*. Offline operation is a heritage requirement, not a
technical preference, because the practitioners are in regional workshops. The asset pack
format exists so that regional motif knowledge, once digitised, is reusable by everyone
rather than trapped in one person's project file.

The same reasoning sets a limit on the AI. A model that generates finished batik would
replace the artisan's judgement. A model that generates editable objects the artisan then
composes, corrects, and signs keeps authorship where it belongs.

---

## AI Approach and Architecture

AI is optional, off by default, and never required for the core workflow.

### Two Families

| | Local | Cloud |
| --- | --- | --- |
| Object batikfication | Stable Diffusion 1.5 + ControlNet | — |
| Motif and pattern generation | SDXL + LoRA (BatikBrew) | OpenAI, Google Gemini, IBM watsonx.ai |
| Runs on | The user's machine | Provider API |
| Requires network | No | Yes |

Providers are selected at runtime (`ai/generation_providers.py`); API keys are stored in
the system keyring, never in a project file.

### Why Style Transfer Instead of Paired Training

The hard requirement is that *any* object — a bottle, a flower, a vehicle — can be
rendered in batik style, including objects absent from the training data.

Paired translation would need hundreds of original-and-batik photo pairs per object
class, which does not scale and generalises poorly. So the LoRA learns **style only**;
shape is supplied at inference:

| Stage | Source of shape | Source of style |
| --- | --- | --- |
| Training | none — batik images only | batik images plus a trigger word |
| Inference | the user's photo (img2img) | the trained LoRA |

The silhouette survives because of two constraints: a low img2img `strength` (0.40–0.55)
and **ControlNet Canny** locking the outline to the source image's edges. Because shape
is never learned, one trained LoRA works for objects it has never seen.

### Guardrails

Running large models on unknown consumer hardware is where this kind of feature usually
fails, so several checks sit in front of inference:

- **Runtime integrity** — a model is only considered ready when the index, tokenisers,
  encoders, UNet, VAE, and scheduler all exist with plausible file sizes. An incomplete
  download is reported rather than failing halfway through generation.
- **CUDA guard** — loading SDXL on CPU is refused when an NVIDIA GPU is present but the
  installed wheel is CPU-only, before `from_pretrained()` can exhaust system RAM.
- **Download deduplication** — the naive download pattern fetched every duplicate weight
  (`.bin` *and* `.safetensors`, fp32 *and* fp16 *and* non-EMA) while the pipeline loads
  one set. Deduplicating cut SD 1.5 from roughly 15 GB to 5.2 GB and ControlNet from
  2.9 GB to 1.45 GB.
- **Offline mode** — a Settings toggle that genuinely prevents any model host contact.

### Training Path

A creator can train their own style adapter: Dataset Studio prepares the data, local LoRA
training runs with progress and cancellation, the result is stored in the local model
library, and it can then be sold through the companion marketplace.

### Where AI Sits in the Architecture

```text
ui/          →  application/  →  domain/
                    ↓
              imaging/, persistence/, ai/
```

`ai/` never manipulates Tkinter widgets, and `domain/` never imports from `ai/`.
Inference runs on worker threads and returns plain data to the main thread. The
deterministic procedural renderer is retained as both a fallback and a pre-processing
stage for the model pipeline.

---

## How IBM Bob Was Used

**Scope: code review, explanation, scaffolding, and boilerplate. Not feature
implementation.**

IBM Bob was used to read and explain existing code and to review diffs during the early
milestones, and to produce scaffolding — package structure, CI configuration, and test
templates — that the team then filled in.

The development log kept during Milestones 1 through 2D
(`docs/BOB_DEVELOPMENT_LOG.md`, available in the git history) recorded each milestone as
*prepared for* Bob review, with the review status stated explicitly per entry. That log
required every entry to distinguish code generated by Bob from code merely reviewed,
explained, or prepared beforehand. This section follows the same rule.

Features in this repository — the domain model, persistence, the canvas renderer, the
tool set, the AI pipeline — were implemented and reviewed by the team.

### AI Assistance Policy

Parts of this codebase were written with the help of AI coding assistants. The team's
standing rules, recorded in [`CONTRIBUTORS.md`](CONTRIBUTORS.md):

- Assistant output is a draft, never a finished change.
- A team member reviews the diff, runs the suite, and takes responsibility before merge.
- Behavioural changes ship with regression tests that fail without the change.
- Performance claims are backed by measurements recorded in the commit message.

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
