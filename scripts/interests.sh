#!/usr/bin/env bash
# The interest profile and its tuning. See scripts/interests.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py interests.py "$@"
