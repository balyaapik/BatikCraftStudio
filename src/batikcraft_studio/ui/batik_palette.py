"""Named colour swatches commonly used in Indonesian Batik palettes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatikColor:
    """One user-facing Batik colour swatch."""

    name: str
    hex_value: str
    family: str


BATIK_COLORS: tuple[BatikColor, ...] = (
    # Malam, charcoal, and deep outlines.
    BatikColor("Hitam Malam", "#171311", "Malam & Netral"),
    BatikColor("Arang", "#27211D", "Malam & Netral"),
    BatikColor("Cokelat Kehitaman", "#35251D", "Malam & Netral"),
    BatikColor("Abu Jelaga", "#4A4540", "Malam & Netral"),
    BatikColor("Abu Batu", "#6B655F", "Malam & Netral"),
    BatikColor("Taupe", "#8A8178", "Malam & Netral"),
    BatikColor("Pasir", "#B8AA98", "Malam & Netral"),
    BatikColor("Mori", "#E9DDC9", "Malam & Netral"),
    BatikColor("Putih Gading", "#F6EEDC", "Malam & Netral"),
    BatikColor("Putih Mori", "#FFF9EC", "Malam & Netral"),
    # Soga and earth colours.
    BatikColor("Soga Tua", "#3F2418", "Soga & Tanah"),
    BatikColor("Soga Klasik", "#56301F", "Soga & Tanah"),
    BatikColor("Kayu Manis", "#6B3B24", "Soga & Tanah"),
    BatikColor("Cokelat Keraton", "#7A452A", "Soga & Tanah"),
    BatikColor("Tembaga", "#955A32", "Soga & Tanah"),
    BatikColor("Soga Muda", "#AC703E", "Soga & Tanah"),
    BatikColor("Karamel", "#C58A4A", "Soga & Tanah"),
    BatikColor("Kunyit", "#D5A64D", "Soga & Tanah"),
    BatikColor("Emas Tua", "#B68A35", "Soga & Tanah"),
    BatikColor("Emas Batik", "#D2AD57", "Soga & Tanah"),
    BatikColor("Gandum", "#DDC08A", "Soga & Tanah"),
    BatikColor("Krem Soga", "#E9D2AC", "Soga & Tanah"),
    BatikColor("Tanah Liat", "#A65335", "Soga & Tanah"),
    BatikColor("Terakota", "#BF6747", "Soga & Tanah"),
    # Mengkudu, red, and warm floral colours.
    BatikColor("Merah Mengkudu", "#7B1F2B", "Merah & Hangat"),
    BatikColor("Marun Keraton", "#5B1B25", "Merah & Hangat"),
    BatikColor("Merah Bata", "#963B32", "Merah & Hangat"),
    BatikColor("Merah Lasem", "#B53C43", "Merah & Hangat"),
    BatikColor("Merah Delima", "#C84E55", "Merah & Hangat"),
    BatikColor("Korál", "#D96E5B", "Merah & Hangat"),
    BatikColor("Salem", "#E49A7E", "Merah & Hangat"),
    BatikColor("Merah Jambu Pudar", "#D8A0A0", "Merah & Hangat"),
    BatikColor("Ungu Manggis", "#56324E", "Merah & Hangat"),
    BatikColor("Ungu Terong", "#704263", "Merah & Hangat"),
    # Indigo, coastal blue, and Mega Mendung tones.
    BatikColor("Nila Pekat", "#17263F", "Nila & Pesisir"),
    BatikColor("Indigo", "#203A5C", "Nila & Pesisir"),
    BatikColor("Biru Keraton", "#294A6D", "Nila & Pesisir"),
    BatikColor("Biru Laut Tua", "#315B7D", "Nila & Pesisir"),
    BatikColor("Biru Mega Mendung", "#3E7194", "Nila & Pesisir"),
    BatikColor("Biru Pesisir", "#5689A6", "Nila & Pesisir"),
    BatikColor("Biru Kabut", "#7FA8B9", "Nila & Pesisir"),
    BatikColor("Biru Kelabu", "#A8C0C7", "Nila & Pesisir"),
    BatikColor("Turkis Tua", "#176B70", "Nila & Pesisir"),
    BatikColor("Turkis Pesisir", "#2F8C8B", "Nila & Pesisir"),
    BatikColor("Toska Muda", "#6FAEAA", "Nila & Pesisir"),
    BatikColor("Hijau Laut", "#3C7B73", "Nila & Pesisir"),
    # Natural greens.
    BatikColor("Hijau Lumut Tua", "#263F32", "Hijau Alam"),
    BatikColor("Hijau Daun", "#355D45", "Hijau Alam"),
    BatikColor("Hijau Jati", "#4B7253", "Hijau Alam"),
    BatikColor("Hijau Lumut", "#637F59", "Hijau Alam"),
    BatikColor("Hijau Zaitun", "#7C8750", "Hijau Alam"),
    BatikColor("Hijau Sage", "#91A17D", "Hijau Alam"),
    BatikColor("Hijau Pucat", "#B8C3A2", "Hijau Alam"),
    BatikColor("Daun Kering", "#9A8B53", "Hijau Alam"),
    # Accent colours used by contemporary and coastal Batik.
    BatikColor("Kuning Gading", "#E8CF76", "Aksen Pesisir"),
    BatikColor("Kuning Kenanga", "#E6B94C", "Aksen Pesisir"),
    BatikColor("Jingga Pesisir", "#D67A3E", "Aksen Pesisir"),
    BatikColor("Oranye Sogan", "#C56634", "Aksen Pesisir"),
    BatikColor("Ungu Pesisir", "#7A557D", "Aksen Pesisir"),
    BatikColor("Lavender Kelabu", "#9D84A0", "Aksen Pesisir"),
    BatikColor("Merah Muda Pesisir", "#D8888E", "Aksen Pesisir"),
    BatikColor("Peach", "#E7AD8D", "Aksen Pesisir"),
    BatikColor("Biru Ungu", "#46547C", "Aksen Pesisir"),
    BatikColor("Hijau Giok", "#3F806B", "Aksen Pesisir"),
)

BATIK_PALETTE_HEX: tuple[str, ...] = tuple(color.hex_value for color in BATIK_COLORS)


__all__ = ["BATIK_COLORS", "BATIK_PALETTE_HEX", "BatikColor"]
