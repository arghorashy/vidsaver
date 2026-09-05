from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vidsaver.player import play

VIDEOS = [Path("/videos/a.mp4")]


class FakeProcess:
    def __init__(self, argv: list[str], *, exit_code: int | None = None) -> None:
        self.argv = argv
        self.returncode = exit_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _fake_popen(procs: list[FakeProcess]) -> object:
    def fake_popen(argv: list[str], **_kwargs: object) -> FakeProcess:
        proc = FakeProcess(argv, exit_code=0)
        procs.append(proc)
        return proc

    return fake_popen


def _play_all(n_displays: int = 2) -> tuple[int, list[FakeProcess]]:
    procs: list[FakeProcess] = []
    with (
        patch("vidsaver.player.shutil.which", return_value="/usr/bin/mpv"),
        patch("vidsaver.player.screen_count", return_value=n_displays),
        patch("vidsaver.player.subprocess.Popen", side_effect=_fake_popen(procs)),
    ):
        code = play(VIDEOS, screens="all")
    return code, procs


def _play_primary() -> tuple[int, list[FakeProcess], MagicMock]:
    procs: list[FakeProcess] = []
    with (
        patch("vidsaver.player.shutil.which", return_value="/usr/bin/mpv"),
        patch("vidsaver.player.screen_count") as count,
        patch("vidsaver.player.subprocess.Popen", side_effect=_fake_popen(procs)),
    ):
        code = play(VIDEOS, screens="primary")
    return code, procs, count


class PlayAllScreensTests(unittest.TestCase):
    def test_starts_one_process_per_display(self) -> None:
        _, procs = _play_all(n_displays=2)
        self.assertEqual(len(procs), 2)

    def test_stops_remaining_windows_when_one_exits(self) -> None:
        procs: list[FakeProcess] = []

        def fake_popen(argv: list[str], **_kwargs: object) -> FakeProcess:
            # First Popen stays running. Second Popen exits immediately.
            second_call = len(procs) == 1
            proc = FakeProcess(argv, exit_code=0 if second_call else None)
            procs.append(proc)
            return proc

        with (
            patch("vidsaver.player.shutil.which", return_value="/usr/bin/mpv"),
            patch("vidsaver.player.screen_count", return_value=2),
            patch("vidsaver.player.subprocess.Popen", side_effect=fake_popen),
        ):
            play(VIDEOS, screens="all")

        still_playing, _exited_immediately = procs
        self.assertTrue(still_playing.terminated)

    def test_pins_each_window_to_its_display(self) -> None:
        _, procs = _play_all(n_displays=2)
        self.assertEqual(
            [flag for flag in procs[0].argv if flag.startswith("--screen=") or flag.startswith("--fs-screen=")],
            ["--screen=0", "--fs-screen=0"],
        )
        self.assertEqual(
            [flag for flag in procs[1].argv if flag.startswith("--screen=") or flag.startswith("--fs-screen=")],
            ["--screen=1", "--fs-screen=1"],
        )

    def test_mutes_extra_windows_only(self) -> None:
        _, procs = _play_all(n_displays=2)
        self.assertNotIn("--ao=null", procs[0].argv)
        self.assertIn("--ao=null", procs[1].argv)


class PlayPrimaryTests(unittest.TestCase):
    def test_starts_one_process(self) -> None:
        _, procs, _ = _play_primary()
        self.assertEqual(len(procs), 1)

    def test_does_not_count_displays(self) -> None:
        _, _, count = _play_primary()
        count.assert_not_called()

    def test_pins_to_screen_zero(self) -> None:
        _, procs, _ = _play_primary()
        self.assertEqual(
            [flag for flag in procs[0].argv if flag.startswith("--screen=") or flag.startswith("--fs-screen=")],
            ["--screen=0", "--fs-screen=0"],
        )

    def test_does_not_mute(self) -> None:
        _, procs, _ = _play_primary()
        self.assertNotIn("--ao=null", procs[0].argv)
