"""Persistence-specific errors for BatikCraft project archives."""


class ProjectArchiveError(Exception):
    """Base class for project archive failures."""


class ArchiveValidationError(ProjectArchiveError, ValueError):
    """Raised when archive input or manifest data violates the format contract."""


class ArchiveSaveError(ProjectArchiveError, OSError):
    """Raised when an archive cannot be written or atomically replaced."""


class CorruptArchiveError(ProjectArchiveError):
    """Raised when a file is not a readable, trustworthy ZIP archive."""


class MissingManifestError(CorruptArchiveError):
    """Raised when ``project.json`` is absent from an archive."""


class UnsupportedSchemaVersionError(ArchiveValidationError):
    """Raised when the archive uses a schema version this application cannot read."""


class UnsafeArchivePathError(ArchiveValidationError):
    """Raised when an archive member could escape the logical project root."""


class DuplicateArchiveEntryError(ArchiveValidationError):
    """Raised when archive paths collide, including case-insensitive collisions."""


class MissingAssetError(ArchiveValidationError):
    """Raised when a layer or manifest references an unavailable asset."""


class AssetIntegrityError(CorruptArchiveError):
    """Raised when an asset size or SHA-256 digest does not match its manifest."""
