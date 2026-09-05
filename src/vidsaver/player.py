from __future__ import annotations

import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from vidsaver.screens import screen_count

MPV_INSTALL_HINT = "mpv is not installed. Install it with: sudo apt install mpv"

# mpv default: Escape leaves fullscreen. For a screensaver, quit instead.
MPV_INPUT_CONF = """\
ESC quit
q quit
"""


class PlayerError(Exception):
    """mpv could not be started."""


def play(videos: list[Path], screens: str = "primary") -> int:
    """Play *videos* looping fullscreen in mpv. Returns mpv's exit code.

    ``screens="primary"`` uses one window on display 0. ``screens="all"``
    starts one window per connected display; extra windows have no audio.
    """
    mpv = shutil.which("mpv")
    if mpv is None:
        raise PlayerError(MPV_INSTALL_HINT)

    # mpv reads key bindings from a file path. Write a temp copy so we do not
    # depend on package data, and keep the file until every mpv process exits
    # (delete=False: the with-block would otherwise unlink it on close).
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".conf",
        prefix="vidsaver-mpv-",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(MPV_INPUT_CONF)
        input_conf = Path(handle.name)

    # One window on screen 0, or one window per detected display.
    count = screen_count() if screens == "all" else 1
    if count < 1:
        count = 1

    # SIGTERM (kill, service stop) normally aborts Python without running
    # `finally`. Save the current handler, then replace it with
    # `_exit_on_sigterm` (raises SystemExit so `finally` still runs).
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _exit_on_sigterm)
    procs: list[subprocess.Popen[bytes]] = []
    try:
        for index in range(count):
            # Mute every window after the first so the same playlist is not
            # mixed through the speakers N times.
            argv = mpv_argv(
                mpv,
                videos,
                input_conf,
                screen=index,
                mute_audio=index != 0,
            )
            procs.append(subprocess.Popen(argv))
        if len(procs) == 1:
            return procs[0].wait()
        # Any window quitting (Escape/q) should tear down the rest.
        return _wait_until_any_exits(procs)
    except OSError as exc:
        raise PlayerError(f"Failed to launch mpv: {exc}") from exc
    finally:
        # Stop leftovers after a normal return, Ctrl+C, or SIGTERM.
        for proc in procs:
            _stop_process(proc)
        signal.signal(signal.SIGTERM, previous_sigterm)
        input_conf.unlink(missing_ok=True)


def mpv_argv(
    mpv: str,
    videos: list[Path],
    input_conf: Path,
    *,
    screen: int,
    mute_audio: bool,
) -> list[str]:
    """Build the mpv command for one display."""
    argv = [
        mpv,
        "--fullscreen",
        "--no-border",
        "--osc=no",
        "--osd-level=0",
        "--cursor-autohide=always",
        "--loop-playlist=inf",
        # Pin both the window and the fullscreen target; otherwise a WM may
        # place the window on screen 0 and fullscreen it on another.
        f"--screen={screen}",
        f"--fs-screen={screen}",
        f"--input-conf={input_conf}",
    ]
    if mute_audio:
        # Discard audio instead of --mute so this instance never opens a device.
        argv.append("--ao=null")
    # "--" so a video named like an option is still treated as a file.
    argv.extend(["--", *[str(path) for path in videos]])
    return argv


def _wait_until_any_exits(procs: list[subprocess.Popen[bytes]]) -> int:
    # poll() is non-blocking; sleep so this is not a busy loop.
    while True:
        for proc in procs:
            code = proc.poll()
            if code is not None:
                return code
        time.sleep(0.05)


def _stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        # SIGTERM ignored: force-kill, then wait so we do not leave a zombie.
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # SIGKILL did not reap it either (stuck kernel state, etc.).
            # Give up rather than hang shutdown forever.
            pass


def _exit_on_sigterm(signum: int, _frame: object) -> None:
    # Raise so play()'s `finally` can stop mpv. 128+signal is the usual
    # shell exit code for "killed by signal".
    raise SystemExit(128 + signum)
