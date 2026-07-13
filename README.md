# BatikCraft Studio

BatikCraft Studio adalah aplikasi desktop native berbasis Python dan Tkinter untuk membuat motif batik secara manual, melakukan batikfikasi objek, mengintegrasikan generative AI, serta menyiapkan motif untuk proses lisensi dan bidding melalui website BatikCraft.

> Status: Milestone 2C — workspace shell. Pengembangan dilakukan bertahap agar setiap modul dapat diuji, diperbaiki, dan disempurnakan menggunakan IBM Bob.

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

## Fitur yang Sudah Berfungsi

- shell aplikasi Tkinter dengan lima workspace;
- project domain tervalidasi;
- format proyek editable `.batikcraft` berbasis ZIP;
- New Project, Open, Save, Save As, Close Project, dan Exit;
- Save–Discard–Cancel untuk proyek yang belum disimpan;
- project context bar berisi judul, creator, ukuran canvas, layer count, path, dan dirty state;
- blank motif canvas yang responsif terhadap aspect ratio proyek;
- keyboard shortcut untuk file dan workspace navigation;
- CI menggunakan Ruff dan Pytest.

## Roadmap Bertahap

### Milestone 1 — Application Foundation ✅

- struktur package Python;
- shell aplikasi Tkinter;
- sidebar dan perpindahan workspace;
- tema, status bar, menu, dan shortcut dasar;
- dokumentasi arsitektur dan CI.

### Milestone 2 — Project and Workspace Core

#### Milestone 2A — Project Domain ✅

- metadata proyek dan schema version;
- ukuran canvas dan warna latar;
- layer descriptor dan transform non-destruktif;
- add, update, remove, reorder, dan selection layer;
- revision dan dirty-state tracking;
- exception domain serta failure-path tests.

#### Milestone 2B — Project Serializer ✅

- format `.batikcraft` berbasis ZIP;
- manifest `project.json` yang strict dan versioned;
- assets, masks, renders, dan metadata;
- atomic save menggunakan temporary file dan `os.replace`;
- verified in-memory load tanpa ekstraksi filesystem;
- SHA-256, size verification, path traversal protection, dan corrupted-file tests.

#### Milestone 2C — Workspace Shell ✅

- application-level `ProjectSession`;
- New Project dan Open Project;
- Save, Save As, Close Project, dan Exit;
- dirty-project Save–Discard–Cancel confirmation;
- project context di main window;
- responsive blank canvas placeholder;
- session lifecycle dan failure-path tests.

#### Milestone 2D — Layer Editing

- import PNG/JPG menggunakan Pillow;
- image-backed layers dan canonical embedded PNG assets;
- select, move, scale, rotate, duplicate, dan delete;
- visibility, lock, dan layer ordering;
- undo/redo melalui application command history.

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
- form konfigurasi lisensi;
- preview ber-watermark;
- publishing manifest;
- autentikasi dan upload ke website;
- membuka halaman bidding dan membaca status bidding.

## Teknologi

- Python 3.11+
- Tkinter / ttk
- Pillow mulai Milestone 2D
- NumPy dan OpenCV untuk pemrosesan citra
- PyTorch atau ONNX Runtime untuk AI
- Requests/HTTPX untuk integrasi website
- Pytest dan Ruff untuk validasi

## Menjalankan Aplikasi

Buat dan aktifkan virtual environment:

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

Instal aplikasi dan development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Jalankan:

```bash
python -m batikcraft_studio
```

atau:

```bash
batikcraft-studio
```

## Workflow Proyek di GUI

1. Pilih **File → New Project** atau tekan `Ctrl+N`.
2. Masukkan judul, creator, ukuran canvas, dan warna latar.
3. Blank canvas tampil di workspace **Motif Editor**.
4. Pilih **File → Save As** atau tekan `Ctrl+Shift+S`.
5. Simpan sebagai file `.batikcraft`.
6. Gunakan `Ctrl+S` untuk penyimpanan berikutnya.
7. Gunakan **Open Project** atau `Ctrl+O` untuk membuka proyek kembali.

Saat proyek memiliki perubahan yang belum tersimpan, New, Open, Close, atau Exit akan menampilkan pilihan Save, Discard, atau Cancel.

## Contoh Application Session

```python
from batikcraft_studio.application import ProjectSession

session = ProjectSession()
session.new_project(
    title="Flora Otomotif",
    creator="Balya Rochmadi",
    width=1600,
    height=1200,
)
session.save_as("flora-otomotif.batikcraft")

snapshot = session.snapshot()
assert snapshot.title == "Flora Otomotif"
assert snapshot.dirty is False
```

## Validasi

```bash
ruff check .
pytest
```

CI GitHub menjalankan kedua perintah tersebut pada setiap push dan pull request.

## Prinsip Pengembangan

- setiap milestone dibuat dalam branch dan pull request tersendiri;
- kode UI, application, domain, persistence, imaging, dan integration dipisahkan;
- domain dan persistence tidak boleh mengimpor Tkinter;
- model domain tidak menyimpan image bytes atau widget state;
- fitur non-AI harus tetap berfungsi saat model tidak tersedia;
- AI tidak boleh membekukan Tkinter main thread;
- perubahan IBM Bob dicatat secara jujur di development log.

## Dokumentasi

- `docs/ARCHITECTURE.md` — batas modul dan arah dependensi;
- `docs/PROJECT_DOMAIN.md` — invariant dan API Milestone 2A;
- `docs/PROJECT_FORMAT.md` — format archive dan keamanan Milestone 2B;
- `docs/WORKSPACE_SHELL.md` — session, file commands, dan GUI contract Milestone 2C;
- `docs/BOB_PROMPTS.md` — prompt bertahap untuk IBM Bob;
- `docs/BOB_DEVELOPMENT_LOG.md` — catatan kontribusi Bob dan hasil review.
