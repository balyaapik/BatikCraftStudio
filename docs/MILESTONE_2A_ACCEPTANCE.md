# Milestone 2A Acceptance Criteria

Milestone 2A is complete when all of the following are true:

- project-domain modules do not import Tkinter or imaging/AI libraries;
- a new project receives a stable UUID and current schema version;
- metadata, canvas dimensions, transforms, layer opacity, and layer kinds are validated;
- layer IDs are immutable UUIDs and unique inside a project;
- layer add, update, remove, reorder, and selection behavior is deterministic;
- content changes increment revision and update the modification timestamp;
- no-op mutations and transient selection do not make a saved project dirty;
- a new project is considered unsaved until `mark_saved()` is called;
- invalid schema versions, timestamps, indexes, and aggregate value types fail explicitly;
- the domain exposes clear exceptions for validation, duplicates, and missing layers;
- focused tests cover happy paths and failure paths;
- `ruff check .` and `pytest` pass in GitHub Actions.

## Explicitly Out of Scope

- `.batikcraft` file persistence;
- JSON manifests;
- ZIP archive handling;
- Tkinter canvas integration;
- image rendering and transforms;
- undo/redo history;
- AI inference;
- website integration.
