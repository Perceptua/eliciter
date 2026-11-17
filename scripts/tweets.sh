#!/usr/bin/env bash
# Validate, render and decide tweet cards; check and install the voice profile.
# See scripts/tweets.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py tweets.py "$@"
