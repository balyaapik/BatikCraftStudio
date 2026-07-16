"""Context-tool application with responsive progress for project and export work."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from batikcraft_studio.application import (
    NoActiveProjectError,
    ProjectPathRequiredError,
)
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging import ProjectRenderError
from batikcraft_studio.persistence import (
    BATIKCRAFT_NFT_EXTENSION,
    PROJECT_EXTENSION,
    BatikNFTError,
    ProjectArchiveError,
    export_batikcraft_nft,
)
from batikcraft_studio.progress import (
    OperationCancelledError,
    ProgressUpdate,
    ensure_not_cancelled,
)
from batikcraft_studio.project_export import (
    creator_id_suggestion,
    discover_project_colors,
    discover_project_motifs,
    render_project_jpeg,
)

from .context_tool_app import ContextToolApplication, _filename_stem
from .ui.nft_export_dialog import NFTExportDialog
from .ui.progress_dialog import run_modal_progress
from .ui.progress_main_window import ProgressViewportMainWindow


class ProgressContextToolApplication(ContextToolApplication):
    """Make archive, save, and export operations visibly responsive."""

    def _create_main_window(self) -> ProgressViewportMainWindow:
        return ProgressViewportMainWindow(
            self.root,
            self.session,
            file_commands={
                "new": self.new_project,
                "open": self.open_project,
                "save": self.save_project,
            },
        )

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
        self._open_project_path(Path(selected))

    def open_recent_project(self, value: str | Path) -> None:
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
        self._open_project_path(path)

    def _open_project_path(self, path: Path) -> None:
        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            report(ProgressUpdate("membuka project", "Membaca arsip project…", 1, 4))
            project = self.session.open_project(path)
            report(ProgressUpdate("memuat asset", "Memuat asset dan struktur canvas…", 3, 4))
            report(ProgressUpdate("menyelesaikan", "Menyiapkan editor…", 4, 4))
            return project

        try:
            project = run_modal_progress(
                self.root,
                title="Membuka Project BatikCraft",
                initial_message=f"Membuka {path.name}…",
                operation=operation,
                cancelable=False,
            )
        except (ProjectArchiveError, OSError) as exc:
            messagebox.showerror(
                tr("dialog.open_project.error"),
                str(exc),
                parent=self.root,
            )
            self.main_window.flash_status(tr("status.open_failed"))
            return
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(
            tr("status.project_opened", title=project.metadata.title)
        )
        self._remember_current_project()

    def save_project(self) -> bool:
        if not self.session.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return False
        if self.session.path is None:
            return self.save_project_as()

        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            report(ProgressUpdate("menyiapkan", "Menyiapkan snapshot project…", 1, 3))
            destination = self.session.save()
            report(ProgressUpdate("menulis file", "Menulis arsip project ke penyimpanan…", 2, 3))
            report(ProgressUpdate("verifikasi", "Memastikan project tersimpan…", 3, 3))
            return destination

        try:
            destination = run_modal_progress(
                self.root,
                title="Menyimpan Project",
                initial_message="Menyimpan perubahan project…",
                operation=operation,
                cancelable=False,
            )
        except ProjectPathRequiredError:
            return self.save_project_as()
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self._show_save_error(exc)
            return False
        self.main_window.refresh_project_context()
        self.main_window.flash_status(tr("status.project_saved", name=destination.name))
        self._remember_current_project()
        return True

    def save_project_as(self) -> bool:
        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.main_window.flash_status(tr("status.no_open_project"))
            return False
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("dialog.save_as.title"),
            defaultextension=PROJECT_EXTENSION,
            initialfile=self._default_project_filename(snapshot.title or "untitled"),
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if not selected:
            return False

        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            report(ProgressUpdate("menyiapkan", "Menyiapkan project dan asset…", 1, 3))
            destination = self.session.save_as(selected)
            report(ProgressUpdate("menulis file", "Membuat arsip project baru…", 2, 3))
            report(ProgressUpdate("verifikasi", "Memastikan file dapat digunakan…", 3, 3))
            return destination

        try:
            destination = run_modal_progress(
                self.root,
                title="Simpan Project Sebagai",
                initial_message="Membuat file project…",
                operation=operation,
                cancelable=False,
            )
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self._show_save_error(exc)
            return False
        self.main_window.refresh_project_context()
        self.main_window.flash_status(tr("status.project_saved", name=destination.name))
        self._remember_current_project()
        return True

    def export_project_image(self, suffix: str) -> None:
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
        assets = dict(self.session.assets)

        def operation(report, cancelled):  # type: ignore[no-untyped-def]
            report(ProgressUpdate("render canvas", "Merender seluruh objek dan layer…", 1, 3))
            content = render_project_jpeg(project, assets)
            ensure_not_cancelled(cancelled)
            report(ProgressUpdate("menulis gambar", "Menyimpan JPEG berkualitas tinggi…", 2, 3))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            report(ProgressUpdate("selesai", "Memastikan file gambar selesai ditulis…", 3, 3))
            return target

        try:
            output = run_modal_progress(
                self.root,
                title="Ekspor Gambar",
                initial_message="Menyiapkan render JPG/JPEG…",
                operation=operation,
                cancelable=True,
            )
        except OperationCancelledError:
            self.main_window.flash_status("Ekspor gambar dibatalkan.")
            return
        except (OSError, ProjectRenderError, ValueError) as exc:
            messagebox.showerror(tr("status.export_failed"), str(exc), parent=self.root)
            return
        self.main_window.flash_status(tr("status.image_exported", name=output.name))

    def export_project_nft(self) -> None:
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
            initialfile=f"{_filename_stem(project.metadata.title)}{BATIKCRAFT_NFT_EXTENSION}",
            filetypes=(
                ("BatikCraft NFT", f"*{BATIKCRAFT_NFT_EXTENSION}"),
                ("All files", "*.*"),
            ),
        )
        if not destination:
            return
        assets = dict(self.session.assets)

        def operation(report, cancelled):  # type: ignore[no-untyped-def]
            report(ProgressUpdate("render preview", "Merender gambar showcase…", 1, 5))
            preview = render_project_jpeg(project, assets)
            ensure_not_cancelled(cancelled)
            report(ProgressUpdate("metadata", "Menyusun identitas, filosofi, motif, dan warna…", 2, 5))
            report(ProgressUpdate("checksum", "Menghitung checksum seluruh project dan asset…", 3, 5))
            target = export_batikcraft_nft(
                destination,
                project,
                assets,
                preview,
                metadata,
            )
            ensure_not_cancelled(cancelled)
            report(ProgressUpdate("seal", "Memverifikasi manifest dan seal paket…", 4, 5))
            report(ProgressUpdate("selesai", "Paket BatikCraft NFT siap diunggah…", 5, 5))
            return target

        try:
            target = run_modal_progress(
                self.root,
                title="Ekspor Paket BatikCraft NFT",
                initial_message="Menyiapkan paket karya terverifikasi…",
                operation=operation,
                cancelable=True,
            )
        except OperationCancelledError:
            self.main_window.flash_status("Ekspor BatikCraft NFT dibatalkan.")
            return
        except (BatikNFTError, OSError, ProjectRenderError, ValueError) as exc:
            messagebox.showerror(tr("status.export_failed"), str(exc), parent=self.root)
            return
        self.main_window.flash_status(tr("status.nft_exported", name=target.name))


__all__ = ["ProgressContextToolApplication"]
