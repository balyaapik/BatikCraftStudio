"""Analisis ekonomi NFT: riwayat harga dari web bridge dan menu marketplace."""

from __future__ import annotations

import inspect

from batikcraft_studio.web_bridge import BatikCraftWebClient


def test_price_history_sorts_and_normalizes_bid_amounts() -> None:
    client = BatikCraftWebClient.__new__(BatikCraftWebClient)
    client.nft_bids = lambda nft_id: [  # type: ignore[method-assign]
        {"amount": "150000", "created_at": "2026-07-02T10:00:00"},
        {"amount": "125,000", "created_at": "2026-07-01T09:00:00"},
        {"price": 200000, "timestamp": "2026-07-03T12:00:00"},
        {"amount": "bukan-angka", "created_at": "2026-07-04T00:00:00"},
    ]

    history = BatikCraftWebClient.nft_price_history(client, 7)

    assert [amount for _stamp, amount in history] == [125000.0, 150000.0, 200000.0]
    assert history[0][0].startswith("2026-07-01")


def test_marketplace_menu_exposes_nft_economics_window() -> None:
    from batikcraft_studio import batikbrew_context_tool_app as app

    source = inspect.getsource(app)
    assert "Analisis Ekonomi NFT…" in source
    assert "NFTEconomicsWindow" in source


def test_economics_window_module_renders_price_chart() -> None:
    from batikcraft_studio.ui import nft_economics_dialog

    source = inspect.getsource(nft_economics_dialog)
    assert "nft_price_history" in source
    assert "_draw_line_chart" in source
    assert "Tren" in source
