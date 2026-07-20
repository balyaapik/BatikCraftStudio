from __future__ import annotations

import inspect
from importlib import metadata
from pathlib import Path

from batikcraft_studio.ai import dependency_profiles
from batikcraft_studio.ui import dependency_profiles_patch

ROOT = Path(__file__).resolve().parents[1]


def _modules(profile_id: str) -> set[str]:
    return {
        item.module
        for item in dependency_profiles.dependencies_for_profile(profile_id)
    }


def test_local_profile_does_not_pull_cloud_sdks() -> None:
    modules = _modules(dependency_profiles.PROFILE_LOCAL)

    assert "torch" in modules
    assert "diffusers" in modules
    assert "openai" not in modules
    assert "google.genai" not in modules
    assert "keyring" not in modules


def test_cloud_profiles_do_not_pull_local_runtime() -> None:
    openai_modules = _modules(dependency_profiles.PROFILE_OPENAI)
    gemini_modules = _modules(dependency_profiles.PROFILE_GEMINI)

    assert openai_modules == {"openai", "keyring"}
    assert gemini_modules == {"google.genai", "keyring"}
    assert "torch" not in openai_modules | gemini_modules


def test_all_profile_deduplicates_shared_dependencies() -> None:
    dependencies = dependency_profiles.dependencies_for_profile(
        dependency_profiles.PROFILE_ALL
    )
    modules = [item.module for item in dependencies]

    assert len(modules) == len(set(modules))
    assert modules.count("keyring") == 1


def test_bundled_module_without_dist_info_is_not_downloaded_again(monkeypatch) -> None:
    spec = next(
        item for item in dependency_profiles.DEPENDENCIES if item.module == "openai"
    )
    monkeypatch.setattr(
        dependency_profiles.importlib.util,
        "find_spec",
        lambda module: object(),
    )

    def missing_distribution(distribution: str) -> str:
        raise metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(dependency_profiles.metadata, "version", missing_distribution)
    status = dependency_profiles.dependency_status(spec)

    assert status.available is True
    assert status.compatible is True
    assert status.version is None
    assert dependency_profiles.missing_requirements(
        dependency_profiles.PROFILE_OPENAI
    ) == ()


def test_incompatible_version_is_selected_for_repair(monkeypatch) -> None:
    spec = next(
        item for item in dependency_profiles.DEPENDENCIES if item.module == "diffusers"
    )
    monkeypatch.setattr(
        dependency_profiles.importlib.util,
        "find_spec",
        lambda module: object(),
    )
    monkeypatch.setattr(
        dependency_profiles.metadata,
        "version",
        lambda distribution: "0.38.0",
    )

    status = dependency_profiles.dependency_status(spec)

    assert status.available is True
    assert status.compatible is False
    assert spec.requirement in dependency_profiles.missing_requirements(
        dependency_profiles.PROFILE_LOCAL
    )


def test_dependency_center_replaces_button_based_manager() -> None:
    """Jendela lama berbasis tombol digantikan Pusat Dependensi bertabel:
    pengguna mencentang komponen, lalu Unduh & Instal / Uninstall."""

    from batikcraft_studio.ui import dependency_center, dependency_profiles_patch

    # Patch tombol lama kini no-op.
    patch_source = inspect.getsource(dependency_profiles_patch)
    assert "Dihapus" in patch_source
    assert "install_all_button" not in patch_source

    source = inspect.getsource(dependency_center)
    assert "Unduh & Instal Terpilih" in source
    assert "Uninstall Terpilih" in source
    assert '"eligibility"' in source
    assert "Log Instalasi" in source
    assert "Model AI Offline & LoRA" in source
    # Tidak boleh ada lagi tombol instal-semua atau instal per komponen.
    assert "Instal Semua AI" not in source


def test_menu_exposes_single_dependency_entry() -> None:
    from batikcraft_studio import batikbrew_context_tool_app as app

    source = inspect.getsource(app)
    assert "Pusat Dependensi (Unduh, Instal, Uninstall)…" in source
    assert "Unduh / Instal BatikBrew SDXL…" not in source
    assert "Instal / Reparasi Python AI Packages…" not in source


def test_pyproject_exposes_scoped_ai_extras() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "ai-local = [" in pyproject
    assert "ai-openai = [" in pyproject
    assert "ai-gemini = [" in pyproject
    assert "ai-training = [" in pyproject
    assert '"packaging>=24,<26"' in pyproject
