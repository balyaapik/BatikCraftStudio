"""Dialog fee bidding creator sebelum karya tayang di BatikCraftWeb.

BatikCraftWeb menolak publish selama fee bidding belum lunas. Fee dihitung dari
persentase harga terendah yang dicantumkan creator, ditambah PPN, dan tidak
dikembalikan walaupun karya tidak terjual. Modul ini menampilkan rinciannya dan
mengarahkan creator ke halaman pembayaran.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox

from batikcraft_studio.web_bridge import ListingFeeRequiredError, format_rupiah

__all__ = ["handle_listing_fee_required", "format_listing_fee"]


def format_listing_fee(fee: dict) -> str:
    """Ringkasan rincian fee untuk ditampilkan di UI."""
    if not fee:
        return "Rincian fee belum tersedia."
    return (
        f"Harga terendah: Rp{format_rupiah(fee.get('base_amount'))}\n"
        f"Fee bidding ({fee.get('fee_percent', '-')}%): "
        f"Rp{format_rupiah(fee.get('fee_amount'))}\n"
        f"PPN ({fee.get('vat_percent', '-')}%): "
        f"Rp{format_rupiah(fee.get('vat_amount'))}\n"
        f"Total dibayar: Rp{format_rupiah(fee.get('total_amount'))}"
    )


def handle_listing_fee_required(
    parent: tk.Misc | None,
    error: ListingFeeRequiredError,
) -> bool:
    """Tampilkan tagihan fee dan buka halaman pembayaran bila creator setuju.

    Mengembalikan True jika halaman pembayaran dibuka.
    """
    checkout_url = error.checkout_url
    if not checkout_url:
        messagebox.showerror("Fee bidding belum lunas", error.summary(), parent=parent)
        return False

    proceed = messagebox.askyesno(
        "Fee bidding belum lunas",
        f"{error.summary()}\n\nBuka halaman pembayaran sekarang?",
        parent=parent,
    )
    if not proceed:
        return False
    webbrowser.open(checkout_url, new=2)
    messagebox.showinfo(
        "Selesaikan pembayaran",
        (
            "Selesaikan pembayaran di browser, lalu ulangi publish dari Studio "
            "setelah statusnya menjadi lunas."
        ),
        parent=parent,
    )
    return True
