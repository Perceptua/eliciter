#!/usr/bin/env bash
# Check every source eliciter depends on, and say plainly which are reachable.
# Run this first when a digest comes back empty — "quiet" and "broken" look alike.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
run_py doctor.py "$@"
