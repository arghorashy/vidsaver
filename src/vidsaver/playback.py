"""Talk to the running mpv windows.

This module does not decide when to leave a file or what offset to
remember. It reports path / time / EOF and can load the next or previous
playlist entry already seeked to a given time.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vidsaver.mpv_ipc import MpvIpc, MpvIpcError


class PlaybackError(Exception):
    """mpv stopped responding (usually the process is exiting)."""


class Playback:
    """One or more mpv processes playing the same playlist."""

    def __init__(
        self,
        procs: list[subprocess.Popen[bytes]],
        clients: list[MpvIpc],
    ) -> None:
        if not clients:
            raise ValueError("Playback needs at least one mpv client")
        self._procs = procs
        self._clients = clients

    def poll(self) -> int | None:
        """Exit code of the first mpv process that has exited, else None."""
        for proc in self._procs:
            code = proc.poll()
            if code is not None:
                return code
        return None

    def connect(self, timeout: float = 0.2) -> None:
        try:
            for client in self._clients:
                client.connect(timeout=timeout)
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc

    def current_path(self) -> Path | None:
        try:
            raw = self._clients[0].command("get_property", "path")
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc
        if not raw:
            return None
        return _offset_key(Path(str(raw)))

    def time_pos(self) -> float:
        try:
            raw = self._clients[0].command("get_property", "time-pos")
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc
        if raw is None:
            return 0.0
        return float(raw)

    def duration(self) -> float | None:
        """Length of the current file in seconds, or None if unknown."""
        try:
            raw = self._clients[0].command("get_property", "duration")
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc
        if raw is None:
            return None
        return float(raw)

    def time_remaining(self) -> float | None:
        """Seconds left in the current file, or None if mpv does not know."""
        try:
            raw = self._clients[0].command("get_property", "time-remaining")
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc
        if raw is None:
            return None
        return float(raw)

    def eof_reached(self) -> bool:
        try:
            return self._clients[0].command("get_property", "eof-reached") is True
        except MpvIpcError:
            return False

    def peek_next_path(self) -> Path | None:
        return self._peek_path(1)

    def peek_prev_path(self) -> Path | None:
        return self._peek_path(-1)

    def _peek_path(self, delta: int) -> Path | None:
        try:
            pos = self._clients[0].command("get_property", "playlist-pos")
            count = self._clients[0].command("get_property", "playlist-count")
            if pos is None or count is None or int(count) < 1:
                return None
            next_pos = (int(pos) + delta) % int(count)
            raw = self._clients[0].command(
                "get_property", f"playlist/{next_pos}/filename"
            )
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc
        if not raw:
            return None
        return _offset_key(Path(str(raw)))

    def skip_request(self) -> str | None:
        """``"next"`` / ``"prev"`` from mpv ``script-message``, else None.

        Drains IPC events on every window. A skip is not mpv's raw
        playlist-next: rotation tallies and seeks like a timer cut.
        """
        found: str | None = None
        for client in self._clients:
            for event in client.drain_events():
                if event.get("event") != "client-message":
                    continue
                args = event.get("args")
                if not isinstance(args, list) or not args:
                    continue
                name = args[0]
                if name == "vidsaver-next":
                    found = "next"
                elif name == "vidsaver-prev":
                    found = "prev"
        return found

    def go_next(self, start: float = 0.0) -> Path | None:
        """Load the next playlist entry so the first shown frame is *start*."""
        return self._advance(1, start)

    def go_prev(self, start: float = 0.0) -> Path | None:
        """Load the previous playlist entry so the first shown frame is *start*."""
        return self._advance(-1, start)

    def _advance(self, delta: int, start: float) -> Path | None:
        """Pause → playlist-next/prev → wait until that file is current →
        seek to *start* → unpause. We cannot set mpv's ``start`` option at
        runtime (0.37 rejects it), so the seek has to happen after the new
        file is loaded and before it is allowed to play. At EOF, ``keep-open``
        has already paused mpv; the unpause at the end is what starts the
        next file.
        """
        try:
            expected = self._peek_path(delta)
            previous_pos = self._playlist_pos()
            command = "playlist-next" if delta > 0 else "playlist-prev"
            for client in self._clients:
                client.command("set_property", "pause", True)
                # Drop leftover file-loaded events so wait does not return early.
                client.drain_events()
                client.command(command)
            new_path = self._wait_for_file(previous_pos, expected) or expected
            if new_path is not None and start > 0:
                self._seek_all(start)
            for client in self._clients:
                client.command("set_property", "pause", False)
            # keep-open leaves eof-reached true after the old file ends.
            # Do not return until the new file has cleared it, or rotation
            # would see "finished" again and skip another clip.
            self._wait_until_not_eof()
            return new_path
        except MpvIpcError as exc:
            raise PlaybackError(str(exc)) from exc

    def _playlist_pos(self) -> int | None:
        raw = self._clients[0].command("get_property", "playlist-pos")
        if raw is None:
            return None
        return int(raw)

    def _wait_for_file(
        self,
        previous_pos: int | None,
        expected: Path | None,
        timeout: float = 3.0,
    ) -> Path | None:
        """Wait until playlist-next has loaded *expected*.

        Returning as soon as the playlist index moves is too early: ``path``
        can still be the outgoing file, and we would seek the wrong offset.
        Same-path shuffle entries need a new ``file-loaded`` or a pos change.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events = self._clients[0].drain_events()
            loaded = any(event.get("event") == "file-loaded" for event in events)
            pos = self._playlist_pos()
            moved = (
                previous_pos is not None
                and pos is not None
                and pos != previous_pos
            )
            if loaded or moved:
                path = self.current_path()
                if path is not None and (expected is None or path == expected):
                    return path
            time.sleep(0.05)
        return self.current_path() or expected

    def _wait_until_not_eof(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.eof_reached():
                return
            time.sleep(0.05)

    def _seek_all(self, start: float) -> None:
        last_error: MpvIpcError | None = None
        for _ in range(10):
            try:
                for client in self._clients:
                    client.command("seek", start, "absolute")
                return
            except MpvIpcError as exc:
                last_error = exc
                time.sleep(0.05)
        if last_error is not None:
            raise last_error


def _offset_key(path: Path) -> Path:
    return path.expanduser().resolve()
