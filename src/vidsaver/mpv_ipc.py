from __future__ import annotations

import json
import select
import socket
import time
from pathlib import Path
from typing import Any


class MpvIpcError(Exception):
    """The mpv JSON IPC socket could not be used."""


class MpvIpc:
    """Line-delimited JSON IPC client for one mpv process."""

    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._next_id = 1
        self._pending_events: list[dict[str, Any]] = []

    def connect(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            if not self.socket_path.exists():
                time.sleep(0.05)
                continue
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(str(self.socket_path))
            except OSError as exc:
                last_error = exc
                sock.close()
                time.sleep(0.05)
                continue
            sock.settimeout(2.0)
            self._sock = sock
            return
        raise MpvIpcError(
            f"Could not connect to {self.socket_path}: {last_error}"
        )

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        finally:
            self._sock = None

    def fileno(self) -> int:
        if self._sock is None:
            raise MpvIpcError("Not connected")
        return self._sock.fileno()

    def command(self, *args: object, timeout: float = 2.0) -> Any:
        if self._sock is None:
            raise MpvIpcError("Not connected")
        request_id = self._next_id
        self._next_id += 1
        payload = json.dumps({"command": list(args), "request_id": request_id}) + "\n"
        self._sock.sendall(payload.encode("utf-8"))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._read_message(deadline - time.monotonic())
            if message is None:
                continue
            if message.get("event") is not None:
                self._pending_events.append(message)
                continue
            if message.get("request_id") != request_id:
                continue
            if message.get("error") == "property unavailable":
                return None
            if message.get("error") != "success":
                raise MpvIpcError(f"mpv command {args!r} failed: {message}")
            return message.get("data")
        raise MpvIpcError(f"Timed out waiting for mpv command {args!r}")

    def drain_events(self) -> list[dict[str, Any]]:
        """Read every complete JSON line already in the socket buffer."""
        events: list[dict[str, Any]] = list(self._pending_events)
        self._pending_events.clear()
        if self._sock is None:
            return events
        while True:
            ready, _, _ = select.select([self._sock], [], [], 0)
            if not ready:
                break
            message = self._read_message(0.05)
            if message is None:
                break
            if message.get("event") is not None:
                events.append(message)
        return events

    def _read_message(self, timeout: float) -> dict[str, Any] | None:
        if self._sock is None:
            raise MpvIpcError("Not connected")
        if b"\n" not in self._buffer:
            ready, _, _ = select.select([self._sock], [], [], max(timeout, 0))
            if not ready:
                return None
            chunk = self._sock.recv(4096)
            if not chunk:
                raise MpvIpcError("mpv IPC socket closed")
            self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        if not line:
            return None
        data = json.loads(line.decode("utf-8"))
        if not isinstance(data, dict):
            raise MpvIpcError(f"Unexpected IPC payload: {data!r}")
        return data
