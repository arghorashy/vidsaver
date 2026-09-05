from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MPV_INSTALL_HINT = "mpv is not installed. Install it with: sudo apt install mpv"

# mpv default: Escape leaves fullscreen. For a screensaver, quit instead.
MPV_INPUT_CONF = """\
ESC quit
q quit
"""


class PlayerError(Exception):
    """mpv could not be started."""


def play(videos: list[Path]) -> int:
    """Play *videos* looping fullscreen in mpv. Returns mpv's exit code."""
    mpv = shutil.which("mpv")
    if mpv is None:
        raise PlayerError(MPV_INSTALL_HINT)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".conf",
        prefix="vidsaver-mpv-",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(MPV_INPUT_CONF)
        input_conf = Path(handle.name)

    argv = [
        mpv,
        "--fullscreen",
        "--no-border",
        "--osc=no",
        "--osd-level=0",
        "--cursor-autohide=always",
        "--loop-playlist=inf",
        f"--input-conf={input_conf}",
        "--",
        *[str(path) for path in videos],
    ]
    try:
        completed = subprocess.run(argv, check=False)
    except OSError as exc:
        raise PlayerError(f"Failed to launch mpv: {exc}") from exc
    finally:
        input_conf.unlink(missing_ok=True)
    return completed.returncode
