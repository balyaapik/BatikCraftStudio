# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk membuat motif batik secara manual, melakukan batikfikasi objek, mengintegrasikan generative AI, serta menyiapkan motif untuk proses lisensi dan bidding melalui website BatikCraft.

> Status: Milestone 2A — project domain. Pengembangan dilakukan bertahap agar setiap modul dapat diuji, diperbaiki, dan disempurnakan menggunakan IBM Bob.

## Fokus Produk

Aplikasi desktop difokuskan pada proses penciptaan motif:

- membuat dan menyunting motif secara manual;
- memasukkan objek dari foto atau ilustrasi ke workspace;
- mengubah objek menjadi elemen motif melalui Object Batikfication;
- menghasilkan atau memvariasikan motif dengan AI;
- menyusun seamless/repeating pattern;
- menyimpan proyek editable;
- menyiapkan versi final untuk lisensi dan publikasi ke website.

Bidding, transaksi, dan pengelolaan lisensi dilakukan di website BatikCraft. Desktop hanya menyiapkan serta menerbitkan aset motif.

## Roadmap Bertahap

### Milestone 1 — Application Foundation ✅

- struktur package Python;
- shell aplikasi Tkinter;
- sidebar dan perpindahan workspace;
- Dashboard, Motif Editor, Object Batikfication, Pattern Preview, dan Publish placeholder;
- konfigurasi tema;
- status bar dan penanganan error awal;
- dokumentasi arsitektur serta petunjuk menjalankan aplikasi.

### Milestone 2 — Project and Workspace Core

#### Milestone 2A — Project Domain ✅

- model proyek tervalidasi tanpa dependensi GUI;
- metadata proyek dan schema version;
- ukuran canvas dan warna latar;
- layer descriptor dan transform non-destruktif;
- add, update, remove, reorder, dan selection layer;
- revision serta dirty-state tracking;
- exception domain yang eksplisit;
- unit test untuk invariant dan failure path.

#### Milestone 2B — Project Serializer

- format editable `.batikcraft` berbasis ZIP;
- manifest `project.json`;
- folder assets, masks, renders, dan metadata;
- atomic save/open;
- validasi archive dan perlindungan path traversal;
- round-trip serta corrupted-file tests.

#### Milestone 2C — Workspace Shell

- New Project dan Open Project;
- canvas motif kosong;
- integrasi project domain ke aplikasi Tkinter;
- dirty-project close confirmation.

#### Milestone 2D — Layer Editing

- import PNG/JPG;
- select, move, scale, rotate, duplicate, dan delete;
- visibility, lock, dan layer ordering;
- undo/redo.

### Milestone 3 — Manual Motif Tools

- brush dan eraser;
- shape dan line tools;
- motif stamp;
- palet warna;
- mirror dan symmetry drawing;
- isen-isen tools dasar.

### Milestone 4 — Object Batikfication MVP

- import objek;
- object mask dan background removal;
- koreksi mask manual;
- pilihan gaya batik;
- mode Outline, Fill, dan Generative;
- procedural batik fill sebagai fallback yang stabil;
- empat variasi hasil;
- hasil masuk sebagai editable workspace layer.

### Milestone 5 — Pattern Engine

- straight repeat;
- mirror repeat;
- half-drop;
- half-brick;
- rotational repeat;
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
- form konfigurasi lisensi;
- preview ber-watermark;
- publishing manifest;
- autentikasi website;
- upload desain;
- membuka halaman bidding di browser;
- membaca status bidding dari website.

## Teknologi Awal

- Python 3.11+
- Tkinter / ttk
- Pillow pada milestone image workspace
- NumPy dan OpenCV pada milestone pemrosesan citra
- PyTorch atau ONNX Runtime pada milestone AI
- Requests/HTTPX pada milestone integrasi website
- Pytest dan Ruff untuk validasi

## Prinsip Pengembangan

- setiap milestone dibuat dalam branch dan pull request tersendiri;
- modul AI tidak boleh membekukan Tkinter main thread;
- output AI tetap dapat diedit secara manual;
- fitur non-AI harus tetap dapat digunakan saat model belum tersedia;
- kode UI, domain, imaging, dan integrasi eksternal dipisahkan;
- perubahan IBM Bob dicatat di `docs/BOB_DEVELOPMENT_LOG.md`.

## Menjalankan Aplikasi

Pastikan Python 3.11 atau lebih baru tersedia dan instal Tkinter melalui distribusi Python/OS apabila belum disertakan.

```bash
python -m venv .venv
```

Aktifkan virtual environment.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instal aplikasi dan alat pengembangan:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Jalankan aplikasi:

```bash
python -m batikcraft_studio
```

atau:

```bash
batikcraft-studio
```

## Contoh Project Domain

```python
from batikcraft_studio.domain import Layer, Project

project = Project.create("Flora Otomotif", "Balya Rochmadi")
project.add_layer(Layer(name="Main Object"))

assert project.is_dirty
project.mark_saved()
assert not project.is_dirty
```

## Validasi

```bash
ruff check .
pytest
```

CI GitHub menjalankan kedua perintah tersebut pada setiap push dan pull request.

## Dokumentasi

- `docs/ARCHITECTURE.md` — batas modul dan arah dependensi;
- `docs/PROJECT_DOMAIN.md` — invariant dan API Milestone 2A;
- `docs/BOB_PROMPTS.md` — prompt bertahap untuk IBM Bob;
- `docs/BOB_DEVELOPMENT_LOG.md` — catatan kontribusi Bob dan hasil review.
