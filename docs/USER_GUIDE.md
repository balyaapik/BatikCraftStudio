# User Guide

Working in the BatikCraft Studio editor.

## The Workspace

```text
Asset Library  |  Canvas  |  Layer Stack
```

Three permanent regions, nothing else. Tool settings open as small windows from the
**Draw**, **Edit**, and **Asset** menus and close when you are done with them.

## Projects

| Action | Where |
| --- | --- |
| New project | **File → New** |
| Open | **File → Open** |
| Save | **File → Save** (`.batikcraft`) |
| Save a copy | **File → Save As** |

Saves are atomic: the archive is written to a temporary file and swapped into place, so
an interrupted save never destroys the previous version. Projects written by an older
schema are migrated on open.

## Tools

| Tool | Shortcut | Behaviour |
| --- | --- | --- |
| Select | `V` | Selects and transforms objects |
| Brush | `B` | Paints onto the active raster canvas layer |
| Eraser | `E` | Removes pixels — see below |
| Line | `L` | Rasterised on creation |
| Rectangle, Ellipse, Polygon | — | Stay editable vector objects |
| Cap Motif, Cap Isen | — | Stamps procedural motifs |

Hold **Shift** while dragging a shape to constrain it; hold **Alt** to draw from the
centre.

### The Eraser

Select the eraser, then **press the left mouse button, drag, and release**. The erase is
applied when you release, not continuously while dragging. A circular cursor ring shows
the brush size and sits exactly where the tool will act.

A stroke may start anywhere, including empty space. On release, every object and every
raster canvas layer whose ink the stroke passed over is erased. A sweep that only
crosses empty space changes nothing and creates no undo step.

Two things follow from how the document is built:

- **Lines are rasterised.** A line drawn while a raster canvas layer is active is merged
  into that layer's bitmap; a line drawn onto an object layer becomes a stroke object.
  Either way the eraser reaches it. The trade-off is that a line's colour and thickness
  cannot be changed after it is drawn.
- **A sweep across several objects creates one undo step per object.** Pressing undo
  repeatedly walks back through them.

Rectangles, ellipses, and polygons stay vector until you erase part of one; at that
point it is rasterised so the erased pixels can be stored.

## Assets

1. **Asset → Install Asset Pack…** and choose a `.batikpack` file.
2. Search or filter in the left panel.
3. Select the destination sublayer in the right panel.
4. Double-click an asset to place it.

Packs install into a per-user library — `%LOCALAPPDATA%\BatikCraftStudio\asset-library`
on Windows, `~/.local/share/BatikCraftStudio/asset-library` elsewhere, overridable with
`BATIKCRAFT_ASSET_LIBRARY`. An asset is copied into the project file only when it is
actually placed, so a large library does not inflate every project.

## Objects and Layers

The right panel shows the document tree. Objects support visibility, lock, reordering,
duplication, deletion, and transforms. **Edit → Transform…** gives numeric control over
position, size, rotation, and opacity.

**Asset → Humanize** applies non-destructive irregularity so a repeated stamp does not
look mechanically identical. It can be adjusted or removed at any time.

## Navigating the Canvas

| Action | Input |
| --- | --- |
| Zoom | Mouse wheel |
| Pan | Scrollbars, or the hand tool |
| Select all | `Ctrl+A` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |

Zoom is clamped between 10% and 150%. At high zoom the canvas shows a scaled preview
immediately and replaces it with a sharp render once the tiles finish.

## AI Generation

AI is optional; the application is fully usable without it.

- **Local** — install the `ai-local` extra, then download a runtime from the
  Dependencies window. Generation runs on your machine.
- **Cloud** — OpenAI or Gemini. Keys are stored in the system keyring.

A Settings toggle switches between online and offline behaviour. In offline mode the
application never contacts a model host. Runtime integrity is verified before loading,
so an incomplete download is reported rather than failing partway through generation.

## Publishing

The studio prepares work for the BatikCraft website; bidding and licensing happen there.
Before a piece goes live the creator pays a listing fee on the web: a percentage of the
lowest listed price plus VAT, non-refundable even if the piece does not sell. The studio
shows the breakdown and opens the payment page when a publish attempt is rejected. See
[`WEB_LISTING_FEE.md`](WEB_LISTING_FEE.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Eraser does nothing | Are you using the **left** button? Right-click opens the context menu and is not bound to any tool. |
| Canvas is blank at high zoom | Check the log for allocation failures; report it with the zoom level. |
| AI features missing | The `ai-local` extra is not installed, or no runtime has been downloaded. |
| Application will not start | Run `python -m batikcraft_studio` from a terminal to see the error. |

Logs are written to a rotating `batikcraft.log` (5 files, 2 MB each) in a `log/`
directory next to the managed dependency root, falling back to per-user application data
if that location is not writable. On Windows that is usually:

```text
%LOCALAPPDATA%\BatikCraftStudio\log
```

The log captures unhandled exceptions and native crashes, which makes it the most useful
thing to attach to a bug report.
