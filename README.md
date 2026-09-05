# vidsaver

Play every video in a folder fullscreen, looping the playlist. Order is random without replacement each pass, with a 2-video cooldown before a file can play again. Quit with **Escape** or **q**.

## Run

`./run.sh` installs [mpv](https://mpv.io/) via apt if it is missing, then starts the app. No `pip install` is required.


Python 3.11+ is required. On non-apt systems, install mpv yourself, then use the same script.

## Configure

Copy `config.example.toml` to `./config.toml` or `~/.config/vidsaver/config.toml`. Local config wins.

- **`video_dir`** — folder of videos (required). Scanned non-recursively for `mp4`, `mkv`, `webm`, `avi`, `mov`, `m4v`, `wmv`, `3gp`, and `3gpp`.
- **`screens`** — `"primary"` (default: one window on the first display) or `"all"` (one window on each connected display). With `"all"`, Escape or **q** in any window stops playback on every screen.
- **`mute`** — `true` (default: no audio on any window) or `false` (audio on the primary window only). Extra windows are always silent.
- **`rotate_minutes`** — minutes on the current file before jumping to the next (default 15). After a full pass **in this run**, each file resumes at its last offset. Progress is not saved when you quit.

Overrides:

```bash
./run.sh --dir /path/to/videos
./run.sh --config /path/to/config.toml
```

`--dir` wins over `video_dir` in the config file.