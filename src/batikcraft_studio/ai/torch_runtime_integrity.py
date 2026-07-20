"""Inspect and safely replace the app-managed PyTorch runtime.

The dependency centre installs packages into a private ``site-packages`` folder.
Switching between CPU and CUDA wheels must remove the previous wheel completely;
otherwise stale Python modules or DLLs can make a CPU build look like CUDA (or the
reverse) and can crash native inference.
"""

from __future__ import annotations

import importlib
import re
import shutil
from collections.abc import Iterable
from pathlib import Path

_TORCH_PACKAGE_DIRS = ("torch", "functorch", "torchgen")
_TORCH_METADATA_GLOBS = (
    "torch-*.dist-info",
    "functorch-*.dist-info",
    "torchgen-*.dist-info",
)


def requirement_requests_torch(requirements: Iterable[str]) -> bool:
    """Return ``True`` when a pip requirement directly installs ``torch``."""

    for requirement in requirements:
        text = str(requirement).strip().casefold()
        name = re.split(r"[<>=!~\[;\s]", text, maxsplit=1)[0]
        if name == "torch":
            return True
    return False


def installed_torch_version(target: str | Path) -> str | None:
    """Read the managed Torch version without importing native Torch DLLs."""

    root = Path(target).expanduser().resolve()
    version_file = root / "torch" / "version.py"
    try:
        content = version_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        return match.group(1)

    for metadata in root.glob("torch-*.dist-info"):
        stem = metadata.name[: -len(".dist-info")]
        if "-" in stem:
            return stem.split("-", 1)[1]
    return None


def installed_torch_variant(target: str | Path) -> str | None:
    """Return ``cuda``, ``cpu``, or ``None`` for the managed Torch wheel."""

    root = Path(target).expanduser().resolve()
    if not (root / "torch").is_dir():
        return None

    version = (installed_torch_version(root) or "").casefold()
    if "+cu" in version or "+rocm" in version:
        return "cuda"
    if "+cpu" in version:
        return "cpu"

    version_file = root / "torch" / "version.py"
    try:
        content = version_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    cuda_line = re.search(r"^cuda\s*[:=][^\n]*", content, re.MULTILINE)
    if cuda_line and "none" not in cuda_line.group(0).casefold():
        return "cuda"

    for metadata in root.glob("torch-*.dist-info"):
        name = metadata.name.casefold()
        if "+cu" in name or "+rocm" in name:
            return "cuda"
        if "+cpu" in name:
            return "cpu"
    return "cpu"


def purge_managed_torch_installation(target: str | Path) -> int:
    """Remove the previous managed Torch wheel before changing variants."""

    root = Path(target).expanduser().resolve()
    if not root.exists():
        return 0

    removed = 0
    for name in _TORCH_PACKAGE_DIRS:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
            removed += 1
        elif path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
    for pattern in _TORCH_METADATA_GLOBS:
        for path in root.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=False)
            else:
                path.unlink(missing_ok=True)
            removed += 1
    importlib.invalidate_caches()
    return removed


def validate_torch_variant(target: str | Path, expected: str) -> str:
    """Verify the installed wheel and return its version string."""

    wanted = str(expected).strip().casefold()
    if wanted not in {"cpu", "cuda"}:
        raise ValueError("Varian Torch harus cpu atau cuda.")
    actual = installed_torch_variant(target)
    version = installed_torch_version(target) or "tidak diketahui"
    if actual != wanted:
        raise RuntimeError(
            "Verifikasi PyTorch gagal: diminta "
            f"{wanted.upper()}, tetapi runtime yang terpasang adalah "
            f"{(actual or 'tidak ada').upper()} ({version})."
        )
    return version


__all__ = [
    "installed_torch_variant",
    "installed_torch_version",
    "purge_managed_torch_installation",
    "requirement_requests_torch",
    "validate_torch_variant",
]
