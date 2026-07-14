# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk
merakit, menggambar, dan menyunting motif batik dari pustaka asset offline yang dapat
dibangun dari dataset Kaggle.

> Status: Milestone 3G — Kaggle Asset Pack Builder.

## Fokus Produk

Aplikasi desktop menangani proses penciptaan motif:

- memasang pustaka Motif Pokok, Isen-Isen, ornamen, tekstur, dan asset custom;
- mencari serta menggabungkan banyak asset menjadi komposisi baru;
- mengelola Folder, Subfolder, Sublapis, dan banyak objek dalam satu lapis;
- mengubah posisi, ukuran, rotasi, opacity, susunan, metadata, dan humanize;
- menggambar melalui menu Brush, Eraser, Shape, Cap Motif, dan Cap Isen;
- menyimpan proyek editable;
- menyiapkan asset final untuk pattern, AI, publikasi, dan lisensi.

Bidding, transaksi, dan pengelolaan lisensi dilakukan di website BatikCraft.

## Layout Editor

Editor utama hanya memiliki tiga area permanen:

```text
Pustaka Asset | Canvas | Susunan Lapis
```

Pengaturan menggambar tidak memenuhi dock dengan tab. Menu **Draw**, **Edit**, dan
**Asset** membuka jendela kecil ketika diperlukan.

## Fitur yang Sudah Berfungsi

- shell Tkinter native dengan toolbar ikon offline dan menu bar;
- format proyek `.batikcraft` dengan validasi integritas;
- format asset portable `.batikasset`;
- format pustaka `.batikpack` dengan manifest, tags, kategori, thumbnail, dan version;
- install, replace, uninstall, search, filter, preview, dan double-click placement;
- asset library global per-user agar ribuan asset tidak disalin ke setiap proyek;
- Folder, Subfolder, Sublapis, banyak objek per layer, dan object-sized selection;
- visibility, lock, ordering, duplicate, delete, transform, dan Undo/Redo;
- Brush dan Eraser sebagai cropped objects;
- Line, Rectangle, Ellipse, dan Polygon non-destruktif;
- fallback procedural Motif Pokok dan Isen-Isen;
- Humanize non-destruktif;
- notebook Kaggle untuk discovery, deduplication, extraction, alpha cleaning, review,
  thumbnail, `.batikasset`, manifest, dan `.batikpack`;
- builder pack reusable yang divalidasi oleh installer aplikasi;
- migrasi project schema `1.0` ke `1.1`;
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
terkecil. Asset library baru disalin ke proyek ketika benar-benar ditempatkan pada canvas.

## Asset Pack

Paket asset memakai ekstensi `.batikpack`:

```text
manifest.json
assets/
  asset-001.batikasset
thumbnails/
  asset-001.png
```

Kategori resmi:

- `motif-pokok`;
- `isen-isen`;
- `ornamen`;
- `tekstur`;
- `lainnya`.

Windows menyimpan pack terpasang di:

```text
%LOCALAPPDATA%\BatikCraftStudio\asset-library
```

## Kaggle Asset Builder

Notebook:

```text
notebooks/kaggle_batik_asset_pack_builder.ipynb
```

Modul ekstraksi notebook:

```text
notebooks/kaggle_asset_pipeline.py
```

Builder format yang juga dipakai test aplikasi:

```text
src/batikcraft_studio/assets/builder.py
```

Pipeline:

```text
dataset batik
→ exact dan visual deduplication
→ full/component/grid candidates
→ alpha cleaning
→ category/tag suggestion
→ contact sheets + review.csv
→ human curation
→ canonical .batikasset + thumbnail
→ manifest.json
→ validated .batikpack
```

Segmentasi tidak dianggap 100% otomatis. Motif historis, Isen-Isen, dan bagian kain
yang saling menyatu tetap memerlukan kurasi manusia.

## Roadmap

### Milestone 1 — Application Foundation ✅

- package Python, shell Tkinter, tema, menu, status bar, shortcut, dokumentasi, dan CI.

### Milestone 2 — Project and Workspace Core ✅

- project domain, serializer `.batikcraft`, atomic save, raster editing, dan Undo/Redo.

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

- Folder/Sublapis/Objek, `.batikasset`, metadata, dan Humanize.

#### 3F — Pustaka Asset dan UI Ringkas ✅

- `.batikpack`, pack management, Pustaka Asset permanen, dan menu-driven tool windows.

#### 3G — Kaggle Asset Pack Builder ✅

- discovery, duplicate filtering, segmentation/crop, alpha cleaning;
- category/tag suggestion;
- contact sheets dan review queue;
- curated export ke `.batikasset`, thumbnail, manifest, dan `.batikpack`;
- validation menggunakan installer aplikasi.

#### Tahap Manual Berikutnya

- group transform;
- vector path dan node editing;
- pressure curve per titik stroke;
- simetri canting real-time;
- recolor region asset;
- curation manager langsung di aplikasi.

### Milestone 4 — Object Batikfication MVP

- background removal dan mask correction;
- pilihan gaya Batik;
- Outline, Fill, dan Generative;
- hasil masuk sebagai objek editable.

### Milestone 5 — Pattern Engine

- straight, mirror, half-drop, half-brick, rotational repeat, dan seamless export.

### Milestone 6 — AI Integration

- model loader, conditioning, worker thread, progress, cancellation, dan recovery.

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
7. Gunakan **Edit → Transform…** untuk transform numerik.
8. Gunakan **Asset → Metadata/Humanize** bila diperlukan.
9. Gunakan **Draw** hanya ketika perlu menggambar.
10. Simpan sebagai `.batikcraft`.

## Validasi

```bash
ruff check .
pytest
```

## Dokumentasi

- `docs/PROJECT_FORMAT.md` — format project;
- `docs/MILESTONE_3E_OBJECT_TREE_ASSETS.md` — object tree dan Humanize;
- `docs/MILESTONE_3F_ASSET_LIBRARY.md` — pack management dan UI ringkas;
- `docs/MILESTONE_3G_KAGGLE_ASSET_BUILDER.md` — ekstraksi, kurasi, dan export Kaggle.
