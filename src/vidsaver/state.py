"""SQLite catalog of videos we have seen.

Identity is sample-hash ``content_id``. Paths are not stored; each launch
re-hashes whatever ``scan`` found. Rotation still keeps offsets in memory.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vidsaver.config import APP_NAME
from vidsaver.fingerprint import FingerprintError, content_id_for


class StateError(Exception):
    """The catalog could not be opened or updated."""


@dataclass(frozen=True)
class VideoRow:
    content_id: str
    size_bytes: int
    updated_at: str


def default_db_path() -> Path:
    """``$XDG_STATE_HOME/vidsaver/vidsaver.sqlite``, or ``~/.local/state/...``."""
    xdg = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return root / APP_NAME / "vidsaver.sqlite"


class Catalog:
    """Open or create the catalog. ``sync_catalog`` is the public entry."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    content_id TEXT PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(f"Cannot open catalog {db_path}: {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _resolve(self, path: Path) -> str:
        """Hash *path* and insert ``content_id`` if we have not seen it."""
        path = path.expanduser().resolve()
        try:
            content_id = content_id_for(path)
            size_bytes = path.stat().st_size
        except (FingerprintError, OSError) as exc:
            raise StateError(f"Cannot read {path}: {exc}") from exc

        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                """
                INSERT INTO videos (content_id, size_bytes, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (content_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (content_id, size_bytes, now),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(f"Cannot update catalog for {path}: {exc}") from exc
        return content_id

    def rows(self) -> list[VideoRow]:
        cur = self._conn.execute(
            "SELECT content_id, size_bytes, updated_at FROM videos"
        )
        return [
            VideoRow(
                content_id=str(content_id),
                size_bytes=int(size_bytes),
                updated_at=str(updated_at),
            )
            for content_id, size_bytes, updated_at in cur.fetchall()
        ]


def sync_catalog(paths: list[Path], db_path: Path | None = None) -> None:
    """Record a content id for every scanned file."""
    with Catalog(db_path or default_db_path()) as catalog:
        for path in paths:
            catalog._resolve(path)
