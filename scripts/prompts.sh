#!/usr/bin/env bash
# Validate and render the prompts a session wrote. See scripts/prompts.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py prompts.py "$@"
