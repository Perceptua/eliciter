#!/usr/bin/env python3
"""Read every source and write down what is there, for a session to turn into prompts.

  scripts/gather.sh                  # all sources    → state/material.json
  scripts/gather.sh --no-papers      # skip the reading queue
  scripts/gather.sh --stdout         # print the summary, write nothing
  scripts/gather.sh --quiet

This is the deterministic half of eliciting. It reaches into the indexia graph, the
perceptua posts, the audua session summaries and the reading queue — all through the
read-only gate in `eliciterlib/readonly.py` — and writes the whole of what it found to
`state/material.json`.

It does **not** decide what any of it means. Nothing here scores a theme, picks a register
or writes an ask; that is the `elicit-writing` skill's job, in a session that has actually
read the material.

**Normally you do not run this by hand.** Gathering and judging are one move: ask a session
for prompts and it gathers first, so the material behind a run was read at the moment it was
judged. Running it alone is for looking — `--stdout` especially, which writes nothing.
Deliberately nothing schedules it, so a standing run of prompts is never quietly rebuilt
underneath you.

A source that is unreachable is recorded and skipped rather than failing the run: the
indexia container is often down, and three sources' worth of material plus an honest note
about the fourth beats nothing at all.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import material                                     # noqa: E402


def main():
    p = argparse.ArgumentParser(prog="gather", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-papers", action="store_true", help="skip the reading queue")
    p.add_argument("--no-graph", action="store_true", help="skip indexia")
    p.add_argument("--no-audua", action="store_true", help="skip audua session summaries")
    p.add_argument("--no-posts", action="store_true", help="skip perceptua")
    p.add_argument("--stdout", action="store_true", help="print the summary, write nothing")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr))

    data = material.gather(log=log, want_papers=not a.no_papers,
                           want_graph=not a.no_graph, want_posts=not a.no_posts,
                           want_audua=not a.no_audua)
    counts = material.summarize(data)

    if a.stdout:
        print(json.dumps({"summary": counts,
                          "unavailable": data["unavailable"]}, indent=2))
        return 0

    dest = material.write(data, log=log)
    if not a.quiet:
        print("[gather] " + " · ".join(f"{k} {v}" for k, v in counts.items()))
        for name, why in (data.get("unavailable") or {}).items():
            print(f"[gather] {name} unavailable — {why}", file=sys.stderr)
        print(f"  {dest}\n"
              f"  a session asked for prompts reads this; it is not a run on its own")
    # Non-zero when a source did not answer, so a caller that only checks the exit status
    # still finds out. The session that runs this is told to read `unavailable` and say so;
    # this is the belt to that's braces.
    return 1 if data.get("unavailable") else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
