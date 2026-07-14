# Milestone 4F — Zoom, Grid, Ruler Visibility, and Standard Context Actions

## Canvas zoom

The canvas viewport now supports:

```text
Zoom In       Ctrl++
Zoom Out      Ctrl+-
Fit Canvas    Ctrl+0
Actual Size   Ctrl+1
```

Zoom levels range from 10% to 800%. The bottom-right canvas controls provide `−`, `+`, and
`Fit` buttons. Zoom preserves the project point near the center of the visible viewport.
Horizontal and vertical scrollbars appear around the canvas so enlarged documents remain
reachable.

Mouse controls:

```text
Ctrl + Mouse Wheel   Zoom
Mouse Wheel          Vertical scroll
Shift + Mouse Wheel  Horizontal scroll
```

Zoom is a viewport property. It does not modify object transforms, project dimensions, exported
images, or saved project data.

## Grid

Use:

```text
View → Show Grid
```

The grid:

- is drawn only inside the project canvas;
- follows project-space coordinates;
- adapts its interval at low zoom levels;
- distinguishes major and minor lines;
- does not appear in project exports;
- does not modify project history.

## Ruler visibility

Use:

```text
View → Show Rulers
```

Disabling rulers removes the horizontal ruler, vertical ruler, and ruler corner while reclaiming
their viewport space. Re-enabling rulers restores adaptive ticks and cursor guides. Ruler labels
remain synchronized with canvas scrolling.

## Context menu

Right-click with the Select tool to access:

```text
Cut
Copy
Paste
Delete
────────────
Group
Ungroup
────────────
New Layer
New Layer Folder
Move to Layer
────────────
Fill Color
────────────
Batik Process Studio
```

Cut, Copy, Paste, and Delete operate on the complete multi-selection. A grouped selection copied
and pasted receives a new group ID, preventing the pasted objects from joining the original group.
Relative object positions are preserved.

Cut and Delete each create one Undo entry. Paste creates one Undo entry regardless of the number
of pasted objects. Clipboard content survives Undo/Redo because it is editor state rather than
project history.

## Compatibility

The project schema remains `1.1`. Viewport zoom, grid visibility, and ruler visibility are not
stored in `.batikcraft`; object changes made through Cut/Paste/Delete continue to use the existing
object and layer schema.
