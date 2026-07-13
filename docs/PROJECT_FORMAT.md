# BatikCraft Project Archive Format

Milestone 2B memperkenalkan format proyek editable dengan ekstensi:

```text
.batikcraft
```

File tersebut merupakan container ZIP versioned. API persistence tidak mengekstrak isinya ke filesystem ketika membuka proyek.

## Struktur Container

```text
project.batikcraft
├── project.json
├── assets/
│   └── ...
├── masks/
│   └── ...
├── renders/
│   └── ...
└── metadata/
    └── ...
```

Folder tidak perlu memiliki directory entry tersendiri di ZIP. Hanya file yang tercantum dalam manifest yang diperbolehkan.

## Reserved Roots

Aset harus berada di bawah salah satu root berikut:

- `assets/` — objek sumber, raster layer, atau data visual utama;
- `masks/` — object mask dan selection mask;
- `renders/` — hasil render yang dapat dibuat ulang atau preview internal;
- `metadata/` — metadata tambahan seperti parameter generasi AI.

`project.json` adalah satu-satunya file yang diperbolehkan di root archive.

## Canonical Path Rules

Semua path archive menggunakan POSIX `/` dan harus sudah canonical.

Path berikut ditolak:

```text
../escape.png
/assets/absolute.png
assets\windows.png
assets//double.png
assets/./dot.png
C:/assets/file.png
other/file.png
```

Perbandingan duplicate entry dilakukan secara case-insensitive untuk menghindari konflik ketika proyek dipindahkan ke filesystem Windows atau macOS.

## Manifest

Contoh ringkas:

```json
{
  "format": "batikcraft-project",
  "schema_version": "1.0",
  "project": {
    "id": "4e894bf2-f2b1-4540-87b5-e376a2c46589",
    "metadata": {
      "title": "Flora Otomotif",
      "creator": "Balya Rochmadi",
      "description": "Motif eksperimental.",
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

Manifest memakai field yang ketat. Field hilang atau field yang belum dikenal ditolak agar perubahan schema harus dilakukan secara sadar melalui migrasi versi.

## Layer Asset References

`asset_ref` pada layer:

- harus berupa path archive canonical;
- harus tercantum pada `assets` manifest;
- harus benar-benar tersedia sebagai member ZIP;
- harus lolos verifikasi size dan SHA-256.

Aset yang tidak dipakai layer tetap dapat disimpan, misalnya mask atau metadata generasi.

## Integrity and Limits

Reader menerapkan batas awal:

- maksimal 4.096 member archive;
- maksimal 2 MiB untuk `project.json`;
- maksimal 128 MiB per asset;
- maksimal 512 MiB total data tidak terkompresi;
- encrypted ZIP entry tidak didukung;
- directory entry eksplisit tidak diperbolehkan;
- file yang tidak dideklarasikan manifest ditolak.

Batas ini dapat dievaluasi kembali ketika kebutuhan dataset dan resolusi produksi sudah diketahui.

## Atomic Save

Save dilakukan dengan urutan:

1. validasi domain, path, asset, dan manifest;
2. tulis ZIP ke temporary file pada direktori tujuan;
3. flush file;
4. ganti target menggunakan `os.replace`;
5. tandai revision proyek sebagai saved.

Jika penulisan atau replacement gagal:

- file target lama tidak diubah;
- temporary file dibersihkan;
- proyek tetap berstatus dirty.

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

GUI file dialog dan recent-project integration menjadi scope Milestone 2C.
