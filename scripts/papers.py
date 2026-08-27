#!/usr/bin/env python3
"""The reading queue — see what is waiting, and say what you have done with it.

  scripts/papers.sh                    # what is waiting
  scripts/papers.sh list --all         # including read and rejected
  scripts/papers.sh read 2608.24545    # you read it — frees a queue slot
  scripts/papers.sh reject 3           # not for you — never offered again
  scripts/papers.sh reset 2608.24545   # back to unread

Papers can be named by arxiv id, by a unique prefix, or by their number in `list`. The
number is the convenient one and the id is the stable one — a number moves when the queue
changes, so scripts should use ids.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import status                       # noqa: E402

MARK = {"unread": "·", "read": "✓", "rejected": "✗"}


def _resolve(q, needle):
    """Accept a queue position as well as an id. Positions are 1-based over `active()`,
    matching what `list` printed."""
    if needle.isdigit():
        active = q.active()
        n = int(needle)
        if 1 <= n <= len(active):
            return active[n - 1]["id"]
        raise SystemExit(f"no paper {n} in the queue — there are {len(active)}")
    return needle


def cmd_list(q, a):
    active = q.active()
    # Numbers always mean "position in the queue", so they mean the same thing in `list`
    # and `list --all` and stay usable as arguments. Numbering the combined listing by its
    # own row order instead would print numbers that resolve to different papers.
    position = {p["id"]: i for i, p in enumerate(active, 1)}
    rows = active if not a.all else sorted(
        q.papers.values(), key=lambda p: (p.get("status"), -float(p.get("score") or 0)))
    if not rows:
        print("queue is empty — run scripts/arxiv-digest.sh")
        return
    for p in rows:
        st = p.get("status", "unread")
        n = position.get(p["id"])
        num = f"{n:>2}." if n else "   "
        print(f"{num} {MARK.get(st, '?')} {float(p.get('score') or 0):.2f}  "
              f"{p['id']:<14} {p['title'][:64]}")
    if not a.all:
        read = len(q.by_status("read"))
        rej = len(q.by_status("rejected"))
        if read or rej:
            print(f"\n({read} read, {rej} rejected — `list --all` to see them)")


def cmd_mark(q, a, state):
    for needle in a.papers:
        p = q.mark(_resolve(q, needle), state)
        print(f"{MARK[state]} {p['id']}  {p['title'][:64]}")
    q.save()
    print(f"\n{len(q.active())} waiting.")


def main():
    p = argparse.ArgumentParser(prog="papers", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="show the queue")
    ls.add_argument("--all", action="store_true", help="include read and rejected")

    for name, help_text in (("read", "mark as read"), ("reject", "mark as rejected"),
                            ("reset", "back to unread")):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("papers", nargs="+", metavar="ID|N")

    a = p.parse_args()
    q = status.Queue()

    # Subcommand names are imperatives; stored statuses are past participles.
    verb_to_status = {"read": "read", "reject": "rejected", "reset": "unread"}

    if a.cmd in (None, "list"):
        if a.cmd is None:
            a.all = False
        cmd_list(q, a)
    else:
        cmd_mark(q, a, verb_to_status[a.cmd])


if __name__ == "__main__":
    main()
