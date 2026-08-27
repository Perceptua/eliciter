#!/usr/bin/env python3
"""Turn what is waiting into things to write.

Reads three sources — the indexia graph, the perceptua posts, the reading queue — and
renders numbered prompts to `prompts/latest.md`. Every prompt is a request for a **response**:
to a note the corpus is leaning on, to a poem nothing has answered, to a paper you have
read. They arrive in that order, which is `signals.SOURCES`.

  scripts/elicit.sh                  # all sources
  scripts/elicit.sh --no-papers      # skip papers you have read
  scripts/elicit.sh --stdout         # print instead of writing

This does not touch the network — sweeping is `scripts/arxiv-digest.sh`, run weekly. It
does not write to indexia or perceptua either; both are read through the gate in
`eliciterlib/readonly.py`. Use `scripts/write.sh <n>` to open a session where the writing
actually belongs.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import arxiv, corpus, posts, prompts, render, status  # noqa: E402


def main():
    p = argparse.ArgumentParser(prog="elicit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, help="max prompts (default from .env)")
    p.add_argument("--no-papers", action="store_true", help="skip papers you have read")
    p.add_argument("--no-graph", action="store_true", help="skip indexia")
    p.add_argument("--no-posts", action="store_true", help="skip perceptua")
    p.add_argument("--stdout", action="store_true", help="print instead of writing")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr))
    limit = a.limit if a.limit is not None else config.i("ELICITER_MAX_PROMPTS")

    signals, counts, failures = [], {}, []

    def gather(name, fn):
        try:
            got = fn()
            signals.extend(got)
            counts[name] = len(got)
        except SystemExit as e:                      # sources raise SystemExit for "unreachable"
            failures.append(f"{name}: {e}")
            log(f"[{name}] unavailable — {e}")
        except Exception as e:                       # noqa: BLE001
            failures.append(f"{name}: {type(e).__name__}: {e}")
            log(f"[{name}] failed — {type(e).__name__}: {e}")

    db = None
    if not a.no_graph:
        try:
            db = corpus.connect()
        except SystemExit as e:
            failures.append(f"indexia: {e}")
            log(f"[indexia] unavailable — {e}")
    if db is not None:
        gather("indexia", lambda: corpus.signals(db, log=log))
    if not a.no_papers:
        gather("papers", lambda: status.signals(status.Queue(), log=log))
    if not a.no_posts:
        # Posts are matched against the same profile the sweep uses, so the poem that
        # surfaces is the one adjacent to current reading rather than an arbitrary one.
        prof = arxiv.build_profile(db, log=lambda *_: None)
        gather("perceptua", lambda: posts.signals(profile=prof, log=log))

    built = prompts.build(signals, limit=limit)

    quiet = None
    if not built:
        quiet = ("No source produced a signal. " + (
            "All sources answered, so this is a real quiet: nothing in the graph is owed, "
            "no post is unanswered, and no paper you have read is waiting for its note."
            if not failures else
            "Note that some sources did not answer — " + "; ".join(failures)))

    text = render.render(built, stats={"sources": counts, "quiet": quiet})

    if a.stdout:
        print(text)
        return

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = os.path.join(config.out_dir("prompts"), f"{day}.md")
    latest = os.path.join(config.out_dir("prompts"), "latest.md")
    for path in (out, latest):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    # The addressable index: scripts/write.sh resolves a prompt number through this rather
    # than parsing the markdown, so the prose stays free to change.
    with open(os.path.join(config.out_dir("state"), "prompts.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "prompts": render.index(built)}, fh, indent=2)

    print(f"[elicit] {len(built)} prompt(s) from {sum(counts.values())} signal(s)\n"
          f"  {latest}\n"
          f"  write one with:  bash scripts/write.sh <n>")


if __name__ == "__main__":
    main()
