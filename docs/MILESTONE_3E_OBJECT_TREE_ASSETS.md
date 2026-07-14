# Milestone 3E — Object Tree, Pustaka Asset, dan Humanize

Milestone ini mengoreksi fondasi editor agar struktur dokumen lebih dekat dengan aplikasi
grafis native: **folder → sublapis → objek**. Satu lapis dapat memuat banyak objek, dan
setiap objek dapat dipilih, dipindahkan, diputar, diskalakan, dikunci, disembunyikan,
diduplikat, atau dihapus sendiri.

## 1. Struktur Dokumen

### Folder

Folder hanya mengatur susunan. Folder dapat berisi:

- folder lain;
- Lapis Motif;
- Lapis Isen-Isen;
- Lapis Canting;
- sublapis objek lain.

Visibility, lock, dan opacity folder diwariskan kepada seluruh anaknya. Folder tidak
menyimpan PNG atau objek secara langsung.

### Sublapis

Sublapis adalah container objek. Beberapa objek dapat berada dalam satu sublapis.
Contoh struktur yang disarankan:

```text
Ragam Hias Utama
├── Motif Pokok
│   ├── Kawung 1
│   ├── Kawung 2
│   └── Truntum 1
├── Isen-Isen
│   ├── Cecek Telu 1
│   ├── Sawut 1
│   └── Galaran 1
└── Sentuhan Canting
    ├── Gores Canting 1
    ├── Gores Canting 2
    └── Hapus 3
```

### Objek

Objek adalah unit selection terkecil. Motif, isen, gambar impor, shape, stroke kuas,
dan stroke penghapus dapat menjadi objek. Selection box mengikuti bounds objek, bukan
ukuran kanvas atau seluruh lapis.

## 2. Perilaku Kuas dan Penghapus

Setiap gerakan mouse dari press sampai release menghasilkan satu objek:

- `Gores Canting` untuk brush;
- `Hapus` untuk eraser.

PNG stroke dipotong sampai batas alpha aktual. Misalnya stroke hanya menempati area
`140 × 32 px` pada kain `2048 × 2048 px`, maka objek dan selection box juga hanya
sekitar `140 × 32 px`.

Eraser disimpan sebagai mask non-destruktif di dalam Lapis Canting. Urutan objek
penting: eraser mengurangi alpha objek-objek yang berada di bawahnya pada lapis yang
sama.

Satu stroke tetap menjadi satu langkah Undo/Redo.

## 3. Cap Motif dan Cap Isen

Susunan `Cermin empat arah` atau `Putar 8` tidak lagi membuat empat atau delapan
layer. Hasilnya adalah empat atau delapan objek dalam satu lapis dan menggunakan satu
asset PNG bersama.

```text
Motif Pokok
├── Kawung 1 1
├── Kawung 1 2
├── Kawung 1 3
└── Kawung 1 4
```

Seluruh satu proses pengecapan tetap menjadi satu transaksi Undo. Ketika belum ada
lapis target, aplikasi membuat lapis beserta semua objeknya dalam transaksi yang sama.

## 4. Membuat Asset Sendiri

### Format sumber yang disarankan

Gunakan PNG transparan. JPEG dapat diimpor, tetapi tidak mempunyai alpha sehingga
background harus dibersihkan terlebih dahulu.

Pedoman praktis:

- ukuran master `1024 × 1024 px` atau `2048 × 2048 px`;
- satu motif atau satu keluarga isen per file;
- background transparan;
- beri ruang kosong 4–10% di sekeliling bentuk agar tepi tidak terpotong;
- gunakan garis cukup tebal agar tetap terbaca ketika dikecilkan;
- jangan memasukkan repeat kain lengkap ke satu asset; simpan satu unit motif;
- gunakan nama deskriptif, misalnya `kawung-daun-v1.png` atau `cecek-telu-renggang.png`.

### Import ke program

1. Buat atau pilih sublapis tujuan pada panel **Susunan Lapis**.
2. Buka tab **Asset**.
3. Klik ikon **Import Asset**.
4. Pilih PNG, JPEG, atau `.batikasset`.
5. Atur nama dan kategori.
6. Klik ikon Apply untuk menyimpan metadata.
7. Gunakan Select untuk mengatur posisi, rotasi, skala, dan opacity.

Kategori yang tersedia:

- `motif-pokok`;
- `isen-isen`;
- `ornamen`;
- `tekstur`;
- `lainnya`.

## 5. Format `.batikasset`

`.batikasset` adalah JSON UTF-8 yang menyimpan:

- PNG sumber canonical dalam Base64;
- nama asset;
- kategori;
- ukuran sumber;
- metadata tambahan.

Asset dapat diekspor dari objek terpilih dan diimpor ke proyek lain. Transform objek
(position, rotation, scale) tidak dipanggang ke sumber, sehingga file asset tetap
menjadi master yang dapat digunakan ulang.

Format ini bukan font, model AI, atau format cloud. Seluruh isi tersedia offline.

## 6. Humanize Non-Destruktif

Humanize bertujuan mengurangi kesan digital yang terlalu sempurna. Sumber asli tidak
ditimpakan. Aplikasi membuat hasil turunan dan menyimpan referensi ke sumber asli,
sehingga tombol Reset dapat mengembalikan objek kapan saja.

### Parameter

#### Tepi tidak rata

Memberi deformasi frekuensi rendah pada bentuk. Nilai awal yang disarankan:

- motif geometris: `0.05–0.12`;
- motif organik: `0.10–0.22`;
- jangan langsung memakai `1.0`, karena bentuk dapat terlihat rusak.

#### Celah malam

Membuat bagian kecil seperti malam atau tinta yang tidak menutup sempurna.

- bersih/halus: `0.01–0.04`;
- natural: `0.04–0.10`;
- tekstur tua/eksperimental: `0.10–0.20`.

#### Variasi tekanan

Membuat opacity garis tidak sepenuhnya seragam.

- cap cukup rata: `0.03–0.08`;
- canting natural: `0.08–0.18`;
- efek kuat: `0.18–0.30`.

#### Seed

Seed membuat hasil dapat diulang. Parameter dan seed yang sama menghasilkan PNG yang
sama. Ubah seed untuk membuat variasi baru tanpa mengubah intensitas.

### Preset yang disarankan

```text
Cap rapi
Tepi 0.06 | Celah 0.03 | Tekanan 0.05

Canting natural
Tepi 0.14 | Celah 0.06 | Tekanan 0.12

Kain berkarakter
Tepi 0.20 | Celah 0.12 | Tekanan 0.18
```

Humanize memakai mesh warp, variasi opacity frekuensi rendah, dan celah sparse. Sistem
tidak menambahkan noise acak ke seluruh gambar karena noise generik cenderung membuat
motif kotor, bukan terasa dibuat manusia.

## 7. Workflow Humanize yang Aman

1. Import asset master.
2. Duplikat objek jika ingin membandingkan versi bersih dan versi humanized.
3. Mulai dari preset **Cap rapi** atau **Canting natural**.
4. Zoom ke ukuran pemakaian nyata, bukan hanya 800%.
5. Ubah seed sampai karakter bentuk sesuai.
6. Gunakan Reset bila hasil terlalu rusak.
7. Export `.batikasset` untuk menyimpan master asli dan metadata; hasil humanize tetap
   menjadi turunan di proyek.

## 8. Kompatibilitas Proyek

Schema proyek naik dari `1.0` ke `1.1`. Project schema `1.0` tetap dapat dibuka dan
dimigrasikan di memori sebagai legacy single-object layer. Ketika disimpan kembali,
proyek ditulis sebagai schema `1.1`.

Legacy layer tetap dirender. Stroke dan cap baru menggunakan object layer.

## 9. Batas Milestone

Yang sudah editable:

- nama dan kategori asset;
- posisi, rotation, scale, opacity;
- urutan objek;
- folder/sublayer;
- visibility dan lock;
- humanize dan reset;
- import/export asset.

Yang belum termasuk:

- node/path vector editing seperti Inkscape;
- edit bezier dan handle per titik;
- pressure curve per titik stroke;
- recolor berbasis region/vector;
- group transform yang memutar seluruh isi folder sekaligus;
- linked asset file di luar archive;
- sinkronisasi pustaka asset cloud.

Untuk asset yang perlu bentuk garis benar-benar dapat diedit per node, tahap berikutnya
harus menambahkan format vector internal (path + fill + stroke) dan editor node. Pada
milestone ini, asset menggunakan PNG transparan agar stabil, offline, dan kompatibel
dengan renderer yang sudah ada.
