# Scoped IBM Bob Prompts

Use small prompts with explicit file boundaries. Bob should inspect the repository and
tests before making changes.

## Completed Foundation — Milestone 2A: Project Domain

The repository contains the project aggregate and immutable value objects under
`src/batikcraft_studio/domain`. Extend those contracts instead of creating a second
project or layer model.

## Completed Foundation — Milestone 2B: Project Serializer

The persistence API lives under `src/batikcraft_studio/persistence`; the archive
contract is documented in `docs/PROJECT_FORMAT.md`.

## Completed Foundation — Milestone 2C: Workspace Shell

The repository contains `ProjectSession`, New/Open/Save/Save As/Close workflows,
project context, dirty-project confirmation, and the workspace shell contract in
`docs/WORKSPACE_SHELL.md`.

## Completed Foundation — Milestone 2D: Raster Layer Editing

The repository now contains:

- safe raster normalization under `src/batikcraft_studio/imaging/raster.py`;
- bounded Pillow rendering under `src/batikcraft_studio/imaging/renderer.py`;
- layer commands and snapshot history in `ProjectSession`;
- the interactive editor under `src/batikcraft_studio/ui/layer_editor.py`;
- tests in `tests/test_raster_imaging.py` and `tests/test_layer_editor_session.py`;
- the editor contract in `docs/LAYER_EDITOR.md`.

Suggested IBM Bob review prompt:

```text
Review Milestone 2D in:
- src/batikcraft_studio/imaging;
- src/batikcraft_studio/application/session.py;
- src/batikcraft_studio/ui/layer_editor.py;
- src/batikcraft_studio/app.py;
- docs/LAYER_EDITOR.md;
- tests/test_raster_imaging.py;
- tests/test_layer_editor_session.py.

Do not add brush, eraser, shape, motif stamp, Object Batikfication, GAN inference,
pattern repeat, licensing, or website integration.

Check specifically for:
- Pillow decompression-bomb, malformed-file, alpha, color-mode, and EXIF issues;
- preview rendering errors for off-canvas, negative-scale, rotated, and opaque layers;
- transform convention inconsistencies between renderer, hit testing, and UI;
- undo/redo loss of asset bytes, path, saved revision, selection, or layer order;
- shared-asset deletion and duplicate-layer edge cases;
- locked-layer mutation gaps;
- partial mutations after invalid inspector input;
- expensive repeated rendering or Tkinter main-thread responsiveness problems;
- cross-platform file-dialog and keyboard-shortcut behavior;
- missing UI-independent failure-path tests.

Make only clear corrective changes. Run ruff check . and pytest. Record the actual
Bob contribution in docs/BOB_DEVELOPMENT_LOG.md, including manual GUI checks that
were performed and unresolved risks.
```

## Next Prompt — Milestone 3A: Basic Paint Layer

```text
You are extending BatikCraft Studio after the raster layer editor is stable.
Read README.md, docs/LAYER_EDITOR.md, and the existing domain/application/imaging
modules first.

Implement only a basic paint-layer foundation:
- create a paint layer backed by an RGBA PNG asset;
- add brush and eraser tools with adjustable size and opacity;
- draw in project coordinates and preserve the existing center-based layer transform;
- commit one history entry per completed stroke, not per mouse-move event;
- keep raster import, transforms, save/open, and undo/redo working;
- do not implement shapes, stamps, symmetry, Object Batikfication, GAN inference,
  pattern repeat, licensing, or website integration;
- add non-GUI tests for stroke compositing, erasing, history, and save/open;
- run ruff check . and pytest;
- update docs and the Bob development log truthfully.

Before editing, summarize the files you intend to change. After editing, report test
results, manual GUI checks, and unresolved performance decisions.
```

## Review Checklist for Every Bob Task

- Scope matches the prompt.
- No unrelated UI redesign.
- No direct database or marketplace logic in the desktop app.
- No Tkinter imports in domain or persistence packages.
- No AI work on the main UI thread.
- Manual/non-AI fallback remains available.
- Tests cover failure paths, not only happy paths.
- Development log states Bob's actual contribution accurately.
