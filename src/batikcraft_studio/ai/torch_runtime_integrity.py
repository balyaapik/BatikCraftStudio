"""Inspect and safely replace the app-managed PyTorch runtime.

The dependency centre installs packages into a private ``site-packages`` folder.
Switching between CPU and CUDA wheels must remove the previous wheel completely;
otherwise stale Python modules or DLLs can make a CPU build look like CUDA (or the
reverse) and can crash native inference.
"""

from __future__ import annotations

import csv
import importlib
import re
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

_TORCH_PACKAGE_DIRS = ("torch", "functorch", "torchgen")
_TORCH_METADATA_GLOBS = (
    "torch-*.dist-info",
    "functorch-*.dist-info",
    "torchgen-*.dist-info",
)
_REQUIRED_TORCH_FILES = (
    "torch/__init__.py",
    "torch/version.py",
    "torch/amp/__init__.py",
    "torch/cuda/__init__.py",
)
_CRITICAL_RECORD_PREFIXES = (
    "torch/amp/",
    "torch/cuda/",
    "torch/lib/",
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


def _dist_info_version(path: Path) -> str | None:
    metadata_file = path / "METADATA"
    try:
        content = metadata_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    match = re.search(r"^Version:\s*(\S+)\s*$", content, re.MULTILINE | re.IGNORECASE)
    if match:
        return match.group(1)

    stem = path.name[: -len(".dist-info")] if path.name.endswith(".dist-info") else path.name
    if "-" in stem:
        return stem.split("-", 1)[1]
    return None


def _matching_torch_metadata(root: Path, version: str | None) -> Path | None:
    candidates = tuple(root.glob("torch-*.dist-info"))
    if version:
        for candidate in candidates:
            if _dist_info_version(candidate) == version:
                return candidate
    return candidates[0] if len(candidates) == 1 else None


def _critical_record_entry(name: str) -> bool:
    normalized = name.replace("\\", "/").lstrip("./")
    if normalized in _REQUIRED_TORCH_FILES:
        return True
    if normalized.startswith(_CRITICAL_RECORD_PREFIXES):
        return not normalized.endswith((".pyc", "/"))
    return normalized.startswith("torch/_C")


def inspect_torch_runtime(target: str | Path) -> list[str]:
    """Return concrete integrity problems without importing Torch.

    Reading only ``torch/version.py`` is insufficient: a failed ``pip --target``
    replacement can leave that file and the CUDA DLL directory while deleting Python
    modules such as ``torch.amp``. Such a mixed wheel was previously reported as
    installed even though ``import torch`` failed with a circular-import message.
    """

    root = Path(target).expanduser().resolve()
    torch_dir = root / "torch"
    issues: list[str] = []
    if not torch_dir.is_dir():
        return [f"Folder paket PyTorch tidak ditemukan: {torch_dir}"]

    for relative in _REQUIRED_TORCH_FILES:
        path = root / relative
        if not path.is_file():
            issues.append(f"File PyTorch hilang: {relative}")
        else:
            try:
                if path.stat().st_size <= 0:
                    issues.append(f"File PyTorch kosong: {relative}")
            except OSError as exc:
                issues.append(f"File PyTorch tidak dapat dibaca: {relative} ({exc})")

    native_extensions = [*torch_dir.glob("_C*.pyd"), *torch_dir.glob("_C*.so")]
    if not any(path.is_file() and path.stat().st_size > 0 for path in native_extensions):
        issues.append("Ekstensi native torch._C tidak ditemukan atau kosong.")

    lib_dir = torch_dir / "lib"
    if sys.platform == "win32":
        dlls = tuple(lib_dir.glob("*.dll")) if lib_dir.is_dir() else ()
        if not dlls:
            issues.append("DLL PyTorch tidak ditemukan di torch/lib.")
        elif not any(path.name.casefold() == "asmjit.dll" for path in dlls):
            issues.append("DLL penting PyTorch asmjit.dll tidak ditemukan.")

    version = installed_torch_version(root)
    if not version:
        issues.append("Versi PyTorch tidak dapat dibaca.")
    metadata = _matching_torch_metadata(root, version)
    if metadata is None:
        issues.append("Metadata wheel torch yang cocok tidak ditemukan.")
        return issues

    record = metadata / "RECORD"
    if not record.is_file():
        issues.append(f"Inventaris wheel PyTorch tidak ditemukan: {record.name}")
        return issues

    missing_from_record: list[str] = []
    damaged_from_record: list[str] = []
    try:
        with record.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            for row in csv.reader(stream):
                if not row or not _critical_record_entry(row[0]):
                    continue
                relative = row[0].replace("\\", "/").lstrip("./")
                path = root / Path(relative)
                if not path.is_file():
                    missing_from_record.append(relative)
                    continue
                if len(row) >= 3 and row[2].isdigit():
                    try:
                        if path.stat().st_size != int(row[2]):
                            damaged_from_record.append(relative)
                    except OSError:
                        damaged_from_record.append(relative)
    except OSError as exc:
        issues.append(f"Inventaris wheel PyTorch tidak dapat dibaca: {exc}")
        return issues

    if missing_from_record:
        preview = ", ".join(missing_from_record[:4])
        issues.append(
            f"{len(missing_from_record)} file penting PyTorch hilang menurut RECORD: {preview}"
        )
    if damaged_from_record:
        preview = ", ".join(damaged_from_record[:4])
        issues.append(
            f"{len(damaged_from_record)} file penting PyTorch tidak utuh: {preview}"
        )
    return issues


def clear_failed_torch_imports() -> int:
    """Remove only unusable/partial Torch modules left by a failed import."""

    module = sys.modules.get("torch")
    if module is not None and all(
        hasattr(module, attribute) for attribute in ("Tensor", "_C", "amp", "__version__")
    ):
        return 0

    names = [name for name in sys.modules if name == "torch" or name.startswith("torch.")]
    for name in names:
        sys.modules.pop(name, None)
    if names:
        importlib.invalidate_caches()
    return len(names)


def prune_stale_torch_metadata(target: str | Path) -> int:
    """Remove stale Torch metadata without touching loaded native DLLs.

    A failed ``pip --target --upgrade`` can copy metadata for a newer CPU wheel before
    Windows rejects deletion of the active CUDA ``torch`` directory. The Python package
    remains the original runtime, but duplicate ``torch-*.dist-info`` directories can
    confuse later dependency resolution. Only metadata whose version differs from the
    actual ``torch/version.py`` runtime is removed here.
    """

    root = Path(target).expanduser().resolve()
    current = installed_torch_version(root)
    if not current:
        return 0

    removed = 0
    for path in root.glob("torch-*.dist-info"):
        if _dist_info_version(path) == current:
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink(missing_ok=True)
        removed += 1
    if removed:
        importlib.invalidate_caches()
    return removed


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
    clear_failed_torch_imports()
    importlib.invalidate_caches()
    return removed


def validate_torch_variant(target: str | Path, expected: str) -> str:
    """Verify the installed wheel variant and, when available, its wheel inventory."""

    wanted = str(expected).strip().casefold()
    if wanted not in {"cpu", "cuda"}:
        raise ValueError("Varian Torch harus cpu atau cuda.")
    root = Path(target).expanduser().resolve()
    actual = installed_torch_variant(root)
    version = installed_torch_version(root) or "tidak diketahui"
    if actual != wanted:
        raise RuntimeError(
            "Verifikasi PyTorch gagal: diminta "
            f"{wanted.upper()}, tetapi runtime yang terpasang adalah "
            f"{(actual or 'tidak ada').upper()} ({version})."
        )

    # Wheel pip nyata selalu membawa RECORD. Fixture/integrasi lama yang hanya menguji
    # deteksi varian tidak memilikinya, sehingga tetap kompatibel; status GUI tetap
    # memanggil inspect_torch_runtime() secara langsung dan fail-closed.
    metadata = _matching_torch_metadata(root, version)
    if metadata is None or not (metadata / "RECORD").is_file():
        return version

    issues = inspect_torch_runtime(root)
    if issues:
        details = "; ".join(issues[:5])
        raise RuntimeError(
            "Verifikasi PyTorch gagal karena instalasi tidak lengkap atau tercampur: "
            + details
        )
    return version


__all__ = [
    "clear_failed_torch_imports",
    "inspect_torch_runtime",
    "installed_torch_variant",
    "installed_torch_version",
    "prune_stale_torch_metadata",
    "purge_managed_torch_installation",
    "requirement_requests_torch",
    "validate_torch_variant",
]
