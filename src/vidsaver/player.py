from __future__ import annotations

import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from vidsaver.config import ExitOn
from vidsaver.mpv_ipc import MpvIpc
from vidsaver.playback import Playback
from vidsaver.rotation import playable_start, run_rotation
from vidsaver.screens import screen_count
from vidsaver.state import Progress

MPV_INSTALL_HINT = "mpv is not installed. Install it with: sudo apt install mpv"

# mpv default: Escape leaves fullscreen. For a screensaver, quit instead.
# any-input does not bind MOUSE_MOVE: the cursor jumps when the window
# opens and would quit immediately.
# LEFT/RIGHT are not in this list: they skip files (script-message) in
# every exit_on mode, including any-input.
_ANY_INPUT_QUIT = """\
ANY_UNICODE quit
SPACE quit
ENTER quit
TAB quit
BS quit
DEL quit
UP quit
DOWN quit
PGUP quit
PGDWN quit
HOME quit
END quit
ESC quit
q quit
MBTN_LEFT quit
MBTN_RIGHT quit
MBTN_MID quit
WHEEL_UP quit
WHEEL_DOWN quit
"""

# Appended last so they win over any leftover LEFT/RIGHT quit binds.
_ARROW_SKIP = """\
LEFT script-message vidsaver-prev
RIGHT script-message vidsaver-next
"""


def mpv_input_conf(exit_on: ExitOn = "escape") -> str:
    if exit_on == "any-input":
        return _ANY_INPUT_QUIT + _ARROW_SKIP
    return "ESC quit\nq quit\n" + _ARROW_SKIP


class PlayerError(Exception):
    """mpv could not be started."""


def play(
    videos: list[Path],
    screens: str = "primary",
    mute: bool = True,
    rotate_minutes: float = 15,
    start: float = 0,
    skip_ends: bool = True,
    exit_on: ExitOn = "escape",
    *,
    progress: Progress,
) -> int:
    """Play *videos* looping fullscreen in mpv. Returns mpv's exit code.

    ``screens="primary"`` uses one window on display 0. ``screens="all"``
    starts one window per connected display; extra windows have no audio.
    ``mute=True`` (the default) uses ``--no-audio`` on every window.
    After ``rotate_minutes``, jump to the next file. Resume points are stored
    on *progress*.
    ``start`` is the first file's resume point (mpv ``--start``).
    ``skip_ends=True`` (the default) skips the first and last 30 seconds
    of files longer than 60 seconds.
    ``exit_on="escape"`` (the default) quits on Escape or q.
    ``exit_on="any-input"`` also quits on other keys, mouse buttons, and
    the wheel. Left and Right skip files in both modes; they never quit.
    """
    mpv = shutil.which("mpv")
    if mpv is None:
        raise PlayerError(MPV_INSTALL_HINT)

    if videos:
        start = playable_start(
            start, progress.get_duration(videos[0]), skip_ends
        )

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
        handle.write(mpv_input_conf(exit_on))
        input_conf = Path(handle.name)

    ipc_dir = Path(tempfile.mkdtemp(prefix="vidsaver-ipc-"))

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
    clients: list[MpvIpc] = []
    try:
        for index in range(count):
            # Mute extras so the playlist is not mixed N times. mute=True
            # (default) silences the primary window as well.
            ipc_server = ipc_dir / f"mpv-{index}"
            argv = mpv_argv(
                mpv,
                videos,
                input_conf,
                screen=index,
                mute_audio=mute or index != 0,
                ipc_server=ipc_server,
                start=start,
            )
            procs.append(subprocess.Popen(argv))
            clients.append(MpvIpc(ipc_server))
        return run_rotation(
            Playback(procs, clients),
            rotate_minutes,
            progress=progress,
            skip_ends=skip_ends,
        )
    except OSError as exc:
        raise PlayerError(f"Failed to launch mpv: {exc}") from exc
    finally:
        # Stop leftovers after a normal return, Ctrl+C, or SIGTERM.
        for client in clients:
            client.close()
        for proc in procs:
            _stop_process(proc)
        signal.signal(signal.SIGTERM, previous_sigterm)
        input_conf.unlink(missing_ok=True)
        shutil.rmtree(ipc_dir, ignore_errors=True)


def mpv_argv(
    mpv: str,
    videos: list[Path],
    input_conf: Path,
    *,
    screen: int,
    mute_audio: bool,
    ipc_server: Path | None = None,
    start: float = 0,
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
        # Pause at EOF instead of auto-advancing. Rotation issues
        # playlist-next so the next file can be seeked before it plays.
        "--keep-open=always",
        # Pin both the window and the fullscreen target; otherwise a WM may
        # place the window on screen 0 and fullscreen it on another.
        f"--screen={screen}",
        f"--fs-screen={screen}",
        f"--input-conf={input_conf}",
    ]
    if ipc_server is not None:
        argv.append(f"--input-ipc-server={ipc_server}")
    if start > 0:
        argv.append(f"--start={start}")
    if mute_audio:
        # Disable audio entirely. --ao=null still inits a driver, and
        # playlist-next while paused logs "illegal state: start() while paused".
        argv.append("--no-audio")
    # "--" so a video named like an option is still treated as a file.
    argv.extend(["--", *[str(path) for path in videos]])
    return argv


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
