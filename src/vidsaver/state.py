"""SQLite catalog of videos we have seen, plus playback offsets.

Identity is sample-hash ``content_id``. Paths are not stored; each launch
re-hashes whatever ``scan`` found and maps those paths in memory.
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
    created_at: str
    offset_sec: float
    playback_at: str | None
    duration_sec: float | None


@dataclass(frozen=True)
class StatsRow:
    content_id: str
    clip_count: int
    watched_sec: float


def default_db_path() -> Path:
    """``$XDG_STATE_HOME/vidsaver/vidsaver.sqlite``, or ``~/.local/state/...``."""
    xdg = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return root / APP_NAME / "vidsaver.sqlite"


class Catalog:
    """Open or create the catalog. ``sync`` is the public scan entry."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    content_id TEXT PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    offset_sec REAL NOT NULL DEFAULT 0,
                    playback_at TEXT,
                    duration_sec REAL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback_stats (
                    content_id TEXT PRIMARY KEY,
                    clip_count INTEGER NOT NULL DEFAULT 0,
                    watched_sec REAL NOT NULL DEFAULT 0
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

    def sync(self, paths: list[Path]) -> dict[Path, str]:
        """Hash each path and return resolved-path → content_id for this scan."""
        ids: dict[Path, str] = {}
        for path in paths:
            resolved = path.expanduser().resolve()
            ids[resolved] = self._resolve(resolved)
        return ids

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
                INSERT INTO videos (content_id, size_bytes, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (content_id) DO NOTHING
                """,
                (content_id, size_bytes, now),
            )
            self._conn.execute(
                """
                INSERT INTO playback_stats (content_id)
                VALUES (?)
                ON CONFLICT (content_id) DO NOTHING
                """,
                (content_id,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(f"Cannot update catalog for {path}: {exc}") from exc
        return content_id

    def get_offset(self, content_id: str) -> float:
        cur = self._conn.execute(
            "SELECT offset_sec FROM videos WHERE content_id = ?",
            (content_id,),
        )
        row = cur.fetchone()
        if row is None:
            return 0.0
        return float(row[0])

    def get_offsets(self) -> dict[str, float]:
        cur = self._conn.execute("SELECT content_id, offset_sec FROM videos")
        return {
            str(content_id): float(offset_sec)
            for content_id, offset_sec in cur.fetchall()
        }

    def add_stats(
        self,
        content_id: str,
        played_sec: float,
        *,
        clips: int = 0,
    ) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO playback_stats (content_id, clip_count, watched_sec)
                VALUES (?, ?, ?)
                ON CONFLICT (content_id) DO UPDATE SET
                    clip_count = clip_count + excluded.clip_count,
                    watched_sec = watched_sec + excluded.watched_sec
                """,
                (content_id, clips, max(0.0, played_sec)),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(f"Cannot update stats for {content_id}: {exc}") from exc

    def get_stats(self, content_id: str) -> StatsRow | None:
        cur = self._conn.execute(
            """
            SELECT content_id, clip_count, watched_sec
            FROM playback_stats
            WHERE content_id = ?
            """,
            (content_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        content_id, clip_count, watched_sec = row
        return StatsRow(
            content_id=str(content_id),
            clip_count=int(clip_count),
            watched_sec=float(watched_sec),
        )

    def set_duration(self, content_id: str, duration_sec: float) -> None:
        try:
            self._conn.execute(
                "UPDATE videos SET duration_sec = ? WHERE content_id = ?",
                (duration_sec, content_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(
                f"Cannot store duration for {content_id}: {exc}"
            ) from exc

    def set_offset(self, content_id: str, offset_sec: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                """
                UPDATE videos
                SET offset_sec = ?, playback_at = ?
                WHERE content_id = ?
                """,
                (offset_sec, now, content_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StateError(f"Cannot store offset for {content_id}: {exc}") from exc

    def rows(self) -> list[VideoRow]:
        cur = self._conn.execute(
            """
            SELECT content_id, size_bytes, created_at, offset_sec,
                   playback_at, duration_sec
            FROM videos
            """
        )
        return [
            VideoRow(
                content_id=str(content_id),
                size_bytes=int(size_bytes),
                created_at=str(created_at),
                offset_sec=float(offset_sec),
                playback_at=None if playback_at is None else str(playback_at),
                duration_sec=None if duration_sec is None else float(duration_sec),
            )
            for (
                content_id,
                size_bytes,
                created_at,
                offset_sec,
                playback_at,
                duration_sec,
            ) in cur.fetchall()
        ]


class Offsets:
    """Path → offset for this scan. Reads and writes the catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._path_ids: dict[Path, str] = {}
        self._memory: dict[str, float] = {}
        self._last_id: str | None = None

    def sync(self, paths: list[Path]) -> None:
        """Build the path → id map and load each offset into memory."""
        self._path_ids = self._catalog.sync(paths)
        self._memory = self._catalog.get_offsets()
        self._last_id = None

    def get_offset(self, path: Path | None) -> float:
        content_id = self._id_for(path)
        if content_id is None:
            return 0.0
        return self._memory[content_id]

    def set_offset(
        self,
        path: Path | None,
        offset_sec: float,
        *,
        finished: bool = False,
    ) -> None:
        content_id = self._id_for(path)
        if content_id is None:
            return
        previous = self._memory[content_id]
        self._catalog.add_stats(
            content_id,
            offset_sec - previous,
            clips=1 if content_id != self._last_id else 0,
        )
        stored = 0.0 if finished else offset_sec
        self._memory[content_id] = stored
        self._catalog.set_offset(content_id, stored)
        self._last_id = content_id

    def set_duration(self, path: Path | None, duration_sec: float | None) -> None:
        if duration_sec is None:
            return
        content_id = self._id_for(path)
        if content_id is None:
            return
        self._catalog.set_duration(content_id, duration_sec)

    def _id_for(self, path: Path | None) -> str | None:
        if path is None:
            return None
        return self._path_ids.get(path.expanduser().resolve())
