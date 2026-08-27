#!/usr/bin/env bash
# Shared helpers for eliciter's wrappers. `source` this — do not execute directly.
#
# Deliberately thin. indexia's scripts/lib.sh wraps a database; eliciter has no database
# and no daemons, so all this does is find a python and establish ROOT. Credentials are
# NOT loaded here — eliciterlib/config.py reads indexia's docker/.env directly at import,
# so there is one reader of that file and one place the secret is handled.
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
