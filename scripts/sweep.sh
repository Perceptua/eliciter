#!/usr/bin/env bash
# Sweep arxiv and queue what a session picks. See scripts/sweep.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py sweep.py "$@"
