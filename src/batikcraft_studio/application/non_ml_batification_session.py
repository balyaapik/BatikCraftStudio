"""(Dihapus) Sesi batifikasi tanpa model.

Fitur batifikasi non-model telah dihapus: semua batifikasi harus melalui
model (Stable Diffusion lokal atau provider cloud). Kelas ini dipertahankan
kosong sebagai mata rantai warisan sesi dan kompatibilitas impor.
"""

from __future__ import annotations

from .hotfix_session_v2 import FinalHotfixProjectSession


class NonMLBatificationProjectSession(FinalHotfixProjectSession):
    """Passthrough: tidak ada lagi operasi batifikasi tanpa model."""


__all__ = ["NonMLBatificationProjectSession"]
