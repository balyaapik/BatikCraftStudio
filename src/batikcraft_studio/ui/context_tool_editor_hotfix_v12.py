"""Universal progress feedback for editor operations that may take noticeable time."""

from __future__ import annotations

from tkinter import filedialog, messagebox

from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.application import OfflineAIProjectSession, ProjectSessionError
from batikcraft_studio.assets import ASSET_PACK_EXTENSION, AssetLibraryError
from batikcraft_studio.progress import ProgressUpdate

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .context_tool_editor_hotfix_v11 import ContextToolEditorWorkspaceView as _HotfixV11Editor
from .offline_ai_dialogs_progress import (
    ProgressDatasetStudioWindow,
    ProgressOfflineModelManagerWindow,
)
from .progress_dialog import run_modal_progress


class ContextToolEditorWorkspaceView(_HotfixV11Editor):
    """Keep long editor work responsive and visibly progressing."""

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open AI controls, then show progress until Stable Diffusion + LoRA finishes."""

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
        settings = AIObjectBatificationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        self.wait_window(settings)
        options = settings.result
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
            f"Stable Diffusion + LoRA sedang membatikkan {plan.source_name} dengan {reference}."
        )

        def operation(report, _cancelled):  # type: ignore[no-untyped-def]
            report(
                ProgressUpdate(
                    "menyiapkan objek",
                    "Membaca alpha, siluet, dan bentuk objek sumber…",
                    1,
                    6,
                )
            )
            report(
                ProgressUpdate(
                    "menyiapkan motif",
                    f"Menggunakan {reference} sebagai panduan komposisi…",
                    2,
                    6,
                )
            )
            report(
                ProgressUpdate(
                    "memuat model AI",
                    "Memuat Stable Diffusion, ControlNet, dan LoRA Batik. "
                    "Penggunaan pertama dapat memerlukan waktu lebih lama…",
                    detail=(
                        f"Model: {options.model_id_or_path} · Steps: "
                        f"{options.inference_steps} · LoRA: {options.lora_weight:.2f}"
                    ),
                )
            )
            result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            report(
                ProgressUpdate(
                    "pemulihan bentuk",
                    "Memulihkan alpha, outline, dan identitas objek sumber…",
                    5,
                    6,
                )
            )
            report(
                ProgressUpdate(
                    "menyelesaikan",
                    "Menyiapkan hasil AI untuk dimasukkan ke canvas…",
                    6,
                    6,
                )
            )
            return result

        try:
            result = run_modal_progress(
                self,
                title="Batifikasi AI — Stable Diffusion + LoRA",
                initial_message=f"Menyiapkan {plan.source_name}…",
                operation=operation,
                cancelable=False,
                auto_close_ms=450,
            )
        except Exception as exc:  # noqa: BLE001 - normalized to editor status
            self._finish_pretrained_ai_error(str(exc))
            return
        self._finish_pretrained_ai_success(plan, result)

    def install_asset_pack_dialog(self) -> None:
        """Install a large asset pack with visible validation and indexing progress."""

        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Instal Paket Asset BatikCraft",
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if not selected:
            return

        def install(*, replace: bool):  # type: ignore[no-untyped-def]
            def operation(report, _cancelled):  # type: ignore[no-untyped-def]
                report(
                    ProgressUpdate(
                        "membaca paket",
                        "Membaca manifest dan daftar asset…",
                        1,
                        4,
                    )
                )
                report(
                    ProgressUpdate(
                        "validasi asset",
                        "Memeriksa gambar, metadata, dan struktur folder…",
                        2,
                        4,
                    )
                )
                pack = self.asset_library.install_pack(selected, replace=replace)
                report(
                    ProgressUpdate(
                        "indeks pustaka",
                        f"Mengindeks {len(pack.assets)} asset untuk pencarian…",
                        3,
                        4,
                    )
                )
                report(
                    ProgressUpdate(
                        "selesai",
                        "Paket asset siap digunakan.",
                        4,
                        4,
                    )
                )
                return pack

            return run_modal_progress(
                self,
                title="Instal Paket Asset",
                initial_message="Menyiapkan paket asset BatikCraft…",
                operation=operation,
                cancelable=False,
            )

        try:
            pack = install(replace=False)
        except AssetLibraryError as exc:
            if "sudah terpasang" not in str(exc):
                messagebox.showerror("Instal paket gagal", str(exc), parent=self)
                return
            replace = messagebox.askyesno(
                "Ganti paket yang sudah ada?",
                str(exc),
                parent=self,
            )
            if not replace:
                return
            try:
                pack = install(replace=True)
            except (AssetLibraryError, OSError) as replace_exc:
                messagebox.showerror("Instal paket gagal", str(replace_exc), parent=self)
                return
        except OSError as exc:
            messagebox.showerror("Instal paket gagal", str(exc), parent=self)
            return
        self.refresh_library()
        self.library_pack_value.set(pack.name)
        self.set_status(f"{pack.name} terpasang dengan {len(pack.assets)} asset.")

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
