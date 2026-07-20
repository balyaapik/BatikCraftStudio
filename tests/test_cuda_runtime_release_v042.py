from __future__ import annotations

import inspect
from pathlib import Path

from batikcraft_studio import dependency_bootstrap_v042
from batikcraft_studio.ai import torch_runtime_integrity
from batikcraft_studio.ui import dependency_cuda_selection_patch

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_installer_forwards_explicit_cuda_variant(tmp_path: Path) -> None:
    command = dependency_bootstrap_v042.managed_ai_install_command(
        ["torch>=2.4"],
        target=tmp_path / "packages",
        cache_dir=tmp_path / "cache",
        executable="BatikCraftStudio.exe",
        frozen=True,
        torch_variant="cuda",
    )

    assert "--torch-variant" in command
    assert command[command.index("--torch-variant") + 1] == "cuda"
    assert command[-1] == "torch>=2.4"


def test_torch_install_uses_exclusive_official_index(tmp_path: Path) -> None:
    command = dependency_bootstrap_v042.managed_ai_install_command(
        ["torch>=2.4"],
        target=tmp_path / "packages",
        cache_dir=tmp_path / "cache",
        frozen=False,
        torch_variant="cuda",
    )

    assert "--index-url" in command
    assert "--extra-index-url" not in command
    assert dependency_bootstrap_v042.CUDA_WHEEL_INDEX in command


def test_non_torch_packages_do_not_receive_torch_only_index(tmp_path: Path) -> None:
    command = dependency_bootstrap_v042.managed_ai_install_command(
        ["diffusers>=0.39,<0.40", "transformers>=4.48,<5"],
        target=tmp_path / "packages",
        cache_dir=tmp_path / "cache",
        frozen=False,
    )

    assert dependency_bootstrap_v042.CUDA_WHEEL_INDEX not in command
    assert dependency_bootstrap_v042.CPU_WHEEL_INDEX not in command


def test_dual_selection_keeps_only_cuda_on_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(dependency_cuda_selection_patch, "nvidia_gpu_present", lambda: True)
    checked = dependency_cuda_selection_patch.normalise_checked_keys(
        {"torch_cpu", "torch_cuda", "diffusers", "sdxl"}
    )

    assert "torch_cuda" in checked
    assert "torch_cpu" not in checked


def test_dual_selection_keeps_only_cpu_without_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(dependency_cuda_selection_patch, "nvidia_gpu_present", lambda: False)
    checked = dependency_cuda_selection_patch.normalise_checked_keys(
        {"torch_cpu", "torch_cuda", "diffusers"}
    )

    assert "torch_cpu" in checked
    assert "torch_cuda" not in checked


def test_explicit_single_cpu_choice_is_preserved_on_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(dependency_cuda_selection_patch, "nvidia_gpu_present", lambda: True)
    checked = dependency_cuda_selection_patch.normalise_checked_keys(
        {"torch_cpu", "diffusers"}
    )

    assert "torch_cpu" in checked
    assert "torch_cuda" not in checked


def test_torch_variant_detection_and_purge(tmp_path: Path) -> None:
    packages = tmp_path / "site-packages"
    torch_dir = packages / "torch"
    torch_dir.mkdir(parents=True)
    (torch_dir / "version.py").write_text(
        "__version__ = '2.5.1+cu121'\ncuda: str | None = '12.1'\n",
        encoding="utf-8",
    )
    (packages / "torch-2.5.1+cu121.dist-info").mkdir()
    (packages / "functorch").mkdir()

    assert torch_runtime_integrity.installed_torch_variant(packages) == "cuda"
    version = torch_runtime_integrity.validate_torch_variant(packages, "cuda")
    assert version == "2.5.1+cu121"
    assert torch_runtime_integrity.purge_managed_torch_installation(packages) >= 3
    assert torch_runtime_integrity.installed_torch_variant(packages) is None


def test_cuda_guard_runs_before_final_sdxl_factory_call() -> None:
    from batikcraft_studio.ai import cuda_runtime_guard_v042

    source = inspect.getsource(cuda_runtime_guard_v042.install_cuda_runtime_guard_v042)
    assert "nvidia_gpu_present" in source
    assert "guard_cpu_generation" in source
    assert source.rindex("guard_cpu_generation") < source.rindex(
        "return original_factory(settings)"
    )


def test_release_bootstrap_is_installed_before_application_import() -> None:
    source = (ROOT / "src" / "batikcraft_studio" / "__main__.py").read_text(
        encoding="utf-8"
    )

    application_import = "from .integrated_market_app import ContextToolApplication"
    assert source.index("install_dependency_bootstrap_v042()") < source.index(
        application_import
    )
    assert source.index("install_cuda_runtime_guard_v042()") < source.index(
        application_import
    )
    assert source.index("install_dependency_cuda_selection_patch()") < source.index(
        application_import
    )
