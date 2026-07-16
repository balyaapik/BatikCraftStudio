"""Public persistence API for BatikCraft project and marketplace archives."""

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
from batikcraft_studio.persistence.nft_package import (
    BATIKCRAFT_NFT_EXTENSION,
    BATIKCRAFT_NFT_FORMAT,
    BATIKCRAFT_NFT_SCHEMA_VERSION,
    BatikNFTBundle,
    BatikNFTError,
    BatikNFTIntegrityError,
    NFTExportMetadata,
    export_batikcraft_nft,
    load_batikcraft_nft,
)

__all__ = [
    "BATIKCRAFT_NFT_EXTENSION",
    "BATIKCRAFT_NFT_FORMAT",
    "BATIKCRAFT_NFT_SCHEMA_VERSION",
    "PROJECT_EXTENSION",
    "ArchiveOpenError",
    "ArchiveSaveError",
    "ArchiveValidationError",
    "AssetIntegrityError",
    "AssetRecord",
    "BatikNFTBundle",
    "BatikNFTError",
    "BatikNFTIntegrityError",
    "CorruptArchiveError",
    "DuplicateArchiveEntryError",
    "MissingAssetError",
    "MissingManifestError",
    "NFTExportMetadata",
    "ProjectArchive",
    "ProjectArchiveError",
    "ProjectBundle",
    "UnsafeArchivePathError",
    "UnsupportedSchemaVersionError",
    "export_batikcraft_nft",
    "load_batikcraft_nft",
]
