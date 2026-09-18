#!/usr/bin/env bash
# Remove vidsaver idle autostart and stop the running wrapper.
# Usage: ./scripts/uninstall-screensaver.sh

# Exit on error, unset variables, and failed commands in a pipeline.
set -euo pipefail

# Repo root (this file lives in scripts/).
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

desktop_path="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/vidsaver-idle.desktop"

# Stop future logins from starting the wrapper. Repo files stay in place.
if [[ -e "$desktop_path" ]]; then
  rm -f "$desktop_path"
  echo "Removed $desktop_path"
else
  echo "No autostart file at $desktop_path"
fi

# Kill only our wrapper (cmdline check in stop-idle-wrapper.sh), not every
# xidlehook on the machine. A vidsaver already playing is left running.
"$root/scripts/stop-idle-wrapper.sh"

echo "If you turned off the desktop lock/blank when installing, turn it back on in system settings."
echo "Repo scripts remain at $root; only autostart and the running wrapper were removed."
