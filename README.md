# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk
membuat motif batik secara manual, melakukan batikfikasi objek, mengintegrasikan
generative AI, serta menyiapkan motif untuk proses lisensi dan bidding melalui
website BatikCraft.

> Status: Milestone 3C — editable shape and line tools. Pengembangan dilakukan
> bertahap agar setiap modul dapat diuji, diperbaiki, dan disempurnakan menggunakan
> IBM Bob.

## Fokus Produk

Aplikasi desktop difokuskan pada proses penciptaan motif:

- membuat dan menyunting motif secara manual;
- memasukkan objek dari foto atau ilustrasi ke workspace;
- mengubah objek menjadi elemen motif melalui Object Batikfication;
- menghasilkan atau memvariasikan motif dengan AI;
- menyusun seamless/repeating pattern;
- menyimpan proyek editable;
- menyiapkan versi final untuk lisensi dan publikasi ke website.

Bidding, transaksi, dan pengelolaan lisensi dilakukan di website BatikCraft. Desktop
hanya menyiapkan serta menerbitkan aset motif.

## Fitur yang Sudah Berfungsi

- shell aplikasi Tkinter native dengan toolbar ikon offline dan lima workspace;
- project domain tervalidasi;
- format proyek editable `.batikcraft` berbasis ZIP;
- New Project, Open, Save, Save As, Close Project, dan Exit;
- Save–Discard–Cancel untuk proyek yang belum disimpan;
- import PNG/JPEG sebagai raster layer editable;
- normalisasi image source menjadi embedded PNG RGBA;
- Pillow project preview dengan layer composition;
- click selection dan drag-to-move;
- transform X/Y, rotation, scale X/Y, dan opacity;
- duplicate, delete, show/hide, lock/unlock, serta layer ordering;
- undo/redo yang memulihkan project state dan asset bytes;
- paint layer transparan berukuran penuh sesuai canvas;
- brush dan eraser dengan satu history entry per stroke;
- opacity, hardness, smoothing, preset ukuran, dan circular brush cursor;
- line, rectangle, ellipse, dan regular polygon non-destruktif;
- editable fill, stroke, dimensions, stroke width, dan polygon sides;
- klik kanan Layers dengan submenu **New Layer**;
- shortcut `B`, `E`, `V`, `[`, `]`, `L`, `R`, `O`, dan `P`;
- CI menggunakan Ruff dan Pytest.

## Roadmap Bertahap

### Milestone 1 — Application Foundation ✅

- struktur package Python;
- shell aplikasi Tkinter;
- navigasi workspace;
- tema, status bar, menu, shortcut dasar, dokumentasi, dan CI.

### Milestone 2 — Project and Workspace Core

#### Milestone 2A — Project Domain ✅

- metadata proyek dan schema version;
- ukuran canvas dan warna latar;
- layer descriptor dan transform non-destruktif;
- add, update, remove, reorder, selection, revision, dan dirty-state tracking.

#### Milestone 2B — Project Serializer ✅

- format `.batikcraft` berbasis ZIP;
- manifest strict dan versioned;
- atomic save, verified in-memory load, SHA-256, dan size verification;
- path traversal, duplicate entry, dan corrupted-file protection.

#### Milestone 2C — Workspace Shell ✅

- application-level `ProjectSession`;
- New/Open/Save/Save As/Close/Exit;
- dirty-project Save–Discard–Cancel confirmation;
- project context bar dan responsive blank canvas.

#### Milestone 2D — Raster Layer Editing ✅

- import PNG/JPEG menggunakan Pillow;
- canonical embedded PNG assets;
- bounded raster project preview;
- select, move, scale, rotate, opacity, duplicate, dan delete;
- visibility, lock, layer ordering, dan undo/redo.

### Milestone 3 — Manual Motif Tools

#### Milestone 3A — Basic Paint Layer ✅

- full-canvas transparent paint layer;
- brush dan eraser;
- color picker dan brush size;
- satu completed stroke sebagai satu history entry;
- paint asset tersimpan di `.batikcraft`.

#### Milestone 3B — Brush Refinement ✅

- endpoint-preserving stroke smoothing;
- opacity dan hardness;
- partial-opacity eraser;
- preset ukuran dan shortcut `[` / `]`;
- circular cursor sesuai diameter brush;
- bounded stroke resampling dan antialiased brush stamp.

#### Milestone 3C — Shape and Line Tools ✅

- line, rectangle, ellipse, dan regular polygon;
- fill/stroke controls dan editable dimensions;
- stroke width dan polygon sides;
- Shift constraint dan Alt draw-from-center;
- shape selection, move, transform, duplicate, delete, dan ordering;
- klik kanan Layers dengan **New Layer** untuk Paint dan semua shape types;
- shape tersimpan non-destruktif di `.batikcraft` tanpa PNG asset tambahan.

#### Milestone 3D — Motif Stamp and Symmetry

- reusable motif stamp;
- mirror horizontal/vertical;
- radial symmetry;
- palet warna motif;
- isen-isen tools dasar.

### Milestone 4 — Object Batikfication MVP

- import objek;
- object mask dan background removal;
- koreksi mask manual;
- pilihan gaya batik;
- mode Outline, Fill, dan Generative;
- procedural batik fill sebagai fallback;
- empat variasi hasil;
- hasil masuk sebagai editable workspace layer.

### Milestone 5 — Pattern Engine

- straight, mirror, half-drop, half-brick, dan rotational repeat;
- live seamless preview;
- export tile dan repeat preview.

### Milestone 6 — GAN Integration

- refactor notebook training menjadi modul inferensi;
- checkpoint loader;
- image, mask, edge map, style, palette, dan seed conditioning;
- inference di worker thread;
- progress, cancellation, dan error recovery;
- hasil AI dapat diedit kembali di workspace.

### Milestone 7 — Licensing and Website Bridge

- design version dan hash;
- konfigurasi lisensi dan preview ber-watermark;
- publishing manifest;
- autentikasi dan upload ke website;
- membuka halaman bidding dan membaca status bidding.

## Teknologi

- Python 3.11+
- Tkinter / ttk
- Pillow untuk import, raster rendering, paint tools, dan shape rendering
- NumPy dan OpenCV untuk milestone pemrosesan citra
- PyTorch atau ONNX Runtime untuk milestone AI
- Requests/HTTPX untuk integrasi website
- Pytest dan Ruff untuk validasi

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

1. Buat atau buka proyek melalui menu **File**.
2. Import PNG/JPEG melalui `Ctrl+I`, atau pilih Brush dengan `B`.
3. Gunakan `V` untuk memilih dan memindahkan layer.
4. Gunakan `B` untuk menggambar dan `E` untuk menghapus.
5. Gunakan `L`, `R`, `O`, dan `P` untuk membuat shape.
6. Tahan `Shift` untuk constraint dan `Alt` untuk menggambar dari pusat.
7. Atur properti pada tab **Brush**, **Shape**, **Transform**, dan **Layers**.
8. Klik kanan pada daftar Layers untuk membuka submenu **New Layer**.
9. Gunakan `Ctrl+Z` dan `Ctrl+Y` untuk undo/redo.
10. Simpan sebagai `.batikcraft` melalui `Ctrl+Shift+S`.

## Validasi

```bash
ruff check .
pytest
```

CI GitHub menjalankan kedua perintah tersebut pada setiap push dan pull request.

## Prinsip Pengembangan

- setiap milestone dibuat dalam branch dan pull request tersendiri;
- kode UI, application, domain, persistence, imaging, dan integration dipisahkan;
- domain dan persistence tidak mengimpor Tkinter;
- model domain tidak menyimpan image bytes atau widget state;
- fitur non-AI tetap berfungsi saat model tidak tersedia;
- AI tidak boleh membekukan Tkinter main thread;
- perubahan IBM Bob dicatat secara jujur di development log.

## Dokumentasi

- `docs/ARCHITECTURE.md` — batas modul dan arah dependensi;
- `docs/PROJECT_DOMAIN.md` — invariant dan API Milestone 2A;
- `docs/PROJECT_FORMAT.md` — format archive dan keamanan Milestone 2B;
- `docs/WORKSPACE_SHELL.md` — session dan GUI contract Milestone 2C;
- `docs/LAYER_EDITOR.md` — raster layer contract Milestone 2D;
- `docs/MILESTONE_3A_PAINT_LAYER.md` — basic paint-layer contract;
- `docs/MILESTONE_3B_BRUSH_REFINEMENT.md` — refined brush contract;
- `docs/MILESTONE_3C_SHAPE_TOOLS.md` — shape dan layer context-menu contract;
- `docs/BOB_PROMPTS.md` — prompt bertahap untuk IBM Bob;
- `docs/BOB_DEVELOPMENT_LOG.md` — catatan kontribusi Bob dan hasil review.
