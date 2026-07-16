# BatikCraft NFT package (`.batikcraftnft`)

A `.batikcraftnft` file is a ZIP-compatible, checksummed interchange package for
moving a finished BatikCraft artwork from the desktop application to a future
showcase and bidding website.

## User flow

1. Finish the editable project in BatikCraft Studio.
2. Choose **File → Export As → BatikCraft NFT Package**.
3. Enter the website creator ID, artwork philosophy, motifs, colors, and license.
4. Upload the resulting `.batikcraftnft` file to the marketplace.
5. The website must verify the full package before creating a listing.
6. The authenticated uploader ID must equal `identity.creator.user_id`.

The marketplace listing may then expose the preview, creator identity, philosophy,
motifs, colors, tags, canvas information, and package ID to buyers and bidders.

## Archive layout

```text
manifest.json
seal.json
preview.jpg
project/project.json
project/assets/...
project/masks/...
project/metadata/...
```

`project/project.json` is the complete editable BatikCraft project manifest. Every
embedded project asset is stored below `project/` with its original relative path.

## Integrity model

Every payload file has a SHA-256 record containing:

```json
{
  "path": "preview.jpg",
  "role": "preview",
  "size": 12345,
  "sha256": "..."
}
```

The sorted file records produce `payload_root_sha256`. The immutable identity and
payload root produce `package_id`. Finally, `seal.json` stores the SHA-256 of the
complete `manifest.json`.

Validation fails when any of these change:

- creator website ID or display name;
- project UUID, title, or creation timestamp;
- philosophy, motifs, colors, tags, license, or canvas metadata;
- preview pixels;
- editable project structure;
- any embedded raster, mask, or generation metadata asset.

The package also checks that locked identity values match the embedded project.

## Important security boundary

SHA-256 detects modification to an existing package, but it is not a digital
signature. A technically capable party could rebuild a new package and recompute
all checksums. The marketplace should therefore retain the first accepted
`package_id`, bind it to the authenticated account, record upload time, and reject
conflicting ownership claims.

A future schema may add an Ed25519 signature and public-key creator identity. The
current manifest explicitly declares `digital_signature: false` so the website can
distinguish checksum-only packages from signed packages.

## Recommended marketplace validation

Before accepting an upload, the web service should:

1. enforce archive size and entry-count limits;
2. reject path traversal, duplicate paths, directory entries, and encrypted files;
3. verify `seal.json` against `manifest.json`;
4. verify every payload file size and SHA-256;
5. recompute `payload_root_sha256` and `package_id`;
6. validate the embedded BatikCraft project manifest and its asset checksums;
7. verify locked identity against the embedded project;
8. require the authenticated user ID to match `identity.creator.user_id`;
9. store the original package unchanged in immutable object storage;
10. use the verified `preview.jpg` for showcase and bidding pages.

The Python reference verifier is:

```python
from batikcraft_studio.persistence import load_batikcraft_nft

bundle = load_batikcraft_nft("artwork.batikcraftnft")
print(bundle.package_id)
print(bundle.manifest["identity"])
```
