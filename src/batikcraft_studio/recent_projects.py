"""Persistent recent-project history for the desktop File menu."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

RECENT_PROJECT_LIMIT = 10
RECENT_PROJECTS_SCHEMA_VERSION = 1


def default_recent_projects_path() -> Path:
    """Return the per-user recent-project registry path."""

    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    return root / "BatikCraftStudio" / "recent_projects.json"


@dataclass(frozen=True, slots=True)
class RecentProjectEntry:
    """One project shown in the recent-project submenu."""

    path: str
    title: str
    last_opened_at: str

    def __post_init__(self) -> None:
        normalized_path = str(Path(self.path).expanduser())
        normalized_title = str(self.title).strip() or Path(normalized_path).stem
        if len(normalized_title) > 120:
            normalized_title = normalized_title[:120]
        try:
            datetime.fromisoformat(self.last_opened_at)
        except (TypeError, ValueError) as exc:
            raise ValueError("last_opened_at harus berupa waktu ISO-8601.") from exc
        object.__setattr__(self, "path", normalized_path)
        object.__setattr__(self, "title", normalized_title)


class RecentProjectStore:
    """Load and atomically persist a bounded MRU list."""

    def __init__(self, path: str | Path | None = None, *, limit: int = RECENT_PROJECT_LIMIT) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit recent project harus bilangan bulat positif.")
        self.path = Path(path) if path is not None else default_recent_projects_path()
        self.limit = limit
        self.last_error: str | None = None

    def load(self) -> tuple[RecentProjectEntry, ...]:
        """Load valid entries; malformed registries degrade to an empty list."""

        self.last_error = None
        if not self.path.is_file():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Akar recent project harus berupa object JSON.")
            if payload.get("schema_version") != RECENT_PROJECTS_SCHEMA_VERSION:
                raise ValueError("Versi recent project tidak didukung.")
            raw_entries = payload.get("entries")
            if not isinstance(raw_entries, list):
                raise ValueError("entries recent project harus berupa list.")
            entries: list[RecentProjectEntry] = []
            seen: set[str] = set()
            for raw in raw_entries:
                if not isinstance(raw, dict):
                    continue
                try:
                    entry = RecentProjectEntry(
                        path=str(raw["path"]),
                        title=str(raw["title"]),
                        last_opened_at=str(raw["last_opened_at"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                key = _path_key(entry.path)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(entry)
                if len(entries) >= self.limit:
                    break
            return tuple(entries)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.last_error = f"Daftar recent project rusak dan diabaikan: {exc}"
            return ()

    def remember(self, path: str | Path, title: str) -> tuple[RecentProjectEntry, ...]:
        """Move one project to the front of the MRU list."""

        normalized = _normalized_path(path)
        entry = RecentProjectEntry(
            path=str(normalized),
            title=title,
            last_opened_at=datetime.now(UTC).isoformat(),
        )
        key = _path_key(normalized)
        entries = [item for item in self.load() if _path_key(item.path) != key]
        entries.insert(0, entry)
        result = tuple(entries[: self.limit])
        self._save(result)
        return result

    def remove(self, path: str | Path) -> tuple[RecentProjectEntry, ...]:
        """Remove a project path from the registry."""

        key = _path_key(path)
        entries = tuple(item for item in self.load() if _path_key(item.path) != key)
        self._save(entries)
        return entries

    def clear(self) -> None:
        """Clear the registry while keeping a valid empty settings document."""

        self._save(())

    def prune_missing(self) -> tuple[RecentProjectEntry, ...]:
        """Remove entries whose project files no longer exist."""

        current = self.load()
        entries = tuple(item for item in current if Path(item.path).is_file())
        if entries != current:
            self._save(entries)
        return entries

    def _save(self, entries: tuple[RecentProjectEntry, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": RECENT_PROJECTS_SCHEMA_VERSION,
            "entries": [asdict(item) for item in entries[: self.limit]],
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


def _normalized_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def _path_key(value: str | Path) -> str:
    return os.path.normcase(str(_normalized_path(value)))


__all__ = [
    "RECENT_PROJECT_LIMIT",
    "RecentProjectEntry",
    "RecentProjectStore",
    "default_recent_projects_path",
]
