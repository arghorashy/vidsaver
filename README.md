# vidsaver

Play every video in a folder fullscreen, looping the playlist. Order is random without replacement each pass, with a 2-video cooldown before a file can play again. **Left** and **Right** skip files (resume at each file's last offset). Quit with **Escape** or **q**.

A sqlite database of videos is kept at `~/.local/state/vidsaver/vidsaver.sqlite` (or `$XDG_STATE_HOME/vidsaver/`). Identity is a sample hash (size plus the first and last 1 MiB).

## Run

`./run.sh` installs [mpv](https://mpv.io/) via apt if it is missing, then starts the app. No `pip install` is required.

Python 3.11+ is required. On non-apt systems, install mpv yourself, then use the same script.

## Configure

Copy `config.example.toml` to `./config.toml` or `~/.config/vidsaver/config.toml`. Local config wins.

- **`video_dir`** — folder of videos (required). Scanned non-recursively for `mp4`, `mkv`, `webm`, `avi`, `mov`, `m4v`, `wmv`, `3gp`, and `3gpp`.
- **`screens`** — `"primary"` (default: one window on the first display) or `"all"` (one window on each connected display). With `"all"`, Escape or **q** in any window stops playback on every screen.
- **`mute`** — `true` (default: no audio on any window) or `false` (audio on the primary window only). Extra windows are always silent.
- **`skip_ends`** — `true` (default: skip the first and last 30 seconds of each file) or `false` (play from the true start to EOF). Files 60 seconds or shorter always play in full.
- **`rotate_minutes`** — minutes on the current file before jumping to the next (default 15). If less than a quarter of that interval remains in the file, it plays to the end instead (the trimmed end, when `skip_ends` is on). Each file resumes at its last offset after a pass and after quit; identity is the sample hash, so a rename keeps progress.
- **`exit_on`** — `"escape"` (default: quit with Escape or **q**) or `"any-input"` (also quit on other keys, mouse buttons, and the wheel). **Left** and **Right** skip files in both modes; they never quit. The idle screensaver wrapper always uses `"any-input"`.

Overrides:

```bash
./run.sh --dir /path/to/videos
./run.sh --config /path/to/config.toml
./run.sh --exit-on any-input
```

`--dir` wins over `video_dir` in the config file.

## Idle screensaver (X11)

After a period with no keyboard or mouse, vidsaver starts. It does **not** run while another window is fullscreen or while audio is playing (typical YouTube / VLC). Any key or mouse button quits, except **Left** and **Right**, which skip files. This uses [xidlehook](https://github.com/jD91mZM2/xidlehook); it does not replace a desktop lock screen.

X11 only (`DISPLAY` set, not Wayland). Wayland idle hooks are compositor-specific (GNOME, KDE, Sway, and so on each have their own), so they are not implemented here.

```bash
./scripts/install-screensaver.sh
./scripts/uninstall-screensaver.sh
```

Install checks for X11, Python 3.11+, mpv, and xidlehook (and apt-installs mpv when it can). xidlehook is not in Ubuntu/Mint apt; the installer builds it with [cargo](https://rustup.rs) (`cargo install xidlehook --bins --locked`) after installing the X11/Pulse build headers (`libxcb1-dev`, `libxcb-screensaver0-dev`, `libxss-dev`, `libpulse-dev`). Then it writes `~/.config/autostart/vidsaver-idle.desktop` and starts the idle wrapper. It asks for the idle timeout in minutes (default 10) and stores that in the autostart file. Re-run install to change it. Non-interactive installs use `VIDSAVER_IDLE_SECONDS` (default 600).

If Cinnamon, GNOME, XFCE, or similar already blanks or locks on idle, turn that **off** in system settings or you will get two screensavers. The installer does not change those settings. After uninstall, turn the desktop lock back on if you disabled it.

## Scripts

`./scripts/watch_catalog.py` polls that database and prints filename, offset, last playback time, clip count, and cumulative watch time — useful while testing or debugging resume.
