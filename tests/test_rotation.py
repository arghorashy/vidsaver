from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vidsaver.fingerprint import content_id_for
from vidsaver.rotation import (
    SKIP_ENDS_SEC,
    _let_file_finish,
    _rotate,
    playable_remaining,
    playable_start,
)
from vidsaver.state import DBStore, Progress


class FakePlayback:
    def __init__(
        self,
        path: Path,
        time_pos: float,
        nxt: Path,
        *,
        duration: float | None = 46.0,
    ) -> None:
        self._path = path
        self._time = time_pos
        self._next = nxt
        self._duration = duration
        self.go_next_at: float | None = None

    def current_path(self) -> Path:
        return self._path

    def time_pos(self) -> float:
        return self._time

    def duration(self) -> float | None:
        return self._duration

    def peek_next_path(self) -> Path:
        return self._next

    def go_next(self, start: float = 0.0) -> Path:
        self.go_next_at = start
        self._path = self._next
        return self._path


class PlayableStartTests(unittest.TestCase):
    def test_disabled_keeps_the_stored_offset(self) -> None:
        self.assertEqual(playable_start(12.0, 120.0, False), 12.0)

    def test_skips_intro_when_offset_is_zero(self) -> None:
        self.assertEqual(playable_start(0.0, 120.0, True), SKIP_ENDS_SEC)

    def test_skips_intro_when_offset_is_inside_intro(self) -> None:
        self.assertEqual(playable_start(10.0, 120.0, True), SKIP_ENDS_SEC)

    def test_keeps_a_mid_file_offset(self) -> None:
        self.assertEqual(playable_start(50.0, 120.0, True), 50.0)

    def test_restarts_after_intro_when_offset_is_in_outro(self) -> None:
        self.assertEqual(playable_start(95.0, 120.0, True), SKIP_ENDS_SEC)

    def test_unknown_duration_starts_at_zero(self) -> None:
        self.assertEqual(playable_start(0.0, None, True), 0.0)

    def test_short_file_plays_from_the_stored_offset(self) -> None:
        self.assertEqual(playable_start(12.0, 60.0, True), 12.0)


class PlayableRemainingTests(unittest.TestCase):
    def test_disabled_uses_true_end(self) -> None:
        self.assertEqual(playable_remaining(10.0, 46.0, False), 36.0)

    def test_counts_down_to_the_trimmed_end(self) -> None:
        self.assertEqual(playable_remaining(30.0, 120.0, True), 60.0)

    def test_zero_in_the_outro(self) -> None:
        self.assertEqual(playable_remaining(90.0, 120.0, True), 0.0)

    def test_unknown_duration_returns_none(self) -> None:
        self.assertIsNone(playable_remaining(10.0, None, True))

    def test_zero_duration_is_unknown(self) -> None:
        self.assertIsNone(playable_remaining(10.0, 0.0, True))

    def test_short_file_uses_true_end(self) -> None:
        self.assertEqual(playable_remaining(10.0, 50.0, True), 40.0)


class RotateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        self.a = self.root / "a.mp4"
        self.b = self.root / "b.mp4"
        self.a.write_bytes(b"aaa")
        self.b.write_bytes(b"bbb")
        self.store = DBStore(self.root / "vidsaver.sqlite")
        self.addCleanup(self.store.close)
        self.progress = Progress(self.store)
        self.progress.sync([self.a, self.b])

    def test_timer_saves_offset_and_starts_next_at_zero(self) -> None:
        playback = FakePlayback(self.a, 15.0, self.b)
        _rotate(playback, self.progress, finished=False, skip_ends=False)
        self.assertEqual(self.progress.get_offset(self.a), 15.0)
        self.assertEqual(playback.go_next_at, 0.0)
        stats = self.store.get_stats(content_id_for(self.a))
        assert stats is not None
        self.assertEqual(stats.clip_count, 1)
        self.assertEqual(stats.watched_sec, 15.0)
        self.assertEqual(
            next(
                row.duration_sec
                for row in self.store.rows()
                if row.content_id == content_id_for(self.b)
            ),
            46.0,
        )

    def test_later_visit_resumes_saved_offset(self) -> None:
        self.store.set_offset(content_id_for(self.a), 15.0)
        self.progress.sync([self.a, self.b])
        playback = FakePlayback(self.b, 8.0, self.a)
        _rotate(playback, self.progress, finished=False, skip_ends=False)
        self.assertEqual(self.progress.get_offset(self.b), 8.0)
        self.assertEqual(playback.go_next_at, 15.0)

    def test_lets_file_finish_when_leftover_is_under_a_quarter_slot(self) -> None:
        self.assertTrue(_let_file_finish(2.0, 10.0))
        self.assertFalse(_let_file_finish(2.5, 10.0))
        self.assertFalse(_let_file_finish(None, 10.0))

    def test_finished_file_resets_offset_to_zero(self) -> None:
        self.store.set_offset(content_id_for(self.a), 40.0)
        self.progress.sync([self.a, self.b])
        playback = FakePlayback(self.a, 46.0, self.b)
        _rotate(playback, self.progress, finished=True, skip_ends=False)
        self.assertEqual(self.progress.get_offset(self.a), 0.0)
        self.assertEqual(playback.go_next_at, 0.0)
        stats = self.store.get_stats(content_id_for(self.a))
        assert stats is not None
        self.assertEqual(stats.clip_count, 1)
        self.assertEqual(stats.watched_sec, 6.0)

    def test_skip_ends_starts_next_after_intro(self) -> None:
        self.progress.set_duration(self.b, 120.0)
        playback = FakePlayback(self.a, 15.0, self.b, duration=120.0)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, SKIP_ENDS_SEC)

    def test_skip_ends_resumes_a_mid_file_offset(self) -> None:
        self.progress.set_offset(self.a, 50.0)
        self.progress.set_duration(self.a, 120.0)
        playback = FakePlayback(self.b, 8.0, self.a, duration=120.0)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, 50.0)

    def test_skip_ends_clamps_an_intro_offset(self) -> None:
        self.progress.set_offset(self.a, 10.0)
        self.progress.set_duration(self.a, 120.0)
        playback = FakePlayback(self.b, 8.0, self.a, duration=120.0)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, SKIP_ENDS_SEC)

    def test_skip_ends_restarts_when_saved_in_outro(self) -> None:
        self.progress.set_offset(self.a, 95.0)
        self.progress.set_duration(self.a, 120.0)
        playback = FakePlayback(self.b, 8.0, self.a, duration=120.0)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, SKIP_ENDS_SEC)

    def test_skip_ends_leaves_a_short_file_alone(self) -> None:
        self.progress.set_offset(self.a, 15.0)
        self.progress.set_duration(self.a, 46.0)
        playback = FakePlayback(self.b, 8.0, self.a, duration=46.0)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, 15.0)

    def test_skip_ends_unknown_duration_starts_at_zero(self) -> None:
        playback = FakePlayback(self.a, 15.0, self.b, duration=None)
        _rotate(playback, self.progress, finished=False, skip_ends=True)
        self.assertEqual(playback.go_next_at, 0.0)
