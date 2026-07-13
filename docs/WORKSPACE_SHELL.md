# Workspace Shell — Milestone 2C

Milestone 2C connects the existing project domain and `.batikcraft` serializer to
the Tkinter application. It intentionally stops before image rendering and layer
editing.

## Module Boundaries

```text
Tkinter UI
  app.py
  ui/dialogs.py
  ui/main_window.py
  ui/views.py
        ↓
Application service
  application/session.py
        ↓
Domain + persistence
  domain/*
  persistence/*
```

`ProjectSession` contains no Tkinter imports. It owns:

- the active `Project`;
- the current `.batikcraft` path;
- the verified embedded asset bytes loaded from the archive;
- a read-only snapshot used by the UI.

The Tkinter layer owns file dialogs, message boxes, keyboard shortcuts, and visual
presentation.

## File Commands

| Command | Shortcut | Behavior |
|---|---:|---|
| New Project | Ctrl+N | Collect metadata and create a dirty unsaved project |
| Open Project | Ctrl+O | Load a validated `.batikcraft` archive |
| Save | Ctrl+S | Save to the existing path or fall back to Save As |
| Save As | Ctrl+Shift+S | Select a new archive path and save atomically |
| Close Project | Ctrl+W | Close after dirty-state confirmation |
| Exit | — | Exit after dirty-state confirmation |

## Dirty-Project Protection

When a dirty project would be replaced or closed, the user receives three choices:

- **Yes** — save the project, then continue only if saving succeeds;
- **No** — discard the current unsaved changes and continue;
- **Cancel** — abort the requested transition and keep the project open.

Canceling a Save As dialog is treated as an unsuccessful save, so the transition is
also canceled.

## Project Context Bar

The main window displays:

- project title;
- creator;
- canvas dimensions;
- layer count;
- current path or `Not saved yet`;
- saved/unsaved state.

The window title includes `*` when the active project is dirty.

## Blank Canvas Shell

The Motif Editor shows a classic Tk canvas placeholder that:

- uses the project's configured background color;
- preserves the logical canvas aspect ratio;
- scales to the available window area;
- displays the project title and logical dimensions;
- contains no Pillow, image decoding, or permanent rendering state.

Image-backed rendering begins in Milestone 2D.

## Manual GUI Checklist

Run:

```bash
python -m batikcraft_studio
```

Then verify:

1. Create a new project with valid metadata and canvas dimensions.
2. Confirm the editor canvas matches the selected aspect ratio and background.
3. Save As and confirm the project becomes clean and the path appears.
4. Change project data through a domain/debug action and confirm `*`/dirty state.
5. Trigger New/Open/Close/Exit and test Save, Discard, and Cancel paths.
6. Open the saved archive and confirm metadata and canvas context return.
7. Attempt to open a corrupt archive and confirm the current session remains intact.

The automated test suite validates session and archive behavior without requiring a
display server.
