#!/usr/bin/env python3
"""Sweep arxiv, hold the week for a reader, and queue what the reader picks.

  scripts/sweep.sh fetch              # network → state/candidates.json  (~90s)
  scripts/sweep.sh titles             # every candidate, one line each — the cheap pass
  scripts/sweep.sh titles --top 40    # cap each category; small venues stay complete
  scripts/sweep.sh show <id> [<id>…]  # full abstracts for the ones worth opening
  scripts/sweep.sh accept             # state/picks.json → the reading queue
  scripts/sweep.sh explain            # what the interest profile actually contains

Two passes, because a title costs fifteen tokens and an abstract costs three hundred.
`titles` covers **everything** the sweep found; `show` covers only what that pass flagged.
Nothing is dropped for scoring badly — the score orders the list, it does not gate it. See
`eliciterlib/candidates.py` for why the old single-pass ranking was replaced.

`fetch` and `titles` and `show` are pure reads. `accept` is the only step that changes the
queue, and it refuses any id that is not in the candidate set.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import arxiv, candidates, corpus, status   # noqa: E402


def _db_or_none(log):
    """The gated graph if it is up, None if it is not.

    A sweep must not require the database. The corpus only enriches the interest profile;
    `ELICITER_INTERESTS` alone is enough to order a week of papers, so a stopped container
    should cost some ordering quality, not the whole sweep.
    """
    try:
        return corpus.connect()
    except SystemExit as e:
        log(f"[sweep] indexia unreachable, ordering on stated interests alone — {e}")
        return None


def picks_path():
    return os.path.join(config.out_dir("state"), "picks.json")


def cmd_fetch(a, log):
    cats = [c.strip() for c in a.categories.split(",")] if a.categories else None
    data = candidates.fetch(db=_db_or_none(log), categories=cats,
                            lookback_days=a.lookback, log=log)
    dest = candidates.write(data, log=log)
    print(f"[sweep] {len(data['candidates'])} candidate(s) from {data['swept']} swept; "
          f"{data['free_slots']} free slot(s) in the queue\n"
          f"  {dest}\n"
          f"  now: scripts/sweep.sh titles")
    return 0


def cmd_titles(a, log):
    data = candidates.load()
    lines = candidates.title_lines(data, per_group=a.top)
    print(f"# {len(data['candidates'])} candidate(s) · swept {data['swept']} over "
          f"{data['lookback_days']}d · {data['free_slots']} free queue slot(s)")
    print("# Grouped by primary category, smallest group first — the small ones are the")
    print("# specialised venues and are worth reading in full; cs.AI and cs.LG are the")
    print("# firehose. Score is term overlap: it orders, it does not filter. Nothing here")
    print("# was cut for scoring badly.")
    print()
    print("\n".join(lines))
    return 0


def cmd_show(a, log):
    data = candidates.load()
    index = candidates.by_id(data)
    missing = [i for i in a.ids if i not in index]
    if missing:
        raise SystemExit(f"not in this sweep: {', '.join(missing)}")
    print("\n\n".join(candidates.detail(index[i]) for i in a.ids))
    return 0


def cmd_explain(a, log):
    prof = arxiv.build_profile(_db_or_none(log), log=log)
    print(f"\ninterest profile — {len(prof)} term(s), heaviest first:\n")
    for w, wt in sorted(prof.items(), key=lambda kv: -kv[1])[:60]:
        mark = "*" if w in prof.stated else " "
        print(f" {mark}{wt:5.2f}  {w}")
    if prof.banned:
        print(f"\nexcluded: {', '.join(sorted(prof.banned))}")
    print("\n* = stated in ELICITER_INTERESTS. These weight the ordering of the candidate")
    print("  list; since 2026-08-30 they no longer decide what reaches it.")
    return 0


def cmd_accept(a, log):
    data = candidates.load()
    path = picks_path()
    if not os.path.isfile(path):
        raise SystemExit(
            f"no picks yet ({path}).\n"
            "Read `scripts/sweep.sh titles`, open what looks worth opening with "
            "`scripts/sweep.sh show <id>…`, then write that file — see the reading-queue skill.")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, dict):
        raw = raw.get("picks", [])
    try:
        chosen = candidates.validate(raw, data)
    except candidates.InvalidPicks as e:
        raise SystemExit(f"{path}: {e}")

    q = status.Queue()
    cap = a.keep if a.keep is not None else config.i("ELICITER_ARXIV_KEEP")
    room = max(0, cap - len(q.active()))
    # In the order the session listed them — it ranked them, and the cap is what decides
    # where the line falls. Overflow is reported rather than dropped silently: "you picked
    # eight and two fit" is the kind of thing you want to know before next week.
    taking, overflow = chosen[:room], chosen[room:]

    if a.dry_run:
        for p in taking:
            print(f"  would add  {p['id']}  {p['title'][:66]}")
        for p in overflow:
            print(f"  no room    {p['id']}  {p['title'][:66]}")
        return 0

    added = []
    for p in taking:
        entry, existed = q.add(p)
        if not existed:
            entry["why"] = p.get("why", "")
            entry["added_by"] = "sweep"
            added.append(entry)
    q.save()

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = config.out_dir("digest")
    text = arxiv.render_queue(q, day=day, swept=data.get("swept"))
    for name in (f"{day}.md", "latest.md"):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    print(f"[sweep] queued {len(added)} of {len(chosen)} pick(s); "
          f"{len(q.active())} waiting (cap {cap})\n  {os.path.join(out, 'latest.md')}")
    for p in overflow:
        print(f"  no room for  {p['id']}  {p['title'][:60]}", file=sys.stderr)
    return 0


def main():
    p = argparse.ArgumentParser(prog="sweep", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # --quiet hangs off every subcommand rather than off the top level. argparse only
    # accepts a top-level optional *before* the subcommand, so a single `p.add_argument`
    # here makes `sweep.sh fetch --quiet` an error — which is the spelling anyone would
    # reach for, and the one an unattended caller would put in a crontab.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--quiet", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    f = sub.add_parser("fetch", parents=[common],
                       help="sweep arxiv into state/candidates.json")
    f.add_argument("--lookback", type=int, help="days back (default from .env)")
    f.add_argument("--categories", help="comma-separated, overriding .env")

    t = sub.add_parser("titles", parents=[common], help="every candidate, one line each")
    t.add_argument("--top", type=int, help="cap each category at N (small venues stay whole)")

    s = sub.add_parser("show", parents=[common], help="full abstracts for these ids")
    s.add_argument("ids", nargs="+")

    sub.add_parser("explain", parents=[common], help="print the interest profile")

    ac = sub.add_parser("accept", parents=[common],
                        help="state/picks.json → the reading queue")
    ac.add_argument("--keep", type=int, help="queue cap (default from .env)")
    ac.add_argument("--dry-run", action="store_true")

    a = p.parse_args()
    log = (lambda *_: None) if getattr(a, "quiet", False) else (
        lambda m: print(m, file=sys.stderr))
    return {
        "fetch": cmd_fetch, "titles": cmd_titles, "show": cmd_show,
        "explain": cmd_explain, "accept": cmd_accept,
    }.get(a.cmd or "titles", cmd_titles)(a, log)


if __name__ == "__main__":
    sys.exit(main() or 0)
