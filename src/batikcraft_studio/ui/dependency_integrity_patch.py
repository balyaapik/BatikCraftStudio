"""Make model installation state depend on validated files, not folder existence.

A failed Hugging Face download can leave a non-empty destination directory. The
Dependency Center previously interpreted that directory as an installed model,
forced its progress to 100%, and ended the whole batch with a generic success
message. This patch keeps resumable partial files but reports them as incomplete,
checks remaining disk space again before download, and preserves failed batch state.
"""

from __future__ import annotations

from pathlib import Path

_INSTALLED = False
_GIB = 1024**3
_MIN_MODEL_WORKSPACE = 2 * _GIB


def _folder_has_content(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(folder.iterdir())
    except OSError:
        return False


def _folder_size(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    total = 0
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _model_folder(item: object) -> Path:
    from batikcraft_studio.ui import dependency_catalog as catalog

    return catalog.managed_runtime_root() / str(getattr(item, "folder", ""))


def _model_validation_issues(item: object) -> list[str]:
    """Return validation problems for a managed model; an empty list means ready."""

    from batikcraft_studio.ai.runtime_model_installer import (
        RuntimeModelInstallError,
        runtime_model_paths,
        validate_runtime_models,
    )
    from batikcraft_studio.ui import dependency_catalog as catalog

    folder = _model_folder(item)
    if not _folder_has_content(folder):
        return ["Folder model belum berisi file model yang lengkap."]

    key = str(getattr(item, "key", ""))
    try:
        if key == "sdxl":
            from batikcraft_studio.ai.sdxl_runtime_integrity import (
                inspect_batikbrew_runtime,
            )

            return [str(issue) for issue in inspect_batikbrew_runtime(folder)]
        if key == "sd15":
            validate_runtime_models(runtime_model_paths(catalog.managed_runtime_root()))
            return []
    except RuntimeModelInstallError as exc:
        return [line.strip() for line in str(exc).splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001 - validation failure must be visible
        return [f"Validasi model gagal dijalankan: {exc}"]
    return ["Validator kelengkapan untuk model ini belum tersedia."]


def _model_is_complete(item: object) -> bool:
    return not _model_validation_issues(item)


def _partial_model_fraction(item: object) -> float:
    if _model_is_complete(item):
        return 1.0
    expected = max(1, int(getattr(item, "size_bytes", 0) or 0))
    fraction = _folder_size(_model_folder(item)) / expected
    return max(0.0, min(0.99, fraction))


def _remaining_model_workspace(item: object) -> int:
    """Estimate remaining bytes plus extraction workspace for a resumable model."""

    if _model_is_complete(item):
        return 0
    expected = max(0, int(getattr(item, "size_bytes", 0) or 0))
    existing = _folder_size(_model_folder(item))
    remaining = max(0, expected - existing)
    return max(_MIN_MODEL_WORKSPACE, int(remaining * 1.15))


def install_dependency_integrity_patch() -> None:
    """Patch the active Dependency Center with fail-closed model validation."""

    global _INSTALLED
    if _INSTALLED:
        return

    from batikcraft_studio.ui import dependency_catalog as catalog
    from batikcraft_studio.ui import dependency_center as center

    original_is_installed = catalog.is_installed
    original_installed_fraction = catalog.installed_fraction
    original_integrity_status = catalog.integrity_status
    original_eligibility = catalog.eligibility
    original_install_model = center.DependencyCenterWindow._install_model

    def is_installed(item: catalog.DependencyItem) -> bool:
        if item.kind == catalog.KIND_MODEL:
            return _model_is_complete(item)
        return original_is_installed(item)

    def installed_fraction(item: catalog.DependencyItem) -> float:
        if item.kind == catalog.KIND_MODEL:
            return _partial_model_fraction(item)
        return original_installed_fraction(item)

    def integrity_status(item: catalog.DependencyItem) -> tuple[str, str]:
        if item.kind != catalog.KIND_MODEL:
            return original_integrity_status(item)
        folder = _model_folder(item)
        if not _folder_has_content(folder):
            return "Belum terpasang", ""
        issues = _model_validation_issues(item)
        if not issues:
            return "Terpasang", ""
        detail = "; ".join(issues[:3])
        return (
            "PERLU REPARASI",
            "Unduhan model parsial atau rusak. " + detail,
        )

    def eligibility(item: catalog.DependencyItem) -> tuple[bool, str]:
        if item.kind != catalog.KIND_MODEL:
            return original_eligibility(item)
        free = catalog.free_disk_bytes()
        needed = _remaining_model_workspace(item)
        if free and needed and free < needed:
            return False, (
                f"Ruang disk kurang untuk melanjutkan: butuh ±{needed / _GIB:.1f} GB, "
                f"tersedia {free / _GIB:.1f} GB. File parsial tetap disimpan."
            )
        return True, "Kompatibel; unduhan parsial dapat dilanjutkan."

    def install_model(self: object, item: catalog.DependencyItem) -> None:
        free = catalog.free_disk_bytes()
        needed = _remaining_model_workspace(item)
        if free and needed and free < needed:
            raise RuntimeError(
                f"Ruang disk tidak cukup untuk {item.name}: diperlukan sekitar "
                f"{needed / _GIB:.1f} GB, tersedia {free / _GIB:.1f} GB. "
                "Bersihkan ruang lalu jalankan lagi; file parsial tidak dihapus."
            )
        original_install_model(self, item)
        issues = _model_validation_issues(item)
        if issues:
            detail = "; ".join(issues[:3])
            raise RuntimeError(
                "Pengunduh berhenti tanpa menghasilkan model yang lengkap. " + detail
            )

    def install_worker(self: object, items: list[catalog.DependencyItem]) -> None:
        failures: list[str] = []
        succeeded = 0
        for index, item in enumerate(items, start=1):
            self._messages.put(("active", item.key))
            self._messages.put(
                ("status", f"[{index}/{len(items)}] Memasang {item.name}…")
            )
            try:
                if item.kind == center.KIND_MODEL:
                    self._install_model(item)
                else:
                    self._install_packages(item)
            except Exception as exc:  # noqa: BLE001 - report exact installer failure
                failures.append(item.name)
                self._messages.put(("log", f"GAGAL {item.name}: {exc}"))
                self._messages.put(("error", f"{item.name} gagal dipasang: {exc}"))
                self._messages.put(
                    ("progress", (item.key, installed_fraction(item)))
                )
                continue
            succeeded += 1
            self._messages.put(("log", f"Selesai dan tervalidasi: {item.name}"))
            self._messages.put(("progress", (item.key, 1.0)))
        self._messages.put(("active", None))
        self._messages.put(
            (
                "done",
                {
                    "total": len(items),
                    "succeeded": succeeded,
                    "failures": failures,
                },
            )
        )

    def poll_messages(self: object) -> None:
        try:
            while True:
                kind, payload = self._messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_value.set(str(payload))
                elif kind == "progress" and isinstance(payload, tuple):
                    key, fraction = payload
                    self._live_fraction[str(key)] = float(fraction)
                    self._update_row_progress(str(key), float(fraction))
                elif kind == "active":
                    self._active_key = str(payload) if payload else None
                elif kind == "error":
                    center.messagebox.showerror(self.title(), str(payload), parent=self)
                elif kind == "done":
                    result = payload if isinstance(payload, dict) else {}
                    total = max(0, int(result.get("total", 0) or 0))
                    succeeded = max(0, int(result.get("succeeded", 0) or 0))
                    failures = list(result.get("failures", []) or [])
                    self._set_busy(False)
                    if failures:
                        self.status_value.set(
                            f"Instalasi selesai dengan {len(failures)} kegagalan. "
                            "Status model parsial tidak dianggap berhasil."
                        )
                        percent = (succeeded / total * 100.0) if total else 0.0
                        self.overall_progress.configure(value=percent)
                    else:
                        self.status_value.set(
                            "Selesai. Semua komponen berhasil dipasang dan divalidasi."
                        )
                        self.overall_progress.configure(value=100)
                    try:
                        center.activate_managed_ai_packages()
                    except Exception:  # noqa: BLE001 - refresh must still run
                        pass
                    self._live_fraction.clear()
                    self.refresh()
        except center.queue.Empty:
            pass
        try:
            self.after(150, self._poll_messages)
        except center.tk.TclError:
            pass

    catalog.is_installed = is_installed
    catalog.installed_fraction = installed_fraction
    catalog.integrity_status = integrity_status
    catalog.eligibility = eligibility
    center.is_installed = is_installed
    center.installed_fraction = installed_fraction
    center.integrity_status = integrity_status
    center.eligibility = eligibility
    center.DependencyCenterWindow._install_model = install_model
    center.DependencyCenterWindow._install_worker = install_worker
    center.DependencyCenterWindow._poll_messages = poll_messages
    center.DependencyCenterWindow._batikcraft_model_integrity_guard = True
    _INSTALLED = True


__all__ = [
    "install_dependency_integrity_patch",
]
