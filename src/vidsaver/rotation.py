"""Decide when to leave a file and which offset to resume later.

Offsets live in memory for this process. The playback object is the only
player contact: this module does not talk to mpv or parse IPC events.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from vidsaver.playback import Playback, PlaybackError

# How often to ask playback whether the file has ended. Sleeping until
# the rotate deadline would leave the last frame up for the rest of the
# interval.
_EOF_POLL = 0.2
# If the leftover in this file is under this fraction of the rotate
# interval, do not cut — let EOF finish it.
_FINISH_SLACK = 0.25


def run_rotation(playback: Playback, rotate_minutes: float) -> int:
    """Drive rotation until any mpv process exits. Returns that exit code."""
    rotate_seconds = rotate_minutes * 60
    offsets: dict[Path, float] = {}
    curr_path: Path | None = None
    connected = False
    deadline = time.monotonic() + rotate_seconds

    while True:
        code = playback.poll()
        if code is not None:
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
                    _log_start(curr_path, offsets.get(curr_path, 0.0))
            remaining = max(0.0, deadline - time.monotonic())
            time.sleep(min(remaining, _EOF_POLL))
            if playback.eof_reached():
                curr_path = _rotate(playback, offsets, finished=True)
                deadline = time.monotonic() + rotate_seconds
            elif time.monotonic() >= deadline:
                leftover = playback.time_remaining()
                if _let_file_finish(leftover, rotate_seconds):
                    time.sleep(_EOF_POLL)
                    continue
                curr_path = _rotate(playback, offsets, finished=False)
                deadline = time.monotonic() + rotate_seconds
        except PlaybackError as exc:
            # Socket closed usually means mpv is exiting; loop back to poll().
            print(f"vidsaver: playback: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.05)


def _let_file_finish(leftover: float | None, rotate_seconds: float) -> bool:
    """True when cutting now would leave a stub shorter than the slack."""
    return leftover is not None and leftover < rotate_seconds * _FINISH_SLACK


def _rotate(
    playback: Playback,
    offsets: dict[Path, float],
    *,
    finished: bool,
) -> Path | None:
    path = playback.current_path()
    if path is not None:
        offsets[path] = 0.0 if finished else playback.time_pos()
    next_path = playback.peek_next_path()
    start = offsets.get(next_path, 0.0) if next_path is not None else 0.0
    new_path = playback.go_next(start)
    if new_path is not None:
        start = offsets.get(new_path, start)
        _log_start(new_path, start)
    return new_path


def _log_start(path: Path, offset: float) -> None:
    print(f"vidsaver: starting {path} at {offset:.1f}s", file=sys.stderr, flush=True)
