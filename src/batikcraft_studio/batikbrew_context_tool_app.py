"""Application shell with AI settings and BatikCraftWeb marketplace bridge."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.ai.generation_providers import provider_label
from batikcraft_studio.web_bridge import (
    BatikCraftWebClient,
    BatikCraftWebError,
    WebSession,
)

from .context_tool_app import _find_cascade_menu
from .progress_context_tool_app import ContextToolApplication as _ProgressApplication
from .ui.cloud_ai_settings_dialog import CloudAISettingsDialog
from .ui.web_marketplace_dialogs import (
    PublishModelDialog,
    PublishNFTDialog,
    WebAccountWindow,
    WebLoginDialog,
    WebMarketplaceWindow,
)


class ContextToolApplication(_ProgressApplication):
    """Keep generation settings centralized and connect the desktop marketplace."""

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
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Login / Akun BatikCraftWeb…",
            command=self.open_web_account,
        )
        ai_menu.add_command(
            label="NFT Marketplace…",
            command=lambda: self.open_web_marketplace("nfts"),
        )
        ai_menu.add_command(
            label="Model Marketplace…",
            command=lambda: self.open_web_marketplace("models"),
        )
        ai_menu.add_command(
            label="Library Model Saya…",
            command=lambda: self.open_web_marketplace("library"),
        )
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Publish Motif sebagai NFT…",
            command=self.publish_nft_to_web,
        )
        ai_menu.add_command(
            label="Publish Model ke Marketplace…",
            command=self.publish_model_to_web,
        )

        try:
            _edit_index, edit_menu = _find_cascade_menu(menu_bar, "Edit")
        except RuntimeError:
            edit_menu = None
        if edit_menu is not None:
            _remove_commands_containing(edit_menu, "Preferences → AI")

        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(
            label="Provider Cloud & Model API…",
            command=self.open_cloud_ai_settings,
        )
        settings_menu.add_command(
            label="Model Lokal, Runtime & LoRA…",
            command=editor.open_offline_model_manager,
        )
        settings_menu.add_separator()
        settings_menu.add_command(
            label="Runtime AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        end = menu_bar.index(tk.END)
        if end is None:
            menu_bar.add_cascade(label="Settings", menu=settings_menu)
        else:
            menu_bar.insert_cascade(end, label="Settings", menu=settings_menu)

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

    def publish_nft_to_web(self) -> None:
        if self._ensure_web_session() is None:
            return
        dialog = PublishNFTDialog(self.root, self.web_client)
        dialog.focus_set()

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


def _remove_commands_containing(
    menu: tk.Menu,
    fragment: str,
    *,
    rename: bool = False,
) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        if menu.type(index) != "command":
            continue
        label = str(menu.entrycget(index, "label"))
        if fragment not in label:
            continue
        if rename:
            menu.entryconfigure(index, label="Generate Motif BatikBrew…")
        else:
            menu.delete(index)


__all__ = ["ContextToolApplication"]
