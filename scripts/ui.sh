#!/usr/bin/env bash
# Manage the local eliciter UI — start | stop | status | run. See scripts/ui.py --help.
# `start` backgrounds it (setsid, detached, logs to file) so `make ui-up` outlives the
# shell that launched it; `run` is the old foreground behavior, Ctrl-C to stop.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

LOG="${ELICITER_UI_LOG:-$PID_DIR/ui.log}"
PORT="${ELICITER_UI_PORT:-8473}"
NAME="ui"
SCRIPT="$ROOT/scripts/ui.py"

# Where a *running* daemon actually is, worked out from its own argv.
#
# This used to read the flags of the invocation asking the question, which is wrong
# whenever they differ from the ones the daemon was started with: `ui.sh status` on a
# daemon started as `start --port 8474` reported `http://127.0.0.1:8473/`, and so did
# `start` when it declined to start a second one. A URL that is confidently named and
# refuses the connection is worse than no URL — it sends you looking for a crashed server
# that is running fine one port over.
#
# --tailscale is not guessed at all. The FQDN comes from the tailnet at runtime and this
# wrapper cannot know it, so it points at the log, where the server prints the real URL.
url_for_pid() {
  local args port="$PORT"
  args=" $(daemon_cmdline "$1") "
  case "$args" in
    *" --tailscale "*) echo "an https:// tailnet URL — see $LOG"; return ;;
  esac
  [[ "$args" =~ [[:space:]]--port[[:space:]]+([0-9]+) ]] && port="${BASH_REMATCH[1]}"
  echo "http://127.0.0.1:$port/"
}

case "${1:-run}" in
  start)
    if pid="$(daemon_pid "$NAME" "$SCRIPT")"; then
      echo "[ui] already running (pid $pid) — $(url_for_pid "$pid")"
      exit 0
    fi
    mkdir -p "$PID_DIR"
    : >>"$LOG"
    before=$(( $(wc -c <"$LOG") ))          # only read back what THIS start writes
    # Detached so it outlives this shell; PYTHONPATH matches what run_py sets up.
    #
    # `-u` is load-bearing, not a flourish. Python block-buffers stdout when it is a file
    # rather than a tty, so the server's own "eliciter at <url>" banner sat in a buffer
    # that never filled: `start` promised "logs to ~/.eliciter/ui.log" and the log stayed
    # zero bytes for days while the daemon ran. Unbuffered, the log is a log, and the wait
    # below has something to wait for.
    PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      setsid "$PY" -u "$SCRIPT" "${@:2}" >>"$LOG" 2>&1 </dev/null &
    pid=$!
    daemon_write_pid "$NAME" "$pid"

    # Wait for the server to say where it is, or to die trying — up to ~10s. Printing
    # "started (pid N)" the instant the fork returns is a claim the wrapper has not
    # checked: a bad --port, a busy socket or an unreachable indexia all exit within the
    # second, and the old code reported them as a successful start. Taking the URL from
    # the server's own banner also means this line is right for --tailscale, which the
    # wrapper could not have worked out for itself.
    url=""
    for ((i = 0; i < 100; i++)); do
      url="$(tail -c "+$((before + 1))" "$LOG" 2>/dev/null \
             | grep -m1 -oE 'https?://[^ ]+' || true)"
      [[ -n "$url" ]] && break
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done

    if [[ -n "$url" ]]; then
      echo "[ui] started (pid $pid) — $url , log: $LOG"
    elif kill -0 "$pid" 2>/dev/null; then
      echo "[ui] started (pid $pid) but it has not reported a URL — log: $LOG"
    else
      rm -f "$(daemon_pidfile "$NAME")"
      echo "[ui] failed to start — the last of $LOG:" >&2
      tail -c "+$((before + 1))" "$LOG" | tail -n 20 >&2
      exit 1
    fi
    ;;
  run)   # foreground (the old default); pass-through args (--port N, --open, --tailscale)
    run_py ui.py "${@:2}"
    ;;
  stop)
    daemon_stop "$NAME" "$SCRIPT" && echo "[ui] stopped" || echo "[ui] not running"
    ;;
  status)
    if pid="$(daemon_pid "$NAME" "$SCRIPT")"; then
      echo "[ui] UP (pid $pid) — $(url_for_pid "$pid")"
    else
      echo "[ui] DOWN"
    fi
    ;;
  *) echo "usage: ui.sh [start|stop|status|run] [--port N] [--open] [--tailscale]" >&2; exit 2 ;;
esac
