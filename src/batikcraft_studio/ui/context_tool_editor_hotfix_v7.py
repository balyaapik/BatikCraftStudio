"""Background `.batikpack` installation with responsive progress and cancellation."""

from __future__ import annotations

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
from .context_tool_editor_hotfix_v6 import ContextToolEditorWorkspaceView as _HotfixV6Editor


class ContextToolEditorWorkspaceView(_HotfixV6Editor):
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


__all__ = ["ContextToolEditorWorkspaceView"]
