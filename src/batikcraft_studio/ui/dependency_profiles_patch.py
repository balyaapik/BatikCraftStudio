"""Split the dependency manager into local and cloud install profiles."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from batikcraft_studio.ai.dependency_profiles import (
    DEPENDENCIES,
    PROFILE_ALL,
    PROFILE_GEMINI,
    PROFILE_LABELS,
    PROFILE_LOCAL,
    PROFILE_OPENAI,
    dependencies_for_profile,
    dependency_status,
    missing_requirements,
    profile_progress,
    profile_tags,
)
from batikcraft_studio.ui import dependency_manager_dialog as dependency_dialog

_INSTALLED = False


def install_dependency_profiles_patch() -> None:
    """Install scoped dependency actions without replacing the stable worker process."""

    global _INSTALLED
    if _INSTALLED:
        return

    window_class = dependency_dialog.DependencyManagerWindow
    if getattr(window_class, "_batikcraft_dependency_profiles_patch", False):
        _INSTALLED = True
        return

    dependency_dialog.PYTHON_AI_DEPENDENCIES = tuple(
        (item.module, item.requirement) for item in DEPENDENCIES
    )

    original_build = window_class._build
    original_refresh = window_class.refresh
    original_install = window_class.install_python_dependencies
    original_set_installing = window_class._set_installing

    def build(window: Any) -> None:
        original_build(window)
        window.install_all_button.configure(
            text="Instal AI Lokal + BatikBrew SDXL",
            command=window.install_complete_batikbrew,
        )
        window.install_packages_button.configure(
            text="Instal / Reparasi AI Lokal",
            command=lambda: window.install_dependency_profile(PROFILE_LOCAL),
        )

        quick_setup = _find_label_frame(window, "Instalasi Sekali Klik")
        window._dependency_profile_buttons = []
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
        profile_actions = ttk.Frame(quick_setup)
        profile_actions.grid(row=4, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            profile_actions.columnconfigure(column, weight=1)

        actions = (
            ("AI Lokal", PROFILE_LOCAL),
            ("OpenAI", PROFILE_OPENAI),
            ("Gemini", PROFILE_GEMINI),
            ("Semua Profil", PROFILE_ALL),
        )
        for column, (label, profile_id) in enumerate(actions):
            button = ttk.Button(
                profile_actions,
                text=label,
                command=lambda selected=profile_id: window.install_dependency_profile(
                    selected
                ),
            )
            button.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 4, 0),
            )
            window._dependency_profile_buttons.append(button)

        ttk.Label(
            quick_setup,
            textvariable=window.profile_status_value,
            style="Muted.TLabel",
            justify="left",
            wraplength=840,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def install_dependency_profile(
        window: Any,
        profile_id: str,
        *,
        continue_with_sdxl: bool = False,
    ) -> None:
        if window._process is not None:
            window._installation_already_running()
            return

        profile = str(profile_id).strip().casefold()
        requirements = missing_requirements(profile)
        label = PROFILE_LABELS[profile]
        if not requirements:
            window._append_log(
                f"{label} sudah lengkap; tidak ada paket yang diunduh ulang."
            )
            window.refresh()
            if continue_with_sdxl:
                window._continue_with_sdxl = False
                window.after(150, window.install_sdxl)
            return

        specs = dependencies_for_profile(profile)
        selected = tuple(
            (item.module, item.requirement)
            for item in specs
            if item.requirement in requirements
        )
        window._active_dependency_profile = profile
        window._append_log(
            f"Memasang {label}: {len(selected)} paket belum ada atau versinya tidak cocok."
        )

        dependency_dialog.PYTHON_AI_DEPENDENCIES = selected
        try:
            original_install(window, continue_with_sdxl=continue_with_sdxl)
        finally:
            # The worker receives a concrete requirement list before it starts, so the
            # shared catalogue can immediately return to the complete status view.
            dependency_dialog.PYTHON_AI_DEPENDENCIES = tuple(
                (item.module, item.requirement) for item in DEPENDENCIES
            )

    def install_python_dependencies(
        window: Any,
        *,
        continue_with_sdxl: bool = False,
    ) -> None:
        window.install_dependency_profile(
            PROFILE_LOCAL,
            continue_with_sdxl=continue_with_sdxl,
        )

    def install_complete_batikbrew(window: Any) -> None:
        window.install_dependency_profile(PROFILE_LOCAL, continue_with_sdxl=True)

    def missing_local_requirements(window: Any) -> list[str]:
        del window
        return list(missing_requirements(PROFILE_LOCAL))

    def refresh(window: Any) -> None:
        original_refresh(window)

        for item_id in window.tree.get_children(""):
            window.tree.delete(item_id)
        for spec in DEPENDENCIES:
            state = dependency_status(spec)
            window.tree.insert(
                "",
                tk.END,
                values=(
                    f"[{profile_tags(spec)}] {spec.requirement}",
                    state.detail,
                ),
            )

        local_ready, local_total = profile_progress(PROFILE_LOCAL)
        openai_ready, openai_total = profile_progress(PROFILE_OPENAI)
        gemini_ready, gemini_total = profile_progress(PROFILE_GEMINI)
        summary = (
            f"AI Lokal: {local_ready}/{local_total} · "
            f"OpenAI: {openai_ready}/{openai_total} · "
            f"Gemini: {gemini_ready}/{gemini_total}"
        )
        window.profile_status_value.set(
            summary
            + "\nPaket yang tersedia di executable tidak dipasang ulang ke dependencies."
        )

        runtime_lines = str(window.runtime_status.get()).splitlines()
        if runtime_lines and runtime_lines[0].startswith("Python AI Packages:"):
            runtime_lines.pop(0)
        runtime_suffix = "\n" + "\n".join(runtime_lines) if runtime_lines else ""
        window.runtime_status.set(summary + runtime_suffix)

    def set_installing(window: Any, installing: bool) -> None:
        original_set_installing(window, installing)
        state = "disabled" if installing else "normal"
        for button in getattr(window, "_dependency_profile_buttons", ()):
            button.configure(state=state)

    window_class._build = build  # type: ignore[assignment]
    window_class.refresh = refresh  # type: ignore[assignment]
    window_class.install_dependency_profile = (  # type: ignore[attr-defined]
        install_dependency_profile
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


def _find_label_frame(parent: tk.Misc, text: str) -> ttk.LabelFrame | None:
    for child in parent.winfo_children():
        if isinstance(child, ttk.LabelFrame) and str(child.cget("text")) == text:
            return child
        found = _find_label_frame(child, text)
        if found is not None:
            return found
    return None


__all__ = ["install_dependency_profiles_patch"]
