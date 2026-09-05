#!/usr/bin/env python3
"""Poll the vidsaver catalog and print filename, offset, playback_at."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
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
        description="Watch catalog offsets (filename, offset, playback_at).",
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
        help="Catalog sqlite path (default: XDG state location)",
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
        return f"waiting for catalog at {db_path}\n"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.isolation_level = None
        rows = conn.execute(
            "SELECT content_id, offset_sec, playback_at FROM videos"
        ).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        return f"cannot read {db_path}: {exc}\n"

    table = [("filename", "offset", "playback_at")]
    body = [
        (
            names.get(str(content_id), str(content_id)),
            f"{float(offset_sec):.1f}",
            "" if playback_at is None else str(playback_at),
        )
        for content_id, offset_sec, playback_at in rows
    ]
    body.sort(key=lambda row: row[0].lower())
    table.extend(body)
    widths = [max(len(row[col]) for row in table) for col in range(3)]
    lines = [
        f"{row[0]:<{widths[0]}}  {row[1]:>{widths[1]}}  {row[2]:<{widths[2]}}"
        for row in table
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
