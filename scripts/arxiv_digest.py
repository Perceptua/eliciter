#!/usr/bin/env python3
"""Weekly arxiv sweep — the replacement for the Claude Desktop digest task.

Fetches everything submitted to the configured categories in the lookback window, ranks it
by overlap with your interest profile (stated interests + your indexia corpus), and **tops
up the reading queue** to at most ELICITER_ARXIV_KEEP papers. Papers already in the queue
keep their status; ones you rejected never come back.

Writes `digest/<day>.md` — the queue, for reading. Takes seconds, needs no GPU, and works
with the database down.

  scripts/arxiv-digest.sh                 # sweep and top up the queue
  scripts/arxiv-digest.sh --explain       # show the interest profile, sweep nothing
  scripts/arxiv-digest.sh --dry-run       # sweep and rank, change nothing
  scripts/arxiv-digest.sh --lookback 30   # a wider window, e.g. after a gap
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import arxiv, corpus, status        # noqa: E402


def _db_or_none(log):
    """The gated graph if it is up, None if it is not.

    A sweep must not require the database. The corpus only enriches the interest profile;
    `ELICITER_INTERESTS` alone is enough to rank a week of papers, so a stopped container
    should cost some precision, not the whole digest.
    """
    try:
        return corpus.connect()
    except SystemExit as e:
        log(f"[arxiv] indexia unreachable, ranking on stated interests alone — {e}")
        return None


def main():
    p = argparse.ArgumentParser(prog="arxiv-digest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lookback", type=int, help="days back to sweep (default from .env)")
    p.add_argument("--keep", type=int, help="queue cap (default from .env)")
    p.add_argument("--categories", help="comma-separated arxiv categories, overriding .env")
    p.add_argument("--explain", action="store_true",
                   help="print the interest profile and exit, without sweeping")
    p.add_argument("--dry-run", action="store_true", help="do everything but change the queue")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr))
    cats = [c.strip() for c in a.categories.split(",")] if a.categories else None

    if a.explain:
        prof = arxiv.build_profile(_db_or_none(log), log=log)
        print(f"\ninterest profile — {len(prof)} term(s), heaviest first:\n")
        for w, wt in sorted(prof.items(), key=lambda kv: -kv[1])[:60]:
            mark = "*" if w in prof.stated else " "
            print(f" {mark}{wt:5.2f}  {w}")
        if prof.banned:
            print(f"\nexcluded: {', '.join(sorted(prof.banned))}")
        print("\n* = stated in ELICITER_INTERESTS (a paper must match one of these).")
        return

    papers = arxiv.sweep(categories=cats, lookback_days=a.lookback, log=log)
    ranked = arxiv.score(papers, _db_or_none(log), keep=None, log=log)

    q = status.Queue()
    before = len(q.active())
    added, skipped = q.refill(ranked, limit=a.keep)
    log(f"[queue] {before} waiting → {len(q.active())} "
        f"(+{len(added)} new, {skipped} already seen)")

    if a.dry_run:
        for pp in added:
            print(f"  would add  {pp['id']}  {pp['title'][:70]}")
        log("[arxiv] dry run — queue unchanged")
        return

    q.save()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md = os.path.join(config.out_dir("digest"), f"{day}.md")
    text = arxiv.render_queue(q, day=day, swept=len(papers))
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(config.out_dir("digest"), "latest.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"[arxiv] swept {len(papers)}, added {len(added)}; "
          f"{len(q.active())} waiting\n  {md}")


if __name__ == "__main__":
    main()
