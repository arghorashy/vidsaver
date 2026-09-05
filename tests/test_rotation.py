from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vidsaver.rotation import _let_file_finish, _rotate
from vidsaver.state import Catalog, Offsets


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
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        self.a = self.root / "a.mp4"
        self.b = self.root / "b.mp4"
        self.a.write_bytes(b"aaa")
        self.b.write_bytes(b"bbb")
        self.catalog = Catalog(self.root / "vidsaver.sqlite")
        self.addCleanup(self.catalog.close)
        self.offsets = Offsets(self.catalog)
        self.offsets.sync([self.a, self.b])

    def test_timer_saves_offset_and_starts_next_at_zero(self) -> None:
        playback = FakePlayback(self.a, 15.0, self.b)
        _rotate(playback, self.offsets, finished=False)
        self.assertEqual(self.offsets.get_offset(self.a), 15.0)
        self.assertEqual(playback.go_next_at, 0.0)

    def test_later_visit_resumes_saved_offset(self) -> None:
        self.offsets.set_offset(self.a, 15.0)
        playback = FakePlayback(self.b, 8.0, self.a)
        _rotate(playback, self.offsets, finished=False)
        self.assertEqual(self.offsets.get_offset(self.b), 8.0)
        self.assertEqual(playback.go_next_at, 15.0)

    def test_lets_file_finish_when_leftover_is_under_a_quarter_slot(self) -> None:
        self.assertTrue(_let_file_finish(2.0, 10.0))
        self.assertFalse(_let_file_finish(2.5, 10.0))
        self.assertFalse(_let_file_finish(None, 10.0))

    def test_finished_file_resets_offset_to_zero(self) -> None:
        self.offsets.set_offset(self.a, 40.0)
        playback = FakePlayback(self.a, 46.0, self.b)
        _rotate(playback, self.offsets, finished=True)
        self.assertEqual(self.offsets.get_offset(self.a), 0.0)
        self.assertEqual(playback.go_next_at, 0.0)
