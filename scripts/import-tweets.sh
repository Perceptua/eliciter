#!/usr/bin/env bash
# Import your tweets from an X archive into tweets/. See scripts/import_tweets.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py import_tweets.py "$@"
