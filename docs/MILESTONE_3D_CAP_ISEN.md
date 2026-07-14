# Milestone 3D — Cap Isen dan Pola Susun Batik

Milestone 3D menambahkan proses pengecapan motif kecil untuk mengisi dan memperkaya
ornamen batik. Istilah antarmuka sengaja mengikuti praktik visual batik, bukan istilah
generik editor grafis.

## Istilah antarmuka

- **Cap Isen**: tool untuk menempatkan satu isen atau satu susunan isen pada kain.
- **Isen-Isen**: unsur pengisi atau perinci di dalam komposisi motif.
- **Cecek**: isen berbentuk titik.
- **Sawut**: isen berupa deret garis pendek.
- **Ukel**: isen berbentuk lengkung atau gulungan.
- **Cecek Sawut**: kombinasi cecek dan sawut dalam satu cap.
- **Pola Susun**: aturan penempatan hasil cap terhadap pusat kain.
- **Pusat Kain**: titik tengah logical canvas yang menjadi poros cermin dan putar.

Istilah tersebut dipakai sebagai nama kontrol kerja. Implementasi digital ini tidak
mengklaim menggantikan proses membatik tradisional dengan malam, canting, atau cap
tembaga.

## Tool Cap Isen

Shortcut:

```text
C
```

Setelah tool aktif, pengguna memilih:

- jenis isen;
- ukuran cap;
- warna isen;
- pola susun;
- posisi pengecapan pada kain.

Klik pada canvas melakukan satu pengecapan. Lingkaran pratinjau menunjukkan semua
posisi yang akan dihasilkan oleh pola susun saat ini.

## Isen bawaan

Empat isen procedural tersedia:

1. **Cecek** — satu cecek bulat;
2. **Sawut** — tiga sawut sejajar;
3. **Ukel** — satu ukel spiral;
4. **Cecek Sawut** — tiga sawut dengan cecek pada ujungnya.

Setiap isen dirender sebagai PNG RGBA transparan 256×256 menggunakan supersampling.
Sesudah antialiasing, alpha mask dipertahankan dan warna RGB diterapkan kembali agar
warna palet tidak bergeser akibat resampling.

## Palet batik

Tab **Batik** menyediakan swatch kerja:

- Soga;
- Indigo;
- Gading;
- Mengkudu;
- Hitam.

Palet ini adalah preset warna antarmuka. Pengguna tetap dapat membuka color picker dan
memilih warna lain.

## Pola susun

Mode yang tersedia:

- **Tunggal** — satu hasil cap pada posisi pointer;
- **Cermin kiri–kanan** — posisi dan orientasi dicerminkan terhadap sumbu vertikal
  pusat kain;
- **Cermin atas–bawah** — posisi dan orientasi dicerminkan terhadap sumbu horizontal
  pusat kain;
- **Cermin empat arah** — kombinasi cermin kiri–kanan dan atas–bawah;
- **Putar 4** — empat posisi dengan selang 90°;
- **Putar 8** — delapan posisi dengan selang 45°.

Perhitungan menggunakan koordinat logical project, bukan koordinat layar. Zoom dan DPI
Windows tidak mengubah posisi motif di dalam proyek.

## Layer dan asset

Satu proses pengecapan menghasilkan satu atau beberapa `LayerKind.RASTER`.

Semua layer hasil satu pengecapan:

- memakai satu `asset_ref` PNG yang sama;
- memiliki transform posisi, rotasi, dan cermin masing-masing;
- menyimpan metadata jenis isen, ukuran cap, warna, pola susun, dan nomor susun;
- dapat dipilih, dipindahkan, diputar, diskalakan, disembunyikan, dikunci,
  diduplikasi, dan dihapus menggunakan editor layer yang sudah ada.

Metadata utama:

```text
source_format = CAP_ISEN
motif_role = isen-isen
isen_type
isen_label
ukuran_cap
warna_isen
pola_susun
susun_index
susun_count
```

## Undo, redo, dan persistence

Satu pengecapan adalah satu mutation pada `BatikProjectSession`.

Akibatnya:

- satu `Ctrl+Z` menghapus seluruh hasil satu pengecapan;
- satu `Ctrl+Y` memulihkan seluruh layer dan asset bersama;
- save/reopen `.batikcraft` mempertahankan PNG, transform, dan metadata;
- penghapusan semua layer yang memakai asset mengikuti aturan cleanup asset editor.

## Klik kanan New Layer

Menu Layers memiliki jalur:

```text
New Layer
└── Isen-Isen
    ├── Cecek
    ├── Sawut
    ├── Ukel
    └── Cecek Sawut
```

Perintah ini membuat satu lapis isen di pusat kain menggunakan warna dan ukuran Cap
Isen yang sedang aktif.

## Batas milestone

Milestone 3D belum mencakup:

- mengambil layer pengguna sebagai cap motif kustom;
- pustaka cap lintas proyek;
- kelompok layer formal untuk satu susunan;
- cermin canting real-time pada brush dan eraser;
- pusat susun yang dapat dipindahkan;
- jumlah putar bebas;
- repeat tile dan seamless pattern penuh;
- Object Batikfication atau AI.

## Pengujian manual Windows

Periksa:

1. tool `C` aktif tanpa mengganggu Entry atau Spinbox;
2. lingkaran pratinjau sesuai dengan mode Tunggal, Cermin, Putar 4, dan Putar 8;
3. klik kanan **New Layer → Isen-Isen** bekerja pada area Layers;
4. hasil cermin mempunyai orientasi yang benar;
5. satu Undo menghapus seluruh hasil satu pengecapan;
6. save lalu reopen mempertahankan semua hasil;
7. tampilan tetap tepat pada scaling Windows 100%, 125%, 150%, dan 200%.
