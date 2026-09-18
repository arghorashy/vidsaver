from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from vidsaver.playback import Playback


def _playback(*clients: MagicMock) -> Playback:
    return Playback([MagicMock()], list(clients))


class SkipRequestTests(unittest.TestCase):
    def test_none_when_no_events(self) -> None:
        client = MagicMock()
        client.drain_events.return_value = []
        self.assertIsNone(_playback(client).skip_request())

    def test_next_from_script_message(self) -> None:
        client = MagicMock()
        client.drain_events.return_value = [
            {"event": "client-message", "args": ["vidsaver-next"]},
        ]
        self.assertEqual(_playback(client).skip_request(), "next")

    def test_prev_from_script_message(self) -> None:
        client = MagicMock()
        client.drain_events.return_value = [
            {"event": "client-message", "args": ["vidsaver-prev"]},
        ]
        self.assertEqual(_playback(client).skip_request(), "prev")

    def test_ignores_other_events_and_messages(self) -> None:
        client = MagicMock()
        client.drain_events.return_value = [
            {"event": "file-loaded"},
            {"event": "client-message", "args": ["unrelated"]},
        ]
        self.assertIsNone(_playback(client).skip_request())

    def test_drains_every_window(self) -> None:
        primary = MagicMock()
        primary.drain_events.return_value = []
        extra = MagicMock()
        extra.drain_events.return_value = [
            {"event": "client-message", "args": ["vidsaver-prev"]},
        ]
        self.assertEqual(_playback(primary, extra).skip_request(), "prev")
        primary.drain_events.assert_called_once()
        extra.drain_events.assert_called_once()


class PeekPathTests(unittest.TestCase):
    def test_prev_wraps_around_to_the_last_entry(self) -> None:
        client = MagicMock()

        def command(*args: object) -> object:
            if args == ("get_property", "playlist-pos"):
                return 0
            if args == ("get_property", "playlist-count"):
                return 3
            if args == ("get_property", "playlist/2/filename"):
                return "/videos/c.mp4"
            raise AssertionError(args)

        client.command.side_effect = command
        path = _playback(client).peek_prev_path()
        self.assertEqual(path, Path("/videos/c.mp4").resolve())
