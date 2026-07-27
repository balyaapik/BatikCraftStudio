# Fee bidding creator dan PPN pada BatikCraftWeb

Dokumen ini menjelaskan penyesuaian BatikCraft Studio terhadap alur pembayaran
BatikCraftWeb.

## Ringkasan alur

1. Creator login dari Studio dan mengunggah `.batikcraft` ke web.
2. Creator menetapkan harga terendah (`starting_price`).
3. Sebelum karya tayang, creator membayar **fee bidding** melalui payment
   gateway. Fee dihitung dari persentase harga terendah, dengan batas fee
   minimum, lalu ditambah **PPN 11%**.
4. Fee **tidak dikembalikan**. Terjual maupun tidak terjual, creator tetap
   membayar fee beserta PPN-nya.
5. Buyer melakukan bidding. Bid tertinggi yang disetujui creator menghasilkan
   invoice untuk buyer.
6. Invoice buyer memuat subtotal (nilai bid), PPN 11%, dan total tagihan.
7. Setelah buyer melunasi invoice, NFT diterbitkan ke akun buyer dan payout
   senilai subtotal dicatat untuk creator. PPN bukan hak creator sehingga tidak
   ikut dibayarkan pada payout.

## Dampak pada Studio

`POST /api/v1/nfts/{id}/publish/` membalas **402 Payment Required** selama fee
belum lunas. `BatikCraftWebClient` menerjemahkan respons tersebut menjadi
`ListingFeeRequiredError`, yang membawa rincian tagihan dan `checkout_url`.

```python
from batikcraft_studio.web_bridge import ListingFeeRequiredError

try:
    client.publish_nft_package(package, starting_price="200000")
except ListingFeeRequiredError as exc:
    print(exc.summary())      # rincian fee + PPN + catatan non-refundable
    print(exc.checkout_url)   # halaman pembayaran gateway
```

Dialog Studio menampilkan rincian tersebut melalui
`batikcraft_studio.ui.listing_fee_prompt.handle_listing_fee_required`, yang
membuka halaman pembayaran di browser lalu meminta creator mengulang publish
setelah status berubah menjadi lunas.

## Melihat biaya sebelum publish

```python
quote = client.listing_fee(nft_id)     # estimasi, status "not_issued" bila belum terbit
invoice = client.issue_listing_fee(nft_id)  # terbitkan tagihan resmi
```

Tarif yang sedang berlaku juga tersedia pada blok `billing` di endpoint
kemampuan server (`GET /api/v1/capabilities/`).
