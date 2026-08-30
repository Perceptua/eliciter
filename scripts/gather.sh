#!/usr/bin/env bash
# Read every source into state/material.json. See scripts/gather.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py gather.py "$@"
