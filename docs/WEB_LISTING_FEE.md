# Creator Listing Fee and VAT on BatikCraftWeb

How BatikCraft Studio adapts to the BatikCraftWeb payment flow.

## Flow Summary

1. The creator signs in from the Studio and uploads a sealed listing package to the web.
2. The creator sets a starting price (`starting_price`).
3. Before the piece goes live, the creator pays a **listing fee** through the payment
   gateway. The fee is a percentage of the starting price, subject to a minimum, plus
   **11% VAT**.
4. **The fee is non-refundable.** Sold or unsold, the creator pays the fee and its VAT.
5. Buyers place bids. The highest bid the creator accepts generates a buyer invoice.
6. The buyer's invoice shows the subtotal (the bid value), 11% VAT, and the total.
7. Once the buyer settles the invoice, the NFT is issued to the buyer's account and a
   payout equal to the subtotal is recorded for the creator. VAT does not belong to the
   creator and is therefore excluded from the payout.

## Effect on the Studio

`POST /api/v1/nfts/{id}/publish/` replies **402 Payment Required** while the fee is
outstanding. `BatikCraftWebClient` translates that response into a
`ListingFeeRequiredError` carrying the charge breakdown, draft `nft_id`, and a
`checkout_url`.

```python
from batikcraft_studio.web_bridge import ListingFeeRequiredError

try:
    client.publish_nft_package(package, starting_price="200000")
except ListingFeeRequiredError as exc:
    print(exc.summary())      # fee + VAT breakdown and the non-refundable note
    print(exc.checkout_url)   # payment gateway page
```

The Studio dialog renders that breakdown through
`batikcraft_studio.ui.listing_fee_prompt.handle_listing_fee_required`, which opens the
payment page in a browser. The dialog keeps the draft NFT identifier from that failed
publish attempt. Clicking **Check Payment & Publish** retries
`POST /api/v1/nfts/{id}/publish/` for the same draft; it does not upload the package or
create a second marketplace record.

The retry identifier is read from `listing_fee.nft_id` when the server provides it. For
compatibility with older BatikCraftWeb deployments, Studio can also recover the identifier
from the checkout URL generated for that invoice.

## Sealed Asset-Library Listings

A standalone `.batikpack` is installable, but it does not bind a separately uploaded
marketplace preview to its contents. Studio therefore does not upload it directly as
provenance evidence.

For **Jual Pustaka Ini**, Studio creates this structure:

```text
listing.batikcraftnft
├── manifest.json
├── seal.json
├── preview.jpg
├── project/project.json
└── project/assets/library/<pack-id>.batikpack
```

The outer `.batikcraftnft` locks the preview and the exact `.batikpack` bytes under one
manifest and seal. BatikCraftWeb verifies both archives, stores the outer envelope for
audit, and extracts the verified inner `.batikpack` for authorised downloads. The creator
and the paid buyer therefore receive an installable `.batikpack`, not the listing wrapper.

Direct `.batikpack` upload remains rejected by the secure API contract. This prevents an
unrelated preview from being attached to a library package.

## Windows Timezone Data

Auction deadlines are converted from local wall time to an ISO-8601 value with an explicit
offset. Windows does not ship the IANA timezone database used by Python's `zoneinfo`, so
BatikCraft Studio declares `tzdata` as a Windows-only runtime dependency. A normal
installation with `pip install -e .` or the packaged desktop build must therefore populate
the timezone combobox without requiring a separate manual `pip install tzdata` command.

## Checking the Cost Before Publishing

```python
quote = client.listing_fee(nft_id)          # estimate; status "not_issued" if not yet raised
invoice = client.issue_listing_fee(nft_id)  # raise the formal invoice
```

The current rates are also exposed in the `billing` block of the server capabilities
endpoint (`GET /api/v1/capabilities/`).
