from __future__ import annotations

import unittest
from pathlib import Path

from vidsaver.rotation import _rotate

A = Path("/videos/a.mp4")
B = Path("/videos/b.mp4")


class FakePlayback:
    def __init__(self, path: Path, time_pos: float, nxt: Path) -> None:
        self._path = path
        self._time = time_pos
        self._next = nxt
        self.go_next_at: float | None = None

    def current_path(self) -> Path:
        return self._path

    def time_pos(self) -> float:
        return self._time

    def peek_next_path(self) -> Path:
        return self._next

    def go_next(self, start: float = 0.0) -> Path:
        self.go_next_at = start
        self._path = self._next
        return self._path


class RotateTests(unittest.TestCase):
    def test_timer_saves_offset_and_starts_next_at_zero(self) -> None:
        playback = FakePlayback(A, 15.0, B)
        offsets: dict[Path, float] = {}
        _rotate(playback, offsets, finished=False)
        self.assertEqual(offsets[A], 15.0)
        self.assertEqual(playback.go_next_at, 0.0)

    def test_later_visit_resumes_saved_offset(self) -> None:
        offsets = {A: 15.0}
        playback = FakePlayback(B, 8.0, A)
        _rotate(playback, offsets, finished=False)
        self.assertEqual(offsets[B], 8.0)
        self.assertEqual(playback.go_next_at, 15.0)

    def test_finished_file_resets_offset_to_zero(self) -> None:
        offsets = {A: 40.0}
        playback = FakePlayback(A, 46.0, B)
        _rotate(playback, offsets, finished=True)
        self.assertEqual(offsets[A], 0.0)
        self.assertEqual(playback.go_next_at, 0.0)
