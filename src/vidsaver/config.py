from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "vidsaver"

# config.toml at the project root (this file is src/vidsaver/config.py)
PROJECT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"
# ~/.config/vidsaver/config.toml
USER_CONFIG_PATH = Path.home() / ".config" / APP_NAME / "config.toml"


class ConfigError(Exception):
    """Invalid or missing configuration."""


@dataclass(frozen=True)
class Config:
    video_dir: Path
    config_path: Path | None = None


def load_config(config_path: Path | None = None, video_dir: Path | None = None) -> Config:
    """Load config from TOML, then apply CLI overrides.

    ``video_dir`` (``--dir``) overrides ``video_dir`` from the file.

    If ``config_path`` (``--config``) is given, that file is required and no
    other locations are checked. Otherwise the first existing file wins:

    1. ``./config.toml`` — current working directory
    2. ``<project>/config.toml`` — this repo's root, even if cwd is elsewhere
    3. ``~/.config/vidsaver/config.toml`` — user config
    """
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"Config file not found: {config_path}")
        path = config_path
    else:
        path = _find_config_file()

    file_values: dict[str, object] = {}
    used_path: Path | None = None
    if path is not None:
        file_values = _read_toml(path)
        used_path = path

    raw_dir = video_dir if video_dir is not None else file_values.get("video_dir")
    if raw_dir is None:
        raise ConfigError(
            "No video folder set. Pass --dir or set video_dir in "
            f"./config.toml or {USER_CONFIG_PATH}"
        )
    if raw_dir == "":
        where = f" in {used_path}" if used_path is not None else ""
        raise ConfigError(
            f"video_dir{where} is an empty string, not a folder path. "
            "Set it to a folder of videos, or pass --dir."
        )

    return Config(video_dir=Path(raw_dir).expanduser(), config_path=used_path)


def _config_candidates() -> tuple[Path, ...]:
    """Locations checked when ``--config`` is omitted, in precedence order."""
    return (Path.cwd() / "config.toml", PROJECT_CONFIG_PATH, USER_CONFIG_PATH)


def _find_config_file() -> Path | None:
    for path in _config_candidates():
        if path.is_file():
            return path
    return None


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a table: {path}")
    return data
