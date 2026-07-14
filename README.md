# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk
membuat motif batik secara manual, melakukan batikfikasi objek, mengintegrasikan
AI generatif, serta menyiapkan motif untuk lisensi dan bidding melalui website
BatikCraft.

> Status: Milestone 3E — Object Tree, Pustaka Asset, dan Humanize. Pengembangan
> dilakukan bertahap agar setiap modul dapat diuji dan disempurnakan tanpa merusak
> workflow yang sudah stabil.

## Fokus Produk

Aplikasi desktop menangani proses penciptaan motif:

- menggambar dan menyunting motif secara manual;
- mengelola folder, sublapis, dan banyak objek dalam satu lapis;
- memasukkan objek dari foto, ilustrasi, PNG transparan, atau `.batikasset`;
- membentuk Motif Pokok dan Isen-Isen;
- membuat seamless/repeating pattern;
- menyimpan proyek editable;
- menyiapkan aset final untuk publikasi dan lisensi.

Bidding, transaksi, dan pengelolaan lisensi dilakukan di website BatikCraft.

## Fitur yang Sudah Berfungsi

- shell Tkinter native dengan toolbar ikon offline;
- format proyek `.batikcraft` berbasis ZIP dengan validasi integritas;
- New, Open, Save, Save As, Close, dan dirty-project confirmation;
- renderer Pillow untuk raster, shape, paint object, motif, dan isen;
- folder, subfolder, sublapis, dan object tree;
- banyak objek dalam satu layer;
- selection dan transform per objek;
- visibility, lock, ordering, duplicate, delete, dan Undo/Redo;
- brush dan eraser sebagai objek cropped, bukan raster seluas kanvas;
- brush opacity, hardness, smoothing, preset ukuran, dan circular cursor;
- line, rectangle, ellipse, dan polygon non-destruktif;
- Motif Pokok Kawung, Truntum, Ceplok, dan Lereng;
- Cecek, Cecek Telu, Sawut, Cecek Sawut, Ukel, Galaran, Sisik, dan Cacah Gori;
- pengisian isen otomatis;
- susun Tunggal, Cermin, Putar 4, dan Putar 8;
- import/export `.batikasset`;
- humanize non-destruktif dengan seed, wobble tepi, celah malam, dan variasi tekanan;
- migrasi baca project schema `1.0` ke schema `1.1`;
- CI menggunakan Ruff dan Pytest.

## Struktur Dokumen

```text
Folder
├── Subfolder
│   └── Sublapis
│       ├── Objek 1
│       ├── Objek 2
│       └── Objek 3
└── Lapis Canting
    ├── Gores Canting 1
    ├── Gores Canting 2
    └── Hapus 3
```

Folder mengatur susunan. Sublapis menampung objek. Objek adalah unit selection terkecil.
Satu susunan Cap Motif dapat menghasilkan beberapa objek dalam satu sublapis dan tetap
menjadi satu langkah Undo.

## Roadmap

### Milestone 1 — Application Foundation ✅

- package Python;
- shell Tkinter;
- tema, menu, status bar, shortcut, dokumentasi, dan CI.

### Milestone 2 — Project and Workspace Core ✅

#### 2A — Project Domain

- metadata, canvas, layer, transform, revision, dan dirty state.

#### 2B — Project Serializer

- archive `.batikcraft`;
- manifest versioned;
- SHA-256, size verification, atomic save, dan path security.

#### 2C — Workspace Shell

- ProjectSession;
- New/Open/Save/Save As/Close/Exit;
- Save–Discard–Cancel.

#### 2D — Raster Layer Editing

- import PNG/JPEG;
- selection, move, scale, rotation, opacity;
- layer ordering, visibility, lock, duplicate, delete, Undo/Redo.

### Milestone 3 — Manual Motif Tools

#### 3A — Basic Paint Layer ✅

- brush, eraser, color picker, dan satu completed stroke per history entry.

#### 3B — Brush Refinement ✅

- smoothing, opacity, hardness, partial eraser, preset, dan circular cursor.

#### 3C — Shape and Line Tools ✅

- line, rectangle, ellipse, polygon, fill, stroke, dan modifier keyboard.

#### 3D — Cap Isen dan Pola Susun ✅

- isen procedural;
- palet batik;
- cermin dan putar;
- preview susun.

#### Patch 3D.1 — Motif Pokok dan Isen Otomatis ✅

- Motif Pokok Kawung, Truntum, Ceplok, dan Lereng;
- Isen-Isen berulang;
- pengisian isen otomatis.

#### Milestone 3E — Object Tree, Asset, dan Humanize ✅

- folder, subfolder, dan sublapis;
- banyak objek dalam satu lapis;
- selection mengikuti bounds objek;
- stroke kuas/penghapus sebagai cropped object;
- Cap Motif dan Cap Isen sebagai object arrangement;
- portable `.batikasset`;
- metadata asset editable;
- humanize non-destruktif dan reset;
- schema proyek `1.1` dengan migrasi `1.0`.

#### Tahap Manual Berikutnya

- group transform untuk seluruh isi folder;
- vector path dan node editing;
- pressure curve per titik stroke;
- cap kustom dari selection;
- simetri canting real-time;
- recolor region pada asset.

### Milestone 4 — Object Batikfication MVP

- import objek dan background removal;
- koreksi mask;
- pilihan gaya batik;
- Outline, Fill, dan Generative;
- hasil masuk sebagai objek editable.

### Milestone 5 — Pattern Engine

- straight, mirror, half-drop, half-brick, dan rotational repeat;
- live seamless preview;
- export tile dan repeat preview.

### Milestone 6 — AI Integration

- checkpoint loader;
- image, mask, edge, style, palette, dan seed conditioning;
- worker thread, progress, cancellation, dan recovery;
- hasil AI dapat diedit kembali.

### Milestone 7 — Licensing and Website Bridge

- design version dan hash;
- konfigurasi lisensi;
- preview watermark;
- publish manifest dan upload ke website.

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
2. Buat Folder atau Sublapis melalui ikon New atau klik kanan tree.
3. Import PNG/JPEG/`.batikasset` ke sublapis terpilih.
4. Gunakan `M` untuk Cap Motif dan `C` untuk Cap Isen.
5. Gunakan `B` untuk brush, `E` untuk eraser, dan `V` untuk selection.
6. Pilih objek melalui canvas atau tree.
7. Atur transform, opacity, visibility, lock, dan ordering objek.
8. Gunakan tab **Asset** untuk nama, kategori, import/export, humanize, dan reset.
9. Gunakan `Ctrl+Z` dan `Ctrl+Y` untuk Undo/Redo.
10. Simpan sebagai `.batikcraft`.

Panduan lengkap persiapan asset dan parameter humanize tersedia di
`docs/MILESTONE_3E_OBJECT_TREE_ASSETS.md`.

## Validasi

```bash
ruff check .
pytest
```

## Prinsip Pengembangan

- setiap milestone dibuat melalui branch dan pull request;
- UI, application, domain, persistence, imaging, dan integration dipisahkan;
- domain dan persistence tidak mengimpor Tkinter;
- domain tidak menyimpan image bytes atau widget state;
- sumber asset asli dipertahankan untuk operasi non-destruktif;
- AI tidak boleh membekukan Tkinter main thread;
- fitur non-AI tetap berfungsi tanpa model.

## Dokumentasi

- `docs/ARCHITECTURE.md` — batas modul dan arah dependensi;
- `docs/PROJECT_DOMAIN.md` — invariant project domain;
- `docs/PROJECT_FORMAT.md` — format archive dan keamanan;
- `docs/LAYER_EDITOR.md` — raster layer editor;
- `docs/MILESTONE_3A_PAINT_LAYER.md` — basic paint layer;
- `docs/MILESTONE_3B_BRUSH_REFINEMENT.md` — refined brush;
- `docs/MILESTONE_3C_SHAPE_TOOLS.md` — shape tools;
- `docs/MILESTONE_3D_CAP_ISEN.md` — Cap Isen dan pola susun;
- `docs/MILESTONE_3D1_MOTIF_POKOK.md` — Motif Pokok dan isen otomatis;
- `docs/MILESTONE_3E_OBJECT_TREE_ASSETS.md` — object tree, asset, dan humanize;
- `docs/BOB_PROMPTS.md` — prompt bertahap;
- `docs/BOB_DEVELOPMENT_LOG.md` — development log.
