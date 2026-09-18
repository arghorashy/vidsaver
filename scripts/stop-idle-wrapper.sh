#!/usr/bin/env bash
# Stop the vidsaver idle watcher recorded in idle.pid.
# Usage: ./scripts/stop-idle-wrapper.sh [--quiet-if-absent]
# Kills only if /proc/PID/cmdline is our wrapper or our xidlehook (not a
# reused PID). Install uses --quiet-if-absent so a first install stays quiet.

# Exit on error, unset variables, and failed commands in a pipeline.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wrapper="$root/scripts/idle-vidsaver.sh"
run_sh="$root/run.sh"
pid_file="${XDG_STATE_HOME:-$HOME/.local/state}/vidsaver/idle.pid"

quiet_if_absent=0
if [[ "${1:-}" == "--quiet-if-absent" ]]; then
  quiet_if_absent=1
fi

# True if this PID is still our idle job: bash running the wrapper (before
# exec) or xidlehook whose timer command is this repo's run.sh (after exec).
_is_our_watcher() {
  local pid="$1"
  local cmdline
  [[ -r "/proc/${pid}/cmdline" ]] || return 1
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline")"
  if [[ "$cmdline" == *xidlehook* && "$cmdline" == *"$run_sh"* ]]; then
    return 0
  fi
  if [[ "$cmdline" == *"$wrapper"* ]]; then
    return 0
  fi
  return 1
}

_not_running() {
  rm -f "$pid_file"
  if [[ "$quiet_if_absent" -eq 0 ]]; then
    echo "Idle wrapper was not running."
  fi
}

if [[ ! -f "$pid_file" ]]; then
  _not_running
  exit 0
fi

pid="$(cat "$pid_file")"
if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
  _not_running
  exit 0
fi

if ! _is_our_watcher "$pid"; then
  echo "Pidfile $pid_file pointed at PID $pid, which is not our idle wrapper; not killing it." >&2
  rm -f "$pid_file"
  exit 0
fi

kill "$pid" || true
# Wait so a following install does not start a second xidlehook beside this one.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.1
done
rm -f "$pid_file"
echo "Stopped the idle wrapper."
