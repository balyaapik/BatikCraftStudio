# BatikCraft Project Archive Format

An editable project uses the `.batikcraft` extension. The file is a versioned ZIP
container. Opening a project never extracts its contents to the filesystem.

## Container Layout

```text
project.batikcraft
├── project.json
├── assets/
├── masks/
├── renders/
└── metadata/
```

Directories need no explicit ZIP entries. Only files listed in the manifest are allowed.

## Reserved Roots

Every asset lives under one of these roots:

| Root | Holds |
| --- | --- |
| `assets/` | Source objects, raster layers, primary visual data |
| `masks/` | Object masks and selection masks |
| `renders/` | Reproducible renders and internal previews |
| `metadata/` | Supplementary metadata such as AI generation parameters |

`project.json` is the only file permitted at the archive root.

## Canonical Path Rules

Archive paths use POSIX `/` separators and must already be canonical. These are all
rejected:

```text
../escape.png
/assets/absolute.png
assets\windows.png
assets//double.png
assets/./dot.png
C:/assets/file.png
other/file.png
```

Duplicate detection is case-insensitive, so a project does not break when it moves to a
Windows or macOS filesystem.

## Manifest

```json
{
  "format": "batikcraft-project",
  "schema_version": "1.1",
  "project": {
    "id": "4e894bf2-f2b1-4540-87b5-e376a2c46589",
    "metadata": {
      "title": "Flora Otomotif",
      "creator": "Balya Rochmadi",
      "description": "Experimental motif.",
      "tags": ["Batik", "Kontemporer"]
    },
    "canvas": {
      "width": 2048,
      "height": 2048,
      "background_color": "#F4E9D8"
    },
    "active_layer_id": null,
    "created_at": "2026-07-14T01:00:00+00:00",
    "updated_at": "2026-07-14T01:00:00+00:00",
    "revision": 0,
    "layers": []
  },
  "assets": [
    {
      "path": "assets/source.png",
      "size": 12345,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

The manifest schema is strict. A missing field or an unrecognised field is rejected, so
schema changes must go through a deliberate version migration. Projects written against
schema `1.0` are migrated to `1.1` on open.

## Layer Asset References

A layer's `asset_ref` must:

- be a canonical archive path;
- appear in the manifest `assets` list;
- exist as an actual ZIP member;
- pass both size and SHA-256 verification.

Assets no layer references may still be stored — masks and generation metadata, for
example.

## Integrity Limits

| Limit | Value |
| --- | --- |
| Archive members | 4,096 |
| `project.json` size | 2 MiB |
| Single asset size | 128 MiB |
| Total uncompressed data | 512 MiB |

Encrypted ZIP entries are unsupported, explicit directory entries are disallowed, and
any file not declared in the manifest is rejected. These limits are provisional and will
be revisited once production dataset and resolution needs are known.

## Atomic Save

1. Validate the domain, paths, assets, and manifest.
2. Write the ZIP to a temporary file in the destination directory.
3. Flush the file.
4. Swap the target into place with `os.replace`.
5. Mark the project revision as saved.

If writing or replacement fails, the previous target file is untouched, the temporary
file is cleaned up, and the project stays dirty. An interrupted save cannot destroy the
last good version.

## Public API

```python
from batikcraft_studio.persistence import ProjectArchive

ProjectArchive.save(
    "motif.batikcraft",
    project,
    {
        "assets/source.png": source_bytes,
        "masks/source-mask.png": mask_bytes,
    },
)

bundle = ProjectArchive.load("motif.batikcraft")
project = bundle.project
source_bytes = bundle.get_asset("assets/source.png")
```
