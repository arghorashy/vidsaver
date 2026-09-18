#!/usr/bin/env bash
# Install vidsaver as a launch-only X11 idle screensaver (xidlehook + autostart).
# Usage: ./scripts/install-screensaver.sh
# Asks for the idle timeout in minutes (default 10) and writes it into autostart.
# Non-interactive: VIDSAVER_IDLE_SECONDS (default 600) if stdin is not a terminal.

# Exit on error, unset variables, and failed commands in a pipeline.
set -euo pipefail

# Repo root (this file lives in scripts/).
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Freedesktop autostart: most DEs start .desktop files here at login.
desktop_dir="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
desktop_path="$desktop_dir/vidsaver-idle.desktop"
wrapper="$root/scripts/idle-vidsaver.sh"

_fail() {
  echo "$*" >&2
  exit 1
}

# Same apt path as run.sh. Returns 1 when apt-get is missing so the
# caller can print a package-specific install hint.
_install_apt() {
  local pkg="$1"
  if ! command -v apt-get >/dev/null 2>&1; then
    return 1
  fi
  echo "$pkg not found; installing with apt..."
  # Noninteractive so apt does not prompt; -y accepts the package list.
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
}

# Preflight before writing autostart or starting anything.
echo "Checking dependencies..."

# X11 only. Wayland idle hooks are compositor-specific and not implemented.
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  _fail "This installer is for X11 only (WAYLAND_DISPLAY is set). Wayland idle hooks are compositor-specific."
fi
if [[ -z "${DISPLAY:-}" ]]; then
  _fail "No X11 DISPLAY. Log into a graphical X11 session and re-run."
fi

# Same Python floor as the app (3.11+ for tomllib).
if ! command -v python3 >/dev/null 2>&1; then
  _fail "python3 is not installed. Install Python 3.11 or newer."
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  _fail "Python 3.11 or newer is required (found $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])'))."
fi

if ! command -v mpv >/dev/null 2>&1; then
  _install_apt mpv || _fail "mpv is not installed, and apt-get was not found. Install mpv and re-run."
fi
if ! command -v mpv >/dev/null 2>&1; then
  _fail "mpv is still not on PATH after install."
fi

if ! command -v xidlehook >/dev/null 2>&1; then
  _install_apt xidlehook || _fail "xidlehook is not installed. Install it (Debian/Ubuntu: sudo apt install xidlehook) and re-run."
fi
if ! command -v xidlehook >/dev/null 2>&1; then
  _fail "xidlehook is still not on PATH after install."
fi

# Timeout lives on the wrapper, not in config.toml. Ask in minutes; persist
# seconds on Exec= so login uses the same value. Enter keeps 10 minutes.
# A pipe/script skips the prompt and uses VIDSAVER_IDLE_SECONDS or 600.
if [[ -t 0 ]]; then
  read -r -p "Idle timeout in minutes [10]: " idle_minutes
  idle_minutes="${idle_minutes:-10}"
  if ! [[ "$idle_minutes" =~ ^[1-9][0-9]*$ ]]; then
    _fail "Idle timeout must be a positive integer of minutes, not ${idle_minutes}"
  fi
  idle_seconds=$((idle_minutes * 60))
else
  idle_seconds="${VIDSAVER_IDLE_SECONDS:-600}"
  if ! [[ "$idle_seconds" =~ ^[1-9][0-9]*$ ]]; then
    _fail "VIDSAVER_IDLE_SECONDS must be a positive integer, not ${idle_seconds}"
  fi
fi

# Login autostart. Cinnamon is not required; any DE that honors this folder works.
mkdir -p "$desktop_dir"
cat > "$desktop_path" <<EOF
[Desktop Entry]
Type=Application
Name=vidsaver idle
Comment=Start vidsaver after the session is idle
Exec=/usr/bin/env VIDSAVER_IDLE_SECONDS=$idle_seconds $wrapper
X-GNOME-Autostart-enabled=true
Hidden=false
EOF

# Start now so a logout is not required. Restart if a previous install is
# already running, so a new timeout takes effect immediately.
"$root/scripts/stop-idle-wrapper.sh" --quiet-if-absent
VIDSAVER_IDLE_SECONDS="$idle_seconds" nohup "$wrapper" >/dev/null 2>&1 &
echo "Started idle wrapper (timeout ${idle_seconds}s)."

echo "Installed autostart: $desktop_path"
echo "Uninstall with: $root/scripts/uninstall-screensaver.sh"

# Remind only. Flipping DE lock settings here would surprise the user,
# and uninstall would have to restore them.
desktop="${XDG_CURRENT_DESKTOP:-}"
if echo "$desktop" | grep -qiE 'cinnamon|gnome|xfce|mate|kde|lxqt'; then
  echo
  echo "This desktop already has its own idle lock ($desktop)."
  echo "Turn that lock/blank off in system settings, or you may get two"
  echo "screensavers at once (the desktop lock on top of vidsaver)."
  echo "The installer does not change those settings for you."
fi
