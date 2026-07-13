# Scoped IBM Bob Prompts

Use small prompts with explicit file boundaries. Bob should inspect the repository and tests before making changes.

## Next Prompt — Milestone 2A: Project Domain

```text
You are extending BatikCraft Studio, a Python 3.11 Tkinter application.

Read README.md and docs/ARCHITECTURE.md first.

Implement only the project domain foundation. Do not implement the canvas,
image import, AI, licensing, website API, or redesign the existing UI.

Create a new package under src/batikcraft_studio/project with:
- immutable or carefully validated project metadata;
- canvas size and background configuration;
- layer metadata interface without rendering behavior;
- dirty-state tracking;
- schema version constant;
- clear exceptions for invalid project data.

Requirements:
- domain modules must not import tkinter;
- use type hints and dataclasses where appropriate;
- invalid canvas dimensions and duplicate layer IDs must be rejected;
- add focused pytest tests;
- keep existing tests passing;
- run ruff check . and pytest;
- document important design decisions in docs/BOB_DEVELOPMENT_LOG.md.

Before editing, summarize the files you intend to add or change. After editing,
summarize validation results and any unresolved decisions.
```

## Future Prompt — Milestone 2B: Serializer

```text
Implement versioned BatikCraft project save/open behavior using the domain
interfaces already present under src/batikcraft_studio/project.

The .batikcraft format is a ZIP container. Add project.json and reserved
folders for assets, masks, renders, and metadata. Protect against path
traversal, missing manifests, unsupported schema versions, duplicate asset
paths, and corrupted ZIP files. Use atomic save behavior. Do not add Tkinter
file dialogs yet. Add tests for valid round trips and every listed error case.
```

## Future Prompt — Milestone 2C: Workspace Shell

```text
Connect New Project and Open Project to the existing Tkinter application using
application services around the project domain. Add a dirty-project close
confirmation and a basic blank canvas placeholder. Do not implement image
rendering or layer transforms yet. Tkinter must remain in the UI layer.
```

## Review Checklist for Every Bob Task

- Scope matches the prompt.
- No unrelated UI redesign.
- No direct database or marketplace logic in the desktop app.
- No Tkinter imports in domain packages.
- No AI work on the main UI thread.
- Manual/non-AI fallback remains available.
- Tests cover failure paths, not only happy paths.
- Development log states Bob's actual contribution accurately.
