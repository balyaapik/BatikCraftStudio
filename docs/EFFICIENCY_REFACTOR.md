# Catatan Refactor Efisiensi (Juli 2026)

## Performa canvas & rendering objek

1. **Memoisasi digest aset** (`imaging/tile_cache.py`, `imaging/safe_viewport_renderer.py`).
   SHA-1 seluruh bytes aset sebelumnya dihitung ulang untuk setiap objek, setiap tile,
   setiap frame (baik untuk `ObjectRenderCacheKey` maupun `project_visual_fingerprint`).
   Kini digest di-cache berdasarkan identitas objek bytes (aman karena aset immutable;
   cache memegang strong reference sehingga `id()` tidak mungkin dipakai ulang).
   Digest `repr(layer)` juga dimemoisasi per identitas layer (layer adalah frozen dataclass).

2. **PhotoImage tidak dibuat ulang untuk tile yang tidak berubah**
   (`_apply_screen_tiles` di layer hotfix v1, `_apply_tiles` di `viewport_editor.py`).
   Cache hit renderer mengembalikan objek PIL yang sama; konversi PIL→Tk (salin piksel penuh)
   kini dilewati jika gambar identik sudah tampil, dan grid/seleksi/ruler hanya digambar
   ulang jika ada perubahan nyata.

3. **Pembuangan kerja mati** (`viewport_editor.py`): baris revisi ganda dihapus, dan
   `ImageTk.PhotoImage` hasil stitching preview yang tidak pernah ditampilkan tidak lagi dibuat.

## Konsolidasi struktur

- 15 file `ui/context_tool_editor_hotfix*.py` digabung menjadi
  **`ui/context_tool_editor_hotfixes.py`** dengan urutan layer & semantik override identik.
  File lama menjadi shim impor (kompatibel dengan test dan kode lain).
- 8 varian `*MainWindow` digabung menjadi satu kelas **`ui/main_window.MainWindow`**;
  nama lama tetap tersedia sebagai alias.
- 10 file `ui/*_i18n.py` digabung ke katalog `_FEATURE_TRANSLATIONS` di
  **`batikcraft_studio/i18n.py`** (tanpa konflik kunci); fungsi `install_*_translations`
  lama menjadi no-op shim.

## Pekerjaan lanjutan yang disarankan

- Inline `dependency_integrity_patch` + `dependency_profiles_patch` ke
  `dependency_manager_dialog`, dan `ai_menu_consolidation_patch` ke aplikasi—wrapper
  berantai yang urut instalasinya penting, sebaiknya dilakukan sambil menjalankan GUI.
- Meratakan rantai editor `*WorkspaceView` (masih ±25 kelas linier) menjadi mixin per fitur.
- Satu sumber kebenaran profil dependensi dari `pyproject.toml` optional-dependencies.
- Pertimbangkan counter revisi monoton di session menggantikan fingerprint hash per-kick.
