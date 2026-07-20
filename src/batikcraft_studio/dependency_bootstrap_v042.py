"""Release 0.4.2+ dependency-bootstrap corrections.

The frozen Windows installer keeps the selected Torch variant end-to-end, uses
an exclusive official Torch index for direct Torch installs, and protects an
already installed CUDA/CPU runtime while companion packages are added.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import site
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

from batikcraft_studio import dependency_bootstrap as _legacy
from batikcraft_studio.ai.torch_runtime_integrity import (
    installed_torch_variant,
    installed_torch_version,
    prune_stale_torch_metadata,
    purge_managed_torch_installation,
    requirement_requests_torch,
    validate_torch_variant,
)
from batikcraft_studio.ai.torch_wheel_index import (
    CPU_WHEEL_INDEX,
    CUDA_WHEEL_INDEX,
    nvidia_gpu_present,
)

INSTALL_FLAG = _legacy.INSTALL_FLAG
_TORCH_DEPENDENT_PACKAGES = {"accelerate", "peft"}


def _requirement_name(requirement: str) -> str:
    text = str(requirement).strip().casefold()
    return re.split(r"[<>=!~\[;\s]", text, maxsplit=1)[0].replace("_", "-")


def _requirements_need_existing_torch(requirements: Sequence[str]) -> bool:
    return any(_requirement_name(value) in _TORCH_DEPENDENT_PACKAGES for value in requirements)


def _resolved_torch_variant(
    requirements: Sequence[str], requested: str | None
) -> str | None:
    if not requirement_requests_torch(requirements):
        return None
    value = str(requested or "").strip().casefold()
    if value in {"cpu", "cuda"}:
        return value
    return "cuda" if nvidia_gpu_present() else "cpu"


def _torch_index_arguments(
    requirements: Sequence[str], requested: str | None
) -> list[str]:
    variant = _resolved_torch_variant(requirements, requested)
    if variant == "cuda":
        return ["--index-url", CUDA_WHEEL_INDEX]
    if variant == "cpu":
        return ["--index-url", CPU_WHEEL_INDEX]
    return []


def _torch_preservation_arguments(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path,
) -> tuple[list[str], str | None, str | None, int]:
    """Pin an existing Torch runtime while installing companion packages.

    ``pip install --target --upgrade`` replaces existing directories.  PEFT and
    Accelerate declare Torch as a dependency, so an unrestricted companion install
    may stage a newer CPU wheel and then try to delete loaded CUDA DLLs.  For a
    non-Torch request we constrain the resolver to the exact managed Torch version,
    add the matching official wheel index, and omit ``--upgrade`` later.
    """

    if requirement_requests_torch(requirements):
        return [], None, None, 0

    version = installed_torch_version(target)
    variant = installed_torch_variant(target)
    if not version or variant not in {"cpu", "cuda"}:
        return [], None, None, 0

    removed = 0
    try:
        removed = prune_stale_torch_metadata(target)
    except OSError:
        # Metadata cleanup is defensive.  The constraint still prevents selection
        # of a different Torch build even when an antivirus temporarily locks it.
        removed = 0

    cache_dir.mkdir(parents=True, exist_ok=True)
    constraint = cache_dir / "batikcraft-preserve-torch.txt"
    constraint.write_text(f"torch=={version}\n", encoding="utf-8")
    index = CUDA_WHEEL_INDEX if variant == "cuda" else CPU_WHEEL_INDEX
    return ["--constraint", str(constraint), "--extra-index-url", index], version, variant, removed


def _upgrade_arguments(preservation_arguments: Sequence[str]) -> list[str]:
    if preservation_arguments:
        return []
    return ["--upgrade", "--upgrade-strategy", "only-if-needed"]


def managed_ai_install_command(
    requirements: Iterable[str],
    *,
    target: str | Path | None = None,
    cache_dir: str | Path | None = None,
    executable: str | Path | None = None,
    frozen: bool | None = None,
    log_file: str | Path | None = None,
    torch_variant: str | None = None,
) -> list[str]:
    """Build a deterministic dependency-install command."""

    packages = [str(value).strip() for value in requirements if str(value).strip()]
    if not packages:
        raise ValueError("Daftar dependency AI kosong.")
    install_target = Path(target) if target is not None else _legacy.default_managed_ai_package_dir()
    install_target = install_target.expanduser().resolve()
    pip_cache = Path(cache_dir) if cache_dir is not None else _legacy.default_managed_pip_cache_dir()
    pip_cache = pip_cache.expanduser().resolve()
    launcher = str(executable or sys.executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    resolved_variant = _resolved_torch_variant(packages, torch_variant)

    if is_frozen:
        command = [
            launcher,
            INSTALL_FLAG,
            "--target",
            str(install_target),
            "--cache-dir",
            str(pip_cache),
        ]
        if log_file is not None:
            command.extend(["--log-file", str(Path(log_file).expanduser().resolve())])
        if resolved_variant is not None:
            command.extend(["--torch-variant", resolved_variant])
        command.extend(["--", *packages])
        return command

    preservation, _, _, _ = _torch_preservation_arguments(
        packages,
        target=install_target,
        cache_dir=pip_cache,
    )
    return [
        launcher,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        *_upgrade_arguments(preservation),
        "--prefer-binary",
        "--progress-bar",
        "raw",
        "--cache-dir",
        str(pip_cache),
        "--target",
        str(install_target),
        *preservation,
        *_torch_index_arguments(packages, resolved_variant),
        *packages,
    ]


def maybe_run_dependency_installer(argv: Sequence[str] | None = None) -> int | None:
    """Run the corrected hidden installer before the GUI is imported."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != INSTALL_FLAG:
        return None

    parser = argparse.ArgumentParser(prog="BatikCraftStudio AI dependency installer")
    parser.add_argument(INSTALL_FLAG, action="store_true")
    parser.add_argument("--target", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--log-file")
    parser.add_argument("--torch-variant", choices=("cpu", "cuda"))
    parser.add_argument("requirements", nargs=argparse.REMAINDER)
    namespace = parser.parse_args(arguments)
    requirements = list(namespace.requirements)
    if requirements and requirements[0] == "--":
        requirements.pop(0)
    if not requirements:
        parser.error("setidaknya satu dependency diperlukan")

    target = Path(namespace.target).expanduser().resolve()
    cache_dir = Path(namespace.cache_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if namespace.log_file:
        log_path = Path(namespace.log_file).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace", buffering=1) as stream:
            return _run_with_redirected_output(
                requirements,
                target=target,
                cache_dir=cache_dir,
                torch_variant=namespace.torch_variant,
                stream=stream,
            )
    return _dispatch_bundled_install(
        requirements,
        target=target,
        cache_dir=cache_dir,
        torch_variant=namespace.torch_variant,
    )


def _dispatch_bundled_install(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path,
    torch_variant: str | None,
) -> int:
    """Dispatch through the established bootstrap seam used by tests and plugins."""

    kwargs: dict[str, object] = {"target": target, "cache_dir": cache_dir}
    if torch_variant is not None:
        kwargs["torch_variant"] = torch_variant
    return int(_legacy.run_bundled_pip_install(requirements, **kwargs))


def _run_with_redirected_output(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path,
    torch_variant: str | None,
    stream: TextIO,
) -> int:
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        return _dispatch_bundled_install(
            requirements,
            target=target,
            cache_dir=cache_dir,
            torch_variant=torch_variant,
        )


def run_bundled_pip_install(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path | None = None,
    torch_variant: str | None = None,
) -> int:
    """Install packages through bundled pip and verify a requested Torch wheel."""

    _legacy._register_distlib_frozen_resource_finder()
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        print(
            "Installer dependency internal tidak tersedia pada build ini. "
            "Unduh release BatikCraft Studio terbaru.",
            file=sys.stderr,
        )
        return 2

    packages = [str(value).strip() for value in requirements if str(value).strip()]
    resolved_variant = _resolved_torch_variant(packages, torch_variant)
    target = Path(target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    resolved_cache = cache_dir or _legacy.default_managed_pip_cache_dir()
    resolved_cache = Path(resolved_cache).expanduser().resolve()
    resolved_cache.mkdir(parents=True, exist_ok=True)

    if (
        resolved_variant is None
        and _requirements_need_existing_torch(packages)
        and installed_torch_version(target) is None
    ):
        print(
            "PyTorch belum terpasang. Pasang PyTorch GPU (CUDA) atau PyTorch CPU "
            "terlebih dahulu sebelum Accelerate/PEFT.",
            file=sys.stderr,
        )
        return 3

    if resolved_variant is not None:
        removed = purge_managed_torch_installation(target)
        print(
            f"Membersihkan runtime PyTorch lama: {removed} path dihapus; "
            f"memasang varian {resolved_variant.upper()}.",
            flush=True,
        )

    preservation, preserved_version, preserved_variant, stale_removed = (
        _torch_preservation_arguments(
            packages,
            target=target,
            cache_dir=resolved_cache,
        )
    )
    if preservation:
        print(
            "Mempertahankan runtime PyTorch "
            f"{preserved_version} ({str(preserved_variant).upper()}); "
            "paket pendamping tidak diizinkan mengganti torch atau DLL aktif.",
            flush=True,
        )
        if stale_removed:
            print(
                f"Membersihkan metadata Torch gagal sebelumnya: {stale_removed} path dihapus.",
                flush=True,
            )

    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)
    site.addsitedir(target_text)
    previous_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = (
        target_text if not previous_pythonpath else target_text + os.pathsep + previous_pythonpath
    )

    arguments = [
        "install",
        "--disable-pip-version-check",
        "--no-input",
        *_upgrade_arguments(preservation),
        "--prefer-binary",
        "--progress-bar",
        "raw",
        "--cache-dir",
        str(resolved_cache),
        "--target",
        target_text,
        *preservation,
        *_torch_index_arguments(packages, resolved_variant),
        *packages,
    ]
    try:
        code = int(pip_main(arguments))
        if code == 0 and resolved_variant is not None:
            version = validate_torch_variant(target, resolved_variant)
            print(
                f"Verifikasi PyTorch berhasil: {version} ({resolved_variant.upper()}).",
                flush=True,
            )
        if code == 0 and preservation and preserved_variant is not None:
            version = validate_torch_variant(target, preserved_variant)
            print(
                f"PyTorch tetap terlindungi: {version} ({preserved_variant.upper()}).",
                flush=True,
            )
        return code
    except Exception as exc:  # noqa: BLE001 - detail harus masuk log GUI
        print(f"Installer dependency AI gagal: {exc}", file=sys.stderr)
        return 1
    finally:
        if previous_pythonpath:
            os.environ["PYTHONPATH"] = previous_pythonpath
        else:
            os.environ.pop("PYTHONPATH", None)


def install_dependency_bootstrap_v042() -> None:
    """Expose corrected functions through the legacy import location."""

    _legacy.managed_ai_install_command = managed_ai_install_command
    _legacy.maybe_run_dependency_installer = maybe_run_dependency_installer
    _legacy.run_bundled_pip_install = run_bundled_pip_install


__all__ = [
    "install_dependency_bootstrap_v042",
    "managed_ai_install_command",
    "maybe_run_dependency_installer",
    "run_bundled_pip_install",
]
