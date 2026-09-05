"""Count connected displays for ``screens = "all"``.

The player asks ``screen_count()`` how many fullscreen mpv windows to start
(one per display, indexed ``0 .. N-1``). This module does not talk to mpv.

On a native X11 session (``DISPLAY`` set, no ``WAYLAND_DISPLAY``), count
comes from ``xrandr --listmonitors``. On Wayland, or if xrandr is missing
or fails, count connected connectors under ``/sys/class/drm`` (the kernel
Direct Rendering Manager — not copy-protection DRM). If both paths fail,
return 1 so playback still starts on a single window.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

# Direct Rendering Manager: the kernel's list of display connectors
# (HDMI, eDP, …) at /sys/class/drm. Used when xrandr is missing (typical
# on Wayland). Not "digital rights management".
_DRM_DIR = Path("/sys/class/drm")
# First line of `xrandr --listmonitors` looks like: "Monitors: 2"
_XRANDR_MONITORS_RE = re.compile(r"^Monitors:\s+(\d+)\s*$", re.MULTILINE)


def screen_count() -> int:
    """How many displays mpv should cover. Always at least 1."""
    # XWayland sets DISPLAY as well; prefer Wayland detection in that case.
    on_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    on_x11 = bool(os.environ.get("DISPLAY")) and not on_wayland

    if on_x11:
        xrandr_count = _xrandr_monitor_count()
        if xrandr_count is not None and xrandr_count > 0:
            return xrandr_count

    # Wayland, or xrandr missing/failed: count connected kernel connectors.
    drm_count = _count_drm_connected(_DRM_DIR)
    if drm_count > 0:
        return drm_count
    return 1


def _parse_xrandr_monitor_count(output: str) -> int | None:
    """Return the monitor count from ``xrandr --listmonitors``, or None."""
    match = _XRANDR_MONITORS_RE.search(output)
    if match is None:
        return None
    return int(match.group(1))


def _count_drm_connected(drm_dir: Path) -> int:
    """Count DRM connectors whose ``status`` file is ``connected``."""
    try:
        entries = list(drm_dir.iterdir())
    except OSError:
        return 0

    connected = 0
    for entry in entries:
        # card0 itself has no status; connectors look like card0-HDMI-A-1.
        status_path = entry / "status"
        try:
            if not status_path.is_file():
                continue
            status = status_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if status == "connected":
            connected += 1
    return connected


def _xrandr_monitor_count() -> int | None:
    xrandr = shutil.which("xrandr")
    if xrandr is None:
        return None
    try:
        completed = subprocess.run(
            [xrandr, "--listmonitors"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return _parse_xrandr_monitor_count(completed.stdout)
