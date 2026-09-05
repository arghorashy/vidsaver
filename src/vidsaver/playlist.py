from __future__ import annotations

from pathlib import Path

VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".wmv"}
)


class PlaylistError(Exception):
    """The video folder is missing, unreadable, or empty."""


def scan(video_dir: Path) -> list[Path]:
    """Return video files in *video_dir*.

    Non-recursive. Only files with a known video extension are included.
    Order is whatever the filesystem returns.
    """
    if not video_dir.exists():
        raise PlaylistError(f"Video folder does not exist: {video_dir}")
    if not video_dir.is_dir():
        raise PlaylistError(f"Video path is not a directory: {video_dir}")

    try:
        entries = list(video_dir.iterdir())
    except OSError as exc:
        raise PlaylistError(f"Cannot read video folder {video_dir}: {exc}") from exc

    videos = [
        path
        for path in entries
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not videos:
        extensions = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise PlaylistError(
            f"No video files found in {video_dir} (looked for {extensions})"
        )
    return videos
