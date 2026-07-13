"""Path rules shared by BatikCraft archive readers and writers."""

from __future__ import annotations

from pathlib import PurePosixPath

from batikcraft_studio.persistence.errors import UnsafeArchivePathError

MANIFEST_PATH = "project.json"
RESERVED_ROOTS = frozenset({"assets", "masks", "renders", "metadata"})


def normalize_archive_path(value: str, *, allow_manifest: bool = False) -> str:
    """Return a canonical POSIX member path or reject unsafe input.

    Archive paths are logical paths, never native filesystem paths. Backslashes,
    absolute paths, empty segments, ``.`` and ``..`` are rejected so a future
    extractor cannot accidentally write outside its destination.
    """

    if not isinstance(value, str):
        raise UnsafeArchivePathError("Archive path must be a string.")
    if not value or value != value.strip():
        raise UnsafeArchivePathError("Archive path must not be blank or padded.")
    if "\\" in value or "\x00" in value:
        raise UnsafeArchivePathError("Archive path contains a forbidden character.")
    if value.endswith("/"):
        raise UnsafeArchivePathError("Archive file paths must not end with '/'.")

    path = PurePosixPath(value)
    parts = path.parts
    if path.is_absolute() or not parts:
        raise UnsafeArchivePathError("Archive path must be relative.")
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafeArchivePathError("Archive path contains an unsafe segment.")
    if ":" in parts[0]:
        raise UnsafeArchivePathError("Archive path must not contain a drive prefix.")

    normalized = path.as_posix()
    if normalized != value:
        raise UnsafeArchivePathError("Archive path must already be canonical POSIX form.")
    if allow_manifest and normalized == MANIFEST_PATH:
        return normalized
    if len(parts) < 2 or parts[0] not in RESERVED_ROOTS:
        roots = ", ".join(sorted(RESERVED_ROOTS))
        raise UnsafeArchivePathError(
            f"Archive assets must be stored below one of: {roots}."
        )
    return normalized
