from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vidsaver.config import ConfigError, load_config
from vidsaver.player import PlayerError, play
from vidsaver.playlist import PlaylistError, scan


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
    args = parser.parse_args(argv)

    try:
        config = load_config(config_path=args.config, video_dir=args.video_dir)
        videos = scan(config.video_dir)
        return play(videos, screens=config.screens, mute=config.mute)
    except (ConfigError, PlaylistError, PlayerError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
