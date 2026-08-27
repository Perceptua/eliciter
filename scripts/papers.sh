#!/usr/bin/env bash
# The reading queue: list papers, mark them read or rejected. See scripts/papers.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py papers.py "$@"
