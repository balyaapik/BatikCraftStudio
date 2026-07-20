from __future__ import annotations

import inspect
from pathlib import Path

from batikcraft_studio import dependency_bootstrap_v042
from batikcraft_studio.ai import torch_runtime_integrity
from batikcraft_studio.ui import dependency_cuda_selection_patch

ROOT = Path(__file__).resolve().parents[1]


def _write_cuda_torch(packages: Path, version: str = "2.5.1+cu121") -> None:
    torch_dir = packages / "torch"
    (torch_dir / "lib").mkdir(parents=True)
    (torch_dir / "version.py").write_text(
        f"__version__ = '{version}'\ncuda: str | None = '12.1'\n",
        encoding="utf-8",
    )
    (torch_dir / "lib" / "asmjit.dll").write_bytes(b"active-cuda-dll")
    metadata = packages / f"torch-{version}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: torch\nVersion: {version}\n",
        encoding="utf-8",
    )


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


def test_frozen_entry_installs_v042_patch_before_capturing_installer() -> None:
    source = (ROOT / "packaging" / "desktop_entry.py").read_text(encoding="utf-8")

    patch_call = "install_dependency_bootstrap_v042()"
    legacy_import = (
        "from batikcraft_studio.dependency_bootstrap import "
        "maybe_run_dependency_installer"
    )
    installer_call = "maybe_run_dependency_installer(sys.argv[1:])"

    assert source.index(patch_call) < source.index(legacy_import)
    assert source.index(legacy_import) < source.index(installer_call)


def test_torch_install_uses_exclusive_official_index(tmp_path: Path) -> None:
    command = dependency_bootstrap_v042.managed_ai_install_command(
        ["torch>=2.4"],
        target=tmp_path / "packages",
        cache_dir=tmp_path / "cache",
        frozen=False,
        torch_variant="cuda",
    )

    assert "--upgrade" in command
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


def test_companion_install_preserves_existing_cuda_torch(tmp_path: Path) -> None:
    packages = tmp_path / "site-packages"
    cache = tmp_path / "cache"
    _write_cuda_torch(packages)

    command = dependency_bootstrap_v042.managed_ai_install_command(
        ["accelerate>=1.2", "peft>=0.17", "safetensors>=0.4"],
        target=packages,
        cache_dir=cache,
        frozen=False,
    )

    assert "--upgrade" not in command
    assert "--upgrade-strategy" not in command
    assert "--constraint" in command
    constraint = Path(command[command.index("--constraint") + 1])
    assert constraint.read_text(encoding="utf-8") == "torch==2.5.1+cu121\n"
    assert "--extra-index-url" in command
    assert dependency_bootstrap_v042.CUDA_WHEEL_INDEX in command
    assert packages.joinpath("torch", "lib", "asmjit.dll").read_bytes() == b"active-cuda-dll"


def test_stale_cpu_torch_metadata_is_removed_without_touching_cuda_dll(
    tmp_path: Path,
) -> None:
    packages = tmp_path / "site-packages"
    _write_cuda_torch(packages)
    stale = packages / "torch-2.13.0.dist-info"
    stale.mkdir()
    (stale / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: torch\nVersion: 2.13.0\n",
        encoding="utf-8",
    )

    removed = torch_runtime_integrity.prune_stale_torch_metadata(packages)

    assert removed == 1
    assert not stale.exists()
    assert (packages / "torch-2.5.1+cu121.dist-info").is_dir()
    assert packages.joinpath("torch", "lib", "asmjit.dll").read_bytes() == b"active-cuda-dll"


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
