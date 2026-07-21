"""Application lifecycle, bilingual menu bar, and project commands."""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox

from batikcraft_studio.application import (
    NoActiveProjectError,
    ProjectPathRequiredError,
    ProjectSession,
)
from batikcraft_studio.i18n import current_language, set_language, tr
from batikcraft_studio.persistence import PROJECT_EXTENSION, ProjectArchiveError

from .config import APP_NAME, APP_VERSION, DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE
from .ui.dialogs import NewProjectDialog
from .ui.keyboard import event_targets_text_input
from .ui.main_window import MainWindow
from .ui.theme import configure_theme


class BatikCraftApplication:
    """Own the Tk root, bilingual asset-first UI, session, and clean shutdown."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        try:
            from .logging_setup import install_tk_exception_logging

            install_tk_exception_logging(self.root)
        except Exception:  # noqa: BLE001
            pass
        self.root.title(APP_NAME)
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*MINIMUM_WINDOW_SIZE)
        self.root.option_add("*tearOff", False)

        configure_theme(self.root)
        self.session = ProjectSession()
        self.language_value = tk.StringVar(master=self.root, value=current_language())
        self.main_window = self._create_main_window()
        self._build_menu()
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)

    def _create_main_window(self) -> MainWindow:
        return MainWindow(
            self.root,
            self.session,
            file_commands={
                "new": self.new_project,
                "open": self.open_project,
                "save": self.save_project,
            },
        )

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar)
        file_menu.add_command(
            label=tr("file.new_project"),
            accelerator="Ctrl+N",
            command=self.new_project,
        )
        file_menu.add_command(
            label=tr("file.open_project"),
            accelerator="Ctrl+O",
            command=self.open_project,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=tr("file.import_asset"),
            accelerator="Ctrl+I",
            command=self.main_window.editor_import_image,
        )
        file_menu.add_command(
            label=tr("file.install_pack"),
            command=self.main_window.install_asset_pack,
        )
        file_menu.add_command(
            label=tr("file.export_asset"),
            command=self.main_window.export_selected_asset,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=tr("file.save"),
            accelerator="Ctrl+S",
            command=self.save_project,
        )
        file_menu.add_command(
            label=tr("file.save_as"),
            accelerator="Ctrl+Shift+S",
            command=self.save_project_as,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=tr("file.print"),
            accelerator="Ctrl+P",
            command=self.print_project,
        )
        file_menu.add_command(
            label=tr("file.print_as"),
            accelerator="Ctrl+Shift+P",
            command=self.print_project_as,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=tr("file.close_project"),
            accelerator="Ctrl+W",
            command=self.close_project,
        )
        file_menu.add_command(label=tr("file.exit"), command=self.request_close)
        menu_bar.add_cascade(label=tr("menu.file"), menu=file_menu)

        edit_menu = tk.Menu(menu_bar)
        edit_menu.add_command(
            label=tr("edit.undo"),
            accelerator="Ctrl+Z",
            command=self.main_window.editor_undo,
        )
        edit_menu.add_command(
            label=tr("edit.redo"),
            accelerator="Ctrl+Y",
            command=self.main_window.editor_redo,
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label=tr("edit.duplicate"),
            accelerator="Ctrl+D",
            command=self.main_window.editor_duplicate,
        )
        edit_menu.add_command(
            label=tr("edit.delete"),
            accelerator="Delete",
            command=self.main_window.editor_delete,
        )
        edit_menu.add_command(
            label=tr("edit.transform"),
            command=self.main_window.open_transform_settings,
        )
        menu_bar.add_cascade(label=tr("menu.edit"), menu=edit_menu)

        layer_menu = tk.Menu(menu_bar)
        layer_menu.add_command(
            label=tr("layer.new_folder"),
            command=self.main_window.new_folder,
        )
        layer_menu.add_command(
            label=tr("layer.new_object"),
            command=self.main_window.new_object_layer,
        )
        layer_menu.add_command(
            label=tr("layer.new_canting"),
            command=self.main_window.new_paint_layer,
        )
        layer_menu.add_separator()
        layer_menu.add_command(
            label=tr("layer.visibility"),
            command=self.main_window.toggle_visibility,
        )
        layer_menu.add_command(
            label=tr("layer.lock"),
            command=self.main_window.toggle_lock,
        )
        menu_bar.add_cascade(label=tr("menu.layer"), menu=layer_menu)

        draw_menu = tk.Menu(menu_bar)
        draw_menu.add_command(
            label=tr("draw.select"),
            accelerator="V",
            command=self.main_window.activate_select_tool,
        )
        draw_menu.add_separator()
        draw_menu.add_command(
            label=tr("draw.brush"),
            accelerator="B",
            command=self.main_window.open_brush_settings,
        )
        draw_menu.add_command(
            label=tr("draw.eraser"),
            accelerator="E",
            command=self.main_window.open_eraser_settings,
        )
        shape_menu = tk.Menu(draw_menu)
        for key, translation_key, accelerator in (
            ("line", "draw.line", "L"),
            ("rectangle", "draw.rectangle", "R"),
            ("ellipse", "draw.ellipse", "O"),
            ("polygon", "draw.polygon", "P"),
        ):
            shape_menu.add_command(
                label=tr(translation_key),
                accelerator=accelerator,
                command=lambda kind=key: self.main_window.open_shape_settings(kind),
            )
        draw_menu.add_cascade(label=tr("draw.shape"), menu=shape_menu)
        draw_menu.add_separator()
        draw_menu.add_command(
            label=tr("draw.motif"),
            accelerator="M",
            command=self.main_window.open_motif_settings,
        )
        draw_menu.add_command(
            label=tr("draw.isen"),
            accelerator="C",
            command=self.main_window.open_isen_settings,
        )
        menu_bar.add_cascade(label=tr("menu.draw"), menu=draw_menu)

        asset_menu = tk.Menu(menu_bar)
        asset_menu.add_command(
            label=tr("asset.focus_library"),
            accelerator="Ctrl+L",
            command=self.main_window.focus_asset_library,
        )
        asset_menu.add_separator()
        asset_menu.add_command(
            label=tr("file.install_pack"),
            command=self.main_window.install_asset_pack,
        )
        asset_menu.add_command(
            label=tr("asset.remove_pack"),
            command=self.main_window.uninstall_asset_pack,
        )
        asset_menu.add_command(
            label=tr("asset.import_single"),
            command=self.main_window.editor_import_image,
        )
        asset_menu.add_command(
            label=tr("file.export_asset"),
            command=self.main_window.export_selected_asset,
        )
        asset_menu.add_separator()
        asset_menu.add_command(
            label=tr("asset.metadata"),
            command=self.main_window.open_asset_metadata_settings,
        )
        asset_menu.add_command(
            label=tr("asset.humanize"),
            command=self.main_window.open_humanize_settings,
        )
        asset_menu.add_command(
            label=tr("asset.reset_humanize"),
            command=self.main_window.reset_humanize,
        )
        menu_bar.add_cascade(label=tr("menu.asset"), menu=asset_menu)

        view_menu = tk.Menu(menu_bar)
        view_menu.add_command(
            label=tr("asset.focus_library"),
            accelerator="Ctrl+L",
            command=self.main_window.focus_asset_library,
        )
        view_menu.add_command(
            label=tr("view.focus_canvas"),
            command=lambda: self.main_window._editor().canvas.focus_set(),
        )
        menu_bar.add_cascade(label=tr("menu.view"), menu=view_menu)

        language_menu = tk.Menu(menu_bar)
        language_menu.add_radiobutton(
            label=tr("language.indonesian"),
            value="id",
            variable=self.language_value,
            command=lambda: self.change_language("id"),
        )
        language_menu.add_radiobutton(
            label=tr("language.english"),
            value="en",
            variable=self.language_value,
            command=lambda: self.change_language("en"),
        )
        menu_bar.add_cascade(label=tr("menu.language"), menu=language_menu)

        help_menu = tk.Menu(menu_bar)
        help_menu.add_command(label=tr("help.about"), command=self.show_about)
        menu_bar.add_cascade(label=tr("menu.help"), menu=help_menu)

        self.root.configure(menu=menu_bar)
        bindings: tuple[tuple[str, Callable[[], object]], ...] = (
            ("<Control-n>", self.new_project),
            ("<Control-o>", self.open_project),
            ("<Control-i>", self.main_window.editor_import_image),
            ("<Control-s>", self.save_project),
            ("<Control-Shift-S>", self.save_project_as),
            ("<Control-p>", self.print_project),
            ("<Control-Shift-P>", self.print_project_as),
            ("<Control-w>", self.close_project),
            ("<Control-z>", self.main_window.editor_undo),
            ("<Control-y>", self.main_window.editor_redo),
            ("<Control-Shift-Z>", self.main_window.editor_redo),
            ("<Control-d>", self.main_window.editor_duplicate),
            ("<Control-l>", self.main_window.focus_asset_library),
            ("<Delete>", self.main_window.editor_delete),
        )
        for sequence, command in bindings:
            self.root.bind_all(
                sequence,
                lambda event, action=command: self._run_shortcut(event, action),
            )

    def change_language(self, language: str) -> None:
        """Switch language immediately while preserving the active project session."""

        if language == current_language():
            return
        set_language(language)
        self.language_value.set(language)
        self.main_window.destroy()
        self.main_window = self._create_main_window()
        self._build_menu()
        self.main_window.refresh_project_context()
        self.main_window.flash_status(tr("status.ready"))

    def new_project(self) -> None:
        if not self._confirm_project_transition(tr("action.create_new")):
            return
        dialog = NewProjectDialog(self.root)
        request = dialog.result
        if request is None:
            return
        self.session.new_project(
            title=request.title,
            creator=request.creator,
            width=request.width,
            height=request.height,
            background_color=request.background_color,
        )
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(tr("status.project_created", title=request.title))

    def open_project(self) -> None:
        if not self._confirm_project_transition(tr("action.open_another")):
            return
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=tr("dialog.open_project.title"),
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if not selected:
            return

        self.main_window.set_busy(True, tr("status.opening"))
        try:
            project = self.session.open_project(selected)
        except (ProjectArchiveError, OSError) as exc:
            messagebox.showerror(
                tr("dialog.open_project.error"),
                str(exc),
                parent=self.root,
            )
            self.main_window.set_busy(False, tr("status.open_failed"))
            return

        self.main_window.set_busy(False)
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(
            tr("status.project_opened", title=project.metadata.title)
        )

    def save_project(self) -> bool:
        if not self.session.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return False
        try:
            destination = self.session.save()
        except ProjectPathRequiredError:
            return self.save_project_as()
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self._show_save_error(exc)
            return False

        self.main_window.refresh_project_context()
        self.main_window.flash_status(tr("status.project_saved", name=destination.name))
        return True

    def save_project_as(self) -> bool:
        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return False
        initial_file = self._default_project_filename(snapshot.title or "untitled")
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("dialog.save_as.title"),
            defaultextension=PROJECT_EXTENSION,
            initialfile=initial_file,
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if not selected:
            return False

        self.main_window.set_busy(True, tr("status.saving"))
        try:
            destination = self.session.save_as(selected)
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self.main_window.set_busy(False, tr("status.save_failed"))
            self._show_save_error(exc)
            return False

        self.main_window.set_busy(False)
        self.main_window.refresh_project_context()
        self.main_window.flash_status(tr("status.project_saved", name=destination.name))
        return True

    def print_project(self) -> None:
        """Cetak proyek aktif ke printer bawaan sistem."""

        from .printing import PrintError, send_to_printer

        if not self.session.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return
        self.main_window.set_busy(True, tr("status.printing"))
        try:
            send_to_printer(self.session.require_project(), self.session.assets)
        except PrintError as exc:
            self.main_window.set_busy(False)
            messagebox.showerror(tr("file.print"), str(exc), parent=self.root)
            return
        self.main_window.set_busy(False)
        self.main_window.flash_status(tr("status.print_sent"))

    def print_project_as(self) -> None:
        """Simpan hasil cetak sebagai PDF atau gambar pada lokasi pilihan."""

        from .printing import PrintError, save_print_file

        if not self.session.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return
        snapshot = self.session.snapshot()
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("file.print_as"),
            defaultextension=".pdf",
            initialfile=f"{snapshot.title or 'batikcraft'}.pdf",
            filetypes=(
                ("PDF", "*.pdf"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg"),
            ),
        )
        if not selected:
            return
        self.main_window.set_busy(True, tr("status.printing"))
        try:
            destination = save_print_file(
                self.session.require_project(), self.session.assets, selected
            )
        except PrintError as exc:
            self.main_window.set_busy(False)
            messagebox.showerror(tr("file.print_as"), str(exc), parent=self.root)
            return
        self.main_window.set_busy(False)
        self.main_window.flash_status(
            tr("status.print_saved", name=destination.name)
        )

    def close_project(self) -> None:
        if not self.session.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return
        if not self._confirm_project_transition(tr("action.close_project")):
            return
        self.session.close_project()
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(tr("status.project_closed"))

    def _confirm_project_transition(self, action: str) -> bool:
        snapshot = self.session.snapshot()
        if not snapshot.has_project or not snapshot.dirty:
            return True

        decision = messagebox.askyesnocancel(
            tr("dialog.unsaved.title"),
            tr("dialog.unsaved.message", title=snapshot.title, action=action),
            parent=self.root,
        )
        if decision is None:
            return False
        if decision:
            return self.save_project()
        return True

    def _show_save_error(self, exc: Exception) -> None:
        messagebox.showerror(
            tr("dialog.save.error"),
            str(exc),
            parent=self.root,
        )

    @staticmethod
    def _default_project_filename(title: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-.")
        return f"{slug or 'untitled'}{PROJECT_EXTENSION}"

    @staticmethod
    def _run_shortcut(
        event: tk.Event[tk.Misc],
        command: Callable[[], object],
    ) -> str | None:
        if event_targets_text_input(event):
            return None
        command()
        return "break"

    def show_about(self) -> None:
        messagebox.showinfo(
            tr("help.about"),
            f"{APP_NAME} {APP_VERSION}\n\n{tr('about.description')}",
            parent=self.root,
        )

    def request_close(self) -> None:
        if self._confirm_project_transition(tr("action.exit")):
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
