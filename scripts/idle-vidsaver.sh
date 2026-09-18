#!/usr/bin/env bash
# Launch vidsaver after idle. Does not kill it when the user moves again;
# vidsaver itself quits (any key or mouse button when started from here).
# Usage: ./scripts/idle-vidsaver.sh
# VIDSAVER_IDLE_SECONDS (default 600) is the idle timeout.
# install-screensaver.sh asks for minutes and bakes the seconds into autostart.

# Exit on error, unset variables, and failed commands in a pipeline.
set -euo pipefail

# Repo root (this file lives in scripts/).
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default 10 minutes. The installer sets this on autostart; override here
# only for a manual wrapper start. Not a player/config.toml setting.
idle_seconds="${VIDSAVER_IDLE_SECONDS:-600}"

if ! [[ "$idle_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "VIDSAVER_IDLE_SECONDS must be a positive integer, not ${idle_seconds}" >&2
  exit 1
fi

if ! command -v xidlehook >/dev/null 2>&1; then
  echo "xidlehook is not installed. Run ./scripts/install-screensaver.sh" >&2
  exit 1
fi

# Pidfile so stop-idle-wrapper.sh can find this process. After exec,
# xidlehook keeps this PID; the stopper checks cmdline before kill.
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/vidsaver"
mkdir -p "$state_dir"
echo $$ > "$state_dir/idle.pid"

# Launch-only: xidlehook starts vidsaver and then leaves it alone.
# --not-when-fullscreen / --not-when-audio skip typical YouTube and VLC.
# Timer commands go through `sh -c`. The empty abort string means activity
# after launch does not kill the player; vidsaver quits on any-input instead.
exec xidlehook \
  --not-when-fullscreen \
  --not-when-audio \
  --timer "$idle_seconds" \
  "$root/run.sh --exit-on any-input" \
  ""
