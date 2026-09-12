#!/usr/bin/env python3
"""Poll the vidsaver database and print resume points plus watch stats."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vidsaver.config import ConfigError, load_config
from vidsaver.fingerprint import FingerprintError, content_id_for
from vidsaver.playlist import PlaylistError, scan
from vidsaver.state import default_db_path

_POLL_SEC = 1.0
_CLEAR = "\033[H\033[J"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch database resume points and playback stats.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML config path (same search as vidsaver if omitted)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        dest="video_dir",
        help="Folder of video files (overrides video_dir in the config)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Sqlite path (default: XDG state location)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=_POLL_SEC,
        help=f"Seconds between polls (default {_POLL_SEC})",
    )
    args = parser.parse_args(argv)
    if args.interval <= 0:
        print("interval must be greater than 0", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path=args.config, video_dir=args.video_dir)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    db_path = args.db or default_db_path()
    names: dict[str, str] = {}
    seen: set[Path] = set()
    try:
        while True:
            _refresh_names(config.video_dir, names, seen)
            print(_CLEAR + _render(db_path, names), end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        return 0


def _refresh_names(
    video_dir: Path, names: dict[str, str], seen: set[Path]
) -> None:
    try:
        paths = scan(video_dir)
    except PlaylistError:
        return
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        try:
            content_id = content_id_for(resolved)
        except FingerprintError:
            continue
        seen.add(resolved)
        existing = names.get(content_id)
        if existing is None:
            names[content_id] = resolved.name
        elif resolved.name not in existing.split(", "):
            names[content_id] = f"{existing}, {resolved.name}"


def _render(db_path: Path, names: dict[str, str]) -> str:
    if not db_path.is_file():
        return f"waiting for database at {db_path}\n"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.isolation_level = None
        rows = conn.execute(
            """
            SELECT
                v.content_id,
                v.offset_sec,
                v.playback_at,
                COALESCE(s.clip_count, 0),
                COALESCE(s.watched_sec, 0),
                v.duration_sec
            FROM videos AS v
            LEFT JOIN playback_stats AS s ON s.content_id = v.content_id
            """
        ).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        return f"cannot read {db_path}: {exc}\n"

    table = [("filename", "offset", "playback_at", "clips", "watched", "x")]
    body = [
        (
            names.get(str(content_id), str(content_id)),
            _format_offset(float(offset_sec)),
            _format_playback_at(playback_at),
            str(int(clip_count)),
            _format_watched(float(watched_sec)),
            _format_repeats(float(watched_sec), duration_sec),
        )
        for content_id, offset_sec, playback_at, clip_count, watched_sec, duration_sec in rows
    ]
    body.sort(key=lambda row: row[0].lower())
    table.extend(body)
    widths = [max(len(row[col]) for row in table) for col in range(6)]
    align = ("<", ">", "<", ">", "<", ">")
    lines = [
        "  ".join(f"{row[col]:{align[col]}{widths[col]}}" for col in range(6))
        for row in table
    ]
    return "\n".join(lines) + "\n"


def _format_offset(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_playback_at(raw: object) -> str:
    if raw is None:
        return ""
    text = str(raw)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _format_watched(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {secs}s"


def _format_repeats(watched_sec: float, duration_sec: object) -> str:
    if duration_sec is None:
        return ""
    duration = float(duration_sec)
    if duration <= 0:
        return ""
    return f"{watched_sec / duration:.2f}x"


if __name__ == "__main__":
    sys.exit(main())
