# Milestone 3G — Kaggle Asset Pack Builder

Milestone ini menyediakan pipeline semi-otomatis untuk mengubah dataset batik menjadi
pustaka asset modular yang dapat dipasang di BatikCraft Studio.

File utama:

```text
notebooks/kaggle_batik_asset_pack_builder.ipynb
notebooks/kaggle_asset_pipeline.py
src/batikcraft_studio/assets/builder.py
```

## Prinsip pipeline

Dataset kain batik biasanya berisi pola yang:

- saling menempel;
- berulang;
- memiliki warna foreground dan background yang sama kompleksnya;
- tidak mempunyai mask komponen;
- belum dilabeli sebagai Motif Pokok, Isen-Isen, border, atau tekstur.

Karena itu pipeline tidak mengklaim segmentasi otomatis 100%. Workflow yang dipakai:

```text
computer vision extraction
→ candidate queue
→ contact sheet
→ human curation
→ asset pack
```

Asset dengan confidence tinggi dapat diberi saran `keep=1`, tetapi kurator tetap harus
memeriksa bentuk dan kategori sebelum pack didistribusikan sebagai pustaka default.

## Menjalankan notebook di Kaggle

### 1. Tambahkan repository

Repository dapat:

- di-clone ke `/kaggle/working/BatikCraftStudio`; atau
- ditambahkan sebagai Kaggle Dataset yang memiliki folder `src/batikcraft_studio`.

Dengan internet aktif:

```bash
git clone --depth 1 \
  https://github.com/balyaapik/BatikCraftStudio.git \
  /kaggle/working/BatikCraftStudio
```

### 2. Pasang dataset

Ubah konfigurasi:

```python
DATASET_ROOT = Path("/kaggle/input/...nama-dataset...")
```

Path default notebook diarahkan ke dataset batik yang sebelumnya digunakan dalam
proyek, tetapi struktur input tetap dapat diganti.

### 3. Jalankan ekstraksi

Notebook memakai tiga mode:

#### `full`

Satu source image menjadi satu candidate. Cocok untuk:

- dataset yang sudah berupa unit motif;
- crop manual;
- asset yang sudah dibersihkan.

#### `components`

Pipeline memperkirakan warna background dari border image, membuat distance mask,
menambahkan edge map, lalu mengambil connected components. Cocok untuk:

- ilustrasi motif pada background relatif konsisten;
- sheet dengan elemen terpisah;
- hasil scan yang sudah dibersihkan.

#### `grid`

Gambar dibagi menjadi tile overlap. Mode ini dipakai ketika hampir seluruh image
merupakan foreground, seperti foto kain penuh. Hasil grid bukan otomatis asset final;
kurator harus memilih tile yang memiliki unit komposisi berguna.

Mode dapat diatur:

```python
extraction_modes=("full", "components", "grid")
```

## Deduplikasi

Pipeline melakukan dua tahap:

1. SHA-256 untuk source image yang identik;
2. difference hash untuk candidate visual yang sangat mirip.

Deduplikasi visual dibatasi pada kandidat terbaru agar pipeline tetap masuk akal untuk
pack besar. Hasil near-duplicate yang lolos tetap dapat dibuang saat kurasi.

## Kategori awal

Kategori awal diperkirakan dari nama file/folder:

- keyword cecek, sawut, ukel, galaran → `isen-isen`;
- border, pinggir, tumpal, frame → `ornamen`;
- texture, kain, serat, malam → `tekstur`;
- lainnya → `motif-pokok`.

Ini hanya tebakan awal. Kurator bertanggung jawab memperbaiki kategori pada
`review.csv`.

## Review CSV

Kolom penting:

```text
keep
asset_id
name
category
tags
source_path
confidence
notes
extraction_mode
bbox
source_sha256
```

Aturan:

- `keep=1`: masuk pack;
- `keep=0`: ditolak;
- `asset_id`: harus unik dan stabil;
- `name`: nama yang tampil di aplikasi;
- `category`: salah satu kategori resmi;
- `tags`: dipisah dengan `|`;
- `notes`: keputusan kurator atau kebutuhan perbaikan.

Contact sheet ditempatkan di:

```text
/kaggle/working/batikcraft-asset-builder/contact-sheets/
```

Review dapat dilakukan di spreadsheet dengan mengunduh CSV, mengeditnya, lalu
meng-upload kembali sebagai Kaggle Dataset/input.

## Output candidate

Candidate PNG transparan disimpan di:

```text
/kaggle/working/batikcraft-asset-builder/candidates/
```

Nama file mengikuti `asset_id`. Builder membaca file berdasarkan ID dari review CSV,
sehingga mengganti nama file secara manual akan membuat validasi gagal.

## Normalisasi asset

Saat pack dibangun, setiap candidate:

1. dibuka sebagai RGBA;
2. transparent padding berlebih dipotong;
3. di-fit ke master square;
4. diberi margin;
5. disimpan sebagai PNG canonical;
6. dibuat thumbnail;
7. dibungkus menjadi `.batikasset`;
8. dimasukkan ke manifest `.batikpack`.

Default master:

```text
1024 × 1024 px
```

Ukuran ini dapat dinaikkan untuk asset detail, tetapi pack akan membesar.

## Output pack

Default:

```text
/kaggle/working/batikcraft-asset-builder/
  batikcraft-default-library-v1.batikpack
```

Notebook memvalidasi hasil dengan `AssetLibrary.install_pack()` ke folder validation
sementara. Pack yang gagal dibaca aplikasi tidak dianggap selesai.

## Instalasi di aplikasi

Di BatikCraft Studio:

```text
Asset → Install Asset Pack…
```

Setelah install:

- pack tersedia offline;
- asset dapat dicari berdasarkan name, ID, category, dan tags;
- preview dimuat secara lazy;
- double-click menyalin asset terpilih ke project;
- pack dapat diganti dengan versi baru.

## Versioning pack

Gunakan `pack_id` yang tetap untuk seri pack yang sama:

```text
batikcraft-default-library-v1
```

Naikkan `version` ketika isi diperbarui:

```text
1.0.0 → 1.1.0 → 1.1.1
```

Aplikasi dapat mengganti pack terpasang berdasarkan `pack_id`. Objek yang sudah masuk
ke project tidak terpengaruh karena byte asset sudah disalin ke `.batikcraft`.

## Rekomendasi produksi

Jangan membuat satu pack sangat besar tanpa pembagian. Lebih baik:

```text
batikcraft-motif-pokok-jawa-v1.batikpack
batikcraft-isen-isen-v1.batikpack
batikcraft-border-tumpal-v1.batikpack
batikcraft-flora-fauna-v1.batikpack
batikcraft-texture-v1.batikpack
```

Keuntungannya:

- proses kurasi lebih fokus;
- update lebih kecil;
- user hanya memasang pack yang dibutuhkan;
- pencarian dan distribusi lebih mudah.

## Yang belum otomatis

- identifikasi nama motif historis secara pasti;
- pemisahan Motif Pokok dan Isen pada pola yang menyatu;
- tracing vector/path;
- penghapusan watermark;
- pemeriksaan hak cipta dan lisensi dataset;
- validasi budaya/historis motif;
- penilaian kualitas estetika akhir.

Aspek tersebut tetap memerlukan kurator, perajin, atau sumber dokumentasi yang dapat
dipertanggungjawabkan.
