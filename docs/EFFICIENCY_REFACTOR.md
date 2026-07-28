# Efficiency Refactor Notes (July 2026)

## Canvas and Object Rendering

1. **Asset digest memoisation** (`imaging/tile_cache.py`,
   `imaging/safe_viewport_renderer.py`). The SHA-1 of the full asset bytes was
   recomputed for every object, every tile, every frame — for both
   `ObjectRenderCacheKey` and `project_visual_fingerprint`. Digests are now cached by
   the identity of the bytes object. This is safe because assets are immutable and the
   cache holds a strong reference, so an `id()` cannot be reused. The `repr(layer)`
   digest is memoised per layer identity as well, since layers are frozen dataclasses.

2. **PhotoImage is no longer rebuilt for unchanged tiles** (`_apply_screen_tiles` in
   hotfix layer v1, `_apply_tiles` in `viewport_editor.py`). A renderer cache hit
   returns the same PIL object, so the PIL→Tk conversion — a full pixel copy — is
   skipped when the identical image is already on screen. Grid, selection, and rulers
   are redrawn only when something actually changed.

3. **Dead work removed** (`viewport_editor.py`). A duplicated revision line was
   deleted, and the stitched preview no longer builds an `ImageTk.PhotoImage` that was
   never displayed.

## Structural Consolidation

- Fifteen `ui/context_tool_editor_hotfix*.py` files were merged into
  **`ui/context_tool_editor_hotfixes.py`**, preserving the layer order and override
  semantics exactly. The old files became import shims so existing tests and callers
  keep working.
- Eight `*MainWindow` variants were merged into a single **`ui/main_window.MainWindow`**;
  the previous names remain available as aliases.
- Ten `ui/*_i18n.py` files were merged into the `_FEATURE_TRANSLATIONS` catalogue in
  **`batikcraft_studio/i18n.py`** with no key collisions. The old
  `install_*_translations` functions are now no-op shims.

## Suggested Follow-Up

- Inline `dependency_integrity_patch` and `dependency_profiles_patch` into
  `dependency_manager_dialog`, and `ai_menu_consolidation_patch` into the application.
  These are chained wrappers whose installation order matters, so the work should be
  done with the GUI running.
- Flatten the `*WorkspaceView` editor chain — still roughly 25 classes deep and linear —
  into per-feature mixins.
- Derive dependency profiles from a single source of truth: the optional-dependencies
  table in `pyproject.toml`.
- Consider a monotonic revision counter on the session instead of recomputing a
  fingerprint hash on every render kick.
