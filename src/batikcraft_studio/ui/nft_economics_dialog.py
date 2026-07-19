"""Jendela analisis ekonomi NFT: grafik pergerakan harga dan ringkasan pasar."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any

from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError

from .theme import COLORS

_CHART_W = 560
_CHART_H = 300
_MARGIN = 44


def _format_rupiah(value: float) -> str:
    return f"Rp{value:,.0f}".replace(",", ".")


class NFTEconomicsWindow(tk.Toplevel):
    """Tampilkan grafik harga bid NFT dari BatikCraftWeb seperti analisis NFT umum."""

    def __init__(self, parent: tk.Misc, client: BatikCraftWebClient) -> None:
        super().__init__(parent)
        self.title("Analisis Ekonomi NFT — BatikCraftWeb")
        self.client = client
        self.resizable(False, False)
        self._nfts: list[dict[str, Any]] = []
        self._history: list[tuple[str, float]] = []

        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="NFT:").grid(row=0, column=0, sticky="w")
        self.nft_value = tk.StringVar(master=self)
        self.nft_combo = ttk.Combobox(
            body, textvariable=self.nft_value, state="readonly", width=44
        )
        self.nft_combo.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        self.nft_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_history())
        ttk.Button(body, text="Muat Ulang", command=self._load_nfts).grid(
            row=0, column=2, sticky="e"
        )

        self.chart = tk.Canvas(
            body,
            width=_CHART_W,
            height=_CHART_H,
            background="#FFFDF8",
            highlightthickness=1,
            highlightbackground=COLORS.get("muted_ink", "#8A8073"),
        )
        self.chart.grid(row=1, column=0, columnspan=3, pady=(10, 8))

        self.summary_value = tk.StringVar(master=self, value="Memuat data pasar…")
        ttk.Label(
            body,
            textvariable=self.summary_value,
            justify="left",
            wraplength=_CHART_W,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        self._load_nfts()

    # ------------------------------------------------------------------
    def _load_nfts(self) -> None:
        def worker() -> None:
            try:
                items = self.client.list_nfts()
            except BatikCraftWebError as exc:
                self.after(0, lambda: self._show_message(str(exc)))
                return
            self.after(0, lambda: self._apply_nfts(items))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_nfts(self, items: list[dict[str, Any]]) -> None:
        if not self.winfo_exists():
            return
        self._nfts = items
        labels = [
            f"#{item.get('id')} — {item.get('title') or 'NFT'} "
            f"({_format_rupiah(_to_float(item.get('current_price')))})"
            for item in items
        ]
        self.nft_combo.configure(values=labels)
        if labels:
            self.nft_combo.current(0)
            self._load_history()
        else:
            self._show_message("Belum ada NFT di marketplace.")

    def _selected_nft(self) -> dict[str, Any] | None:
        index = self.nft_combo.current()
        if 0 <= index < len(self._nfts):
            return self._nfts[index]
        return None

    def _load_history(self) -> None:
        nft = self._selected_nft()
        if nft is None:
            return
        nft_id = int(nft.get("id") or 0)

        def worker() -> None:
            try:
                points = self.client.nft_price_history(nft_id)
            except BatikCraftWebError:
                points = []
            self.after(0, lambda: self._render(nft, points))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _render(self, nft: dict[str, Any], points: list[tuple[str, float]]) -> None:
        if not self.winfo_exists():
            return
        self._history = points
        chart = self.chart
        chart.delete("all")

        start_price = _to_float(nft.get("starting_price"))
        current = _to_float(nft.get("current_price"))
        values = [amount for _stamp, amount in points]
        if start_price > 0:
            values = [start_price, *values]
        if not values:
            values = [current] if current > 0 else []

        if len(values) < 2:
            self._draw_placeholder(
                "Belum ada riwayat bid untuk NFT ini.\n"
                "Grafik akan terisi setelah ada penawaran."
            )
        else:
            self._draw_line_chart(values)

        # Ringkasan ekonomi
        if values:
            lowest, highest = min(values), max(values)
            first, last = values[0], values[-1]
            change = ((last - first) / first * 100) if first else 0.0
            trend = "naik" if change > 0 else "turun" if change < 0 else "stabil"
            self.summary_value.set(
                f"Harga awal {_format_rupiah(first)}  •  Harga kini {_format_rupiah(last)}\n"
                f"Terendah {_format_rupiah(lowest)}  •  Tertinggi {_format_rupiah(highest)}\n"
                f"Jumlah bid: {int(nft.get('bid_count') or len(points))}  •  "
                f"Tren: {trend} {abs(change):.1f}%  •  "
                f"Lelang {'terbuka' if nft.get('is_auction_open') else 'tutup'}"
            )
        else:
            self.summary_value.set("Belum ada data harga untuk NFT ini.")

    def _draw_placeholder(self, message: str) -> None:
        self.chart.create_text(
            _CHART_W / 2,
            _CHART_H / 2,
            text=message,
            fill=COLORS.get("muted_ink", "#8A8073"),
            justify="center",
            font=("Segoe UI", 11),
        )

    def _draw_line_chart(self, values: list[float]) -> None:
        chart = self.chart
        lo, hi = min(values), max(values)
        span = (hi - lo) or max(hi, 1.0) * 0.1
        lo -= span * 0.08
        hi += span * 0.08
        plot_w = _CHART_W - _MARGIN - 12
        plot_h = _CHART_H - 2 * 24

        def to_xy(index: int, value: float) -> tuple[float, float]:
            x = _MARGIN + plot_w * (index / (len(values) - 1))
            y = 24 + plot_h * (1 - (value - lo) / (hi - lo))
            return x, y

        # sumbu + garis bantu
        axis = COLORS.get("muted_ink", "#8A8073")
        for i in range(5):
            gy = 24 + plot_h * i / 4
            gval = hi - (hi - lo) * i / 4
            chart.create_line(_MARGIN, gy, _CHART_W - 12, gy, fill="#E7DFD2")
            chart.create_text(
                _MARGIN - 6, gy, text=_format_rupiah(gval), anchor="e",
                fill=axis, font=("Segoe UI", 8),
            )
        chart.create_line(_MARGIN, 24, _MARGIN, 24 + plot_h, fill=axis)
        chart.create_line(_MARGIN, 24 + plot_h, _CHART_W - 12, 24 + plot_h, fill=axis)

        rising = values[-1] >= values[0]
        line_color = "#16A34A" if rising else "#DC2626"
        coords: list[float] = []
        for index, value in enumerate(values):
            coords.extend(to_xy(index, value))
        chart.create_line(*coords, fill=line_color, width=2, smooth=False)
        for index, value in enumerate(values):
            x, y = to_xy(index, value)
            chart.create_oval(x - 3, y - 3, x + 3, y + 3, fill=line_color, outline="")

    def _show_message(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self.chart.delete("all")
        self._draw_placeholder(message)
        self.summary_value.set(message)


def _to_float(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


__all__ = ["NFTEconomicsWindow"]
