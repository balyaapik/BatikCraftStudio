# Scoped IBM Bob Prompts

Use small prompts with explicit file boundaries. Bob should inspect the repository and tests before making changes.

## Completed Foundation — Milestone 2A: Project Domain

The repository now contains the project aggregate and value objects under
`src/batikcraft_studio/domain`. IBM Bob should review and extend those contracts,
not replace them with a second document model.

Suggested Bob review prompt:

```text
Review Milestone 2A in src/batikcraft_studio/domain and tests/test_project_domain.py.
Do not redesign the Tkinter UI and do not add serialization yet.

Check specifically for:
- validation gaps;
- dirty-state and revision inconsistencies;
- mutable state escaping from value objects;
- duplicate or missing layer behavior;
- timestamp and schema-version edge cases;
- missing failure-path tests.

Make only clear corrective changes. Run ruff check . and pytest. Record the actual
Bob contribution in docs/BOB_DEVELOPMENT_LOG.md.
```

## Next Prompt — Milestone 2B: Serializer

```text
You are extending BatikCraft Studio, a Python 3.11 Tkinter application.
Read README.md, docs/ARCHITECTURE.md, and docs/PROJECT_DOMAIN.md first.

Implement versioned BatikCraft project save/open behavior using the existing
interfaces under src/batikcraft_studio/domain. Do not duplicate project or layer
models and do not add Tkinter file dialogs yet.

The .batikcraft format is a ZIP container with:
- project.json;
- assets/;
- masks/;
- renders/;
- metadata/.

Requirements:
- provide explicit conversion between domain objects and manifest data;
- use atomic save behavior;
- reject path traversal, missing manifests, unsupported schema versions,
  duplicate asset paths, and corrupted ZIP files;
- preserve project UUIDs, timestamps, revisions, layer order, transforms,
  properties, and asset references;
- call project.mark_saved() only after a successful save;
- add valid round-trip tests and tests for every listed error case;
- keep domain modules free from Tkinter and persistence imports;
- run ruff check . and pytest;
- update docs/BOB_DEVELOPMENT_LOG.md with Bob's actual contribution.

Before editing, summarize the files you intend to add or change. After editing,
summarize validation results and unresolved decisions.
```

## Future Prompt — Milestone 2C: Workspace Shell

```text
Connect New Project and Open Project to the existing Tkinter application using
application services around the project domain and serializer. Add a dirty-project
close confirmation and a basic blank canvas placeholder. Do not implement image
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
