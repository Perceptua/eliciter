#!/usr/bin/env bash
# Manage the local eliciter UI — start | stop | status | run. See scripts/ui.py --help.
# `start` backgrounds it (setsid, detached, logs to file) so `make ui-up` outlives the
# shell that launched it; `run` is the old foreground behavior, Ctrl-C to stop.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

LOG="${ELICITER_UI_LOG:-$PID_DIR/ui.log}"
PORT="${ELICITER_UI_PORT:-8473}"
NAME="ui"
SCRIPT="$ROOT/scripts/ui.py"

running() { daemon_running "$NAME" "$SCRIPT"; }

# --tailscale picks its own host/port at runtime (see ui.py); the guess below only
# applies to the default loopback case.
url_hint() {
  for a in "${@:2}"; do
    [ "$a" = "--tailscale" ] && { echo "check the log for the https:// tailnet URL"; return; }
  done
  echo "http://127.0.0.1:$PORT/"
}

case "${1:-run}" in
  start)
    running && { echo "[ui] already running — $(url_hint "$@")"; exit 0; }
    mkdir -p "$PID_DIR"
    # Detached so it outlives this shell; PYTHONPATH matches what run_py sets up.
    PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      setsid "$PY" "$SCRIPT" "${@:2}" >>"$LOG" 2>&1 </dev/null &
    daemon_write_pid "$NAME" $!
    echo "[ui] started (pid $!) — $(url_hint "$@") , log: $LOG"
    ;;
  run)   # foreground (the old default); pass-through args (--port N, --open, --tailscale)
    run_py ui.py "${@:2}"
    ;;
  stop)
    daemon_stop "$NAME" "$SCRIPT" && echo "[ui] stopped" || echo "[ui] not running"
    ;;
  status)
    if running; then
      echo "[ui] UP (pid $(daemon_pid "$NAME" "$SCRIPT")) — $(url_hint "$@")"
    else
      echo "[ui] DOWN"
    fi
    ;;
  *) echo "usage: ui.sh [start|stop|status|run] [--port N] [--open] [--tailscale]" >&2; exit 2 ;;
esac
