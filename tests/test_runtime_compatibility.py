from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

from batikcraft_studio import dependency_bootstrap, runtime_compatibility
from batikcraft_studio.config import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_all_managed_model_directories_share_one_dependency_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dependency_root = tmp_path / "BatikCraft Studio" / "dependencies"
    monkeypatch.setenv(dependency_bootstrap.DEPENDENCIES_DIR_ENV, str(dependency_root))

    assert dependency_bootstrap.default_managed_huggingface_cache_dir() == (
        dependency_root / "cache" / "huggingface"
    )
    assert dependency_bootstrap.default_managed_runtime_model_dir() == (
        dependency_root / "models" / "runtime"
    )
    assert dependency_bootstrap.default_managed_model_library_dir() == (
        dependency_root / "models" / "lora"
    )


def test_stale_paths_from_another_windows_user_are_remapped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dependency_root = tmp_path / "install" / "dependencies"
    monkeypatch.setenv(dependency_bootstrap.DEPENDENCIES_DIR_ENV, str(dependency_root))

    old_runtime = (
        r"C:\Users\hp\AppData\Local\BatikCraftStudio\models\runtime"
        r"\stable-diffusion-xl-base-1.0"
    )
    old_lora = (
        r"C:\Users\hp\AppData\Local\BatikCraftStudio\models"
        r"\my-batik-model\lora\weights.safetensors"
    )

    assert runtime_compatibility._managed_runtime_path(old_runtime) == str(
        dependency_root / "models" / "runtime" / "stable-diffusion-xl-base-1.0"
    )
    assert runtime_compatibility._managed_lora_path(old_lora) == str(
        dependency_root
        / "models"
        / "lora"
        / "my-batik-model"
        / "lora"
        / "weights.safetensors"
    )


def test_windowed_build_gets_writable_output_streams(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    stdout, stderr = runtime_compatibility.ensure_windowed_text_streams()

    assert stdout is not None
    assert stderr is not None
    assert stdout.write("hidden stdout") == len("hidden stdout")
    assert stderr.write("hidden stderr") == len("hidden stderr")
    assert stdout.isatty() is False
    assert stderr.isatty() is False


def test_legacy_huggingface_download_accepts_batikcraft_progress_class(
    monkeypatch,
) -> None:
    fake_package = types.ModuleType("huggingface_hub")
    fake_file_download = types.ModuleType("huggingface_hub.file_download")
    original_tqdm = object()
    fake_file_download.tqdm = original_tqdm
    observed: dict[str, object] = {}

    def old_hf_hub_download(*args: object, **kwargs: object) -> str:
        observed["tqdm"] = fake_file_download.tqdm
        bar = fake_file_download.tqdm(total=10, name="legacy-group", file=None)
        observed["bar"] = bar
        return "downloaded"

    fake_package.hf_hub_download = old_hf_hub_download
    fake_package.file_download = fake_file_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.file_download", fake_file_download)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    class ProgressBar:
        def __init__(self, *args: object, **kwargs: object) -> None:
            assert "name" not in kwargs
            stream = kwargs.get("file")
            assert stream is not None
            assert stream.write("progress") == len("progress")
            self.total = kwargs.get("total")

    assert runtime_compatibility._patch_legacy_hf_hub_download() is True
    result = fake_package.hf_hub_download(tqdm_class=ProgressBar)

    assert result == "downloaded"
    assert isinstance(observed["bar"], ProgressBar)
    assert fake_file_download.tqdm is original_tqdm
    assert sys.stderr is not None


def test_app_and_package_versions_are_aligned() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project_version = str(tomllib.load(stream)["project"]["version"])

    assert APP_VERSION == "0.9.15"
    assert project_version == APP_VERSION


def test_runtime_compatibility_runs_before_application_import() -> None:
    source = (ROOT / "src" / "batikcraft_studio" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert source.index("activate_managed_ai_packages()") < source.index(
        "install_runtime_compatibility()"
    )
    assert source.index("install_runtime_compatibility()") < source.index(
        "from .integrated_market_app import ContextToolApplication"
    )
