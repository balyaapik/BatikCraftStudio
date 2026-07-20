"""(Dihapus) Patch jendela dependensi lama.

Jendela Dependency Manager berbasis tombol telah digantikan Pusat
Dependensi berbasis tabel bercentang (``ui/dependency_center.py``),
sehingga patch tombol/label lama tidak lagi berlaku. Fungsi dipertahankan
sebagai no-op agar urutan pemasangan di ``__main__`` tetap utuh.
"""

from __future__ import annotations


def install_dependency_profiles_patch() -> None:
    """Tidak ada operasi: lihat ui/dependency_center.py."""


__all__ = ["install_dependency_profiles_patch"]
