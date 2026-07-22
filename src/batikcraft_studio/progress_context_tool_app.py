"""Application shell that exposes progress for project and export operations."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from batikcraft_studio.application import NoActiveProjectError
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging import ProjectRenderError
from batikcraft_studio.persistence import (
    BATIKCRAFT_NFT_EXTENSION,
    PROJECT_EXTENSION,
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

from .context_tool_app import ContextToolApplication as _BaseApplication
from .context_tool_app import _filename_stem
from .ui.nft_export_dialog import NFTExportDialog
from .ui.progress_dialog import ProgressDialog
from .ui.progress_main_window import ProgressViewportMainWindow


class ContextToolApplication(_BaseApplication):
    """Show visible progress instead of leaving long operations apparently frozen."""

    def __init__(self) -> None:
        self._project_open_progress: ProgressDialog | None = None
        super().__init__()

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
        """Choose a project, then read and validate it on a worker thread."""

        if not self._confirm_project_transition(tr("action.open_another")):
            return
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=tr("dialog.open_project.title"),
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if selected:
            self._start_project_open(Path(selected))

    def open_recent_project(self, value: str | Path) -> None:
        """Open one Recent Project entry with the same responsive progress UI."""

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
        self._start_project_open(path)

    def _start_project_open(self, path: Path) -> None:
        current = self._project_open_progress
        if current is not None and current.winfo_exists():
            current.lift()
            return
        progress = ProgressDialog(
            self.root,
            title="Membuka Project",
            message="Membaca dan memvalidasi project…",
            cancellable=False,
        )
        self._project_open_progress = progress

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 1/4 — Membaca arsip project",
                    1,
                    4,
                    detail=str(path),
                )
                project = self.session.open_project(path)
                reporter.update(
                    "Tahap 2/4 — Memvalidasi struktur project",
                    2,
                    4,
                )
                reporter.update(
                    "Tahap 3/4 — Memuat asset dan metadata",
                    3,
                    4,
                    detail=f"{len(self.session.assets)} asset ditemukan.",
                )
            except (ProjectArchiveError, OSError) as exc:
                self.root.after(
                    0,
                    lambda error=exc: self._finish_project_open_error(progress, error),
                )
                return
            self.root.after(
                0,
                lambda: self._finish_project_open_success(progress, project),
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-open-project",
        ).start()

    def _finish_project_open_success(self, progress: ProgressDialog, project: object) -> None:
        progress.reporter.update(
            "Tahap 4/4 — Menampilkan project pada canvas",
            4,
            4,
        )
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        title = self.session.require_project().metadata.title
        self.main_window.flash_status(tr("status.project_opened", title=title))
        self._remember_current_project()
        progress.finish("Project berhasil dibuka")
        self._project_open_progress = None

    def _finish_project_open_error(
        self,
        progress: ProgressDialog,
        error: Exception,
    ) -> None:
        progress.fail(str(error))
        self._project_open_progress = None
        self.main_window.flash_status(tr("status.open_failed"))
        messagebox.showerror(
            tr("dialog.open_project.error"),
            str(error),
            parent=self.root,
        )

    def save_project(self) -> bool:
        # Unsaved projects must show the native Save As chooser before a modal progress
        # window grabs focus. Existing projects can display progress immediately.
        if self.session.path is None:
            return self.save_project_as()
        progress = ProgressDialog(
            self.root,
            title="Menyimpan Project",
            message="Menyiapkan data project…",
            cancellable=False,
        )
        progress.reporter.update("Tahap 1/3 — Menyiapkan data", 1, 3)
        self.root.update_idletasks()
        try:
            saved = super().save_project()
        except Exception as exc:  # noqa: BLE001 - preserve application error handling
            progress.fail(str(exc))
            raise
        if saved:
            progress.reporter.update("Tahap 3/3 — Menyelesaikan arsip", 3, 3)
            progress.finish("Project berhasil disimpan")
        else:
            progress.close()
        return saved

    def save_project_as(self) -> bool:
        """Show a progress dialog after the native destination chooser closes."""

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
        progress = ProgressDialog(
            self.root,
            title="Simpan Project Sebagai",
            message="Menyiapkan project dan seluruh asset…",
            cancellable=False,
        )
        progress.reporter.update("Tahap 1/4 — Menyiapkan snapshot", 1, 4)
        self.root.update_idletasks()
        try:
            progress.reporter.update("Tahap 2/4 — Mengompresi asset", 2, 4)
            destination = self.session.save_as(selected)
            progress.reporter.update(
                "Tahap 3/4 — Menulis arsip project",
                3,
                4,
                detail=str(destination),
            )
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            progress.fail(str(exc))
            self._show_save_error(exc)
            return False
        progress.reporter.update("Tahap 4/4 — Memverifikasi file", 4, 4)
        progress.finish("Project berhasil disimpan")
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
        assets = {key: bytes(value) for key, value in self.session.assets.items()}
        progress = ProgressDialog(
            self.root,
            title="Ekspor Gambar",
            message="Merender canvas project…",
            cancellable=False,
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 1/3 — Merender seluruh canvas",
                    1,
                    3,
                    detail=f"Resolusi: {project.canvas.width} × {project.canvas.height}",
                )
                content = render_project_jpeg(project, assets)
                reporter.update(
                    "Tahap 2/3 — Menulis file JPEG",
                    2,
                    3,
                    detail=target.name,
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                from batikcraft_studio.persistence.raster_archive import (
                    write_bytes_atomic,
                )

                target = write_bytes_atomic(target, content)
                reporter.update("Tahap 3/3 — Memverifikasi hasil", 3, 3)
            except (OSError, ProjectRenderError, ValueError) as exc:
                self.root.after(
                    0,
                    lambda error=exc: self._finish_export_error(progress, error),
                )
                return
            self.root.after(0, lambda: self._finish_image_export(progress, target))

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-export-image",
        ).start()

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
        assets = {key: bytes(value) for key, value in self.session.assets.items()}
        progress = ProgressDialog(
            self.root,
            title="Ekspor BatikCraft NFT",
            message="Menyiapkan paket karya terverifikasi…",
            cancellable=False,
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update("Tahap 1/5 — Merender preview", 1, 5)
                preview = render_project_jpeg(project, assets)
                reporter.update("Tahap 2/5 — Menyusun project dan asset", 2, 5)
                reporter.update("Tahap 3/5 — Menghitung checksum SHA-256", 3, 5)
                target = export_batikcraft_nft(
                    destination,
                    project,
                    assets,
                    preview,
                    metadata,
                )
                reporter.update("Tahap 4/5 — Menulis manifest dan seal", 4, 5)
                reporter.update("Tahap 5/5 — Memverifikasi paket", 5, 5)
            except (BatikNFTError, OSError, ProjectRenderError, ValueError) as exc:
                self.root.after(
                    0,
                    lambda error=exc: self._finish_export_error(progress, error),
                )
                return
            self.root.after(0, lambda: self._finish_nft_export(progress, target))

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-export-nft",
        ).start()

    def _finish_image_export(self, progress: ProgressDialog, target: Path) -> None:
        progress.finish("Ekspor gambar selesai")
        self.main_window.flash_status(tr("status.image_exported", name=target.name))

    def _finish_nft_export(self, progress: ProgressDialog, target: Path) -> None:
        progress.finish("Paket BatikCraft NFT selesai")
        self.main_window.flash_status(tr("status.nft_exported", name=target.name))

    def _finish_export_error(self, progress: ProgressDialog, error: Exception) -> None:
        progress.fail(str(error))
        messagebox.showerror(
            tr("status.export_failed"),
            str(error),
            parent=self.root,
        )


__all__ = ["ContextToolApplication"]
