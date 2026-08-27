#!/usr/bin/env bash
# Run the test suite. The read-only gate is the part that must never regress.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
cd "$ROOT" && PYTHONPATH="$ROOT" exec "$PY" -m unittest discover -s tests -v
