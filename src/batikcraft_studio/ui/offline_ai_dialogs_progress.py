"""Progress-aware Dataset Studio and offline LoRA model manager dialogs."""

from __future__ import annotations

import threading
from pathlib import Path
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
from batikcraft_studio.model_transfer import (
    ModelTransferCancelled,
    copy_model_pack_with_progress,
    default_model_download_cache,
)

from .offline_ai_dialogs import DatasetStudioWindow
from .offline_ai_dialogs_global import GlobalOfflineModelManagerWindow
from .progress_dialog import ProgressDialog


class ProgressDatasetStudioWindow(DatasetStudioWindow):
    """Export large `.batikdataset` archives without blocking the Tk event loop."""

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
        samples = tuple(self.samples)
        progress = ProgressDialog(
            self,
            title="Ekspor Dataset BatikCraft",
            message="Menyiapkan sampel training…",
            cancellable=False,
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 1/4 — Memvalidasi sampel training",
                    1,
                    4,
                    detail=f"Jumlah sampel: {len(samples)}",
                )
                reporter.update(
                    "Tahap 2/4 — Menulis gambar, caption, dan mask",
                    2,
                    4,
                )
                output = build_batik_dataset(samples, metadata, destination)
                reporter.update(
                    "Tahap 3/4 — Menulis manifest dan checksum",
                    3,
                    4,
                )
                reporter.update(
                    "Tahap 4/4 — Memverifikasi arsip dataset",
                    4,
                    4,
                )
            except (BatikDatasetError, OSError) as exc:
                self.after(
                    0,
                    lambda error=exc: self._finish_dataset_error(progress, error),
                )
                return
            self.after(
                0,
                lambda: self._finish_dataset_export(progress, output),
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-export-dataset",
        ).start()

    def _finish_dataset_export(self, progress: ProgressDialog, output: object) -> None:
        progress.finish("Dataset training berhasil dibuat")
        messagebox.showinfo(
            self.title(),
            tr("offline.dataset.exported", path=output),
            parent=self,
        )

    def _finish_dataset_error(
        self,
        progress: ProgressDialog,
        error: Exception,
    ) -> None:
        progress.fail(str(error))
        messagebox.showerror(self.title(), str(error), parent=self)


class ProgressOfflineModelManagerWindow(GlobalOfflineModelManagerWindow):
    """Install and verify `.batikmodel` packages with real byte progress."""

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
        progress = ProgressDialog(
            self,
            title="Instal Model LoRA Batik",
            message="Membaca paket model…",
            cancellable=True,
            auto_close_ms=None,
        )

        def worker() -> None:
            reporter = progress.reporter
            source = Path(selected)
            cached = default_model_download_cache() / f"local-{source.name}"

            def report_bytes(completed: int, total: int, filename: str) -> None:
                scaled = (completed / total * 85.0) if total > 0 else None
                reporter.update(
                    "Menyalin paket LoRA ke folder dependencies…",
                    scaled,
                    100 if scaled is not None else None,
                    detail=(
                        f"{filename} · {_format_bytes(completed)} / {_format_bytes(total)}"
                        if total > 0
                        else filename
                    ),
                )

            try:
                cached = copy_model_pack_with_progress(
                    source,
                    cached,
                    progress=report_bytes,
                    cancel_event=reporter.cancel_event,
                )
                if reporter.cancelled:
                    raise ModelTransferCancelled("Instalasi model LoRA dibatalkan.")
                reporter.update(
                    "Memvalidasi manifest dan checksum LoRA…",
                    90,
                    100,
                    detail=source.name,
                )
                installed = self.session.install_model_pack(cached, replace=True)
                reporter.update(
                    "Memperbarui library model lokal…",
                    100,
                    100,
                    detail=str(installed.root),
                )
            except ModelTransferCancelled as exc:
                cached.unlink(missing_ok=True)
                self.after(
                    0,
                    lambda error=exc: progress.mark_cancelled(str(error)),
                )
                return
            except (ProjectSessionError, OSError) as exc:
                cached.unlink(missing_ok=True)
                self.after(
                    0,
                    lambda error=exc: self._finish_model_install_error(progress, error),
                )
                return
            cached.unlink(missing_ok=True)
            self.after(
                0,
                lambda: self._finish_model_install(progress, installed),
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-install-lora-model",
        ).start()

    def _finish_model_install(self, progress: ProgressDialog, _installed: object) -> None:
        self._refresh()
        self._changed()
        self.status.configure(text="Model LoRA berhasil dipasang dan siap diaktifkan.")
        progress.finish("Model LoRA berhasil dipasang")

    def _finish_model_install_error(
        self,
        progress: ProgressDialog,
        error: Exception,
    ) -> None:
        progress.fail(str(error))
        messagebox.showerror(self.title(), str(error), parent=self)


def _format_bytes(value: int) -> str:
    amount = float(max(0, int(value)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024.0 or unit == "TB":
            precision = 0 if unit == "B" else 2
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024.0
    return f"{int(value)} B"


__all__ = [
    "ProgressDatasetStudioWindow",
    "ProgressOfflineModelManagerWindow",
]
