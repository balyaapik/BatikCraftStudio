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

Suggested Bob review prompt:

```text
Review Milestone 2B in src/batikcraft_studio/persistence,
docs/PROJECT_FORMAT.md, and tests/test_project_archive.py.

Do not add Tkinter dialogs or image rendering yet. Do not replace the domain
model or introduce another serializer.

Check specifically for:
- unsafe ZIP member handling and path traversal gaps;
- atomic-save failure behavior;
- missing, duplicate, encrypted, oversized, or corrupted members;
- manifest/domain round-trip loss;
- SHA-256 and size verification gaps;
- mutable asset state escaping from ProjectBundle;
- insufficient failure-path tests.

Make only clear corrective changes. Run ruff check . and pytest. Record the actual
Bob contribution in docs/BOB_DEVELOPMENT_LOG.md.
```

## Next Prompt — Milestone 2C: Workspace Shell

```text
You are extending BatikCraft Studio, a Python 3.11 Tkinter application.
Read README.md, docs/ARCHITECTURE.md, docs/PROJECT_DOMAIN.md, and
 docs/PROJECT_FORMAT.md first.

Implement only the workspace application shell around the existing domain and
persistence APIs. Do not implement image rendering, layer transforms, drawing,
Object Batikfication, GAN inference, licensing, or website integration.

Requirements:
- create an application-level document/session service that owns the current
  Project, loaded asset bytes, and current file path;
- implement New Project, Open Project, Save, and Save As commands;
- use ProjectArchive for all save/open operations;
- add Tkinter file dialogs only in the UI layer;
- display the current project title, canvas dimensions, dirty state, and file path;
- add a basic blank canvas placeholder without Pillow or image rendering;
- prompt before replacing or closing a dirty project with Save, Discard, Cancel;
- prevent a failed open/save operation from replacing the current valid session;
- keep domain and persistence modules free from Tkinter imports;
- add unit tests for the session service and targeted UI-independent command logic;
- run ruff check . and pytest;
- update docs/BOB_DEVELOPMENT_LOG.md with Bob's actual contribution.

Before editing, summarize the files you intend to add or change. After editing,
summarize validation results and unresolved decisions.
```

## Future Prompt — Milestone 2D: Layer Editing

```text
Add image-backed workspace layers after Milestone 2C is stable. Implement PNG/JPG
import, selection, move, scale, rotate, duplicate, delete, visibility, lock, layer
ordering, and undo/redo. Keep rendering concerns out of the project domain and use
application commands for mutations. Do not add Object Batikfication or GAN work yet.
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
