from __future__ import annotations

import inspect
import json
import tomllib
import zipfile
from pathlib import Path

import pytest

from batikcraft_studio import batikbrew_context_tool_app
from batikcraft_studio.web_bridge import (
    BatikCraftWebError,
    inspect_model_pack,
    normalize_base_url,
)


def test_normalize_web_base_url_removes_api_suffix() -> None:
    assert normalize_base_url("https://example.com/api/v1/") == "https://example.com"
    assert normalize_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"


def test_normalize_web_base_url_rejects_invalid_value() -> None:
    with pytest.raises(BatikCraftWebError):
        normalize_base_url("example.com")


def test_inspect_model_pack_reads_manifest(tmp_path) -> None:
    path = tmp_path / "ornament.batikmodel"
    manifest = {
        "format": "batikcraft-model-pack",
        "model": {
            "model_id": "ornament-v1",
            "name": "Ornament V1",
            "version": "1.0.0",
            "base_model_family": "sdxl",
            "trigger_words": ["bcr_ornament"],
            "capabilities": ["ornament"],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))

    assert inspect_model_pack(path)["model"]["model_id"] == "ornament-v1"


def test_marketplace_menu_exposes_account_and_marketplace_actions() -> None:
    source = inspect.getsource(batikbrew_context_tool_app.ContextToolApplication)
    assert "marketplace_menu =" in source
    assert "Login / Akun BatikCraftWeb" in source
    assert "NFT Marketplace" in source
    assert "Model Marketplace" in source
    assert "Mint & Publish Project Aktif sebagai NFT" in source
    assert "Jual Model ke Marketplace" in source
    assert '_insert_before_help(menu_bar, "Marketplace", marketplace_menu)' in source


# ---------------------------------------------------------------------------
# Fee bidding creator (BatikCraftWeb menolak publish sebelum fee lunas)
# ---------------------------------------------------------------------------


def _fee_payload() -> dict:
    return {
        "detail": "Fee bidding harus dilunasi sebelum NFT tayang di market.",
        "listing_fee": {
            "status": "pending",
            "invoice_number": "BCFEE-20260727-A1B2C3D4E5",
            "currency": "IDR",
            "base_amount": "200000.00",
            "fee_percent": "5.00",
            "fee_amount": "10000.00",
            "vat_percent": "11.00",
            "vat_amount": "1100.00",
            "total_amount": "11100.00",
            "checkout_url": "https://web.batikcraft.id/payments/nfts/12/listing-fee/checkout/",
            "refundable": False,
        },
    }


def _raise_http_error(code: int, payload: dict):
    import io
    import urllib.error

    def _fake(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "error",
            {},
            io.BytesIO(json.dumps(payload).encode("utf-8")),
        )

    return _fake


def test_publish_without_paid_fee_raises_listing_fee_required(monkeypatch) -> None:
    import urllib.request

    from batikcraft_studio.web_bridge import BatikCraftWebClient, ListingFeeRequiredError

    client = BatikCraftWebClient(base_url="https://web.batikcraft.id", token="tok")
    monkeypatch.setattr(
        urllib.request, "urlopen", _raise_http_error(402, _fee_payload())
    )

    with pytest.raises(ListingFeeRequiredError) as excinfo:
        client._request_json("POST", "nfts/12/publish/", payload={})

    error = excinfo.value
    assert error.total_amount == "11100.00"
    assert error.checkout_url.endswith("/listing-fee/checkout/")
    assert error.fee["vat_percent"] == "11.00"
    assert error.fee["refundable"] is False


def test_listing_fee_summary_shows_fee_vat_and_non_refundable_note() -> None:
    from batikcraft_studio.web_bridge import ListingFeeRequiredError

    payload = _fee_payload()
    error = ListingFeeRequiredError(payload["detail"], payload["listing_fee"])

    summary = error.summary()

    assert "Rp200.000" in summary
    assert "Fee bidding (5.00%): Rp10.000" in summary
    assert "PPN (11.00%): Rp1.100" in summary
    assert "Total dibayar: Rp11.100" in summary
    assert "tidak dikembalikan" in summary


def test_other_http_errors_are_not_treated_as_listing_fee(monkeypatch) -> None:
    import urllib.request

    from batikcraft_studio.web_bridge import BatikCraftWebClient, ListingFeeRequiredError

    client = BatikCraftWebClient(base_url="https://web.batikcraft.id", token="tok")
    monkeypatch.setattr(
        urllib.request, "urlopen", _raise_http_error(400, {"detail": "harga kosong"})
    )

    with pytest.raises(BatikCraftWebError) as excinfo:
        client._request_json("POST", "nfts/12/publish/", payload={})

    assert not isinstance(excinfo.value, ListingFeeRequiredError)
    assert "harga kosong" in str(excinfo.value)


def test_client_exposes_listing_fee_endpoints() -> None:
    from batikcraft_studio.web_bridge import BatikCraftWebClient

    assert callable(BatikCraftWebClient.listing_fee)
    assert callable(BatikCraftWebClient.issue_listing_fee)


def test_format_rupiah_uses_indonesian_separator() -> None:
    from batikcraft_studio.web_bridge import format_rupiah

    assert format_rupiah("200000.00") == "200.000"
    assert format_rupiah("11100.00") == "11.100"


def test_listing_fee_retry_recovers_existing_draft_id() -> None:
    from batikcraft_studio.ui.marketplace_mint_dialog import _listing_fee_nft_id
    from batikcraft_studio.web_bridge import ListingFeeRequiredError

    payload = _fee_payload()
    error = ListingFeeRequiredError(payload["detail"], payload["listing_fee"])
    assert _listing_fee_nft_id(error) == 12

    payload["listing_fee"]["nft_id"] = 27
    error = ListingFeeRequiredError(payload["detail"], payload["listing_fee"])
    assert _listing_fee_nft_id(error) == 27


def test_marketplace_dialog_rows_do_not_overlap() -> None:
    from batikcraft_studio.ui.marketplace_mint_dialog import MintCurrentProjectDialog

    source = inspect.getsource(MintCurrentProjectDialog._build)
    assert "self.philosophy_text.grid(row=10" in source
    assert ").grid(row=11, column=0, columnspan=2" in source
    assert ").grid(row=12, column=0, columnspan=2" in source
    assert "actions.grid(row=13" in source


def test_async_error_callbacks_bind_messages_before_after_runs() -> None:
    from batikcraft_studio.ui import asset_pack_studio_dialog, nft_economics_dialog

    asset_source = inspect.getsource(asset_pack_studio_dialog.AssetPackStudioWindow.sell_pack)
    economics_source = inspect.getsource(nft_economics_dialog.NFTEconomicsWindow._load_nfts)

    assert "except ListingFeeRequiredError as exc" in asset_source
    assert "lambda message=str(exc)" in asset_source
    assert "lambda message=str(exc)" in economics_source


def test_windows_timezone_database_is_declared() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject["project"]["dependencies"]
    assert any(
        dependency.startswith("tzdata") and "win32" in dependency
        for dependency in dependencies
    )


# ---------------------------------------------------------------------------
# Zona waktu batas lelang
# ---------------------------------------------------------------------------


def test_local_input_gets_explicit_offset() -> None:
    from batikcraft_studio.auction_time import local_input_to_iso

    assert local_input_to_iso("2026-08-01 17:00", "Asia/Jakarta") == (
        "2026-08-01T17:00:00+07:00"
    )
    # Makassar berbeda satu jam dari Jakarta; offset harus ikut berubah.
    assert local_input_to_iso("2026-08-01 17:00", "Asia/Makassar") == (
        "2026-08-01T17:00:00+08:00"
    )


def test_input_that_already_has_offset_is_left_alone() -> None:
    from batikcraft_studio.auction_time import local_input_to_iso

    value = "2026-08-01T17:00:00+09:00"
    assert local_input_to_iso(value, "Asia/Jakarta") == value


def test_blank_deadline_stays_blank() -> None:
    from batikcraft_studio.auction_time import local_input_to_iso

    assert local_input_to_iso("", "Asia/Jakarta") == ""
    assert local_input_to_iso("   ", "Asia/Jakarta") == ""


def test_unparseable_deadline_is_rejected() -> None:
    from batikcraft_studio.auction_time import AuctionTimeError, local_input_to_iso

    with pytest.raises(AuctionTimeError):
        local_input_to_iso("besok sore", "Asia/Jakarta")


def test_unknown_timezone_is_rejected() -> None:
    from batikcraft_studio.auction_time import AuctionTimeError, local_input_to_iso

    with pytest.raises(AuctionTimeError):
        local_input_to_iso("2026-08-01 17:00", "Mars/Olympus")


def test_timezone_preference_round_trip(tmp_path) -> None:
    from batikcraft_studio.auction_time import TimezonePreference

    store = TimezonePreference(tmp_path / "config.json")
    store.save("Asia/Makassar")

    assert TimezonePreference(tmp_path / "config.json").load() == "Asia/Makassar"


def test_timezone_preference_ignores_corrupt_config(tmp_path) -> None:
    from batikcraft_studio.auction_time import TimezonePreference, is_valid_timezone

    path = tmp_path / "config.json"
    path.write_text("{ bukan json", encoding="utf-8")

    assert is_valid_timezone(TimezonePreference(path).load())


def test_normalize_auction_deadline_wraps_errors_as_web_error() -> None:
    from batikcraft_studio.web_bridge import normalize_auction_deadline

    with pytest.raises(BatikCraftWebError):
        normalize_auction_deadline("besok sore", "Asia/Jakarta")
