"""Progress-aware Dataset Studio and offline LoRA model manager."""

from __future__ import annotations

from tkinter import filedialog, messagebox

from batikcraft_studio.ai import (
    BATIK_DATASET_EXTENSION,
    BATIK_MODEL_EXTENSION,
    BatikDatasetError,
    BatikDatasetMetadata,
    build_batik_dataset,
)
from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.i18n import tr
from batikcraft_studio.progress import OperationCancelledError, ProgressUpdate

from .offline_ai_dialogs import DatasetStudioWindow
from .offline_ai_dialogs_global import GlobalOfflineModelManagerWindow
from .progress_dialog import run_modal_progress


class ProgressDatasetStudioWindow(DatasetStudioWindow):
    """Export a potentially large `.batikdataset` without blocking Tk."""

    def _export(self) -> None:
        if not self.samples:
            messagebox.showerror(
                self.title(),
                tr("offline.dataset.empty"),
                parent=self,
            )
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title=tr("offline.dataset.export"),
            defaultextension=BATIK_DATASET_EXTENSION,
            filetypes=[
                ("BatikCraft Dataset", f"*{BATIK_DATASET_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not destination:
            return
        samples = tuple(self.samples)
        try:
            metadata = BatikDatasetMetadata(
                dataset_id=self.dataset_id.get(),
                name=self.dataset_name.get(),
                author=self.author_value.get(),
                base_model_family=self.base_family_value.get(),
                trigger_word=self.trigger_value.get(),
            )
        except BatikDatasetError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return

        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            total = max(1, len(samples))
            report(
                ProgressUpdate(
                    "validasi dataset",
                    f"Memvalidasi {len(samples)} sampel training…",
                    0,
                    total + 2,
                )
            )
            report(
                ProgressUpdate(
                    "menulis dataset",
                    "Mengompresi gambar, caption, mask, dan metadata…",
                    total,
                    total + 2,
                    detail=f"{len(samples)} sampel akan dimasukkan ke arsip.",
                )
            )
            output = build_batik_dataset(samples, metadata, destination)
            report(
                ProgressUpdate(
                    "checksum",
                    "Menyelesaikan manifest dan checksum dataset…",
                    total + 1,
                    total + 2,
                )
            )
            report(
                ProgressUpdate(
                    "selesai",
                    "Dataset training berhasil dibuat.",
                    total + 2,
                    total + 2,
                )
            )
            return output

        try:
            output = run_modal_progress(
                self,
                title="Ekspor Dataset BatikCraft",
                initial_message="Menyiapkan paket training…",
                operation=operation,
                cancelable=False,
            )
        except (BatikDatasetError, OSError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        messagebox.showinfo(
            self.title(),
            tr("offline.dataset.exported", path=output),
            parent=self,
        )


class ProgressOfflineModelManagerWindow(GlobalOfflineModelManagerWindow):
    """Install and validate `.batikmodel` packages with visible progress."""

    def _install(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title=tr("offline.models.install"),
            filetypes=[
                ("BatikCraft Model", f"*{BATIK_MODEL_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return

        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            report(
                ProgressUpdate(
                    "validasi paket",
                    "Membaca manifest dan memeriksa struktur `.batikmodel`…",
                    1,
                    4,
                )
            )
            report(
                ProgressUpdate(
                    "checksum",
                    "Memverifikasi ukuran dan SHA-256 setiap file model…",
                    2,
                    4,
                )
            )
            installed = self.session.install_model_pack(selected, replace=True)
            report(
                ProgressUpdate(
                    "instalasi",
                    "Menyalin LoRA ke penyimpanan model aplikasi…",
                    3,
                    4,
                )
            )
            report(
                ProgressUpdate(
                    "selesai",
                    "Model LoRA berhasil dipasang.",
                    4,
                    4,
                )
            )
            return installed

        try:
            run_modal_progress(
                self,
                title="Instal Model LoRA Batik",
                initial_message="Memeriksa paket model…",
                operation=operation,
                cancelable=False,
            )
        except OperationCancelledError:
            return
        except ProjectSessionError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh()
        self._changed()
        self.status.configure(text="Model LoRA berhasil dipasang dan siap diaktifkan.")


__all__ = ["ProgressDatasetStudioWindow", "ProgressOfflineModelManagerWindow"]
