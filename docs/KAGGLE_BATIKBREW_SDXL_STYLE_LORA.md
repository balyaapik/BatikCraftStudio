# Melatih LoRA Gaya Batik SDXL untuk BatikBrew

Notebook: `notebooks/kaggle_train_batikbrew_sdxl_style_lora.ipynb`

## Untuk apa

Mengubah **foto objek apa pun** (botol, bunga, wayang, kendaraan) menjadi ornamen
batik lewat **BatikBrew**. LoRA hanya mempelajari *gaya* batik; bentuk objek
disuplai saat inferensi, sehingga objek target **tidak perlu ada di dataset**.

## Mengapa notebook baru

| | `kaggle_train_batik_style_any_object.ipynb` | notebook ini |
| --- | --- | --- |
| Base model | Stable Diffusion 1.5 | **Stable Diffusion XL** |
| Resolusi | 512 px | 1024 px |
| Dipakai fitur | Batifikasi Objek | **BatikBrew** |
| `base_model_family` | `sd15` | `sdxl` |

BatikBrew memuat pipeline SDXL. LoRA `sd15` tidak dapat dipakai di sana (dan
sebaliknya) — sejak 0.5.3 aplikasi mendeteksi ketidakcocokan ini dan
menjalankan LoRA SD 1.5 pada pipeline SD 1.5.

## Kebutuhan Kaggle

- Accelerator **GPU T4 ×2** atau **P100** (butuh ±15 GB VRAM).
- **Internet: On** (mengunduh SDXL base 1.0).
- Dataset: folder berisi **gambar batik saja**, minimal ±20 gambar; 200–500
  gambar memberi gaya yang jauh lebih konsisten.

## Langkah

1. Unggah gambar batik sebagai Kaggle Dataset.
2. Buka notebook, ubah `CFG.dataset_root` ke path dataset tersebut.
3. Opsional: sesuaikan `trigger_word`, `max_steps` (1200 ≈ 1,5–2 jam di T4),
   dan `resolution` (turunkan ke 768 bila kehabisan VRAM).
4. **Run All**. Sel 5 menampilkan pratinjau objek → batik.
5. Unduh `*.batikmodel` dari panel Output.

## Memasang di aplikasi

**Pusat Dependensi → tab Model AI Offline & LoRA → Pasang .batikmodel…**,
lalu pilih model tersebut dan tekan **Aktifkan Model**. Pastikan base model
yang aktif adalah **Model BatikBrew SDXL (base model)**.

## Menggunakan

Klik kanan objek/gambar di canvas → **Generate Motif/Pola BatikBrew**. Panel log
akan menampilkan `Keluarga base model: Stable Diffusion XL` dan
`Keluarga LoRA: Stable Diffusion XL` bila pasangannya benar.

## Menyetel hasil

| Gejala | Penyetelan |
| --- | --- |
| Bentuk objek berubah terlalu jauh | turunkan `strength` (0,40–0,50) |
| Gaya batik kurang kuat | naikkan `strength` (0,65–0,75) atau bobot LoRA |
| Motif terlalu ramai | kurangi `max_steps`, atau perkaya caption dataset |
| Warna meleset dari palet batik | tambah gambar bernuansa soga/indigo ke dataset |
