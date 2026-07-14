# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk
merakit, menggambar, dan menyunting motif batik dari pustaka asset offline yang dapat
dikembangkan dari dataset Kaggle.

> Status: Milestone 3F — Pustaka Asset dan UI Ringkas.

## Fokus Produk

Aplikasi desktop menangani proses penciptaan motif:

- memasang pustaka Motif Pokok, Isen-Isen, ornamen, tekstur, dan asset custom;
- mencari serta menggabungkan banyak asset menjadi komposisi baru;
- mengelola Folder, Subfolder, Sublapis, dan banyak objek dalam satu lapis;
- mengubah posisi, ukuran, rotasi, opacity, susunan, metadata, dan humanize;
- menggambar dengan Brush, Eraser, Shape, Cap Motif, dan Cap Isen bila diperlukan;
- menyimpan proyek editable;
- menyiapkan asset final untuk pattern, AI, publikasi, dan lisensi.

Bidding, transaksi, dan pengelolaan lisensi dilakukan di website BatikCraft.

## Layout Editor

Editor utama hanya memiliki tiga area permanen:

```text
Pustaka Asset | Canvas | Susunan Lapis
```

Pengaturan menggambar tidak lagi memenuhi dock dengan tab. Menu **Draw**, **Edit**, dan
**Asset** membuka jendela kecil yang hanya tampil ketika diperlukan.

## Fitur yang Sudah Berfungsi

- shell Tkinter native dengan toolbar ikon offline dan menu bar;
- format proyek `.batikcraft` berbasis ZIP dengan validasi integritas;
- format asset portable `.batikasset`;
- format pustaka `.batikpack` dengan manifest, tags, kategori, thumbnail, dan version;
- install/replace/uninstall pack secara atomik;
- pencarian serta filter asset berdasarkan nama, ID, tag, kategori, dan pack;
- preview asset dan double-click untuk menempatkan asset pada canvas;
- asset library global per-user, sehingga ribuan asset tidak disalin ke setiap proyek;
- renderer Pillow untuk raster, shape, paint object, motif, dan isen;
- Folder, Subfolder, Sublapis, dan object tree;
- banyak objek dalam satu layer;
- selection dan transform per objek;
- visibility, lock, ordering, duplicate, delete, dan Undo/Redo;
- Brush dan Eraser sebagai objek cropped, bukan raster seluas kanvas;
- Brush opacity, hardness, smoothing, preset ukuran, dan circular cursor;
- Line, Rectangle, Ellipse, dan Polygon non-destruktif;
- Motif Pokok Kawung, Truntum, Ceplok, dan Lereng sebagai fallback procedural;
- Cecek, Cecek Telu, Sawut, Cecek Sawut, Ukel, Galaran, Sisik, dan Cacah Gori;
- pengisian isen otomatis dan pola susun Cermin/Putar;
- Humanize non-destruktif dengan seed, wobble tepi, celah malam, dan variasi tekanan;
- migrasi baca project schema `1.0` ke schema `1.1`;
- CI menggunakan Ruff dan Pytest.

## Struktur Dokumen

```text
Folder
├── Subfolder
│   └── Sublapis
│       ├── Objek Asset 1
│       ├── Objek Asset 2
│       └── Objek Asset 3
└── Lapis Canting
    ├── Gores Canting 1
    ├── Gores Canting 2
    └── Hapus 3
```

Folder mengatur susunan. Sublapis menampung banyak objek. Objek adalah unit selection
terkecil. Asset dari pustaka baru disalin ke proyek ketika benar-benar ditempatkan pada
canvas.

## Asset Pack

Paket asset memakai ekstensi:

```text
.batikpack
```

Struktur dasarnya:

```text
manifest.json
assets/
  asset-001.batikasset
thumbnails/
  asset-001.png
```

Kategori yang didukung:

- `motif-pokok`;
- `isen-isen`;
- `ornamen`;
- `tekstur`;
- `lainnya`.

Windows menyimpan pack terpasang di:

```text
%LOCALAPPDATA%\BatikCraftStudio\asset-library
```

Panduan format lengkap tersedia di `docs/MILESTONE_3F_ASSET_LIBRARY.md`.

## Roadmap

### Milestone 1 — Application Foundation ✅

- package Python, shell Tkinter, tema, menu, status bar, shortcut, dokumentasi, dan CI.

### Milestone 2 — Project and Workspace Core ✅

- project domain;
- serializer `.batikcraft`;
- atomic save dan integrity validation;
- raster object editing dan Undo/Redo.

### Milestone 3 — Manual and Asset-Based Motif Tools

#### 3A — Basic Paint Layer ✅

- Brush, Eraser, color picker, dan satu completed stroke per history entry.

#### 3B — Brush Refinement ✅

- smoothing, opacity, hardness, partial eraser, preset, dan circular cursor.

#### 3C — Shape and Line Tools ✅

- Line, Rectangle, Ellipse, Polygon, fill, stroke, dan modifier keyboard.

#### 3D — Cap Isen dan Pola Susun ✅

- isen procedural, palet batik, cermin, putar, dan preview susun.

#### Patch 3D.1 — Motif Pokok dan Isen Otomatis ✅

- Kawung, Truntum, Ceplok, Lereng, dan pengisian isen otomatis.

#### 3E — Object Tree, Asset, dan Humanize ✅

- Folder/Sublapis/Objek;
- selection mengikuti bounds objek;
- `.batikasset`;
- metadata asset dan Humanize non-destruktif.

#### 3F — Pustaka Asset dan UI Ringkas ✅

- `.batikpack`;
- install, replace, uninstall, search, filter, dan preview;
- Pustaka Asset permanen;
- layout Asset Library → Canvas → Susunan Lapis;
- tool settings melalui jendela kecil dari menu bar;
- rail workspace dan dock tab menggambar dihapus dari workflow utama.

#### 3G — Kaggle Asset Pack Builder

- scan dataset;
- segmentasi/crop kandidat komponen batik;
- pembersihan alpha;
- klasifikasi dan tagging;
- review/curation queue;
- export `.batikasset`, thumbnail, manifest, dan `.batikpack`.

#### Tahap Manual Berikutnya

- group transform;
- vector path dan node editing;
- pressure curve per titik stroke;
- simetri canting real-time;
- recolor region asset.

### Milestone 4 — Object Batikfication MVP

- background removal dan mask correction;
- pilihan gaya Batik;
- Outline, Fill, dan Generative;
- hasil masuk sebagai objek editable.

### Milestone 5 — Pattern Engine

- straight, mirror, half-drop, half-brick, dan rotational repeat;
- seamless preview dan export tile.

### Milestone 6 — AI Integration

- model/checkpoint loader;
- image, mask, edge, style, palette, dan seed conditioning;
- worker thread, progress, cancellation, dan recovery.

### Milestone 7 — Licensing and Website Bridge

- design version, hash, lisensi, watermark, publish manifest, dan upload.

## Menjalankan Aplikasi

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instal dan jalankan:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m batikcraft_studio
```

## Workflow Editor

1. Buat atau buka proyek.
2. Install `.batikpack` melalui **Asset → Install Asset Pack…**.
3. Cari/filter asset di panel kiri.
4. Pilih Sublapis tujuan pada panel kanan.
5. Double-click asset untuk memasukkannya ke canvas.
6. Pilih dan susun objek melalui canvas atau tree.
7. Buka **Edit → Transform…** untuk transform numerik.
8. Buka **Asset → Edit Asset Metadata…** atau **Humanize…** bila diperlukan.
9. Buka **Draw** hanya ketika perlu Brush, Eraser, Shape, Motif, atau Isen.
10. Gunakan `Ctrl+Z` dan `Ctrl+Y` untuk Undo/Redo.
11. Simpan sebagai `.batikcraft`.

## Validasi

```bash
ruff check .
pytest
```

## Prinsip Pengembangan

- setiap milestone dibuat melalui branch dan pull request;
- UI, application, domain, persistence, imaging, asset library, dan integration dipisahkan;
- domain dan persistence tidak mengimpor Tkinter;
- sumber asset asli dipertahankan untuk operasi non-destruktif;
- library besar diindeks dari manifest, bukan membuka seluruh PNG saat startup;
- fitur non-AI tetap berfungsi tanpa model;
- AI tidak boleh membekukan Tkinter main thread.

## Dokumentasi

- `docs/ARCHITECTURE.md` — batas modul dan arah dependensi;
- `docs/PROJECT_DOMAIN.md` — invariant project domain;
- `docs/PROJECT_FORMAT.md` — format archive dan keamanan;
- `docs/MILESTONE_3E_OBJECT_TREE_ASSETS.md` — object tree dan Humanize;
- `docs/MILESTONE_3F_ASSET_LIBRARY.md` — pack management dan UI ringkas;
- `docs/BOB_PROMPTS.md` — prompt bertahap;
- `docs/BOB_DEVELOPMENT_LOG.md` — development log.
