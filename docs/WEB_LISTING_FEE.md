# Creator Listing Fee and VAT on BatikCraftWeb

How BatikCraft Studio adapts to the BatikCraftWeb payment flow.

## Flow Summary

1. The creator signs in from the Studio and uploads a `.batikcraft` file to the web.
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
`ListingFeeRequiredError` carrying the charge breakdown and a `checkout_url`.

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
payment page in a browser and then asks the creator to retry publishing once the status
turns to paid.

## Checking the Cost Before Publishing

```python
quote = client.listing_fee(nft_id)          # estimate; status "not_issued" if not yet raised
invoice = client.issue_listing_fee(nft_id)  # raise the formal invoice
```

The current rates are also exposed in the `billing` block of the server capabilities
endpoint (`GET /api/v1/capabilities/`).
