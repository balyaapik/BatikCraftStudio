# Patch 3D.1 — Motif Pokok dan Isen Otomatis

Patch ini memperbaiki pembagian fungsi pada Milestone 3D. **Motif pokok** menjadi
ornamen utama, sedangkan **isen-isen** menjadi detail pengisi di dalam bidang motif.
Pengguna tidak lagi diminta membangun seluruh motif dari Cap Isen satu per satu.

## Motif Pokok

Template awal yang tersedia:

- **Kawung** — empat bidang oval dengan pusat belah ketupat;
- **Truntum** — bentuk bintang atau bunga berulang dengan cecek di sekelilingnya;
- **Ceplok** — susunan roset simetris;
- **Lereng** — susunan bidang diagonal dengan aksen lengkung.

Template dibuat sebagai konstruksi digital bergaya batik yang dapat diedit. Template
bukan klaim reproduksi persis kain pusaka, varian keraton, atau karya perajin tertentu.

## Isen-Isen

Generator isen diperluas menjadi:

- Cecek;
- Cecek Telu;
- Sawut;
- Cecek Sawut;
- Ukel;
- Galaran;
- Sisik;
- Cacah Gori.

Generator lama menggambar satu simbol besar di tengah cap. Generator baru menggambar
susunan detail berulang sehingga fungsinya lebih sesuai sebagai pengisi bidang motif.

## Isen Bawaan Otomatis

Ketika **Isi isen otomatis** aktif, aplikasi memilih pasangan awal berikut:

| Motif pokok | Isen bawaan |
|---|---|
| Kawung | Cecek Sawut |
| Truntum | Cecek Telu |
| Ceplok | Ukel |
| Lereng | Galaran |

Pengguna tetap dapat mengganti isen bawaan dengan jenis lain atau mematikan pengisian
otomatis untuk membuat motif garis saja.

## Alur Penggunaan

1. Buka tab **Batik**.
2. Pilih **Motif Pokok**.
3. Pilih ukuran, warna garis motif, dan warna isen.
4. Biarkan **Isi isen otomatis** aktif untuk hasil lengkap.
5. Tekan `M` atau tombol ikon **Cap Motif**.
6. Klik kain untuk menempatkan motif.
7. Gunakan `C` hanya ketika ingin menambah **Cap Isen** secara manual.

Klik kanan pada panel Layers juga menyediakan:

```text
New Layer
└── Motif Pokok
    ├── Kawung
    ├── Truntum
    ├── Ceplok
    └── Lereng
```

## Pola Susun

Cap Motif menggunakan pola susun yang sama dengan Cap Isen:

- Tunggal;
- Cermin kiri–kanan;
- Cermin atas–bawah;
- Cermin empat arah;
- Putar 4;
- Putar 8.

Satu pengecapan tetap menjadi satu langkah Undo meskipun menghasilkan beberapa layer.
Semua layer hasil susun berbagi satu asset PNG transparan.

## Metadata Proyek

Layer motif menyimpan metadata berikut:

```text
source_format = CAP_MOTIF_BATIK
motif_role = motif-pokok
motif_type
motif_label
ukuran_motif
warna_motif
isen_type
isen_label
warna_isen
isi_isen_otomatis
pola_susun
susun_index
susun_count
```

Metadata dan asset tetap tersedia setelah save dan reopen `.batikcraft`.

## Batas Patch

Belum termasuk:

- reproduksi presisi varian regional atau koleksi museum;
- motif pokok flora/fauna yang kompleks;
- konversi layer pengguna menjadi cap kustom;
- node/path editing untuk motif;
- repeat kain seamless penuh;
- validasi filosofi dan aturan pemakaian motif tertentu;
- AI Object Batikfication.
