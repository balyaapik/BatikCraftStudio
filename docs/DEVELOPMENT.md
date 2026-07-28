# Development

## Environment

Python 3.11 or newer, plus Tkinter.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m batikcraft_studio
```

On Debian and Ubuntu, Tkinter is a separate package:

```bash
sudo apt install python3-tk
```

## Repository Layout

```text
src/batikcraft_studio/
├── __main__.py          Entry point and startup sequence
├── domain/              Immutable value objects and the Project aggregate
├── application/         Session classes: one concern per subclass
├── imaging/             Rendering, caches, brushes, shapes, hit masks
├── persistence/         Archives, manifests, export locations
├── ai/                  Model runtimes, installers, providers
├── assets/              Asset pack builder and personal store
└── ui/                  Tkinter views, editors, dialogs, runtime patches

tests/                   Pytest suite
notebooks/               Kaggle asset and LoRA pipelines
docs/                    This documentation
packaging/               Desktop build inputs
```

## The Layer Rule

Dependencies point one way:

```text
ui  →  application  →  domain
        ↓
      imaging, persistence
```

`domain` imports nothing from the layers above it. `imaging` is pure Pillow work and
never touches Tkinter. When a rendering helper needs UI state, that is a signal the
state belongs somewhere else.

## Session Composition

Application behaviour is assembled by subclassing. `ProjectSession` is an alias for the
most derived class:

```text
ProjectSession = RasterLineProjectSession
    → AIBatikBackgroundProjectSession
        → OutlineCleanupProjectSession
            → … → PaintProjectSession → base session
```

Each subclass adds one concern and calls `super()` for the rest. To change how a feature
behaves, find the subclass that owns it rather than editing the base.

## Startup Sequence

`__main__.main()` runs a deliberately ordered sequence before the UI exists: dependency
bootstrap, private installer dispatch, managed package activation, storage directories,
runtime compatibility shims, model connectivity, integrity guards, then the canvas
runtime patches, and finally the application shell.

The order matters. Several steps must complete before any UI module captures a function
through `from … import`. Read the comments in that file before rearranging anything.

## Runtime Patches

Four modules monkey-patch the editor classes at startup — `realtime_canvas_patch`,
`inkscape_canvas_patch`, `inkscape_pointer_hotpath`, and `canvas_selection_semantics`.
They all patch `MultiObjectEditorWorkspaceView`, a base class, so subclass overrides
still win through the MRO.

This is known technical debt. Folding them into the core editor is worthwhile but should
be done one module per pull request, with the Tk-dependent tests actually running.

## Editor Class Hierarchy

The live editor is assembled from fifteen hotfix layers on top of the base editors. To
find out which class actually provides a method:

```python
from batikcraft_studio.ui.context_tool_editor_hotfixes import (
    ContextToolEditorWorkspaceView as C,
)
print(C._on_canvas_press.__module__)
print([c.__name__ for c in C.__mro__])
```

Do this before assuming where an override lives. It is faster than reading fifteen files.

## Logging

```python
import logging
_LOG = logging.getLogger(__name__)
```

File logging, a rotating handler, `faulthandler`, and an exception hook are installed at
startup so a crash leaves a trace. When adding a feature that can silently do nothing,
log the reason. Status-bar messages do not reach the log file and cannot be diagnosed
remotely.

## Style

- `ruff` enforces lint; line length 101; target `py311`.
- Comments explain *why*. The code already states *what*.
- Prefer a named helper over a comment explaining a dense expression.
