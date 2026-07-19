"""Consolidated contextual-editor hotfix layers (v1..v15).

Sebelumnya 15 file `context_tool_editor_hotfix*.py` membentuk rantai subclass
linier. Semua layer kini berada dalam satu modul, dengan urutan dan semantik
override yang identik. Kelas publik terakhir adalah
``ContextToolEditorWorkspaceView`` (alias dari layer v15).
Modul-modul lama dipertahankan sebagai shim kompatibilitas impor.
"""

from __future__ import annotations

# ==========================================================================
# Layer v1 (dulu context_tool_editor_hotfix.py)
# ==========================================================================

"""Safety hotfixes for the contextual editor viewport.

The M4J implementation treated a 512 unit project tile as a 512 pixel screen
tile.  At 800% zoom that produced 4096x4096 Pillow images.  This subclass keeps
tiles bounded to 512 physical output pixels, snapshots project state before
worker rendering, never calls Tk from a worker thread, and releases invisible
``PhotoImage`` instances.
"""


import copy
import queue
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from PIL import Image, ImageTk

from batikcraft_studio.imaging.safe_viewport_renderer import (
    SCREEN_TILE_SIZE,
    SafeViewportRenderer,
    project_visual_fingerprint,
    visible_screen_tile_coords,
)

from .context_tool_editor import ContextToolEditorWorkspaceView as _BaseContextToolEditor


class _HotfixV1(_BaseContextToolEditor):
    """Context editor with bounded, cancellable, main-thread-safe rendering."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._safe_renderer = SafeViewportRenderer()
        self._render_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="batikcraft-viewport",
        )
        self._render_results: queue.SimpleQueue[
            tuple[
                int,
                list[tuple[int, int, Image.Image]],
                float,
                float,
                float,
                frozenset[tuple[int, int]],
            ]
        ] = queue.SimpleQueue()
        self._render_future: Future[None] | None = None
        self._render_shutdown = False
        super().__init__(*args, **kwargs)
        # Replace the legacy renderer before the first scheduled render executes.
        legacy = getattr(self, "_cached_renderer", None)
        if legacy is not None:
            try:
                legacy.clear_project()
            except Exception:  # noqa: BLE001
                pass
        self._cached_renderer = self._safe_renderer
        self.after(16, self._poll_render_results)

    def _set_fixed_zoom(
        self,
        scale: float,
        *,
        anchor_screen: tuple[int, int] | None = None,
    ) -> None:
        # Do not keep wrongly-scaled Tk tiles while waiting for the new generation.
        self._delete_all_screen_tiles()
        super()._set_fixed_zoom(scale, anchor_screen=anchor_screen)

    def _show_quick_preview(
        self,
        old_scale: float,
        new_scale: float,
        anchor_proj: tuple[float, float] | None,
    ) -> None:
        # The previous quick preview stitched visible tiles into another giant image.
        # Keeping the UI responsive is preferable to allocating that duplicate buffer.
        del old_scale, new_scale, anchor_proj

    def _stitch_preview_pil(
        self,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
    ) -> None:
        # Intentionally disabled: individual tiles are already the preview.
        del tiles, zoom_scale, preview_left, preview_top
        self._last_preview_pil = None
        self._preview_photo = None
        self._preview_canvas_id = None

    def _kick_tile_render(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        del content_width, content_height
        self._submit_visible_tiles(project, zoom_scale, generation)

    def _schedule_tile_update(self) -> None:
        project = self.session.project
        if project is None or self._preview_scale <= 0 or self._render_shutdown:
            return
        generation = self._increment_render_generation()
        self._submit_visible_tiles(project, self._preview_scale, generation)

    def _submit_visible_tiles(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
    ) -> None:
        if self._render_shutdown:
            return

        # Cancel queued work. A running worker observes generation changes and exits.
        if self._render_future is not None and not self._render_future.done():
            self._render_future.cancel()

        project_snapshot = copy.deepcopy(project)
        assets_snapshot = {key: bytes(value) for key, value in self.session.assets.items()}
        fingerprint = project_visual_fingerprint(project_snapshot, assets_snapshot)
        preview_left = float(self._preview_left)
        preview_top = float(self._preview_top)

        viewport_left = max(0.0, self.canvas.canvasx(0) - preview_left)
        viewport_top = max(0.0, self.canvas.canvasy(0) - preview_top)
        viewport_width = max(1.0, float(self.canvas.winfo_width()))
        viewport_height = max(1.0, float(self.canvas.winfo_height()))
        tile_coords = visible_screen_tile_coords(
            viewport_left,
            viewport_top,
            viewport_width,
            viewport_height,
            project_snapshot.canvas.width,
            project_snapshot.canvas.height,
            zoom_scale,
            overscan=1,
        )
        active_keys = frozenset(tile_coords)
        renderer = self._safe_renderer

        def worker() -> None:
            rendered: list[tuple[int, int, Image.Image]] = []
            for tile_x, tile_y in tile_coords:
                if self._render_shutdown or generation != self._render_generation:
                    return
                image = renderer.render_tile(
                    project_snapshot,
                    assets_snapshot,
                    project_fingerprint=fingerprint,
                    zoom_scale=zoom_scale,
                    tile_x=tile_x,
                    tile_y=tile_y,
                )
                rendered.append((tile_x, tile_y, image))
            if not self._render_shutdown and generation == self._render_generation:
                self._render_results.put(
                    (
                        generation,
                        rendered,
                        zoom_scale,
                        preview_left,
                        preview_top,
                        active_keys,
                    )
                )

        self._render_future = self._render_executor.submit(worker)

    def _poll_render_results(self) -> None:
        if self._render_shutdown:
            return
        latest: tuple[
            int,
            list[tuple[int, int, Image.Image]],
            float,
            float,
            float,
            frozenset[tuple[int, int]],
        ] | None = None
        while True:
            try:
                candidate = self._render_results.get_nowait()
            except queue.Empty:
                break
            if candidate[0] == self._render_generation:
                latest = candidate
        if latest is not None:
            self._apply_screen_tiles(*latest)
        try:
            self.after(16, self._poll_render_results)
        except Exception:  # noqa: BLE001
            self._render_shutdown = True

    def _apply_screen_tiles(
        self,
        generation: int,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
        active_keys: frozenset[tuple[int, int]],
    ) -> None:
        del zoom_scale
        if generation != self._render_generation or self._render_shutdown:
            return

        # Release Tk image references that are no longer in the visible+overscan set.
        stale = set(self._tile_canvas_ids) - set(active_keys)
        changed = bool(stale)
        for key in stale:
            canvas_id = self._tile_canvas_ids.pop(key, None)
            if canvas_id is not None:
                self.canvas.delete(canvas_id)
            self._tile_photos.pop(key, None)

        for tile_x, tile_y, image in tiles:
            if image.width > SCREEN_TILE_SIZE or image.height > SCREEN_TILE_SIZE:
                raise RuntimeError("oversized viewport tile reached the Tk main thread")
            key = (tile_x, tile_y)
            canvas_x = preview_left + tile_x * SCREEN_TILE_SIZE
            canvas_y = preview_top + tile_y * SCREEN_TILE_SIZE
            canvas_id = self._tile_canvas_ids.get(key)
            applied = self._tile_photos.get(key)
            if applied is not None and applied[0] is image and canvas_id is not None:
                # Cache hit returned the exact image object already on screen:
                # skip the expensive PhotoImage pixel copy, just fix coords.
                current = self.canvas.coords(canvas_id)
                if current != [canvas_x, canvas_y]:
                    self.canvas.coords(canvas_id, canvas_x, canvas_y)
                    changed = True
                continue
            photo = ImageTk.PhotoImage(image)
            self._tile_photos[key] = (image, photo)
            changed = True
            if canvas_id is None:
                canvas_id = self.canvas.create_image(
                    canvas_x,
                    canvas_y,
                    image=photo,
                    anchor="nw",
                    tags="project-tile",
                )
                self._tile_canvas_ids[key] = canvas_id
            else:
                self.canvas.itemconfigure(canvas_id, image=photo)
                self.canvas.coords(canvas_id, canvas_x, canvas_y)

        if changed:
            self._draw_grid()
            self._draw_selection()
            self._draw_rulers()

    def _clear_tile_overlays(self) -> None:
        self._delete_all_screen_tiles()
        self._safe_renderer.clear_project()
        self._preview_photo = None
        self._preview_canvas_id = None
        self._last_preview_pil = None

    def _delete_all_screen_tiles(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            for canvas_id in tuple(getattr(self, "_tile_canvas_ids", {}).values()):
                canvas.delete(canvas_id)
        if hasattr(self, "_tile_canvas_ids"):
            self._tile_canvas_ids.clear()
        if hasattr(self, "_tile_photos"):
            self._tile_photos.clear()

    def destroy(self) -> None:
        self._render_shutdown = True
        self._render_generation += 1
        if self._render_future is not None:
            self._render_future.cancel()
        self._render_executor.shutdown(wait=False, cancel_futures=True)
        self._safe_renderer.clear_project()
        super().destroy()


# ==========================================================================
# Layer v2 (dulu context_tool_editor_hotfix_v2.py)
# ==========================================================================

"""Final viewport hotfix layer using immutable project snapshots."""


from typing import Any

from PIL import Image

from batikcraft_studio.domain import Project
from batikcraft_studio.imaging.safe_viewport_renderer import (
    project_visual_fingerprint,
    visible_screen_tile_coords,
)



class _HotfixV2(_HotfixV1):
    """Use a Project aggregate clone instead of unsafe ``deepcopy`` calls."""

    def _submit_visible_tiles(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
    ) -> None:
        if self._render_shutdown:
            return
        if self._render_future is not None and not self._render_future.done():
            self._render_future.cancel()

        project_snapshot = _clone_project_for_render(project)
        assets_snapshot = {key: bytes(value) for key, value in self.session.assets.items()}
        fingerprint = project_visual_fingerprint(project_snapshot, assets_snapshot)
        preview_left = float(self._preview_left)
        preview_top = float(self._preview_top)

        viewport_left = max(0.0, self.canvas.canvasx(0) - preview_left)
        viewport_top = max(0.0, self.canvas.canvasy(0) - preview_top)
        viewport_width = max(1.0, float(self.canvas.winfo_width()))
        viewport_height = max(1.0, float(self.canvas.winfo_height()))
        tile_coords = visible_screen_tile_coords(
            viewport_left,
            viewport_top,
            viewport_width,
            viewport_height,
            project_snapshot.canvas.width,
            project_snapshot.canvas.height,
            zoom_scale,
            overscan=1,
        )
        active_keys = frozenset(tile_coords)
        renderer = self._safe_renderer

        def worker() -> None:
            rendered: list[tuple[int, int, Image.Image]] = []
            for tile_x, tile_y in tile_coords:
                if self._render_shutdown or generation != self._render_generation:
                    return
                image = renderer.render_tile(
                    project_snapshot,
                    assets_snapshot,
                    project_fingerprint=fingerprint,
                    zoom_scale=zoom_scale,
                    tile_x=tile_x,
                    tile_y=tile_y,
                )
                rendered.append((tile_x, tile_y, image))
            if not self._render_shutdown and generation == self._render_generation:
                self._render_results.put(
                    (
                        generation,
                        rendered,
                        zoom_scale,
                        preview_left,
                        preview_top,
                        active_keys,
                    )
                )

        self._render_future = self._render_executor.submit(worker)


def _clone_project_for_render(project: Project) -> Project:
    """Clone the mutable aggregate while reusing immutable layer value objects."""

    return Project(
        metadata=project.metadata,
        canvas=project.canvas,
        layers=project.layers,
        project_id=project.project_id,
        schema_version=project.schema_version,
        active_layer_id=project.active_layer_id,
        active_object_id=project.active_object_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        revision=project.revision,
        saved_revision=project.saved_revision,
    )


# ==========================================================================
# Layer v3 (dulu context_tool_editor_hotfix_v3.py)
# ==========================================================================

"""Viewport hotfix that separates project background from transparent artwork tiles."""


import tkinter as tk
from typing import Any

from batikcraft_studio.imaging.artwork_viewport_renderer import ArtworkViewportRenderer



class _HotfixV3(_HotfixV2):
    """Prevent artwork refreshes from exposing an opaque shadow-sized colour block."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._project_background_id: int | None = None
        super().__init__(*args, **kwargs)
        previous_renderer = self._safe_renderer
        self._safe_renderer = ArtworkViewportRenderer()
        self._cached_renderer = self._safe_renderer
        previous_renderer.clear_project()
        self._increment_render_generation()
        self._schedule_render()

    def _kick_tile_render(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        self._draw_project_background(project, zoom_scale)
        super()._kick_tile_render(
            project,
            zoom_scale,
            generation,
            content_width,
            content_height,
        )

    def _draw_project_background(self, project: Any, zoom_scale: float) -> None:
        left = float(self._preview_left)
        top = float(self._preview_top)
        right = left + float(project.canvas.width) * zoom_scale
        bottom = top + float(project.canvas.height) * zoom_scale
        background = str(project.canvas.background_color)

        background_id = self._project_background_id
        if not self._canvas_item_exists(background_id):
            # Do not use the canvas-chrome tag here. The base viewport intentionally
            # deletes that tag before every render; retaining the deleted numeric ID
            # exposed the brown canvas-shadow rectangle after a line/brush mutation.
            background_id = self.canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=background,
                outline="",
                tags=("project-background",),
            )
            self._project_background_id = background_id
        else:
            self.canvas.coords(background_id, left, top, right, bottom)
            self.canvas.itemconfigure(background_id, fill=background)

        # Keep a deterministic stack: shadow < project background < artwork tiles.
        self.canvas.tag_raise(background_id, "canvas-shadow")
        self.canvas.tag_raise("project-tile", background_id)

    def _canvas_item_exists(self, item_id: int | None) -> bool:
        if item_id is None:
            return False
        try:
            return bool(self.canvas.type(item_id))
        except (tk.TclError, AttributeError):
            return False

    def _clear_tile_overlays(self) -> None:
        background_id = self._project_background_id
        if background_id is not None:
            self.canvas.delete(background_id)
            self._project_background_id = None
        super()._clear_tile_overlays()


# ==========================================================================
# Layer v4 (dulu context_tool_editor_hotfix_v4.py)
# ==========================================================================

"""Context-menu entry for preview-first deterministic Batification."""


import tkinter as tk

from batikcraft_studio.application import (
    ProjectSessionError,
)
from batikcraft_studio.assets import PersonalAssetStore



class _HotfixV4(_HotfixV3):
    """(Dihapus) Batifikasi tanpa model tidak lagi tersedia.

    Semua batifikasi kini harus melalui model (Stable Diffusion lokal atau
    provider cloud). Layer ini dipertahankan kosong agar rantai kelas dan
    kompatibilitas impor tetap utuh.
    """


# ==========================================================================
# Layer v5 (dulu context_tool_editor_hotfix_v5.py)
# ==========================================================================

"""UI command for pretrained AI Batification without custom training."""


import threading
import tkinter as tk

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.application import (
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)



class _HotfixV5(_HotfixV4):
    """Expose pretrained img2img Batification while keeping Tk mutations on main."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._pretrained_ai_running = False
        self._pretrained_ai_destroyed = False
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_command(
            label="Batifikasi AI Pretrained (Tanpa Training)",
            command=self.batify_selected_with_pretrained_ai,
        )
        self.bind_all(
            "<Control-Alt-B>",
            self._on_pretrained_ai_shortcut,
            add="+",
        )

    def batify_selected_with_pretrained_ai(self) -> None:
        """Run Stable Diffusion img2img from source-first, motif-second selection."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        self.set_status(
            "Batifikasi AI dimulai. Model pretrained akan diunduh pada penggunaan pertama."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - convert worker errors to UI status
                message = str(exc)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_pretrained_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-pretrained-ai",
        ).start()

    def _post_pretrained_ai_callback(self, callback: object) -> None:
        if self._pretrained_ai_destroyed:
            return
        try:
            self.after(0, callback)
        except tk.TclError:
            self._pretrained_ai_destroyed = True

    def _finish_pretrained_ai_success(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> None:
        self._pretrained_ai_running = False
        if self._pretrained_ai_destroyed:
            return
        try:
            output = self._pretrained_ai_session.commit_pretrained_ai_result(plan, result)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(
            f"{output.name} dibuat dengan model pretrained tanpa training khusus."
        )

    def _finish_pretrained_ai_error(self, message: str) -> None:
        self._pretrained_ai_running = False
        if not self._pretrained_ai_destroyed:
            self.set_status(message)

    def _on_pretrained_ai_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.batify_selected_with_pretrained_ai()
        return "break"

    @property
    def _pretrained_ai_session(self) -> PretrainedAIBatificationProjectSession:
        if not isinstance(self.session, PretrainedAIBatificationProjectSession):
            raise RuntimeError("Editor memerlukan PretrainedAIBatificationProjectSession.")
        return self.session

    def destroy(self) -> None:
        self._pretrained_ai_destroyed = True
        if not self._pretrained_ai_running:
            self._pretrained_ai_session.unload_pretrained_ai()
        super().destroy()


# ==========================================================================
# Layer v6 (dulu context_tool_editor_hotfix_v6.py)
# ==========================================================================

"""External image insertion through file dialog, OS drag-and-drop, and clipboard."""


import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from batikcraft_studio.application import ExternalImageProjectSession, ProjectSessionError
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore

from .external_image_io import (
    clipboard_payloads,
    image_dialog_filetypes,
    paths_from_clipboard_text,
    paths_from_drop_data,
    payloads_from_paths,
)


class _HotfixV6(_HotfixV5):
    """Make external raster images first-class transformable canvas objects."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._personal_asset_store = PersonalAssetStore(self.asset_library)
        self._external_drop_available = self._register_external_drop_target()

    def import_external_image_dialog(self) -> None:
        """Select one or more supported image files and insert them at canvas center."""

        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum memasukkan gambar.")
            return
        selected = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Insert Gambar",
            filetypes=image_dialog_filetypes(),
        )
        if not selected:
            return
        self._import_external_payloads(
            payloads_from_paths(Path(value) for value in selected),
            position=None,
            source_label="file",
        )

    def paste_external_image(self) -> bool:
        """Insert an OS clipboard image or copied external image files."""

        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menempel gambar.")
            return False
        payloads = clipboard_payloads()
        if not payloads:
            try:
                text = self.clipboard_get()
            except tk.TclError:
                text = ""
            payloads = payloads_from_paths(paths_from_clipboard_text(text))
        if not payloads:
            self.set_status("Clipboard sistem tidak berisi gambar atau file gambar yang didukung.")
            return False
        self._import_external_payloads(payloads, position=None, source_label="clipboard")
        return True

    def paste_object(self) -> None:
        """Preserve internal object paste; otherwise let Ctrl+V accept external images."""

        if self._external_image_session.has_object_clipboard:
            super().paste_object()
            return
        if not self.paste_external_image():
            super().paste_object()

    def _register_external_drop_target(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return False
        register = getattr(self.canvas, "drop_target_register", None)
        bind = getattr(self.canvas, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            return False
        try:
            register(DND_FILES)
            bind("<<DropEnter>>", self._on_external_drop_enter)
            bind("<<DropLeave>>", self._on_external_drop_leave)
            bind("<<Drop>>", self._on_external_image_drop)
        except tk.TclError:
            return False
        return True

    def _on_external_drop_enter(self, _event: Any) -> str:
        self.canvas.configure(cursor="plus")
        self.set_status("Lepaskan file gambar untuk memasukkannya ke canvas dan pustaka.")
        return "copy"

    def _on_external_drop_leave(self, _event: Any) -> str:
        self.canvas.configure(cursor="arrow")
        return "copy"

    def _on_external_image_drop(self, event: Any) -> str:
        self.canvas.configure(cursor="arrow")
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menjatuhkan gambar.")
            return "refuse_drop"
        paths = paths_from_drop_data(self.tk.splitlist, str(getattr(event, "data", "")))
        payloads = payloads_from_paths(paths)
        if not payloads:
            self.set_status("Drop ditolak: tidak ada file gambar yang didukung.")
            return "refuse_drop"
        position = self._drop_project_position(event)
        self._import_external_payloads(payloads, position=position, source_label="drag-and-drop")
        return "copy"

    def _drop_project_position(self, event: Any) -> tuple[float, float] | None:
        if self._preview_scale <= 0:
            return None
        try:
            root_x = float(event.x_root)
            root_y = float(event.y_root)
            canvas_x = root_x - float(self.canvas.winfo_rootx())
            canvas_y = root_y - float(self.canvas.winfo_rooty())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            try:
                canvas_x = float(event.x)
                canvas_y = float(event.y)
            except (AttributeError, TypeError, ValueError):
                return None
        return (
            (canvas_x - self._preview_left) / self._preview_scale,
            (canvas_y - self._preview_top) / self._preview_scale,
        )

    def _import_external_payloads(
        self,
        payloads: tuple[tuple[str, bytes], ...],
        *,
        position: tuple[float, float] | None,
        source_label: str,
    ) -> None:
        if not payloads:
            return
        imported = []
        errors: list[str] = []
        category = str(self.asset_category_value.get() or "ornamen")
        for index, (filename, content) in enumerate(payloads):
            current_position = (
                None
                if position is None
                else (position[0] + index * 20.0, position[1] + index * 20.0)
            )
            try:
                record = self._personal_asset_store.import_image(
                    filename,
                    content,
                    category=category,
                )
                item = self._external_image_session.import_external_image(
                    filename,
                    content,
                    position=current_position,
                    library_key=record.key,
                    category=record.category,
                )
            except (AssetLibraryError, ProjectSessionError, OSError) as exc:
                errors.append(f"{filename}: {exc}")
                continue
            imported.append(item)

        self.asset_library.refresh()
        try:
            self.refresh_library()
        except (AttributeError, tk.TclError):
            pass
        if imported:
            self.refresh_context()
            self.activate_select_tool()
            self.set_status(
                f"{len(imported)} gambar dari {source_label} dimasukkan dan disimpan "
                "ke pustaka Gambar Impor Saya."
            )
        if errors:
            messagebox.showwarning(
                "Sebagian gambar gagal dimasukkan",
                "\n".join(errors[:12]),
                parent=self.winfo_toplevel(),
            )

    @property
    def _external_image_session(self) -> ExternalImageProjectSession:
        if not isinstance(self.session, ExternalImageProjectSession):
            raise RuntimeError("Editor memerlukan ExternalImageProjectSession.")
        return self.session


# ==========================================================================
# Layer v7 (dulu context_tool_editor_hotfix_v7.py)
# ==========================================================================

"""Background `.batikpack` installation with responsive progress and cancellation."""


import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox

from batikcraft_studio.assets import ASSET_PACK_EXTENSION, AssetLibrary, AssetLibraryError
from batikcraft_studio.assets.progressive_install import (
    AssetInstallCancelled,
    AssetInstallProgress,
    install_pack_with_progress,
)
from batikcraft_studio.i18n import tr

from .asset_pack_progress_dialog import AssetPackProgressDialog


class _HotfixV7(_HotfixV6):
    """Keep large pack validation and extraction away from the Tk main thread."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._asset_pack_install_running = False
        self._asset_pack_install_destroyed = False
        self._asset_pack_cancel_event: threading.Event | None = None
        self._asset_pack_queue: Queue[tuple[str, object]] | None = None
        self._asset_pack_poll_after_id: str | None = None
        self._asset_pack_dialog: AssetPackProgressDialog | None = None
        self._asset_pack_selected_path: Path | None = None
        super().__init__(*args, **kwargs)

    def install_asset_pack_dialog(self) -> None:
        """Choose a pack and install it without freezing the editor window."""

        if self._asset_pack_install_running:
            self.set_status("Pemasangan paket asset masih berjalan di latar belakang.")
            if self._asset_pack_dialog is not None:
                try:
                    self._asset_pack_dialog.lift()
                except tk.TclError:
                    pass
            return
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=tr("library.install_title"),
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if not selected:
            return
        self._start_asset_pack_install(Path(selected), replace=False)

    def _start_asset_pack_install(self, path: Path, *, replace: bool) -> None:
        self._asset_pack_install_running = True
        self._asset_pack_selected_path = path
        self._asset_pack_cancel_event = threading.Event()
        self._asset_pack_queue = Queue()
        self._asset_pack_dialog = AssetPackProgressDialog(
            self,
            archive_path=path,
            on_cancel=self._request_asset_pack_cancel,
        )
        self.set_status(
            "Paket asset sedang dipasang di latar belakang. Editor tetap responsif."
        )

        queue = self._asset_pack_queue
        cancel_event = self._asset_pack_cancel_event
        library_root = self.asset_library.root

        def worker() -> None:
            worker_library = AssetLibrary(library_root)
            try:
                pack = install_pack_with_progress(
                    worker_library,
                    path,
                    replace=replace,
                    progress=lambda update: queue.put(("progress", update)),
                    cancel_event=cancel_event,
                )
            except AssetInstallCancelled:
                queue.put(("cancelled", None))
            except AssetLibraryError as exc:
                queue.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - worker failures must reach Tk safely
                queue.put(("error", f"Kesalahan tak terduga: {exc}"))
            else:
                queue.put(
                    (
                        "success",
                        (pack.pack_id, pack.name, len(pack.assets)),
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-asset-pack-install",
        ).start()
        self._asset_pack_poll_after_id = self.after(80, self._poll_asset_pack_install)

    def _poll_asset_pack_install(self) -> None:
        self._asset_pack_poll_after_id = None
        if self._asset_pack_install_destroyed:
            return
        queue = self._asset_pack_queue
        if queue is None:
            return

        terminal: tuple[str, object] | None = None
        while True:
            try:
                event = queue.get_nowait()
            except Empty:
                break
            kind, payload = event
            if kind == "progress" and isinstance(payload, AssetInstallProgress):
                dialog = self._asset_pack_dialog
                if dialog is not None:
                    try:
                        dialog.apply_progress(payload)
                    except tk.TclError:
                        pass
            else:
                terminal = event

        if terminal is None:
            self._asset_pack_poll_after_id = self.after(
                80,
                self._poll_asset_pack_install,
            )
            return
        self._finish_asset_pack_install(*terminal)

    def _finish_asset_pack_install(self, kind: str, payload: object) -> None:
        selected_path = self._asset_pack_selected_path
        dialog = self._asset_pack_dialog
        if dialog is not None:
            dialog.close()
        self._asset_pack_dialog = None
        self._asset_pack_install_running = False
        self._asset_pack_cancel_event = None
        self._asset_pack_queue = None
        self._asset_pack_selected_path = None

        if self._asset_pack_install_destroyed:
            return
        if kind == "cancelled":
            self.set_status("Pemasangan paket asset dibatalkan dengan aman.")
            return
        if kind == "error":
            message = str(payload)
            if "sudah terpasang" in message and selected_path is not None:
                replace = messagebox.askyesno(
                    tr("library.replace_title"),
                    tr("library.replace_question", error=message),
                    parent=self.winfo_toplevel(),
                )
                if replace:
                    self._start_asset_pack_install(selected_path, replace=True)
                return
            messagebox.showerror(
                tr("library.install_error"),
                message,
                parent=self.winfo_toplevel(),
            )
            self.set_status(message)
            return
        if kind != "success" or not isinstance(payload, tuple) or len(payload) != 3:
            self.set_status("Pemasangan paket selesai dengan hasil yang tidak dikenali.")
            return

        pack_id, pack_name, asset_count = payload
        self.asset_library.refresh()
        self.refresh_library()
        self.library_pack_value.set(str(pack_name))
        self.set_status(
            tr(
                "library.installed",
                name=str(pack_name),
                count=int(asset_count),
            )
        )
        try:
            self.asset_library.get_pack(str(pack_id))
        except AssetLibraryError:
            self.set_status("Paket selesai dipasang, tetapi indeks pustaka perlu dimuat ulang.")

    def _request_asset_pack_cancel(self) -> None:
        event = self._asset_pack_cancel_event
        if event is not None:
            event.set()

    def destroy(self) -> None:
        self._asset_pack_install_destroyed = True
        event = self._asset_pack_cancel_event
        if event is not None:
            event.set()
        if self._asset_pack_poll_after_id is not None:
            try:
                self.after_cancel(self._asset_pack_poll_after_id)
            except tk.TclError:
                pass
            self._asset_pack_poll_after_id = None
        if self._asset_pack_dialog is not None:
            self._asset_pack_dialog.close()
            self._asset_pack_dialog = None
        super().destroy()


# ==========================================================================
# Layer v8 (dulu context_tool_editor_hotfix_v8.py)
# ==========================================================================

"""Context-menu workflow for preview-first raster outline cleanup."""


import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.application import (
    OutlineCleanupProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore

from .outline_cleanup_dialog_safe import OutlineCleanupDialog


class _HotfixV8(_HotfixV7):
    """Clean one selected image object without changing it before user approval."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="Rapikan Outline…",
            command=self.clean_selected_outline,
        )
        self.bind_all(
            "<Control-Alt-o>",
            self._on_outline_cleanup_shortcut,
            add="+",
        )

    def clean_selected_outline(self) -> None:
        """Open a modal source/result preview for one selected raster-like object."""

        try:
            plan = self._outline_cleanup_session.prepare_outline_cleanup()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        dialog = OutlineCleanupDialog(
            self,
            source_name=plan.source_object.name,
            source_content=plan.source_content,
            render_preview=lambda options: (
                self._outline_cleanup_session.render_outline_cleanup_preview(plan, options)
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Rapikan Outline dibatalkan. Objek pada canvas tidak berubah.")
            return

        try:
            result = self._outline_cleanup_session.commit_outline_cleanup_preview(plan, preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        saved_to_library = False
        category = plan.source_object.properties.get("asset_category", "ornamen")
        if not isinstance(category, str):
            category = "ornamen"
        try:
            PersonalAssetStore(self.asset_library).import_image(
                f"{plan.source_object.name}-outline-bersih.png",
                preview.result.content,
                category=category,
            )
        except AssetLibraryError as exc:
            messagebox.showwarning(
                "Outline diterapkan, tetapi pustaka gagal diperbarui",
                str(exc),
                parent=self.winfo_toplevel(),
            )
        else:
            saved_to_library = True
            try:
                self.refresh_library()
            except (AttributeError, tk.TclError):
                pass

        self.refresh_context()
        self.activate_select_tool()
        removed = preview.result.removed_components
        suffix = (
            " Salinan bersih juga disimpan ke Gambar Impor Saya."
            if saved_to_library
            else ""
        )
        self.set_status(
            f"Outline {result.name} dirapikan; {removed} bercak dihapus. "
            f"Gunakan Undo untuk kembali.{suffix}"
        )

    def _on_outline_cleanup_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.clean_selected_outline()
        return "break"

    @property
    def _outline_cleanup_session(self) -> OutlineCleanupProjectSession:
        if not isinstance(self.session, OutlineCleanupProjectSession):
            raise RuntimeError("Editor memerlukan OutlineCleanupProjectSession.")
        return self.session


# ==========================================================================
# Layer v9 (dulu context_tool_editor_hotfix_v9.py)
# ==========================================================================

"""Selected-object recolor and preview-first AI Batik background generation."""


import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.application import (
    AIBatikBackgroundProjectSession,
    DirectStyleProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore
from batikcraft_studio.imaging import BatikAssetError, load_batik_asset

from .ai_batik_background_dialog import AIBatikBackgroundDialog


def apply_palette_color_to_current_selection(
    session: DirectStyleProjectSession,
    color: str,
) -> tuple[object, ...]:
    """Apply a clicked primary palette color to the current object selection."""

    if not session.has_project or not session.selected_object_ids:
        return ()
    return tuple(session.apply_color_to_selected(color, target="auto"))


class _HotfixV9(_HotfixV8):
    """Make palette clicks recolor selection and expose AI background generation."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._background_ai_destroyed = False
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="AI Batik Background…",
            command=self.generate_ai_batik_background,
        )
        self.bind_all(
            "<Control-Alt-g>",
            self._on_ai_background_shortcut,
            add="+",
        )
        self._background_ai_button = ttk.Button(
            self.palette_host,
            text="AI Background…",
            style="Secondary.TButton",
            command=self.generate_ai_batik_background,
        )
        self._background_ai_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

    def _set_primary_color(self, color: str, *, announce: bool = True) -> None:
        """Set drawing color and immediately recolor the selected compatible object."""

        super()._set_primary_color(color, announce=announce)
        if not announce or not hasattr(self, "session"):
            return
        if not isinstance(self.session, DirectStyleProjectSession):
            return
        try:
            updated = apply_palette_color_to_current_selection(self.session, color)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        if not updated:
            return
        self.refresh_context()
        self.activate_select_tool()
        count = len(updated)
        self.set_status(
            f"Warna {color.upper()} diterapkan ke {count} objek terpilih. "
            "Gunakan Undo untuk kembali."
        )

    def generate_ai_batik_background(self) -> None:
        """Open the Stable Diffusion background dialog and commit only approved output."""

        if not self.session.has_project:
            self.set_status("Buat atau buka project sebelum membuat AI Batik Background.")
            return
        try:
            context = self._background_ai_session.prepare_background_ai_context()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        reference_content, reference_name = self._selected_library_reference()
        dialog = AIBatikBackgroundDialog(
            self,
            reference_content=reference_content,
            reference_name=reference_name,
            render_preview=lambda options, content, name: (
                self._background_ai_session.render_background_ai_preview(
                    context,
                    options,
                    reference_content=content,
                    reference_name=name,
                )
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Generasi AI Batik Background dibatalkan. Canvas tidak berubah.")
            return
        try:
            result = self._background_ai_session.commit_background_ai_preview(preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        saved = False
        try:
            PersonalAssetStore(self.asset_library).import_image(
                f"ai-batik-background-seed-{preview.options.seed}.png",
                preview.result.content,
                category="ornamen",
            )
        except AssetLibraryError as exc:
            messagebox.showwarning(
                "Background diterapkan, tetapi pustaka gagal diperbarui",
                str(exc),
                parent=self.winfo_toplevel(),
            )
        else:
            saved = True
            try:
                self.refresh_library()
            except (AttributeError, tk.TclError):
                pass

        self.refresh_context()
        suffix = " Hasil juga disimpan ke Gambar Impor Saya." if saved else ""
        self.set_status(
            f"{result.name} diterapkan pada layer paling bawah sebagai background terkunci."
            f"{suffix} Gunakan Undo untuk kembali."
        )

    def _selected_library_reference(self) -> tuple[bytes | None, str | None]:
        if not hasattr(self, "library_list"):
            return None, None
        selection = self.library_list.selection()
        if not selection:
            return None, None
        record = self._library_records.get(selection[0])
        if record is None:
            return None, None
        try:
            payload = self.asset_library.read_asset(record)
            asset = load_batik_asset(
                payload,
                filename=Path(record.relative_path).name,
                default_category=record.category,
            )
        except (AssetLibraryError, BatikAssetError, OSError, ValueError):
            return None, None
        return asset.content, record.name

    def _on_ai_background_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.generate_ai_batik_background()
        return "break"

    @property
    def _background_ai_session(self) -> AIBatikBackgroundProjectSession:
        if not isinstance(self.session, AIBatikBackgroundProjectSession):
            raise RuntimeError("Editor memerlukan AIBatikBackgroundProjectSession.")
        return self.session

    def destroy(self) -> None:
        self._background_ai_destroyed = True
        try:
            self._background_ai_session.unload_background_ai()
        except (AttributeError, RuntimeError):
            pass
        super().destroy()


# ==========================================================================
# Layer v10 (dulu context_tool_editor_hotfix_v10.py)
# ==========================================================================

"""Global AI/GPU settings integration for every editor inference workflow."""


import threading
import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.ai.global_runtime import (
    GlobalPretrainedBatikBackgroundProvider,
    GlobalPretrainedImg2ImgBatificationProvider,
    pretrained_batification_options_from_global,
)
from batikcraft_studio.application import (
    AIBatikBackgroundProjectSession,
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore

from .ai_batik_background_dialog_global import GlobalAIBatikBackgroundDialog
from .offline_ai_dialogs_global import GlobalOfflineModelManagerWindow


class _HotfixV10(_HotfixV9):
    """Consume one persisted compute profile for background, pretrained, and LoRA AI."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(
                GlobalPretrainedImg2ImgBatificationProvider()
            )
        if isinstance(self.session, AIBatikBackgroundProjectSession):
            self.session.set_background_ai_provider(
                GlobalPretrainedBatikBackgroundProvider()
            )

    def batify_selected_with_pretrained_ai(self) -> None:
        """Run object Batification using the global device and memory configuration."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        try:
            options = pretrained_batification_options_from_global()
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        self.set_status(
            f"Batifikasi AI dimulai dengan runtime global {options.device} / "
            f"{options.precision}."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - worker errors return to Tk
                message = str(exc)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_pretrained_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-pretrained-ai-global-runtime",
        ).start()

    def _finish_pretrained_ai_success(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> None:
        self._pretrained_ai_running = False
        if self._pretrained_ai_destroyed:
            return
        try:
            output = self._pretrained_ai_session.commit_pretrained_ai_result(plan, result)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        device = result.metadata.get("device", "-")
        self.set_status(
            f"{output.name} selesai menggunakan {device}. "
            "Runtime dapat diubah melalui Edit → Preferences → AI & GPU."
        )

    def generate_ai_batik_background(self) -> None:
        """Generate a preview using the current persisted global runtime profile."""

        if not self.session.has_project:
            self.set_status("Buat atau buka project sebelum membuat AI Batik Background.")
            return
        try:
            context = self._background_ai_session.prepare_background_ai_context()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        reference_content, reference_name = self._selected_library_reference()
        dialog = GlobalAIBatikBackgroundDialog(
            self,
            reference_content=reference_content,
            reference_name=reference_name,
            render_preview=lambda options, content, name: (
                self._background_ai_session.render_background_ai_preview(
                    context,
                    options,
                    reference_content=content,
                    reference_name=name,
                )
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Generasi AI Batik Background dibatalkan. Canvas tidak berubah.")
            return
        try:
            result = self._background_ai_session.commit_background_ai_preview(preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        saved = False
        try:
            PersonalAssetStore(self.asset_library).import_image(
                f"ai-batik-background-seed-{preview.options.seed}.png",
                preview.result.content,
                category="ornamen",
            )
        except AssetLibraryError as exc:
            messagebox.showwarning(
                "Background diterapkan, tetapi pustaka gagal diperbarui",
                str(exc),
                parent=self.winfo_toplevel(),
            )
        else:
            saved = True
            try:
                self.refresh_library()
            except (AttributeError, tk.TclError):
                pass

        self.refresh_context()
        device = preview.result.metadata.get("device", "-")
        suffix = " Hasil juga disimpan ke Gambar Impor Saya." if saved else ""
        self.set_status(
            f"{result.name} diterapkan menggunakan {device} pada layer paling bawah."
            f"{suffix} Gunakan Undo untuk kembali."
        )

    def open_offline_model_manager(self) -> None:
        """Keep model paths local while device/precision come from global preferences."""

        window = self._model_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        if not isinstance(self.session, OfflineAIProjectSession):
            raise RuntimeError("Editor AI offline memerlukan OfflineAIProjectSession.")
        self._model_window = GlobalOfflineModelManagerWindow(
            self,
            self.session,
            on_change=self._announce_provider,
        )


# ==========================================================================
# Layer v11 (dulu context_tool_editor_hotfix_v11.py)
# ==========================================================================

"""Expanded Batik palette and menu-first Stable Diffusion AI workflows."""


import threading
import tkinter as tk
from tkinter import ttk

from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.lora_object_batification import LoraObjectBatificationProvider
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.i18n import tr

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .batik_palette import BATIK_COLORS
from .theme import COLORS
from .tooltip import ToolTip

_AI_CONTEXT_LABEL = "Batifikasi AI — Stable Diffusion + LoRA…"
_NON_AI_CONTEXT_LABEL = "Batifikasi Cepat (Non-AI)…"


class _HotfixV11(_HotfixV10):
    """Show a larger Batik palette and open object AI through a LoRA settings window."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._remove_background_ai_from_editor_chrome()
        self._configure_object_batification_context_actions()
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(LoraObjectBatificationProvider())

    def _build_color_palette(self, parent: ttk.Frame) -> None:
        """Build a wide, named palette based on common Indonesian Batik colours."""

        parent.columnconfigure(1, weight=1)
        controls = ttk.Frame(parent, style="Toolbar.TFrame")
        controls.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 8))
        ttk.Label(controls, text="Palet Warna Batik", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(0, 3),
        )
        self._primary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.SUNKEN,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=True),
        )
        self._primary_color_preview.grid(row=1, column=0, rowspan=2, padx=(0, 3))
        self._secondary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=False),
        )
        self._secondary_color_preview.grid(row=2, column=1, padx=(0, 3))
        ttk.Button(
            controls,
            text="⇄",
            width=3,
            style="Secondary.TButton",
            command=self.swap_palette_colors,
        ).grid(row=1, column=2, padx=1)
        ttk.Button(
            controls,
            text="D",
            width=3,
            style="Secondary.TButton",
            command=self.reset_palette_colors,
        ).grid(row=2, column=2, padx=1)

        palette_area = ttk.Frame(parent, style="Toolbar.TFrame")
        palette_area.grid(row=0, column=1, rowspan=2, sticky="ew")
        palette_area.columnconfigure(0, weight=1)
        ttk.Label(
            palette_area,
            text=(
                "Soga · Malam · Mori · Mengkudu · Nila · Mega Mendung · "
                "Hijau Alam · Aksen Pesisir"
            ),
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        swatches = ttk.Frame(palette_area, style="Toolbar.TFrame")
        swatches.grid(row=1, column=0, sticky="ew")
        self._batik_swatch_buttons: list[tk.Button] = []
        columns = 22
        for index, color in enumerate(BATIK_COLORS):
            row, column = divmod(index, columns)
            button = tk.Button(
                swatches,
                background=color.hex_value,
                activebackground=color.hex_value,
                width=2,
                height=1,
                relief=tk.FLAT,
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=COLORS["line"],
                cursor="hand2",
                command=lambda value=color.hex_value: self._set_primary_color(value),
            )
            button.grid(row=row, column=column, padx=1, pady=1)
            button.bind(
                "<Button-3>",
                lambda _event, value=color.hex_value: self._set_secondary_color(value),
            )
            ToolTip(
                button,
                f"{color.name} · {color.hex_value}\n"
                "Klik kiri: warna utama · Klik kanan: warna sekunder",
            )
            self._batik_swatch_buttons.append(button)

        ttk.Button(
            parent,
            text=tr("palette.custom"),
            style="Secondary.TButton",
            command=lambda: self._choose_palette_color(primary=True),
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

        canvas_controls = ttk.Frame(parent, style="Toolbar.TFrame")
        canvas_controls.grid(row=0, column=3, rowspan=2, sticky="e", padx=(10, 0))
        ttk.Label(
            canvas_controls,
            text=tr("palette.canvas"),
            style="PanelTitle.TLabel",
        ).pack(side="left", padx=(0, 5))
        self._canvas_color_preview = tk.Button(
            canvas_controls,
            width=4,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=self._choose_canvas_color,
        )
        self._canvas_color_preview.pack(side="left")
        ToolTip(self._canvas_color_preview, tr("palette.canvas_tooltip"))
        self._update_color_previews()

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open AI settings and Batikify one object with an optional motif reference."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek sumber. Shift-pilih satu motif Batik bila ingin memakai "
                "referensi khusus."
            )
            return

        defaults = pretrained_batification_options_from_global()
        installed_models = (
            self.session.installed_models
            if isinstance(self.session, OfflineAIProjectSession)
            else ()
        )
        runtime = (
            self.session.runtime_selection
            if isinstance(self.session, OfflineAIProjectSession)
            else None
        )
        if runtime is not None:
            installed_models = tuple(
                sorted(
                    installed_models,
                    key=lambda item: item.manifest.model_id != runtime.model_id,
                )
            )
        dialog = AIObjectBatificationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        self.wait_window(dialog)
        options = dialog.result
        if options is None:
            self.set_status("Batifikasi Objek dengan AI dibatalkan.")
            return
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        reference = "motif terpilih" if plan.uses_selected_motif else "referensi Batik otomatis"
        self.set_status(
            f"Stable Diffusion + LoRA sedang membatikkan {plan.source_name} dengan {reference}. "
            "Bentuk dan alpha objek akan dipertahankan."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - worker failures return to Tk
                message = str(exc)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_pretrained_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-object-stable-diffusion-lora",
        ).start()

    def _remove_background_ai_from_editor_chrome(self) -> None:
        button = getattr(self, "_background_ai_button", None)
        if button is not None:
            try:
                button.destroy()
            except tk.TclError:
                pass
            self._background_ai_button = None
        _delete_menu_command(self._selection_context_menu, "AI Batik Background…")

    def _configure_object_batification_context_actions(self) -> None:
        """Guarantee that right-click AI opens the Stable Diffusion + LoRA dialog."""

        menu = self._selection_context_menu
        ai_index: int | None = None
        non_ai_index: int | None = None
        end = menu.index("end")
        if end is not None:
            for index in range(int(end) + 1):
                try:
                    label = str(menu.entrycget(index, "label"))
                except tk.TclError:
                    continue
                if label.startswith(("Batifikasi AI Pretrained", "Batifikasi Objek dengan AI")):
                    ai_index = index
                elif label in {"Batifikasi Non-AI…", _NON_AI_CONTEXT_LABEL}:
                    non_ai_index = index

        if non_ai_index is not None:
            # Batifikasi tanpa model telah dihapus: semua batifikasi via model.
            try:
                menu.delete(non_ai_index)
            except tk.TclError:
                pass
        if ai_index is not None:
            menu.entryconfigure(
                ai_index,
                label=_AI_CONTEXT_LABEL,
                command=self.batify_selected_with_pretrained_ai,
            )
            return

        menu.add_separator()
        menu.add_command(
            label=_AI_CONTEXT_LABEL,
            command=self.batify_selected_with_pretrained_ai,
        )


def _delete_menu_command(menu: tk.Menu, label: str) -> bool:
    """Delete a named command and an immediately preceding orphan separator."""

    end = menu.index("end")
    if end is None:
        return False
    for index in range(int(end), -1, -1):
        try:
            current = str(menu.entrycget(index, "label"))
        except tk.TclError:
            continue
        if current != label:
            continue
        menu.delete(index)
        if index > 0:
            try:
                if menu.type(index - 1) == "separator":
                    menu.delete(index - 1)
            except tk.TclError:
                pass
        return True
    return False


# ==========================================================================
# Layer v12 (dulu context_tool_editor_hotfix_v12.py)
# ==========================================================================

"""Progress-aware Stable Diffusion and LoRA object Batification."""


import threading

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .progress_dialog import ProgressDialog, ProgressUpdate


class _HotfixV12(_HotfixV11):
    """Keep the editor responsive and visibly progressing while AI runs."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._object_ai_progress: ProgressDialog | None = None
        super().__init__(*args, **kwargs)

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open settings, then show progress throughout Stable Diffusion inference."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek sumber. Shift-pilih satu motif Batik bila ingin memakai "
                "referensi khusus."
            )
            return

        defaults = pretrained_batification_options_from_global()
        installed_models = (
            self.session.installed_models
            if isinstance(self.session, OfflineAIProjectSession)
            else ()
        )
        runtime = (
            self.session.runtime_selection
            if isinstance(self.session, OfflineAIProjectSession)
            else None
        )
        if runtime is not None:
            installed_models = tuple(
                sorted(
                    installed_models,
                    key=lambda item: item.manifest.model_id != runtime.model_id,
                )
            )
        dialog = AIObjectBatificationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        self.wait_window(dialog)
        options = dialog.result
        if options is None:
            self.set_status("Batifikasi Objek dengan AI dibatalkan.")
            return

        progress = ProgressDialog(
            self,
            title="Batifikasi AI",
            message="Menyiapkan objek dan referensi motif…",
            cancellable=False,
            auto_close_ms=800,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Menyiapkan input objek",
                1,
                6,
                detail="Membaca alpha, siluet, dan objek sumber dari canvas.",
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        reference = "motif terpilih" if plan.uses_selected_motif else "referensi Batik otomatis"
        self.set_status(
            f"Stable Diffusion + LoRA sedang membatikkan {plan.source_name} dengan {reference}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menyiapkan runtime AI",
                    2,
                    6,
                    detail=(
                        f"Model: {plan.options.model_id_or_path}\n"
                        "Memuat Stable Diffusion, ControlNet bila aktif, dan LoRA Batik."
                    ),
                )
                reporter.update(
                    "Tahap 3/6 — Menjalankan Stable Diffusion + LoRA",
                    detail=(
                        f"Inference steps: {plan.options.inference_steps}. "
                        "Tahap ini biasanya memerlukan waktu paling lama."
                    ),
                )
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
                reporter.update(
                    "Tahap 4/6 — Memulihkan bentuk objek",
                    4,
                    6,
                    detail="Menerapkan kembali alpha, siluet, dan outline objek sumber.",
                )
                reporter.update(
                    "Tahap 5/6 — Menyiapkan hasil untuk canvas",
                    5,
                    6,
                    detail="Menyusun PNG hasil dan metadata model.",
                )
            except Exception as exc:  # noqa: BLE001 - worker failures return to Tk
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_progress_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-object-ai-with-progress",
        ).start()

    def _finish_progress_ai_success(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> None:
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.post(
                ProgressUpdate(
                    "Tahap 6/6 — Menambahkan hasil ke canvas",
                    6,
                    6,
                    detail="Menyimpan hasil sebagai objek baru dan menyiapkan Undo.",
                )
            )
        super()._finish_pretrained_ai_success(plan, result)
        if progress is not None and progress.winfo_exists():
            progress.finish("Batifikasi AI selesai")
        self._object_ai_progress = None

    def _finish_pretrained_ai_error(self, message: str) -> None:
        super()._finish_pretrained_ai_error(message)
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.fail(message)
        self._object_ai_progress = None


# ==========================================================================
# Layer v13 (dulu context_tool_editor_hotfix_v13.py)
# ==========================================================================

"""Progress feedback for remaining editor installation and packaging workflows."""


import threading
from tkinter import filedialog, messagebox

from batikcraft_studio.application import OfflineAIProjectSession
from batikcraft_studio.assets import ASSET_PACK_EXTENSION, AssetLibraryError

from .offline_ai_dialogs_progress import (
    ProgressDatasetStudioWindow,
    ProgressOfflineModelManagerWindow,
)
from .progress_dialog import ProgressDialog


class _HotfixV13(_HotfixV12):
    """Ensure remaining disk-heavy editor commands never appear frozen."""

    def install_asset_pack_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Instal Paket Asset BatikCraft",
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if selected:
            self._start_asset_pack_install(selected, replace=False)

    def _start_asset_pack_install(self, selected: str, *, replace: bool) -> None:
        progress = ProgressDialog(
            self,
            title="Instal Paket Asset",
            message="Membaca paket asset BatikCraft…",
            cancellable=False,
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 1/4 — Membaca manifest paket",
                    1,
                    4,
                    detail=selected,
                )
                reporter.update(
                    "Tahap 2/4 — Memvalidasi gambar dan metadata",
                    2,
                    4,
                )
                pack = self.asset_library.install_pack(selected, replace=replace)
                reporter.update(
                    "Tahap 3/4 — Mengindeks pustaka asset",
                    3,
                    4,
                    detail=f"Jumlah asset: {len(pack.assets)}",
                )
                reporter.update(
                    "Tahap 4/4 — Menyegarkan pencarian dan thumbnail",
                    4,
                    4,
                )
            except (AssetLibraryError, OSError) as exc:
                self.after(
                    0,
                    lambda error=exc: self._finish_asset_pack_error(
                        progress,
                        selected,
                        replace,
                        error,
                    ),
                )
                return
            self.after(
                0,
                lambda: self._finish_asset_pack_install(progress, pack),
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-install-asset-pack",
        ).start()

    def _finish_asset_pack_install(self, progress: ProgressDialog, pack: object) -> None:
        self.refresh_library()
        name = str(getattr(pack, "name", "Paket Asset"))
        assets = tuple(getattr(pack, "assets", ()))
        self.library_pack_value.set(name)
        self.set_status(f"{name} terpasang dengan {len(assets)} asset.")
        progress.finish("Paket asset berhasil dipasang")

    def _finish_asset_pack_error(
        self,
        progress: ProgressDialog,
        selected: str,
        replace: bool,
        error: Exception,
    ) -> None:
        message = str(error)
        if not replace and "sudah terpasang" in message:
            progress.close()
            should_replace = messagebox.askyesno(
                "Ganti paket yang sudah ada?",
                message,
                parent=self,
            )
            if should_replace:
                self._start_asset_pack_install(selected, replace=True)
            return
        progress.fail(message)
        messagebox.showerror("Instal paket gagal", message, parent=self)

    def open_dataset_studio(self) -> None:
        window = self._dataset_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        self._dataset_window = ProgressDatasetStudioWindow(self)

    def open_offline_model_manager(self) -> None:
        window = self._model_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        if not isinstance(self.session, OfflineAIProjectSession):
            raise RuntimeError("Editor AI offline memerlukan OfflineAIProjectSession.")
        self._model_window = ProgressOfflineModelManagerWindow(
            self,
            self.session,
            on_change=self._announce_provider,
        )


# ==========================================================================
# Layer v14 (dulu context_tool_editor_hotfix_v14.py)
# ==========================================================================

"""Notebook-compatible BatikBrew generation with local and cloud providers."""


import threading
import tkinter as tk
from dataclasses import asdict, replace

from batikcraft_studio.ai.batikbrew_generation import SDXL_BASE_MODEL_ID
from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    BatikBrewModeGenerationOptions,
)
from batikcraft_studio.ai.generation_providers import PROVIDER_LOCAL, provider_label
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.hybrid_batik_generation import (
    CloudBatikBrewOptions,
    HybridBatikGenerationProvider,
)
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.ai.runtime_model_installer import find_installed_batikbrew_runtime
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)

from .batik_ai_provider_dialog import BatikAIProviderDialog
from .batikbrew_generation_dialog import BatikBrewGenerationDialog
from .batikbrew_output_mode_dialog import BatikBrewOutputModeDialog
from .batikbrew_variation_dialog import BatikBrewVariationDialog
from .cloud_batik_generation_dialog import CloudBatikGenerationDialog
from .progress_dialog import ProgressDialog, ProgressUpdate

_BATIKBREW_CONTEXT_LABEL = "Generate Motif BatikBrew — Lokal / API…"


class _HotfixV14(_HotfixV13):
    """Generate an isolated ornament or full pattern using a selectable provider."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(HybridBatikGenerationProvider())
        self._configure_batikbrew_context_action()

    def batify_selected_with_pretrained_ai(self) -> None:
        """Choose output mode and provider, generate variations, then apply one result."""

        if self._pretrained_ai_running:
            self.set_status("Generasi BatikBrew masih berjalan. Tunggu proses sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek inspirasi. Shift-pilih objek kedua untuk menggabungkan "
                "dua sumber inspirasi."
            )
            return

        mode_dialog = BatikBrewOutputModeDialog(self)
        self.wait_window(mode_dialog)
        output_mode = mode_dialog.result
        if output_mode is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return

        provider_dialog = BatikAIProviderDialog(self, output_mode=output_mode)
        self.wait_window(provider_dialog)
        provider_id = provider_dialog.result
        if provider_id is None:
            self.set_status("Pemilihan provider BatikBrew dibatalkan.")
            return

        defaults = pretrained_batification_options_from_global()
        options = self._collect_generation_options(
            defaults=defaults,
            output_mode=output_mode,
            provider_id=provider_id,
        )
        if options is None:
            return

        progress = ProgressDialog(
            self,
            title=(
                "Generate Ornamen BatikBrew"
                if output_mode == OUTPUT_MODE_ORNAMENT
                else "Generate Pola BatikBrew"
            ),
            message="Menyiapkan objek inspirasi…",
            cancellable=False,
            auto_close_ms=None,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Membaca objek inspirasi",
                1,
                6,
                detail=(
                    "Satu objek" if len(selected) == 1 else "Dua objek akan dianalisis bersama"
                ),
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        kind = "ornamen tunggal" if output_mode == OUTPUT_MODE_ORNAMENT else "pola penuh"
        provider_name = provider_label(provider_id)
        self.set_status(
            f"{provider_name} sedang membuat {options.variation_count} variasi {kind}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menganalisis warna, garis, tema, dan komposisi",
                    2,
                    6,
                    detail="Dominant palette, edge density, theme keywords, dan prompt Batik.",
                )
                if provider_id == PROVIDER_LOCAL:
                    stage = "Tahap 3/6 — Memuat Stable Diffusion XL dan LoRA BatikBrew"
                    detail = f"Base model: {options.model_id_or_path}"
                else:
                    stage = f"Tahap 3/6 — Menghubungkan {provider_name}"
                    detail = f"Model API: {getattr(options, 'provider_model', '-')}"
                reporter.update(stage, 3, 6, detail=detail)
                reporter.update(
                    "Tahap 4/6 — Menghasilkan variasi gambar",
                    detail=(
                        f"{options.variation_count} variasi · provider {provider_name} · "
                        f"seed hint {options.seed}"
                    ),
                )
                results = self._pretrained_ai_session.render_pretrained_ai_variations(plan)
                reporter.update(
                    "Tahap 5/6 — Menyelesaikan transparansi atau tileable output",
                    5,
                    6,
                    detail=(
                        "Background dihapus untuk ornamen tunggal"
                        if output_mode == OUTPUT_MODE_ORNAMENT
                        else "Opposite-edge blending untuk pola seamless"
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - worker failures return to Tk
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_batikbrew_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._show_batikbrew_variations(plan, results)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"batikcraft-batikbrew-{provider_id}-generation",
        ).start()

    def _collect_generation_options(
        self,
        *,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        provider_id: str,
    ) -> BatikBrewModeGenerationOptions | CloudBatikBrewOptions | None:
        if provider_id != PROVIDER_LOCAL:
            dialog = CloudBatikGenerationDialog(
                self,
                provider_id=provider_id,
                output_mode=output_mode,
                defaults=defaults,
            )
            self.wait_window(dialog)
            if dialog.result is None:
                self.set_status("Generasi BatikBrew API dibatalkan.")
            return dialog.result

        managed = find_installed_batikbrew_runtime()
        local_defaults = replace(
            defaults,
            model_id_or_path=(
                str(managed.base_model) if managed is not None else SDXL_BASE_MODEL_ID
            ),
            local_files_only=managed is not None,
            inference_steps=max(30, defaults.inference_steps),
            guidance_scale=7.5,
            resolution=max(512, defaults.resolution),
        )
        installed_models = (
            self.session.installed_models
            if isinstance(self.session, OfflineAIProjectSession)
            else ()
        )
        dialog = BatikBrewGenerationDialog(
            self,
            defaults=local_defaults,
            installed_models=installed_models,
        )
        if output_mode == OUTPUT_MODE_ORNAMENT:
            dialog.title("BatikBrew Lokal — Ornamen Tunggal")
            dialog.tileable_value.set(False)
        else:
            dialog.title("BatikBrew Lokal — Pola")
        self.wait_window(dialog)
        raw_options = dialog.result
        if raw_options is None:
            self.set_status("Generasi BatikBrew lokal dibatalkan.")
            return None
        try:
            return BatikBrewModeGenerationOptions(
                **asdict(raw_options),
                output_mode=output_mode,
            )
        except (TypeError, ValueError) as exc:
            self.set_status(f"Pengaturan BatikBrew tidak valid: {exc}")
            return None

    def _show_batikbrew_variations(
        self,
        plan: PretrainedAIPlan,
        results: tuple[PretrainedAIBatificationResult, ...],
    ) -> None:
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.post(
                ProgressUpdate(
                    "Tahap 6/6 — Pilih variasi yang akan dipakai",
                    6,
                    6,
                    detail=f"{len(results)} variasi berhasil dibuat.",
                )
            )
            progress.close()
        self._object_ai_progress = None
        if self._pretrained_ai_destroyed:
            self._pretrained_ai_running = False
            return

        chooser = BatikBrewVariationDialog(self, results)
        self.wait_window(chooser)
        selected = chooser.result
        if selected is None:
            self._pretrained_ai_running = False
            self.set_status("Hasil BatikBrew tidak diterapkan karena pemilihan dibatalkan.")
            return
        super()._finish_pretrained_ai_success(plan, selected)

        project = self.session.project
        if project is not None and project.active_object_id is not None:
            self.session.set_selected_objects([project.active_object_id])
        self.focus_set()
        self.set_status("Hasil AI aktif dan siap disalin dengan Ctrl+C / Ctrl+V.")

    def _finish_batikbrew_error(self, message: str) -> None:
        super()._finish_pretrained_ai_error(message)
        self._object_ai_progress = None

    def _configure_batikbrew_context_action(self) -> None:
        menu = self._selection_context_menu
        end = menu.index(tk.END)
        if end is None:
            return
        for index in range(int(end) + 1):
            try:
                label = str(menu.entrycget(index, "label"))
            except tk.TclError:
                continue
            if label.startswith(("Batifikasi AI", "Generate Motif BatikBrew")):
                menu.entryconfigure(
                    index,
                    label=_BATIKBREW_CONTEXT_LABEL,
                    command=self.batify_selected_with_pretrained_ai,
                )
                return
        menu.add_separator()
        menu.add_command(
            label=_BATIKBREW_CONTEXT_LABEL,
            command=self.batify_selected_with_pretrained_ai,
        )


# ==========================================================================
# Layer v15 (dulu context_tool_editor_hotfix_v15.py)
# ==========================================================================

"""BatikBrew generation that consumes centrally managed AI settings."""


import threading
from pathlib import Path
from tkinter import messagebox

from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    BatikBrewModeGenerationOptions,
)
from batikcraft_studio.ai.batikbrew_model_settings import (
    get_batikbrew_model_settings_store,
)
from batikcraft_studio.ai.generation_providers import (
    PROVIDER_LOCAL,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_label,
)
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.hybrid_batik_generation import CloudBatikBrewOptions
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.imaging.structured_batification import BatificationError

from .batik_ai_provider_dialog import BatikAIProviderDialog
from .batikbrew_output_mode_dialog import BatikBrewOutputModeDialog
from .batikbrew_request_dialog import BatikBrewRequest, BatikBrewRequestDialog
from .progress_dialog import ProgressDialog, ProgressUpdate


class ContextToolEditorWorkspaceView(_HotfixV14):
    """Generate with a model explicitly selected from centrally saved settings."""

    def batify_selected_with_pretrained_ai(self) -> None:
        if self._pretrained_ai_running:
            self.set_status("Generasi BatikBrew masih berjalan. Tunggu proses sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek inspirasi. Shift-pilih objek kedua untuk menggabungkan "
                "dua sumber inspirasi."
            )
            return

        mode_dialog = BatikBrewOutputModeDialog(self)
        self.wait_window(mode_dialog)
        output_mode = mode_dialog.result
        if output_mode is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return

        model_dialog = BatikAIProviderDialog(self, output_mode=output_mode)
        self.wait_window(model_dialog)
        provider_id = model_dialog.result
        if provider_id is None:
            self.set_status("Pemilihan model BatikBrew dibatalkan.")
            return

        defaults = pretrained_batification_options_from_global()
        options = self._collect_centralized_options(
            defaults=defaults,
            output_mode=output_mode,
            provider_id=provider_id,
        )
        if options is None:
            return

        progress = ProgressDialog(
            self,
            title=(
                "Generate Ornamen BatikBrew"
                if output_mode == OUTPUT_MODE_ORNAMENT
                else "Generate Pola BatikBrew"
            ),
            message="Menyiapkan objek inspirasi…",
            cancellable=False,
            auto_close_ms=None,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Membaca objek inspirasi",
                1,
                6,
                detail=(
                    "Satu objek" if len(selected) == 1 else "Dua objek akan dianalisis bersama"
                ),
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        kind = "ornamen tunggal" if output_mode == OUTPUT_MODE_ORNAMENT else "pola penuh"
        provider_name = provider_label(provider_id)
        self.set_status(
            f"{provider_name} sedang membuat {options.variation_count} variasi {kind}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menganalisis warna, garis, tema, dan komposisi",
                    2,
                    6,
                    detail="Dominant palette, edge density, theme keywords, dan prompt Batik.",
                )
                if provider_id == PROVIDER_LOCAL:
                    stage = "Tahap 3/6 — Memuat model dan LoRA aktif dari Settings"
                    detail = (
                        f"Base model: {options.model_id_or_path}\n"
                        f"LoRA: {Path(options.lora_path).name}"
                    )
                else:
                    stage = f"Tahap 3/6 — Menghubungkan {provider_name}"
                    detail = f"Model API: {getattr(options, 'provider_model', '-')}"
                reporter.update(stage, 3, 6, detail=detail)
                reporter.update(
                    "Tahap 4/6 — Menghasilkan variasi gambar",
                    detail=(
                        f"{options.variation_count} variasi · provider {provider_name} · "
                        f"seed hint {options.seed}"
                    ),
                )
                results = self._pretrained_ai_session.render_pretrained_ai_variations(plan)
                reporter.update(
                    "Tahap 5/6 — Menyelesaikan transparansi atau tileable output",
                    5,
                    6,
                    detail=(
                        "Background dihapus untuk ornamen tunggal"
                        if output_mode == OUTPUT_MODE_ORNAMENT
                        else "Opposite-edge blending untuk pola seamless"
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - provider SDK errors vary
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_batikbrew_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._show_batikbrew_variations(plan, results)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"batikcraft-batikbrew-{provider_id}-generation",
        ).start()

    def _collect_centralized_options(
        self,
        *,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        provider_id: str,
    ) -> BatikBrewModeGenerationOptions | CloudBatikBrewOptions | None:
        provider_summary = self._provider_summary(provider_id)
        if provider_summary is None:
            return None
        cloud_request = provider_id != PROVIDER_LOCAL
        dialog = BatikBrewRequestDialog(
            self,
            output_mode=output_mode,
            provider_summary=provider_summary,
            prompt=defaults.prompt,
            negative_prompt=defaults.negative_prompt,
            seed=defaults.seed,
            default_variation_count=1 if cloud_request else 4,
            request_notice=(
                "Setiap variasi cloud mengirim satu request gambar terpisah. Default dibuat "
                "1 variasi untuk mengurangi biaya dan mencegah error 429 Too Many Requests."
                if cloud_request
                else "Generasi lokal tidak memakai kuota API; default tetap 4 variasi."
            ),
        )
        self.wait_window(dialog)
        request = dialog.result
        if request is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return None
        try:
            if provider_id == PROVIDER_LOCAL:
                return self._local_options(defaults, output_mode, request)
            return self._cloud_options(defaults, output_mode, provider_id, request)
        except (BatificationError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan AI tidak valid", str(exc), parent=self)
            return None

    def _provider_summary(self, provider_id: str) -> str | None:
        if provider_id == PROVIDER_LOCAL:
            active = get_batikbrew_model_settings_store().load()
            if not active.configured:
                messagebox.showerror(
                    "Model lokal belum diatur",
                    "Belum ada model SDXL + LoRA aktif. Buka Settings → Pengaturan AI, "
                    "Model & LoRA → Model Lokal, Runtime & LoRA, lalu aktifkan satu model.",
                    parent=self,
                )
                return None
            return f"{provider_label(provider_id)} · {active.model_id}"

        cloud = get_cloud_generation_settings_store().load()
        model = cloud.model_for(provider_id)
        if not get_api_secret_store().has(provider_id):
            messagebox.showerror(
                "API key belum diatur",
                f"API key {provider_label(provider_id)} belum tersedia. Buka Settings → "
                "Pengaturan AI, Model & LoRA → Provider Cloud & Model API.",
                parent=self,
            )
            return None
        return f"{provider_label(provider_id)} · {model}"

    def _local_options(
        self,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        request: BatikBrewRequest,
    ) -> BatikBrewModeGenerationOptions:
        active = get_batikbrew_model_settings_store().load()
        if not active.configured:
            raise BatificationError("Model lokal BatikBrew belum dipilih dari Settings.")
        if not Path(active.lora_path).expanduser().is_file():
            raise BatificationError(
                "File LoRA aktif tidak ditemukan. Pilih ulang model dari Settings."
            )
        model_path = Path(active.base_model_path).expanduser()
        return BatikBrewModeGenerationOptions(
            model_id_or_path=active.base_model_path,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            inference_steps=active.inference_steps,
            guidance_scale=active.guidance_scale,
            seed=request.seed,
            device=defaults.device,
            precision=defaults.precision,
            local_files_only=model_path.exists(),
            cpu_offload=defaults.cpu_offload,
            cache_dir=defaults.cache_dir,
            resolution=active.resolution,
            lora_path=active.lora_path,
            lora_weight=active.lora_weight,
            lora_trigger_words=active.trigger_words,
            variation_count=request.variation_count,
            tileable=request.tileable,
            output_mode=output_mode,
        )

    def _cloud_options(
        self,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        provider_id: str,
        request: BatikBrewRequest,
    ) -> CloudBatikBrewOptions:
        settings = get_cloud_generation_settings_store().load()
        return CloudBatikBrewOptions(
            model_id_or_path=defaults.model_id_or_path,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            strength=defaults.strength,
            ai_blend=defaults.ai_blend,
            pattern_scale=defaults.pattern_scale,
            preserve_shading=defaults.preserve_shading,
            inference_steps=defaults.inference_steps,
            guidance_scale=defaults.guidance_scale,
            seed=request.seed,
            device=defaults.device,
            precision=defaults.precision,
            local_files_only=False,
            cpu_offload=False,
            cache_dir=defaults.cache_dir,
            resolution=defaults.resolution,
            lora_path="",
            lora_weight=0.0,
            lora_trigger_words=("traditional Indonesian batik",),
            variation_count=request.variation_count,
            tileable=request.tileable,
            generation_provider=provider_id,
            provider_model=settings.model_for(provider_id),
            output_mode=output_mode,
        )


__all__ = ["ContextToolEditorWorkspaceView"]
