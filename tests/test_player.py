from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from vidsaver.player import mpv_argv, play
from vidsaver.state import Catalog, Offsets

VIDEOS = [Path("/videos/a.mp4")]


@contextmanager
def _offsets() -> Iterator[Offsets]:
    with TemporaryDirectory() as tmp:
        with Catalog(Path(tmp) / "vidsaver.sqlite") as catalog:
            yield Offsets(catalog)


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


def _play_all(n_displays: int = 2, *, mute: bool = True) -> tuple[int, list[FakeProcess]]:
    procs: list[FakeProcess] = []
    with (
        patch("vidsaver.player.shutil.which", return_value="/usr/bin/mpv"),
        patch("vidsaver.player.screen_count", return_value=n_displays),
        patch("vidsaver.player.subprocess.Popen", side_effect=_fake_popen(procs)),
    ):
        with _offsets() as offsets:
            code = play(VIDEOS, screens="all", mute=mute, offsets=offsets)
    return code, procs


def _play_primary(*, mute: bool = True) -> tuple[int, list[FakeProcess], MagicMock]:
    procs: list[FakeProcess] = []
    with (
        patch("vidsaver.player.shutil.which", return_value="/usr/bin/mpv"),
        patch("vidsaver.player.screen_count") as count,
        patch("vidsaver.player.subprocess.Popen", side_effect=_fake_popen(procs)),
    ):
        with _offsets() as offsets:
            code = play(VIDEOS, screens="primary", mute=mute, offsets=offsets)
    return code, procs, count


class MpvArgvTests(unittest.TestCase):
    def test_primary_screen_has_no_null_audio(self) -> None:
        argv = mpv_argv(
            "/usr/bin/mpv",
            [Path("/videos/a.mp4")],
            Path("/tmp/input.conf"),
            screen=0,
            mute_audio=False,
        )
        self.assertEqual(
            argv,
            [
                "/usr/bin/mpv",
                "--fullscreen",
                "--no-border",
                "--osc=no",
                "--osd-level=0",
                "--cursor-autohide=always",
                "--loop-playlist=inf",
                "--keep-open=always",
                "--screen=0",
                "--fs-screen=0",
                "--input-conf=/tmp/input.conf",
                "--",
                "/videos/a.mp4",
            ],
        )

    def test_resume_passes_start(self) -> None:
        argv = mpv_argv(
            "/usr/bin/mpv",
            [Path("/videos/a.mp4")],
            Path("/tmp/input.conf"),
            screen=0,
            mute_audio=False,
            start=12.5,
        )
        self.assertIn("--start=12.5", argv)

    def test_extra_screen_is_muted(self) -> None:
        argv = mpv_argv(
            "/usr/bin/mpv",
            [Path("/videos/a.mp4")],
            Path("/tmp/input.conf"),
            screen=1,
            mute_audio=True,
        )
        self.assertEqual(
            argv,
            [
                "/usr/bin/mpv",
                "--fullscreen",
                "--no-border",
                "--osc=no",
                "--osd-level=0",
                "--cursor-autohide=always",
                "--loop-playlist=inf",
                "--keep-open=always",
                "--screen=1",
                "--fs-screen=1",
                "--input-conf=/tmp/input.conf",
                "--no-audio",
                "--",
                "/videos/a.mp4",
            ],
        )


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
            with _offsets() as offsets:
                play(VIDEOS, screens="all", offsets=offsets)

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
        _, procs = _play_all(n_displays=2, mute=False)
        self.assertNotIn("--no-audio", procs[0].argv)
        self.assertIn("--no-audio", procs[1].argv)

    def test_mutes_every_window_when_mute_is_true(self) -> None:
        _, procs = _play_all(n_displays=2, mute=True)
        self.assertIn("--no-audio", procs[0].argv)
        self.assertIn("--no-audio", procs[1].argv)


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
        _, procs, _ = _play_primary(mute=False)
        self.assertNotIn("--no-audio", procs[0].argv)

    def test_mutes_when_mute_is_true(self) -> None:
        _, procs, _ = _play_primary(mute=True)
        self.assertIn("--no-audio", procs[0].argv)
