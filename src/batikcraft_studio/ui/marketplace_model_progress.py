"""Byte-accurate progress for Marketplace LoRA downloads and installation."""

from __future__ import annotations

import threading
from tkinter import messagebox

from batikcraft_studio.ai.model_pack import OfflineModelLibrary
from batikcraft_studio.model_transfer import (
    ModelTransferCancelled,
    download_marketplace_model,
)
from batikcraft_studio.web_bridge import BatikCraftWebError

from .progress_dialog import ProgressDialog


def install_marketplace_model_progress() -> None:
    """Replace the synchronous Marketplace installer with a progress-aware workflow."""

    from .web_marketplace_dialogs import WebMarketplaceWindow

    if getattr(WebMarketplaceWindow, "__batikcraft_model_progress__", False):
        return
    WebMarketplaceWindow._install_selected = _install_selected  # type: ignore[method-assign]
    WebMarketplaceWindow.__batikcraft_model_progress__ = True


def _install_selected(self: object) -> None:
    purchase = self._selected(self.library_tree, self.library_rows)
    if purchase is None:
        return
    model_id = int(purchase["model"])
    model_name = str(purchase.get("model_name") or f"Model {model_id}")
    progress = ProgressDialog(
        self,
        title="Download & Instal Model LoRA",
        message=f"Menyiapkan unduhan {model_name}…",
        cancellable=True,
        auto_close_ms=None,
    )

    def worker() -> None:
        reporter = progress.reporter

        def report_bytes(completed: int, total: int, filename: str) -> None:
            scaled = (completed / total * 90.0) if total > 0 else None
            reporter.update(
                f"Mengunduh model LoRA — {model_name}",
                scaled,
                100 if scaled is not None else None,
                detail=(
                    f"{filename} · {_format_bytes(completed)} / {_format_bytes(total)}"
                    if total > 0
                    else f"{filename} · {_format_bytes(completed)}"
                ),
            )

        downloaded = None
        try:
            downloaded = download_marketplace_model(
                self.client,
                model_id,
                progress=report_bytes,
                cancel_event=reporter.cancel_event,
            )
            if reporter.cancelled:
                raise ModelTransferCancelled(
                    "Unduhan model dibatalkan. File parsial disimpan untuk dilanjutkan."
                )
            reporter.update(
                "Memverifikasi manifest dan checksum model…",
                95,
                100,
                detail=downloaded.name,
            )
            installed = OfflineModelLibrary().install(downloaded, replace=True)
            reporter.update(
                "Memperbarui library model…",
                100,
                100,
                detail=str(installed.root),
            )
        except ModelTransferCancelled as exc:
            self.after(0, lambda error=exc: progress.mark_cancelled(str(error)))
            return
        except (BatikCraftWebError, OSError, RuntimeError) as exc:
            self.after(
                0,
                lambda error=exc: _finish_error(self, progress, error),
            )
            return
        finally:
            if downloaded is not None:
                downloaded.unlink(missing_ok=True)
        self.after(
            0,
            lambda: _finish_success(self, progress, installed),
        )

    threading.Thread(
        target=worker,
        daemon=True,
        name="batikcraft-marketplace-lora-download",
    ).start()


def _finish_success(self: object, progress: ProgressDialog, installed: object) -> None:
    progress.finish("Model LoRA berhasil diunduh dan dipasang")
    manifest = installed.manifest
    messagebox.showinfo(
        "Model terpasang",
        f"{manifest.name} berhasil dipasang ke folder dependencies.",
        parent=self,
    )
    self.refresh_library()


def _finish_error(self: object, progress: ProgressDialog, error: Exception) -> None:
    progress.fail(str(error))
    messagebox.showerror("BatikCraftWeb", str(error), parent=self)


def _format_bytes(value: int) -> str:
    amount = float(max(0, int(value)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024.0 or unit == "TB":
            precision = 0 if unit == "B" else 2
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024.0
    return f"{int(value)} B"


__all__ = ["install_marketplace_model_progress"]
