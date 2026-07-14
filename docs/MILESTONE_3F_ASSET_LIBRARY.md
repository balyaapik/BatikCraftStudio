# Milestone 3F — Pustaka Asset dan UI Ringkas

Milestone ini mengubah BatikCraft Studio menjadi aplikasi **asset-first**. Asset hasil
kurasi atau ekstraksi dataset dipasang satu kali sebagai asset pack, lalu dapat dipakai
berulang kali pada banyak proyek.

## Layout utama

Editor hanya menampilkan tiga area permanen:

```text
Pustaka Asset | Canvas | Susunan Lapis
```

Pengaturan Brush, Eraser, Shape, Cap Motif, Cap Isen, Transform, Metadata, dan Humanize
dibuka dari menu bar sebagai jendela kecil. Tidak ada lagi tab Brush/Shape/Batik/Asset
yang memenuhi dock kanan.

## Lokasi library

Paket terpasang disimpan di folder user, bukan di repository atau file project.

Windows:

```text
%LOCALAPPDATA%\BatikCraftStudio\asset-library
```

Linux:

```text
$XDG_DATA_HOME/BatikCraftStudio/asset-library
```

Lokasi dapat dioverride untuk testing/deployment menggunakan environment variable:

```text
BATIKCRAFT_ASSET_LIBRARY
```

## Mengapa asset berada di luar `.batikcraft`

Satu pack dapat memiliki ribuan asset. Menyalin semuanya ke setiap project akan:

- membuat project sangat besar;
- memperlambat save/open;
- menduplikasi asset yang sama berkali-kali;
- menyulitkan update pack.

Karena itu asset library bersifat global per-user. Hanya asset yang benar-benar
ditempatkan pada canvas yang disalin ke project sebagai object asset.

## Format `.batikpack`

`.batikpack` adalah ZIP dengan struktur:

```text
manifest.json
assets/
  kawung-001.batikasset
  kawung-002.batikasset
thumbnails/
  kawung-001.png
  kawung-002.png
```

Manifest minimal:

```json
{
  "format": "batikcraft-asset-pack",
  "schema_version": "1.0",
  "pack": {
    "id": "batik-jawa-v1",
    "name": "Batik Jawa Curated",
    "version": "1.0.0",
    "author": "Balya Rochmadi",
    "description": "Motif dan isen hasil kurasi dataset"
  },
  "assets": [
    {
      "id": "kawung-001",
      "name": "Kawung 001",
      "category": "motif-pokok",
      "file": "assets/kawung-001.batikasset",
      "thumbnail": "thumbnails/kawung-001.png",
      "tags": ["kawung", "geometris", "jawa"],
      "width": 1024,
      "height": 1024,
      "metadata": {
        "source": "dataset",
        "source_index": 1
      }
    }
  ]
}
```

Kategori yang didukung:

- `motif-pokok`;
- `isen-isen`;
- `ornamen`;
- `tekstur`;
- `lainnya`.

## Validasi instalasi

Installer pack memeriksa:

- format dan schema manifest;
- ID pack dan asset;
- kategori;
- duplicate ID/file;
- path traversal;
- jumlah file;
- ukuran manifest dan asset;
- keberadaan file asset/thumbnail;
- apakah PNG atau `.batikasset` dapat dibaca.

Instalasi dilakukan melalui staging directory. Pack lama dipindahkan ke backup sebelum
replace, sehingga kegagalan tidak meninggalkan instalasi setengah jadi.

## Workflow pengguna

1. Buka menu **Asset → Install Asset Pack…**.
2. Pilih file `.batikpack`.
3. Cari asset berdasarkan nama, ID, kategori, atau tag.
4. Filter berdasarkan pack atau kategori.
5. Klik asset untuk melihat preview.
6. Double-click atau klik ikon Add untuk menambah asset ke sublapis aktif.
7. Atur posisi, rotasi, skala, opacity, metadata, atau humanize.

Asset dapat dihapus dari library melalui filter pack kemudian **Remove Selected Pack**.
Objek yang sudah disalin ke project tetap ada karena project menyimpan byte assetnya
sendiri.

## Menu gambar

Menu **Draw** membuka jendela kecil:

- Brush;
- Eraser;
- Line;
- Rectangle;
- Ellipse;
- Polygon;
- Cap Motif;
- Cap Isen-Isen.

Tombol **Aktifkan** menutup sementara dialog dan mengembalikan fokus ke canvas. Nilai
setting tetap tersimpan pada editor selama aplikasi berjalan.

## Skalabilitas

Index pack dibaca dari manifest, bukan dengan membuka semua PNG saat startup. Preview
hanya didekode untuk asset yang sedang dipilih. Hasil pencarian UI dibatasi 5.000 item
per tampilan agar Treeview tetap responsif, tetapi seluruh asset tetap tersimpan dan
dapat dicari melalui filter.

## Tahap berikutnya

Notebook Kaggle akan menghasilkan struktur pack ini secara langsung:

```text
dataset batik
→ segmentasi/crop kandidat
→ pembersihan alpha
→ klasifikasi kategori
→ metadata dan tags
→ thumbnail
→ .batikasset
→ manifest.json
→ .batikpack
```
