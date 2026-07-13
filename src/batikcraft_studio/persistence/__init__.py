"""Public persistence API for BatikCraft project archives."""

from batikcraft_studio.persistence.archive import (
    PROJECT_EXTENSION,
    ProjectArchive,
    ProjectBundle,
)
from batikcraft_studio.persistence.errors import (
    ArchiveOpenError,
    ArchiveSaveError,
    ArchiveValidationError,
    AssetIntegrityError,
    CorruptArchiveError,
    DuplicateArchiveEntryError,
    MissingAssetError,
    MissingManifestError,
    ProjectArchiveError,
    UnsafeArchivePathError,
    UnsupportedSchemaVersionError,
)
from batikcraft_studio.persistence.manifest import AssetRecord

__all__ = [
    "PROJECT_EXTENSION",
    "ArchiveOpenError",
    "ArchiveSaveError",
    "ArchiveValidationError",
    "AssetIntegrityError",
    "AssetRecord",
    "CorruptArchiveError",
    "DuplicateArchiveEntryError",
    "MissingAssetError",
    "MissingManifestError",
    "ProjectArchive",
    "ProjectArchiveError",
    "ProjectBundle",
    "UnsafeArchivePathError",
    "UnsupportedSchemaVersionError",
]
