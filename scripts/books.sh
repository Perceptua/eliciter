#!/usr/bin/env bash
# Your reading list outside arxiv: add, update, list. See scripts/books.py --help.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py books.py "$@"
