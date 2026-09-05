#!/usr/bin/env bash
# Install runtime deps (mpv) if needed, then run vidsaver.
# Usage: ./run.sh [--dir FOLDER] [--config FILE]

# Exit on error, unset variables, and failed commands in a pipeline.
set -euo pipefail

# Directory this script lives in, even if invoked from elsewhere.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# mpv is the fullscreen player; vidsaver just launches it.
# If it is not on PATH, try to install it with apt (Debian/Ubuntu/Mint).
if ! command -v mpv >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "mpv is not installed, and apt-get was not found." >&2
    echo "Install mpv and re-run." >&2
    exit 1
  fi
  echo "mpv not found; installing with apt..."
  # Noninteractive so apt does not prompt; -y accepts the package list.
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y mpv
fi

# Put the repo's src/ on PYTHONPATH so this works without `pip install`.
# If PYTHONPATH was already set, keep those entries after src/.
export PYTHONPATH="${root}/src${PYTHONPATH:+:${PYTHONPATH}}"

# Replace this shell with the app; pass through CLI args unchanged.
exec python3 -m vidsaver "$@"
