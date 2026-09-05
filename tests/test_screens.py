from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vidsaver.screens import (
    _count_drm_connected,
    _parse_xrandr_monitor_count,
    screen_count,
)

XRANDR_ONE = """\
Monitors: 1
 0: +*eDP-1 1920/344x1080/194+0+0  eDP-1
"""

XRANDR_TWO = """\
Monitors: 2
 0: +*eDP-1 1920/344x1080/194+0+0  eDP-1
 1: +HDMI-1 1920/480x1080/270+1920+0  HDMI-1
"""


def _write_status(drm_dir: Path, name: str, status: str) -> None:
    connector = drm_dir / name
    connector.mkdir()
    (connector / "status").write_text(f"{status}\n", encoding="utf-8")


class ParseXrandrTests(unittest.TestCase):
    def test_one_monitor(self) -> None:
        self.assertEqual(_parse_xrandr_monitor_count(XRANDR_ONE), 1)

    def test_two_monitors(self) -> None:
        self.assertEqual(_parse_xrandr_monitor_count(XRANDR_TWO), 2)

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(_parse_xrandr_monitor_count("not xrandr output\n"))


class CountDrmTests(unittest.TestCase):
    def test_counts_connected_connectors(self) -> None:
        with TemporaryDirectory() as tmp:
            drm_dir = Path(tmp)
            (drm_dir / "card0").mkdir()
            _write_status(drm_dir, "card0-eDP-1", "connected")
            _write_status(drm_dir, "card0-HDMI-A-1", "connected")
            _write_status(drm_dir, "card0-DP-1", "disconnected")
            self.assertEqual(_count_drm_connected(drm_dir), 2)

    def test_missing_dir_returns_zero(self) -> None:
        self.assertEqual(_count_drm_connected(Path("/no/such/drm")), 0)


class ScreenCountTests(unittest.TestCase):
    def test_x11_uses_xrandr(self) -> None:
        def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(argv[1], "--listmonitors")
            return subprocess.CompletedProcess(argv, 0, stdout=XRANDR_TWO, stderr="")

        with (
            patch.dict("vidsaver.screens.os.environ", {"DISPLAY": ":0"}, clear=True),
            patch("vidsaver.screens.shutil.which", return_value="/usr/bin/xrandr"),
            patch("vidsaver.screens.subprocess.run", side_effect=run),
        ):
            self.assertEqual(screen_count(), 2)

    def test_wayland_uses_drm_not_xrandr(self) -> None:
        with TemporaryDirectory() as tmp:
            drm_dir = Path(tmp)
            _write_status(drm_dir, "card0-eDP-1", "connected")
            _write_status(drm_dir, "card0-HDMI-A-1", "connected")

            def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"xrandr should not run on Wayland: {argv}")

            with (
                patch.dict(
                    "vidsaver.screens.os.environ",
                    {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"},
                    clear=True,
                ),
                patch("vidsaver.screens._DRM_DIR", drm_dir),
                patch("vidsaver.screens.subprocess.run", side_effect=run),
            ):
                self.assertEqual(screen_count(), 2)

    def test_x11_falls_back_to_drm_when_xrandr_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            drm_dir = Path(tmp)
            _write_status(drm_dir, "card0-HDMI-A-1", "connected")
            _write_status(drm_dir, "card0-DP-1", "connected")
            _write_status(drm_dir, "card0-DP-2", "connected")

            def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="fail")

            with (
                patch.dict("vidsaver.screens.os.environ", {"DISPLAY": ":0"}, clear=True),
                patch("vidsaver.screens._DRM_DIR", drm_dir),
                patch("vidsaver.screens.shutil.which", return_value="/usr/bin/xrandr"),
                patch("vidsaver.screens.subprocess.run", side_effect=run),
            ):
                self.assertEqual(screen_count(), 3)

    def test_both_fail_defaults_to_one(self) -> None:
        with (
            patch.dict("vidsaver.screens.os.environ", {"DISPLAY": ":0"}, clear=True),
            patch("vidsaver.screens._DRM_DIR", Path("/no/such/drm")),
            patch("vidsaver.screens.shutil.which", return_value=None),
        ):
            self.assertEqual(screen_count(), 1)
