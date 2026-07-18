"""Keep the dependency manager focused on local AI and model installation.

OpenAI and Gemini are remote providers. Their client SDKs are bundled with desktop
builds and their user-facing setup belongs in the provider/API-key dialog, not in the
local runtime installer. This patch also makes the dependency window large enough to
show every local package and its complete status.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from batikcraft_studio.ai.dependency_profiles import (
    PROFILE_LOCAL,
    dependencies_for_profile,
    dependency_status,
    missing_requirements,
    profile_progress,
)
from batikcraft_studio.ui import dependency_manager_dialog as dependency_dialog

_INSTALLED = False
_LOCAL_DEPENDENCIES = dependencies_for_profile(PROFILE_LOCAL)
_LOCAL_REQUIREMENTS = tuple(
    (item.module, item.requirement) for item in _LOCAL_DEPENDENCIES
)


def install_dependency_profiles_patch() -> None:
    """Install local-only dependency actions without replacing the worker process."""

    global _INSTALLED
    if _INSTALLED:
        return

    window_class = dependency_dialog.DependencyManagerWindow
    if getattr(window_class, "_batikcraft_dependency_profiles_patch", False):
        _INSTALLED = True
        return

    dependency_dialog.PYTHON_AI_DEPENDENCIES = _LOCAL_REQUIREMENTS

    original_build = window_class._build
    original_refresh = window_class.refresh
    original_install = window_class.install_python_dependencies
    original_set_installing = window_class._set_installing

    def build(window: Any) -> None:
        original_build(window)
        window.title("AI Lokal & Model")
        _fit_window_to_screen(window)
        _configure_local_dependency_table(window)
        _rewrite_window_copy(window)

        window.install_all_button.configure(
            text="Instal AI Lokal + BatikBrew SDXL",
            command=window.install_complete_batikbrew,
        )
        window.install_packages_button.configure(
            text="Instal / Reparasi AI Lokal",
            command=window.install_local_dependencies,
        )

        quick_setup = _find_label_frame(window, "Instalasi Sekali Klik")
        window.profile_status_value = tk.StringVar(master=window, value="")
        if quick_setup is None:
            return

        ttk.Separator(quick_setup, orient="horizontal").grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(10, 8),
        )
        ttk.Label(
            quick_setup,
            textvariable=window.profile_status_value,
            style="Muted.TLabel",
            justify="left",
            wraplength=1040,
        ).grid(row=4, column=0, columnspan=2, sticky="w")

    def install_local_dependencies(
        window: Any,
        *,
        continue_with_sdxl: bool = False,
    ) -> None:
        if window._process is not None:
            window._installation_already_running()
            return

        requirements = missing_requirements(PROFILE_LOCAL)
        if not requirements:
            window._append_log(
                "AI Lokal sudah lengkap; tidak ada paket yang perlu diunduh ulang."
            )
            window.refresh()
            if continue_with_sdxl:
                window._continue_with_sdxl = False
                window.after(150, window.install_sdxl)
            return

        selected = tuple(
            (item.module, item.requirement)
            for item in _LOCAL_DEPENDENCIES
            if item.requirement in requirements
        )
        window._append_log(
            "Memasang AI Lokal: "
            f"{len(selected)} paket belum ada atau versinya tidak sesuai."
        )

        dependency_dialog.PYTHON_AI_DEPENDENCIES = selected
        try:
            original_install(window, continue_with_sdxl=continue_with_sdxl)
        finally:
            # The worker already received a concrete requirements list. Restore the
            # complete local catalogue immediately for refresh/status rendering.
            dependency_dialog.PYTHON_AI_DEPENDENCIES = _LOCAL_REQUIREMENTS

    def install_python_dependencies(
        window: Any,
        *,
        continue_with_sdxl: bool = False,
    ) -> None:
        window.install_local_dependencies(continue_with_sdxl=continue_with_sdxl)

    def install_complete_batikbrew(window: Any) -> None:
        window.install_local_dependencies(continue_with_sdxl=True)

    def missing_local_requirements(window: Any) -> list[str]:
        del window
        return list(missing_requirements(PROFILE_LOCAL))

    def refresh(window: Any) -> None:
        original_refresh(window)

        for item_id in window.tree.get_children(""):
            window.tree.delete(item_id)
        for spec in _LOCAL_DEPENDENCIES:
            state = dependency_status(spec)
            window.tree.insert(
                "",
                tk.END,
                values=(
                    f"{spec.label}  ·  {spec.requirement}",
                    state.detail,
                ),
            )

        local_ready, local_total = profile_progress(PROFILE_LOCAL)
        summary = f"AI Lokal siap: {local_ready}/{local_total} dependency"
        window.profile_status_value.set(
            summary
            + "\nOpenAI dan Gemini memakai API key. Tidak ada model atau paket cloud "
            "yang perlu diunduh dari jendela ini."
        )

        runtime_lines = str(window.runtime_status.get()).splitlines()
        if runtime_lines and runtime_lines[0].startswith("Python AI Packages:"):
            runtime_lines.pop(0)
        runtime_suffix = "\n" + "\n".join(runtime_lines) if runtime_lines else ""
        window.runtime_status.set(summary + runtime_suffix)

    def set_installing(window: Any, installing: bool) -> None:
        original_set_installing(window, installing)

    window_class._build = build  # type: ignore[assignment]
    window_class.refresh = refresh  # type: ignore[assignment]
    window_class.install_local_dependencies = (  # type: ignore[attr-defined]
        install_local_dependencies
    )
    window_class.install_python_dependencies = (  # type: ignore[assignment]
        install_python_dependencies
    )
    window_class.install_complete_batikbrew = (  # type: ignore[assignment]
        install_complete_batikbrew
    )
    window_class._missing_requirements = (  # type: ignore[assignment]
        missing_local_requirements
    )
    window_class._set_installing = set_installing  # type: ignore[assignment]
    window_class._batikcraft_dependency_profiles_patch = (  # type: ignore[attr-defined]
        True
    )
    _INSTALLED = True


def _fit_window_to_screen(window: tk.Toplevel) -> None:
    """Use most of the monitor while keeping the window fully visible."""

    window.update_idletasks()
    screen_width = max(1, int(window.winfo_screenwidth()))
    screen_height = max(1, int(window.winfo_screenheight()))
    width = min(1220, max(900, screen_width - 80))
    height = min(900, max(680, screen_height - 100))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(min(980, width), min(700, height))


def _configure_local_dependency_table(window: Any) -> None:
    window.tree.configure(height=14)
    window.tree.heading("requirement", text="Dependency AI Lokal")
    window.tree.heading("status", text="Status Instalasi")
    window.tree.column("requirement", width=720, minwidth=440, stretch=True)
    window.tree.column("status", width=300, minwidth=240, stretch=True)


def _rewrite_window_copy(window: tk.Misc) -> None:
    replacements = {
        "BatikCraft AI Setup": "BatikCraft AI Lokal & Model",
        (
            "Paket Python AI, pengunduh model, dan BatikBrew dipasang langsung "
            "dari aplikasi ke folder dependencies. Pengguna tidak perlu mencari "
            "Python, pip, atau dependency melalui terminal."
        ): (
            "Jendela ini hanya untuk dependency AI lokal, runtime SDXL/SD1.5, dan "
            "LoRA. OpenAI serta Gemini adalah provider API dan diatur melalui "
            "AI → Pengaturan AI → Provider Cloud & Model API."
        ),
        (
            "Memasang atau memperbaiki seluruh paket AI, lalu otomatis membuka "
            "unduhan BatikBrew SDXL dengan progres byte dan persentase."
        ): (
            "Memasang atau memperbaiki paket AI lokal yang belum tersedia, lalu "
            "membuka unduhan BatikBrew SDXL dengan progres byte dan persentase."
        ),
    }
    for child in _walk_widgets(window):
        if isinstance(child, ttk.Label):
            text = str(child.cget("text"))
            replacement = replacements.get(text)
            if replacement is not None:
                child.configure(text=replacement, wraplength=1080)
        elif isinstance(child, ttk.LabelFrame):
            if str(child.cget("text")) == "Python AI Packages":
                child.configure(text="Dependency AI Lokal")


def _walk_widgets(parent: tk.Misc) -> tuple[tk.Misc, ...]:
    widgets: list[tk.Misc] = []
    for child in parent.winfo_children():
        widgets.append(child)
        widgets.extend(_walk_widgets(child))
    return tuple(widgets)


def _find_label_frame(parent: tk.Misc, text: str) -> ttk.LabelFrame | None:
    for child in parent.winfo_children():
        if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) == text:
            return child
        found = _find_label_frame(child, text)
        if found is not None:
            return found
    return None


__all__ = ["install_dependency_profiles_patch"]
