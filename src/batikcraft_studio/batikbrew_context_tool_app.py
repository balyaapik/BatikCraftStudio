"""Application shell with clearly separated AI, effects, dependencies, and market menus."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox

from batikcraft_studio.ai import default_ai_cache_dir
from batikcraft_studio.ai.generation_providers import provider_label
from batikcraft_studio.ai.local_lora_training import default_training_root
from batikcraft_studio.web_bridge import (
    BatikCraftWebClient,
    BatikCraftWebError,
    WebSession,
)

from .context_tool_app import _find_cascade_menu
from .progress_context_tool_app import ContextToolApplication as _ProgressApplication
from .ui.ai_runtime_model_install_dialog import RuntimeModelInstallDialog
from .ui.cloud_ai_settings_dialog import CloudAISettingsDialog
from .ui.dependency_manager_dialog import DependencyManagerWindow, reveal_path
from .ui.enhanced_humanize_dialog import (
    EnhancedHumanizeWindow,
    HUMANIZE_PRESETS,
    apply_humanize_preset,
)
from .ui.local_training_dialog import (
    LocalLoraTrainingWindow,
    SDXLDatasetStudioWindow,
    TrainingResultsWindow,
)
from .ui.marketplace_mint_dialog import MintCurrentProjectDialog
from .ui.web_marketplace_dialogs import (
    PublishModelDialog,
    WebAccountWindow,
    WebLoginDialog,
    WebMarketplaceWindow,
)


class ContextToolApplication(_ProgressApplication):
    """Keep each major workflow in its own top-level menu."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.web_client = BatikCraftWebClient()
        self.web_session: WebSession | None = None
        super().__init__(*args, **kwargs)

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        editor = self.main_window._editor()

        _ai_index, ai_menu = _find_cascade_menu(
            menu_bar,
            "AI Batik",
            "Batik AI",
            "AI",
        )
        _remove_commands_containing(ai_menu, "Pengaturan AI")
        _remove_commands_containing(ai_menu, "Stable Diffusion + LoRA", rename=True)
        _remove_commands_containing(ai_menu, "Login / Akun")
        _remove_commands_containing(ai_menu, "Marketplace")
        _remove_commands_containing(ai_menu, "Library Model")
        _remove_commands_containing(ai_menu, "Publish Motif")
        _remove_commands_containing(ai_menu, "Publish Model")
        # Alur baru: batifikasi tidak lagi bergantung pada objek terpilih di
        # kanvas. Gambar diseret langsung ke jendela studio.
        ai_menu.insert_command(
            0,
            label="Studio Batifikasi BatikBrew…",
            command=self.open_batikbrew_studio,
        )
        ai_menu.insert_command(
            1,
            label="Kanvas Lukis (Raster) — pratinjau…",
            command=self.open_raster_paint,
        )
        ai_menu.insert_separator(2)
        _normalize_separators(ai_menu)

        self._remove_nft_export_from_file(menu_bar)
        self._remove_humanize_from_asset(menu_bar)

        effects_menu = tk.Menu(menu_bar, tearoff=False)
        effects_menu.add_command(
            label="Humanize…",
            command=self.open_humanize_effect,
        )
        preset_menu = tk.Menu(effects_menu, tearoff=False)
        for key, preset in HUMANIZE_PRESETS.items():
            preset_menu.add_command(
                label=preset.label,
                command=lambda selected=key: apply_humanize_preset(editor, selected),
            )
        effects_menu.add_cascade(label="Preset Humanize", menu=preset_menu)
        effects_menu.add_command(
            label="Acak Seed Humanize",
            command=self.randomize_humanize_seed,
        )
        effects_menu.add_separator()
        effects_menu.add_command(
            label="Reset Humanize ke Asset Sumber",
            command=editor.reset_humanize,
        )
        _insert_before_help(menu_bar, "Effects", effects_menu)

        dependencies_menu = tk.Menu(menu_bar, tearoff=False)
        # Satu pintu: seluruh unduhan/instalasi/uninstall dilakukan lewat tabel
        # bercentang di Pusat Dependensi (tanpa tombol instal tersebar).
        dependencies_menu.add_command(
            label="Pusat Dependensi (Unduh, Instal, Uninstall)…",
            command=self.open_dependency_manager,
        )
        dependencies_menu.add_separator()
        dependencies_menu.add_command(
            label="Buka Folder Unduhan AI",
            command=lambda: self.open_folder(default_ai_cache_dir()),
        )
        dependencies_menu.add_command(
            label="Buka Folder Log Aplikasi",
            command=self.open_log_folder,
        )
        _insert_before_help(menu_bar, "Dependencies", dependencies_menu)

        self._extend_asset_menu(menu_bar)

        marketplace_menu = tk.Menu(menu_bar, tearoff=False)
        marketplace_menu.add_command(
            label="Login / Akun BatikCraftWeb…",
            command=self.open_web_account,
        )
        marketplace_menu.add_command(
            label="Buka BatikCraftWeb",
            command=self.open_marketplace_website,
        )
        marketplace_menu.add_separator()
        marketplace_menu.add_command(
            label="NFT Marketplace…",
            command=lambda: self.open_web_marketplace("nfts"),
        )
        marketplace_menu.add_command(
            label="Model Marketplace…",
            command=lambda: self.open_web_marketplace("models"),
        )
        marketplace_menu.add_command(
            label="Library Model Saya…",
            command=lambda: self.open_web_marketplace("library"),
        )
        marketplace_menu.add_command(
            label="Analisis Ekonomi NFT…",
            command=self.open_nft_economics,
        )

        marketplace_menu.add_separator()
        marketplace_menu.add_command(
            label="Mint & Publish Project Aktif sebagai NFT…",
            command=self.mint_current_project_to_web,
        )
        marketplace_menu.add_command(
            label="Jual Model ke Marketplace…",
            command=self.publish_model_to_web,
        )
        _insert_before_help(menu_bar, "Marketplace", marketplace_menu)

        training_menu = tk.Menu(menu_bar, tearoff=False)
        training_menu.add_command(
            label="Dataset Studio SDXL…",
            command=self.open_dataset_studio,
        )
        training_menu.add_command(
            label="Train LoRA di Komputer Ini…",
            command=self.open_local_training,
        )
        training_menu.add_command(
            label="Hasil Training Lokal…",
            command=self.open_training_results,
        )
        training_menu.add_separator()
        training_menu.add_command(
            label="Buka Folder Training",
            command=lambda: self.open_folder(default_training_root()),
        )
        _insert_before_help(menu_bar, "Training AI Lokal", training_menu)

        try:
            _edit_index, edit_menu = _find_cascade_menu(menu_bar, "Edit")
        except RuntimeError:
            edit_menu = None
        if edit_menu is not None:
            _remove_commands_containing(edit_menu, "Preferences → AI")
            _normalize_separators(edit_menu)

        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(
            label="Provider Cloud & Model API…",
            command=self.open_cloud_ai_settings,
        )
        settings_menu.add_command(
            label="Model Lokal Aktif, Runtime & LoRA…",
            command=editor.open_offline_model_manager,
        )
        settings_menu.add_separator()
        settings_menu.add_command(
            label="Runtime AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )
        _insert_before_help(menu_bar, "Settings", settings_menu)

    def open_raster_paint(self) -> None:
        """Buka jendela lukis raster gaya MS Paint (pratinjau tahap 2)."""

        from .ui.raster_paint_window import RasterPaintWindow

        existing = getattr(self, "_raster_paint_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        self._raster_paint_window = RasterPaintWindow(
            self.root, library_saver=self._save_raster_document_to_library
        )

    def _save_raster_document_to_library(self, document: object) -> str:
        """Ratakan dokumen raster penuh dan simpan sebagai satu aset pustaka."""

        from tkinter import simpledialog

        from batikcraft_studio.assets.personal_store import list_user_libraries
        from batikcraft_studio.assets.raster_document_library import (
            add_document_to_library,
        )

        library = self._asset_library()
        libraries = list_user_libraries(library)
        if not libraries:
            messagebox.showinfo(
                "Belum ada pustaka",
                "Buat wadah pustaka dulu lewat menu Asset → Buat Pustaka Aset Baru.",
                parent=self.root,
            )
            return ""
        # Pilih pustaka tujuan: kalau cuma satu, langsung; kalau banyak, tanya.
        if len(libraries) == 1:
            target = libraries[0]
        else:
            names = [getattr(pack, "name", pack.pack_id) for pack in libraries]
            listing = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names))
            choice = simpledialog.askstring(
                "Pilih pustaka",
                "Simpan ke pustaka mana?\n\n" + listing,
                parent=self.root,
            )
            if not choice:
                return ""
            try:
                target = libraries[int(choice) - 1]
            except (ValueError, IndexError):
                messagebox.showerror("Pilihan tidak sah", "Nomor pustaka tidak valid.", parent=self.root)
                return ""
        name = simpledialog.askstring(
            "Nama karya", "Nama untuk karya ini di pustaka:", parent=self.root
        )
        if not name:
            return ""
        add_document_to_library(
            library, document, pack_id=target.pack_id, name=name
        )
        return f"Karya '{name}' disimpan ke pustaka '{getattr(target, 'name', target.pack_id)}'."

    def open_batikbrew_studio(self) -> None:
        """Buka jendela batifikasi mandiri (seret gambar, bukan pilih objek)."""

        from .ui.batikbrew_studio_window import BatikBrewStudioWindow

        existing = getattr(self, "_batikbrew_studio", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        self._batikbrew_studio = BatikBrewStudioWindow(
            self.root, on_insert=self._insert_batification_results
        )

    def _insert_batification_results(self, results: object) -> None:
        """Masukkan hasil batifikasi ke kanvas.

        Memakai jalur impor yang sama dengan drag-and-drop ke kanvas, jadi hasil
        studio diperlakukan persis seperti gambar dari luar aplikasi.
        """

        editor = self.main_window._editor()
        importer = getattr(editor, "_import_external_payloads", None)
        if not callable(importer):
            raise RuntimeError(
                "Editor kanvas belum mendukung penyisipan gambar dari studio."
            )
        payloads = tuple(
            (result.label, result.content) for result in results  # type: ignore[union-attr]
        )
        if not payloads:
            return
        importer(payloads, position=None, source_label="studio batifikasi")

    def _remove_nft_export_from_file(self, menu_bar: tk.Menu) -> None:
        try:
            _index, file_menu = _find_cascade_menu(menu_bar, "Berkas", "File")
        except RuntimeError:
            return
        _remove_nested_commands(file_menu, lambda label: "nft" in label.casefold())
        _normalize_separators_recursive(file_menu)

    def _remove_humanize_from_asset(self, menu_bar: tk.Menu) -> None:
        try:
            _index, asset_menu = _find_cascade_menu(menu_bar, "Asset", "Aset")
        except RuntimeError:
            return
        _remove_nested_commands(asset_menu, lambda label: "humanize" in label.casefold())
        _normalize_separators_recursive(asset_menu)

    def open_humanize_effect(self) -> None:
        window = EnhancedHumanizeWindow(self.root, self.main_window._editor())
        window.focus_set()

    def randomize_humanize_seed(self) -> None:
        window = EnhancedHumanizeWindow(self.root, self.main_window._editor())
        window.randomize_seed()
        window.focus_set()

    def open_log_folder(self) -> None:
        """Buka folder log (batikcraft.log + crash-native.log) di file manager."""

        from .logging_setup import default_log_dir, install_file_logging

        try:
            self.open_folder(install_file_logging())
        except Exception:  # noqa: BLE001
            self.open_folder(default_log_dir())

    def open_dependency_manager(self) -> None:
        """Buka Pusat Dependensi: tabel bercentang + model offline + log."""

        from .ui.dependency_center import DependencyCenterWindow

        try:
            session = self.main_window._editor().session
        except Exception:  # noqa: BLE001 - tetap buka walau editor belum siap
            session = None
        window = DependencyCenterWindow(self.root, session=session)
        window.focus_set()

    def install_runtime_models(self, family: str) -> None:
        dialog = RuntimeModelInstallDialog(self.root, family=family)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        label = "BatikBrew SDXL" if family == "sdxl" else "SD1.5 + ControlNet"
        self.main_window.flash_status(f"Dependency {label} berhasil dipasang.")

    def open_folder(self, path: object) -> None:
        try:
            reveal_path(str(path))
        except RuntimeError as exc:
            messagebox.showerror("Folder tidak dapat dibuka", str(exc), parent=self.root)

    def open_dataset_studio(self) -> None:
        window = SDXLDatasetStudioWindow(self.root)
        window.focus_set()

    def open_local_training(self) -> None:
        window = LocalLoraTrainingWindow(self.root)
        window.focus_set()

    def open_training_results(self) -> None:
        window = TrainingResultsWindow(self.root)
        window.focus_set()

    def open_cloud_ai_settings(self) -> None:
        """Configure provider defaults, API models, endpoints, and API keys."""

        dialog = CloudAISettingsDialog(self.root)
        self.root.wait_window(dialog)
        settings = dialog.result
        if settings is None:
            return
        self.main_window.flash_status(
            "Pengaturan provider disimpan: "
            f"Ornamen {provider_label(settings.ornament_provider)} · "
            f"Pola {provider_label(settings.pattern_provider)}."
        )

    def open_web_account(self) -> None:
        session = self._restore_web_session()
        if session is None:
            dialog = WebLoginDialog(self.root, self.web_client)
            self.root.wait_window(dialog)
            session = dialog.result
            if session is None:
                return
            self.web_session = session
            self.main_window.flash_status(
                f"Login BatikCraftWeb berhasil: {session.account.public_name}."
            )
        window = WebAccountWindow(
            self.root,
            self.web_client,
            session,
            on_logout=self._on_web_logout,
        )
        window.focus_set()

    def open_marketplace_website(self) -> None:
        url = self.web_client.base_url.rstrip("/") + "/market/"
        webbrowser.open(url)

    def open_web_marketplace(self, tab: str) -> None:
        if self._ensure_web_session() is None:
            return
        try:
            window = WebMarketplaceWindow(
                self.root,
                self.web_client,
                initial_tab=tab,
            )
        except BatikCraftWebError as exc:
            messagebox.showerror("BatikCraftWeb", str(exc), parent=self.root)
            return
        window.focus_set()

    def _extend_asset_menu(self, menu_bar: tk.Menu) -> None:
        """Masukkan seluruh fungsi pustaka aset ke dalam menu Asset."""

        from batikcraft_studio.i18n import tr as _tr

        asset_label = _tr("menu.asset")
        end = menu_bar.index("end")
        asset_menu: tk.Menu | None = None
        if end is not None:
            for index in range(int(end) + 1):
                try:
                    if str(menu_bar.entrycget(index, "label")) == asset_label:
                        menu_name = str(menu_bar.entrycget(index, "menu"))
                        asset_menu = menu_bar.nametowidget(menu_name)
                        break
                except tk.TclError:
                    continue
        if asset_menu is None:
            asset_menu = tk.Menu(menu_bar, tearoff=False)
            _insert_before_help(menu_bar, asset_label, asset_menu)

        asset_menu.add_separator()
        asset_menu.add_command(
            label="Buat Pustaka Aset Baru…",
            command=self.create_asset_library,
        )
        asset_menu.add_command(
            label="Studio Pustaka Aset (Isi, Kelola, Jual)…",
            command=self.open_asset_pack_studio,
        )
        asset_menu.add_command(
            label="Simpan Objek Terpilih ke Pustaka…",
            command=self.save_selection_to_asset_library,
        )

    def create_asset_library(self) -> None:
        """Buat wadah pustaka (nama, author, filosofi, tipe) sebelum diisi."""

        from .ui.asset_pack_studio_dialog import CreateLibraryDialog

        dialog = CreateLibraryDialog(self.root, self._asset_library())
        dialog.focus_set()

    def save_selection_to_asset_library(self) -> None:
        try:
            editor = self.main_window._editor()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Editor tidak tersedia", str(exc), parent=self.root)
            return
        editor.save_selected_objects_to_library()

    def _asset_library(self):
        from batikcraft_studio.assets import AssetLibrary

        try:
            return self.main_window._editor().asset_library
        except Exception:  # noqa: BLE001
            return AssetLibrary()

    def open_asset_pack_studio(self) -> None:
        """Buat pustaka aset, isi dari canvas/impor, ekspor, dan jual."""

        from .ui.asset_pack_studio_dialog import AssetPackStudioWindow

        library = self._asset_library()

        def client_provider():
            if self._ensure_web_session() is None:
                return None
            return self.web_client

        window = AssetPackStudioWindow(
            self.root, library=library, client_provider=client_provider
        )
        window.focus_set()

    def open_nft_economics(self) -> None:
        """Grafik pergerakan harga NFT seperti analisis pasar pada umumnya."""

        if self._ensure_web_session() is None:
            return
        from .ui.nft_economics_dialog import NFTEconomicsWindow

        try:
            window = NFTEconomicsWindow(self.root, self.web_client)
        except BatikCraftWebError as exc:
            messagebox.showerror("BatikCraftWeb", str(exc), parent=self.root)
            return
        window.focus_set()

    def mint_current_project_to_web(self) -> None:
        session = self._ensure_web_session()
        if session is None:
            return
        if session.account.role != "creator":
            messagebox.showerror(
                "Akun creator diperlukan",
                "Hanya akun Creator / User yang dapat mint dan menjual NFT.",
                parent=self.root,
            )
            return
        project = self.session.project
        if project is None:
            messagebox.showerror(
                "Project belum dibuka",
                "Buat atau buka project sebelum minting NFT.",
                parent=self.root,
            )
            return
        dialog = MintCurrentProjectDialog(
            self.root,
            client=self.web_client,
            session=session,
            project=project,
            assets=self.session.assets,
        )
        dialog.focus_set()

    def publish_nft_to_web(self) -> None:
        """Compatibility alias for the new Marketplace minting workflow."""

        self.mint_current_project_to_web()

    def publish_model_to_web(self) -> None:
        session = self._ensure_web_session()
        if session is None:
            return
        if session.account.role != "creator":
            messagebox.showerror(
                "Akun creator diperlukan",
                "Hanya akun Creator / User yang dapat menjual model.",
                parent=self.root,
            )
            return
        dialog = PublishModelDialog(self.root, self.web_client)
        dialog.focus_set()

    def _ensure_web_session(self) -> WebSession | None:
        session = self._restore_web_session()
        if session is not None:
            return session
        dialog = WebLoginDialog(self.root, self.web_client)
        self.root.wait_window(dialog)
        self.web_session = dialog.result
        return self.web_session

    def _restore_web_session(self) -> WebSession | None:
        if self.web_session is not None:
            return self.web_session
        self.web_session = self.web_client.restore_session()
        return self.web_session

    def _on_web_logout(self) -> None:
        self.web_session = None
        self.main_window.flash_status("Akun BatikCraftWeb telah logout.")


def _insert_before_help(menu_bar: tk.Menu, label: str, menu: tk.Menu) -> None:
    end = menu_bar.index(tk.END)
    if end is None:
        menu_bar.add_cascade(label=label, menu=menu)
        return
    for index in range(int(end) + 1):
        if menu_bar.type(index) != "cascade":
            continue
        current = str(menu_bar.entrycget(index, "label")).casefold()
        if current in {"help", "bantuan"}:
            menu_bar.insert_cascade(index, label=label, menu=menu)
            return
    menu_bar.add_cascade(label=label, menu=menu)


def _remove_commands_containing(
    menu: tk.Menu,
    fragment: str,
    *,
    rename: bool = False,
) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    needle = fragment.casefold()
    for index in range(int(end), -1, -1):
        if menu.type(index) != "command":
            continue
        label = str(menu.entrycget(index, "label"))
        if needle not in label.casefold():
            continue
        if rename:
            menu.entryconfigure(index, label="Generate Motif BatikBrew…")
        else:
            menu.delete(index)


def _remove_nested_commands(menu: tk.Menu, predicate: object) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        item_type = menu.type(index)
        if item_type == "cascade":
            child = menu.nametowidget(str(menu.entrycget(index, "menu")))
            _remove_nested_commands(child, predicate)
            continue
        if item_type != "command":
            continue
        label = str(menu.entrycget(index, "label"))
        if predicate(label):
            menu.delete(index)


def _normalize_separators_recursive(menu: tk.Menu) -> None:
    end = menu.index(tk.END)
    if end is not None:
        for index in range(int(end) + 1):
            if menu.type(index) == "cascade":
                child = menu.nametowidget(str(menu.entrycget(index, "menu")))
                _normalize_separators_recursive(child)
    _normalize_separators(menu)


def _normalize_separators(menu: tk.Menu) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        if menu.type(index) != "separator":
            continue
        previous_separator = index == 0 or menu.type(index - 1) == "separator"
        last_item = index == menu.index(tk.END)
        if previous_separator or last_item:
            menu.delete(index)


__all__ = ["ContextToolApplication"]
