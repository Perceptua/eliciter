#!/usr/bin/env bash
# Shared helpers for eliciter's wrappers. `source` this — do not execute directly.
#
# Deliberately thin. indexia's scripts/lib.sh wraps a database; eliciter has no database,
# so most of this does is find a python and establish ROOT. Credentials are NOT loaded
# here — eliciterlib/config.py reads indexia's docker/.env directly at import, so there is
# one reader of that file and one place the secret is handled.
#
# The one daemon eliciter runs is the backgrounded UI (scripts/ui.sh start); the helpers
# below are a trimmed copy of indexia's daemon_* functions in its own lib.sh.
set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$LIB_DIR/.." && pwd)"

c_info=$'\033[1;36m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
log() { printf '%s[eliciter]%s %s\n' "$c_info" "$c_off" "$*"; }
die() { printf '%s[eliciter] ERROR:%s %s\n' "$c_err" "$c_off" "$*" >&2; exit 1; }

PY="${ELICITER_PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || die "no $PY on PATH (set ELICITER_PYTHON)"

# Run a script in scripts/ with the project root importable.
run_py() {
  local script="$1"; shift
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" "$LIB_DIR/$script" "$@"
}

# -- daemon helpers (currently only scripts/ui.sh) ---------------------------
#
# Pid files go stale (the process died; worse, the number was reused), so daemon_pid
# confirms the pid is alive AND that its command line still names the script before
# believing it. The match is against the full script path, not the bare name, because
# indexia runs its own scripts/ui.py on this machine — a bare-name match once mistook
# eliciter's ui.py for indexia's (see indexia's scripts/lib.sh).
PID_DIR="${ELICITER_RUN_DIR:-$HOME/.eliciter}"

daemon_pidfile() { printf '%s/%s.pid\n' "$PID_DIR" "$1"; }

# Print the live pid of a daemon, or nothing. Usage: daemon_pid <name> <$ROOT/scripts/x.py>
daemon_pid() {
  local name="$1" script="$2" pidfile pid=""
  pidfile="$(daemon_pidfile "$name")"
  if [[ -r "$pidfile" ]]; then
    read -r pid <"$pidfile" 2>/dev/null || pid=""
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null \
       && tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -Fq -- "$script"; then
      printf '%s\n' "$pid"
      return 0
    fi
    rm -f "$pidfile"                      # gone, or the number belongs to something else now
  fi
  # No usable pid file. Fall back to a scan that CANNOT match an ordinary shell: the command
  # line has to begin with a python interpreter running that script. This also adopts a daemon
  # started before pid files existed, so an upgrade does not orphan a running process.
  pid="$(pgrep -f "^[^ ]*python[0-9.]* [^ ]*${script}([[:space:]]|\$)" 2>/dev/null | head -n1)"
  [[ -n "$pid" ]] || return 1
  daemon_write_pid "$name" "$pid"
  printf '%s\n' "$pid"
}

daemon_running() { daemon_pid "$@" >/dev/null 2>&1; }

daemon_write_pid() {
  mkdir -p "$PID_DIR"
  printf '%s\n' "$2" >"$(daemon_pidfile "$1")"
}

# Stop a daemon: TERM, wait up to 5s, then KILL. Exit 0 only if something was actually stopped.
daemon_stop() {
  local name="$1" script="$2" pid i
  pid="$(daemon_pid "$name" "$script")" || return 1
  kill "$pid" 2>/dev/null || true
  for ((i = 0; i < 50; i++)); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  rm -f "$(daemon_pidfile "$name")"
  return 0
}
