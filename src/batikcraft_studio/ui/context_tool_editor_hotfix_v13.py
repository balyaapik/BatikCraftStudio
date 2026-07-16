"""Progress feedback for remaining editor installation and packaging workflows."""

from __future__ import annotations

import threading
from tkinter import filedialog, messagebox

from batikcraft_studio.application import OfflineAIProjectSession
from batikcraft_studio.assets import ASSET_PACK_EXTENSION, AssetLibraryError

from .context_tool_editor_hotfix_v12 import ContextToolEditorWorkspaceView as _HotfixV12Editor
from .offline_ai_dialogs_progress import (
    ProgressDatasetStudioWindow,
    ProgressOfflineModelManagerWindow,
)
from .progress_dialog import ProgressDialog


class ContextToolEditorWorkspaceView(_HotfixV12Editor):
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


__all__ = ["ContextToolEditorWorkspaceView"]
