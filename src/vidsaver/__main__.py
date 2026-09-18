from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vidsaver.config import ConfigError, load_config
from vidsaver.player import PlayerError, play
from vidsaver.playlist import PlaylistError, scan
from vidsaver.shuffle import get_shuffled_playlist
from vidsaver.state import DBStore, Progress, StateError, default_db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidsaver",
        description="Play a folder of videos fullscreen, looping the playlist.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML config path (with otherwise look for ./config.toml, then ~/.config/vidsaver/config.toml)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        dest="video_dir",
        help="Folder of video files (overrides video_dir in the config)",
    )
    parser.add_argument(
        "--exit-on",
        choices=("escape", "any-input"),
        default=None,
        dest="exit_on",
        help="What quits playback (overrides exit_on in the config)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(
            config_path=args.config,
            video_dir=args.video_dir,
            exit_on=args.exit_on,
        )
        paths = scan(config.video_dir)
        with DBStore(default_db_path()) as db:
            progress = Progress(db)
            progress.sync(paths)
            videos = get_shuffled_playlist(paths)
            start = progress.get_offset(videos[0]) if videos else 0.0
            return play(
                videos,
                screens=config.screens,
                mute=config.mute,
                rotate_minutes=config.rotate_minutes,
                start=start,
                skip_ends=config.skip_ends,
                exit_on=config.exit_on,
                progress=progress,
            )
    except (ConfigError, PlaylistError, PlayerError, StateError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
