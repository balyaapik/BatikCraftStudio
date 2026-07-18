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


def test_dependency_manager_installs_only_local_ai_packages() -> None:
    modules = {module for module, _requirement in dependency_profiles_patch._LOCAL_REQUIREMENTS}

    assert "torch" in modules
    assert "diffusers" in modules
    assert "openai" not in modules
    assert "google.genai" not in modules
    assert "keyring" not in modules


def test_dependency_manager_explains_cloud_api_and_uses_large_status_table() -> None:
    source = inspect.getsource(dependency_profiles_patch)

    assert "OpenAI dan Gemini memakai API key" in source
    assert 'window.title("AI Lokal & Model")' in source
    assert "width = min(1220" in source
    assert "window.tree.configure(height=14)" in source
    assert 'text="Dependency AI Lokal"' in source


def test_pyproject_exposes_scoped_ai_extras() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "ai-local = [" in pyproject
    assert "ai-openai = [" in pyproject
    assert "ai-gemini = [" in pyproject
    assert "ai-training = [" in pyproject
    assert '"packaging>=24,<26"' in pyproject
