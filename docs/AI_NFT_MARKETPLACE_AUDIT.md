# Audit Fitur AI, Training, NFT & Marketplace (Juli 2026)

## Dua keluarga AI

**Model sendiri (lokal)** — tersedia dan berfungsi: Stable Diffusion 1.5 + ControlNet
(batifikasi objek) dan SDXL + LoRA (BatikBrew). Dimuat dari pustaka model lokal
(`runtime_model_installer`, `batikbrew_generation`).

**Model cloud** — tersedia: **OpenAI** (Image API), **Google Gemini** (Image API),
**IBM watsonx.ai** (`generation_providers.PROVIDER_WATSONX`). Pemilihan provider
lewat dialog "Pilih Model Generasi AI"; API key disimpan via keyring.

**Claude (Anthropic)** — *tidak dapat dipakai untuk batifikasi*: Anthropic tidak
menyediakan API generasi gambar, sedangkan batifikasi membutuhkan model
image-to-image. Opsi realistis bila tetap ingin integrasi Claude: gunakan Claude
untuk memperkaya/menyusun prompt yang kemudian dieksekusi provider gambar
(OpenAI/Gemini/watsonx/SDXL). Belum diimplementasikan — perlu keputusan produk.

## Efisiensi unduhan Stable Diffusion (DIPERBAIKI)

Penyebab unduhan "sangat besar dan sangat lama": pola `unet/*`, `vae/*`,
`text_encoder/*` mengunduh SEMUA duplikat bobot — `.bin` + `.safetensors`,
varian fp32 + `.fp16` + `non_ema` — padahal pipeline hanya memuat satu set.
Kini installer mendeduplikasi per bobot (`_dedupe_weight_files`): prioritas
`.safetensors`, varian `.fp16`/`non_ema` duplikat dilewati.
Perkiraan penghematan: SD1.5 ±15GB → ±5,2GB; SDXL ±19GB → ±13GB;
ControlNet 2,9GB → 1,45GB. Resume per-file dan pembatalan aman sudah ada
sebelumnya dan tetap berfungsi; progress bar berbasis byte nyata.

## Batifikasi wajib via model (DIPERBAIKI)

"Batifikasi Non-AI" (tanpa model) telah dihapus dari menu konteks, shortcut
(Ctrl+Shift+B), dan dialognya. Semua batifikasi kini lewat model (SD lokal /
LoRA / cloud). Renderer deterministik internal tetap ada karena dipakai sebagai
tahap pra-proses pipeline model.

## Dependensi AI & progress bar

Dependency Manager memasang paket AI ke direktori terkelola per profil,
streaming log, dan bisa dibatalkan. Progress unduhan model menampilkan persen
byte nyata per tahap. Perbaikan lanjutan yang disarankan (belum dikerjakan,
perlu uji GUI langsung): satu jendela progres seragam untuk SEMUA unduhan
(dependensi + model + asset pack) dengan antrean, estimasi waktu, dan riwayat.

## Pelatihan model oleh user — SUDAH SESUAI ALUR YANG DIMAKSUD

1. **Latih**: menu AI → Dataset Studio (siapkan dataset) → LoRA Training lokal
   (`LocalLoraTrainingWindow`) dengan progres + log + batal.
2. **Simpan ke pustaka**: hasil training tersimpan ke pustaka model lokal dan
   dapat diaktifkan untuk generasi (aktivasi LoRA persisten).
3. **Jual via BatikCraftWeb**: `publish_model_pack` (menu Marketplace) dengan
   harga; pembeli membeli (`purchase_model`) lalu mengunduh & memasang
   (`download_model` + tab "Library Model Saya").

## NFT motif — SUDAH ADA TERMASUK MINTING

Project/motif dipaketkan sebagai `.batiknft` (format `BATIKCRAFT_NFT_FORMAT`),
menu "Mint & Publish Project Aktif sebagai NFT…" mengunggah via
`publish_nft_package` dengan harga awal lelang; marketplace menampilkan NFT,
status lelang, dan penawaran (`place_bid`).

## Pustaka model dijual — SUDAH BISA

Tab "Model Marketplace" (beli) dan "Library Model Saya" (pasang) berfungsi via
`list_models` / `purchase_model` / `model_library` / `download_model`.

## Tampilan ekonomi NFT (BARU)

Menu Marketplace → **"Analisis Ekonomi NFT…"** membuka jendela grafik garis
pergerakan harga per NFT (dari riwayat bid, endpoint `GET nfts/{id}/bids/`),
dengan ringkasan: harga awal/kini, terendah/tertinggi, jumlah bid, tren
naik/turun (%), dan status lelang. Catatan: bila backend BatikCraftWeb belum
menyediakan endpoint riwayat bid, jendela menampilkan pesan fallback — sisi
server perlu mengekspos daftar bid (route POST-nya sudah ada).
