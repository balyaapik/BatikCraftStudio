"""Application shell for contextual tools, recent projects, and NFT export."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from batikcraft_studio.ai import get_ai_runtime_store
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging import ProjectRenderError
from batikcraft_studio.persistence import (
    BATIKCRAFT_NFT_EXTENSION,
    BatikNFTError,
    ProjectArchiveError,
    export_batikcraft_nft,
)
from batikcraft_studio.project_export import (
    creator_id_suggestion,
    discover_project_colors,
    discover_project_motifs,
    render_project_jpeg,
)
from batikcraft_studio.recent_projects import RecentProjectStore

from . import app as app_module
from .direct_style_app import DirectStyleApplication
from .ui.ai_runtime_settings_dialog import AIRuntimeSettingsDialog
from .ui.external_image_i18n import install_external_image_translations
from .ui.nft_export_dialog import NFTExportDialog
from .ui.project_export_i18n import install_project_export_translations

install_external_image_translations()
install_project_export_translations()


class ContextToolApplication(DirectStyleApplication):
    """Launch the editor with global AI, recent projects, and verified exports."""

    def __init__(self) -> None:
        self.recent_projects = RecentProjectStore()
        self._recent_menu: tk.Menu | None = None
        try:
            from tkinterdnd2 import TkinterDnD
        except ImportError:
            super().__init__()
            return

        # TkinterDnD.Tk.__init__ internally calls tkinter.Tk.__init__. Replacing
        # tkinter.Tk with TkinterDnD.Tk before constructing the root therefore
        # recurses forever. Construct the DnD root first while tkinter.Tk is still
        # the original class, then let the existing application initializer adopt
        # that already-created root through a short-lived factory.
        dnd_root = TkinterDnD.Tk()
        original_tk_factory = app_module.tk.Tk
        app_module.tk.Tk = lambda: dnd_root  # type: ignore[misc,assignment]
        try:
            super().__init__()
        except Exception:
            try:
                dnd_root.destroy()
            except tk.TclError:
                pass
            raise
        finally:
            app_module.tk.Tk = original_tk_factory  # type: ignore[misc,assignment]

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        _file_index, file_menu = _find_cascade_menu(
            menu_bar,
            tr("menu.file"),
            "Berkas",
            "File",
        )
        recent_menu = tk.Menu(file_menu, postcommand=self._refresh_recent_menu)
        file_menu.insert_cascade(
            2,
            label=tr("file.recent_projects"),
            menu=recent_menu,
        )
        self._recent_menu = recent_menu
        self._refresh_recent_menu()

        export_menu = tk.Menu(file_menu)
        export_menu.add_command(
            label=tr("file.export_jpg"),
            command=lambda: self.export_project_image(".jpg"),
        )
        export_menu.add_command(
            label=tr("file.export_jpeg"),
            command=lambda: self.export_project_image(".jpeg"),
        )
        export_menu.add_separator()
        export_menu.add_command(
            label=tr("file.export_nft"),
            command=self.export_project_nft,
        )
        save_as_index = _find_command_index(
            file_menu,
            tr("file.save_as"),
            "Simpan Sebagai…",
            "Save As…",
        )
        file_menu.insert_cascade(
            save_as_index + 1,
            label=tr("file.export_as"),
            menu=export_menu,
        )

        _edit_index, edit_menu = _find_cascade_menu(
            menu_bar,
            tr("menu.edit"),
            "Edit",
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Preferences → AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        editor = self.main_window._editor()
        insert_menu = tk.Menu(menu_bar)
        insert_menu.add_command(
            label=tr("insert.image_file"),
            accelerator="Ctrl+Shift+I",
            command=editor.import_external_image_dialog,
        )
        insert_menu.add_command(
            label=tr("insert.image_clipboard"),
            accelerator="Ctrl+V",
            command=editor.paste_external_image,
        )
        menu_bar.insert_cascade(2, label=tr("menu.insert"), menu=insert_menu)

        # Structured Batification already creates the AI Batik menu. Reuse that
        # cascade instead of adding a second top-level menu with overlapping functions.
        ai_index, ai_menu = _find_cascade_menu(
            menu_bar,
            tr("menu.ai"),
            "AI Batik",
            "Batik AI",
            "AI",
        )
        menu_bar.entryconfigure(ai_index, label=tr("menu.ai"))
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Batifikasi Objek dengan Stable Diffusion + LoRA…",
            accelerator="Ctrl+Alt+Shift+B",
            command=editor.batify_selected_with_pretrained_ai,
        )
        ai_menu.add_command(
            label="AI Batik Background…",
            accelerator="Ctrl+Alt+Shift+G",
            command=editor.generate_ai_batik_background,
        )
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Pengaturan AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        bindings = (
            ("<Control-Shift-i>", editor.import_external_image_dialog),
            ("<Control-Shift-I>", editor.import_external_image_dialog),
            ("<Control-comma>", self.open_ai_runtime_settings),
            ("<Control-Alt-Shift-b>", editor.batify_selected_with_pretrained_ai),
            ("<Control-Alt-Shift-g>", editor.generate_ai_batik_background),
        )
        for sequence, command in bindings:
            self.root.bind_all(
                sequence,
                lambda event, action=command: self._run_shortcut(event, action),
            )

    def open_project(self) -> None:
        """Open through the standard dialog and remember successful paths."""

        previous = self.session.path
        super().open_project()
        current = self.session.path
        if current is not None and (previous is None or current != previous):
            self._remember_current_project()

    def save_project(self) -> bool:
        """Save and refresh the MRU entry for the current project."""

        saved = super().save_project()
        if saved:
            self._remember_current_project()
        return saved

    def save_project_as(self) -> bool:
        """Save As and place the new path at the front of Recent Projects."""

        saved = super().save_project_as()
        if saved:
            self._remember_current_project()
        return saved

    def open_recent_project(self, value: str | Path) -> None:
        """Open one MRU entry without displaying a second file chooser."""

        path = Path(value)
        if not path.is_file():
            try:
                self.recent_projects.remove(path)
            except OSError:
                pass
            self._refresh_recent_menu()
            messagebox.showwarning(
                tr("recent.missing.title"),
                tr("recent.missing.message", path=path),
                parent=self.root,
            )
            return
        if not self._confirm_project_transition(tr("action.open_another")):
            return
        self.main_window.set_busy(True, tr("status.opening"))
        try:
            project = self.session.open_project(path)
        except (ProjectArchiveError, OSError) as exc:
            self.main_window.set_busy(False, tr("status.open_failed"))
            messagebox.showerror(
                tr("recent.open_error"),
                str(exc),
                parent=self.root,
            )
            return
        self.main_window.set_busy(False)
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(
            tr("status.project_opened", title=project.metadata.title)
        )
        self._remember_current_project()

    def export_project_image(self, suffix: str) -> None:
        """Flatten the full canvas to a high-quality JPG or JPEG file."""

        project = self.session.project
        if project is None:
            self.main_window.flash_status(tr("status.no_open_project"))
            return
        suffix = ".jpeg" if suffix.casefold() == ".jpeg" else ".jpg"
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("dialog.export_image.title"),
            defaultextension=suffix,
            initialfile=f"{_filename_stem(project.metadata.title)}{suffix}",
            filetypes=(("JPEG image", "*.jpg *.jpeg"),),
        )
        if not destination:
            return
        target = Path(destination)
        if target.suffix.casefold() not in {".jpg", ".jpeg"}:
            target = target.with_suffix(suffix)
        self.main_window.set_busy(True, tr("status.saving"))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            from batikcraft_studio.persistence.raster_archive import write_bytes_atomic

            target = write_bytes_atomic(
                target, render_project_jpeg(project, self.session.assets)
            )
        except (OSError, ProjectRenderError, ValueError) as exc:
            self.main_window.set_busy(False, tr("status.export_failed"))
            messagebox.showerror(
                tr("status.export_failed"),
                str(exc),
                parent=self.root,
            )
            return
        self.main_window.set_busy(False)
        self.main_window.flash_status(tr("status.image_exported", name=target.name))

    def export_project_nft(self) -> None:
        """Collect marketplace metadata and export a checksummed project package."""

        project = self.session.project
        if project is None:
            self.main_window.flash_status(tr("status.no_open_project"))
            return
        dialog = NFTExportDialog(
            self.root,
            creator_name=project.metadata.creator,
            creator_user_id=creator_id_suggestion(project.metadata.creator),
            philosophy=project.metadata.description,
            motifs=discover_project_motifs(project),
            colors=discover_project_colors(project),
        )
        metadata = dialog.result
        if metadata is None:
            return
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("dialog.export_nft.title"),
            defaultextension=BATIKCRAFT_NFT_EXTENSION,
            initialfile=(
                f"{_filename_stem(project.metadata.title)}{BATIKCRAFT_NFT_EXTENSION}"
            ),
            filetypes=(
                ("BatikCraft NFT", f"*{BATIKCRAFT_NFT_EXTENSION}"),
                ("All files", "*.*"),
            ),
        )
        if not destination:
            return
        self.main_window.set_busy(True, tr("status.saving"))
        try:
            preview = render_project_jpeg(project, self.session.assets)
            target = export_batikcraft_nft(
                destination,
                project,
                self.session.assets,
                preview,
                metadata,
            )
        except (BatikNFTError, OSError, ProjectRenderError, ValueError) as exc:
            self.main_window.set_busy(False, tr("status.export_failed"))
            messagebox.showerror(
                tr("status.export_failed"),
                str(exc),
                parent=self.root,
            )
            return
        self.main_window.set_busy(False)
        self.main_window.flash_status(tr("status.nft_exported", name=target.name))

    def _remember_current_project(self) -> None:
        project = self.session.project
        path = self.session.path
        if project is None or path is None:
            return
        try:
            self.recent_projects.remember(path, project.metadata.title)
        except OSError:
            return
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        menu = self._recent_menu
        if menu is None:
            return
        menu.delete(0, tk.END)
        try:
            entries = self.recent_projects.prune_missing()
        except OSError:
            entries = self.recent_projects.load()
        if not entries:
            menu.add_command(label=tr("file.recent_empty"), state=tk.DISABLED)
        else:
            for index, entry in enumerate(entries, start=1):
                label = f"{index}. {entry.title} — {entry.path}"
                menu.add_command(
                    label=label,
                    command=lambda path=entry.path: self.open_recent_project(path),
                )
        menu.add_separator()
        menu.add_command(
            label=tr("file.recent_clear"),
            command=self._clear_recent_projects,
            state=tk.NORMAL if entries else tk.DISABLED,
        )

    def _clear_recent_projects(self) -> None:
        try:
            self.recent_projects.clear()
        except OSError as exc:
            messagebox.showerror(
                tr("file.recent_projects"),
                str(exc),
                parent=self.root,
            )
        self._refresh_recent_menu()

    def open_ai_runtime_settings(self) -> None:
        """Open the one persistent compute profile used by all AI workflows."""

        dialog = AIRuntimeSettingsDialog(
            self.root,
            get_ai_runtime_store(),
            unload_models=self._unload_ai_models,
        )
        self.root.wait_window(dialog)
        settings = dialog.result
        if settings is None:
            return
        offload = "aktif" if settings.effective_cpu_offload else "nonaktif"
        self.main_window.flash_status(
            f"Runtime AI global disimpan: {settings.device} / {settings.precision}; "
            f"CPU offload {offload}."
        )

    def _unload_ai_models(self) -> None:
        """Release cached pipelines without clearing the selected offline LoRA."""

        for method_name in ("unload_pretrained_ai", "unload_background_ai"):
            callback = getattr(self.session, method_name, None)
            if callable(callback):
                callback()
        provider = getattr(self.session, "_batification_provider", None)
        unload = getattr(provider, "unload", None)
        if callable(unload):
            unload()


def _find_cascade_menu(menu_bar: tk.Menu, *labels: str) -> tuple[int, tk.Menu]:
    """Find a cascade by label without depending on a fixed menu index."""

    expected = {str(label) for label in labels}
    end = menu_bar.index(tk.END)
    if end is not None:
        for index in range(end + 1):
            if menu_bar.type(index) != "cascade":
                continue
            if str(menu_bar.entrycget(index, "label")) not in expected:
                continue
            child = menu_bar.nametowidget(str(menu_bar.entrycget(index, "menu")))
            return index, child
    raise RuntimeError(f"Menu tidak ditemukan: {', '.join(sorted(expected))}")


def _find_command_index(menu: tk.Menu, *labels: str) -> int:
    expected = {str(label) for label in labels}
    end = menu.index(tk.END)
    if end is not None:
        for index in range(end + 1):
            if menu.type(index) != "command":
                continue
            if str(menu.entrycget(index, "label")) in expected:
                return index
    raise RuntimeError(f"Perintah menu tidak ditemukan: {', '.join(sorted(expected))}")


def _filename_stem(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-.")
    return slug or "untitled"


__all__ = ["ContextToolApplication"]
