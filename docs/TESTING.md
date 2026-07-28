# Testing

```bash
pytest                       # everything
pytest tests/test_shape.py   # one file
pytest -k eraser             # by keyword
ruff check .                 # lint
```

Both `pytest` and `ruff` run in CI on every push.

## Requirements

Most of the suite imports UI modules, so **Tkinter must be installed** or roughly 35
test files fail to collect. That failure looks alarming and is purely environmental:

```text
ModuleNotFoundError: No module named 'tkinter'
```

Install your platform's Tk package before concluding something is broken.

## What Good Coverage Looks Like Here

A behavioural change ships with a test that **fails before the change**. For this
codebase that usually means one of:

- **Pixel equality.** When an optimisation claims to preserve output, assert
  `image.tobytes() == expected.tobytes()` rather than eyeballing it.
- **A measurable direction.** For destructive edits, assert that the alpha sum decreased
  rather than asserting exact pixel values.
- **The real session.** Construct the same `ProjectSession` the application uses.
  Several bugs existed precisely because a line created through the full session is not
  an object, while one created in a simplified test setup is.

## Testing UI Logic Without a Display

Helpers that take plain data can be called on an uninitialised instance:

```python
view = object.__new__(RefinedPaintLayerEditorWorkspaceView)
view._screen_point = lambda point: (point[0] * 2.0, point[1] * 2.0)
assert view._brush_cursor_center((10.0, 20.0), 999.0, 999.0) == (20.0, 40.0)
```

For event bindings, pass a recording stand-in rather than a real canvas:

```python
class _RecordingCanvas:
    def __init__(self):
        self.bindings = []

    def bind(self, sequence, handler, add=""):
        self.bindings.append((sequence, add))
```

This is why binding setup lives in `_bind_brush_cursor_events` instead of inline in
`__init__` — extracting it made it testable.

## Regression Test Naming

Name the test after the behaviour, not the function:

```python
def test_diagonal_line_is_not_hit_in_the_empty_corner_of_its_bounding_box(): ...
def test_stroke_starting_in_empty_space_touches_every_crossed_object(): ...
```

A year from now the name is the only thing telling a reader why the test exists. Add a
docstring explaining the failure mode it guards against.

## Benchmarking

Performance work needs numbers in the commit message, measured before and after on the
same machine. Use `time.perf_counter()` and report what was measured. Claims without
measurements do not belong in the documentation.
