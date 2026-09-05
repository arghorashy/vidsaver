"""Decide when to leave a file and which offset to resume later.

Offsets are path-keyed via the catalog. The playback object is the
only player contact.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from vidsaver.playback import Playback, PlaybackError
from vidsaver.state import Offsets

# How often to ask playback whether the file has ended. Sleeping until
# the rotate deadline would leave the last frame up for the rest of the
# interval.
_EOF_POLL_SEC = 0.2
# If the leftover in this file is under this fraction of the rotate
# interval, do not cut — let EOF finish it.
_FINISH_SLACK_FRAC = 0.25
# Persist the current offset this often after playback starts.
_SAVE_EVERY_SEC = 60


def run_rotation(
    playback: Playback,
    rotate_minutes: float,
    offsets: Offsets,
) -> int:
    """Drive rotation until any mpv process exits. Returns that exit code."""
    rotate_seconds = rotate_minutes * 60
    curr_path: Path | None = None
    connected = False
    deadline = time.monotonic() + rotate_seconds
    last_save = 0.0

    while True:
        code = playback.poll()
        if code is not None:
            try:
                offsets.set_offset(curr_path, playback.time_pos())
            except PlaybackError:
                pass
            return code

        if not connected:
            try:
                playback.connect(timeout=0.2)
            except PlaybackError:
                time.sleep(0.05)
                continue
            connected = True
            deadline = time.monotonic() + rotate_seconds

        try:
            if curr_path is None:
                curr_path = playback.current_path()
                if curr_path is not None:
                    start = offsets.get_offset(curr_path)
                    _log_start(curr_path, start)
                    last_save = time.monotonic()
            remaining = max(0.0, deadline - time.monotonic())
            time.sleep(min(remaining, _EOF_POLL_SEC))
            if playback.eof_reached():
                curr_path = _rotate(playback, offsets, finished=True)
                deadline = time.monotonic() + rotate_seconds
                last_save = time.monotonic()
            elif time.monotonic() >= deadline:
                leftover = playback.time_remaining()
                if _let_file_finish(leftover, rotate_seconds):
                    time.sleep(_EOF_POLL_SEC)
                    continue
                curr_path = _rotate(playback, offsets, finished=False)
                deadline = time.monotonic() + rotate_seconds
                last_save = time.monotonic()
            elif time.monotonic() - last_save >= _SAVE_EVERY_SEC:
                offsets.set_offset(curr_path, playback.time_pos())
                last_save = time.monotonic()
        except PlaybackError as exc:
            # Socket closed usually means mpv is exiting; loop back to poll().
            print(f"vidsaver: playback: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.05)


def _let_file_finish(leftover: float | None, rotate_seconds: float) -> bool:
    """True when cutting now would leave a stub shorter than the slack."""
    return leftover is not None and leftover < rotate_seconds * _FINISH_SLACK_FRAC


def _rotate(
    playback: Playback,
    offsets: Offsets,
    *,
    finished: bool,
) -> Path | None:
    path = playback.current_path()
    offsets.set_offset(path, 0.0 if finished else playback.time_pos())
    next_path = playback.peek_next_path()
    start = offsets.get_offset(next_path)
    new_path = playback.go_next(start)
    if new_path is not None:
        start = offsets.get_offset(new_path)
        _log_start(new_path, start)
    return new_path


def _log_start(path: Path, offset: float) -> None:
    print(f"vidsaver: starting {path} at {offset:.1f}s", file=sys.stderr, flush=True)
