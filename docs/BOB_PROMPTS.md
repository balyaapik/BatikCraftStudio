# Scoped IBM Bob Prompts

Use small prompts with explicit file boundaries. Bob should inspect the repository and tests before making changes.

## Completed Foundation — Milestone 2A: Project Domain

The repository contains the project aggregate and immutable value objects under
`src/batikcraft_studio/domain`. IBM Bob should extend those contracts rather than
create a second project or layer model.

## Completed Foundation — Milestone 2B: Project Serializer

The repository contains the public persistence API under
`src/batikcraft_studio/persistence` and the archive contract in
`docs/PROJECT_FORMAT.md`.

## Completed Foundation — Milestone 2C: Workspace Shell

The repository now contains:

- `ProjectSession` under `src/batikcraft_studio/application`;
- New/Open/Save/Save As/Close workflows in `app.py`;
- project context and a blank responsive editor canvas;
- Save–Discard–Cancel protection for dirty projects;
- session tests under `tests/test_project_session.py`;
- the shell contract in `docs/WORKSPACE_SHELL.md`.

Suggested Bob review prompt:

```text
Review Milestone 2C in src/batikcraft_studio/application,
src/batikcraft_studio/app.py, src/batikcraft_studio/ui, docs/WORKSPACE_SHELL.md,
and tests/test_project_session.py.

Do not implement image import, image rendering, layer transforms, drawing tools,
Object Batikfication, GAN inference, licensing, or website integration.

Check specifically for:
- session replacement after failed open/save operations;
- dirty-state confirmation edge cases;
- canceled Save As behavior during close/new/open/exit;
- asset bytes or mutable session state escaping;
- file-dialog logic leaking into domain or persistence modules;
- cross-platform Tkinter shortcut and dialog issues;
- missing UI-independent failure-path tests.

Make only clear corrective changes. Run ruff check . and pytest. Record the actual
Bob contribution in docs/BOB_DEVELOPMENT_LOG.md.
```

## Next Prompt — Milestone 2D: Layer Editing

```text
You are extending BatikCraft Studio, a Python 3.11 Tkinter application.
Read README.md, docs/ARCHITECTURE.md, docs/PROJECT_DOMAIN.md,
docs/PROJECT_FORMAT.md, and docs/WORKSPACE_SHELL.md first.

Implement only image-backed layer editing on top of the existing ProjectSession,
Project aggregate, and Tkinter editor shell. Do not implement drawing tools,
Object Batikfication, GAN inference, pattern repeat, licensing, or website APIs.

Requirements:
- add Pillow only for PNG/JPG decoding, preview rendering, and RGBA conversion;
- import PNG/JPG through the UI and embed canonical PNG bytes below assets/;
- create one existing domain Layer per imported image with a stable asset_ref;
- render layers in stack order without putting image bytes into the domain model;
- support selection, move, scale, rotate, duplicate, delete, visibility, lock,
  and layer ordering;
- keep transformations non-destructive and stored in Layer.transform;
- add an application command/history service with undo and redo;
- prevent locked layers from being transformed or deleted;
- keep active selection transient and do not dirty the project by selection alone;
- refresh project context after every content mutation;
- preserve all imported assets through Save/Open round trips;
- add UI-independent tests for commands, history, asset naming, and mutations;
- keep domain and persistence modules free from Tkinter and Pillow imports;
- run ruff check . and pytest;
- update docs/BOB_DEVELOPMENT_LOG.md with Bob's actual contribution.

Before editing, summarize the files you intend to add or change. After editing,
summarize validation results, manual GUI checks, and unresolved decisions.
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
