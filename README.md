# vidsaver

Play every video in a folder fullscreen, looping the playlist. Quit with **Escape** or **q**.

## Run

`./run.sh` installs [mpv](https://mpv.io/) via apt if it is missing, then starts the app. No `pip install` is required.

```bash
./run.sh
```

Set `video_dir` in `./config.toml` (copy from `config.example.toml`) or `~/.config/vidsaver/config.toml`. Local config wins.

`screens` is `"primary"` (default: one window on the first display) or `"all"` (one window on each connected display). With `"all"`, audio plays on the primary display only; Escape or **q** in any window stops playback on every screen.

Overrides:

```bash
./run.sh --dir /path/to/videos
./run.sh --config /path/to/config.toml
```

`--dir` wins over `video_dir` in the config file.

The folder is scanned non-recursively for `mp4`, `mkv`, `webm`, `avi`, `mov`, `m4v`, and `wmv`.

Python 3.11+ is required. On non-apt systems, install mpv yourself, then use the same script.

