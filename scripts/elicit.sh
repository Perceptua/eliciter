#!/usr/bin/env bash
# Gather every source and render today's writing prompts. See scripts/elicit.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py elicit.py "$@"
