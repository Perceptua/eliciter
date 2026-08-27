#!/usr/bin/env bash
# Sweep arxiv and rank it against your corpus. See scripts/arxiv_digest.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py arxiv_digest.py "$@"
