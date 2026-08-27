#!/usr/bin/env bash
# Serve the local eliciter UI on 127.0.0.1. See scripts/ui.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py ui.py "$@"
