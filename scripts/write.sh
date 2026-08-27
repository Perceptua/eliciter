#!/usr/bin/env bash
# Open a writing session in indexia or perceptua. See scripts/write.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py write.py "$@"
