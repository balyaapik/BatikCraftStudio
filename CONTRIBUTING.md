# Contributing

Thanks for taking an interest in BatikCraft Studio.

## Getting Set Up

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Confirm the checkout is healthy before you change anything:

```bash
ruff check .
pytest
```

If Tkinter is missing, install your platform's Tk package (`python3-tk` on
Debian/Ubuntu). A large part of the suite imports the UI modules and will fail to
collect without it.

## Making a Change

1. **Branch** from `main` with a descriptive name.
2. **Write a failing test first** for any behavioural change. A bug fix without a test
   that fails before the fix is not finished.
3. **Keep the change focused.** Unrelated cleanups belong in their own commit.
4. **Run `ruff check .` and `pytest`.** Both must pass.
5. **Write the commit message for a reader who was not there.** Explain what was wrong
   and why the fix works, not just what you typed.

## Commit Messages

The repository uses long-form commit bodies. A useful message states the symptom, the
root cause, and the evidence:

```text
Fix eraser missing lines fused into the raster canvas layer

When the active layer is a raster canvas, raster_line_session merges a line
into the layer bitmap instead of creating an object, so object_count stays 0.
The contextual eraser only scanned objects and could never find such a line.

The release handler now also applies the stroke as a bitmap erase on every
visible, unlocked raster canvas layer whose ink falls inside the stroke
bounds. Ink is checked first so a sweep over empty space produces no mutation
and no undo step.
```

## Performance Claims

If a change is about speed or memory, measure it. Put the before and after numbers in
the commit message, and say what you measured them on. Claims without numbers get
removed from the documentation.

## Code Style

- `ruff` enforces the lint rules; line length is 101.
- Target Python 3.11.
- Comments explain *why*, not *what*. The code already says what it does.
- Public functions and modules carry docstrings.

## Documentation

The documentation is written in English. If your change alters behaviour a user can
see, update the relevant file under `docs/` in the same pull request.

## Cultural Care

This project works with batik, a living Indonesian tradition. When adding motif
presets or example content, prefer documented regional patterns and credit their
origin. Avoid presenting generated output as an authentic historical motif.
