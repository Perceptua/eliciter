#!/usr/bin/env python3
"""Preflight — can eliciter actually read what it claims to read, and only read it?

Every source, checked independently, with the failure stated in terms of the thing to go
fix. This exists because an empty prompts file has two very different causes — a settled
corpus and a stopped container — and reading the file cannot tell you which.

The gate is checked too: the last line is not "sources are up" but "sources are readable
*and not writable*", which is the property this project actually promises.

  scripts/doctor.sh              # check everything
  scripts/doctor.sh --no-network # skip the arxiv reachability probe
"""
import argparse
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

OK, BAD, MEH = "\033[1;32m✓\033[0m", "\033[1;31m✗\033[0m", "\033[1;33m!\033[0m"


def check(label, fn):
    try:
        mark, detail = fn()
    except Exception as e:                            # noqa: BLE001
        mark, detail = BAD, f"{type(e).__name__}: {e}"
    print(f"  {mark} {label:<20} {detail}")
    return mark is not BAD


def c_config():
    config.bootstrap()
    return OK, f"indexia at {os.environ['ELICITER_INDEXIA_ROOT']}, db {os.environ['DB']}"


def c_graph():
    import notelib
    from eliciterlib import corpus
    db = corpus.connect()
    n = notelib.first_row(db.query("SELECT count(*) AS n FROM Note")).get("n", 0)
    if not n:
        return MEH, ("reachable, but the corpus is empty — the graph will produce no "
                     "prompts and the profile falls back to ELICITER_INTERESTS")
    return OK, f"{os.environ['BASE_URL']} — {n} note(s)"


def c_gate():
    """The promise, asserted at runtime: the handle we hand around cannot write."""
    from eliciterlib import corpus, readonly
    db = corpus.connect()
    try:
        db.query("DELETE FROM Note")
    except readonly.ReadOnlyViolation:
        pass
    else:
        return BAD, "a DELETE was NOT refused — the gate is broken"
    try:
        db.command
    except readonly.ReadOnlyViolation:
        pass
    else:
        return BAD, "the mutating .command() API is reachable"
    return OK, "writes refused (statement + method); `scripts/test.sh` proves the rest"


def c_moves():
    """Move 7 lives in indexia's analytics package, which is a separate import path."""
    from analytics import common, debt              # noqa: F401
    return OK, "notelib moves 4–6 + analytics.debt (move 7) importable"


def c_posts():
    from eliciterlib import posts
    ps = posts.load()
    if not ps:
        return MEH, f"{config.posts_dir()} — no posts matched YYYY-MM-DD-slug.md"
    return OK, f"{len(ps)} post(s), latest {max(p['date'] for p in ps)} (read-only)"


def c_profile():
    from eliciterlib import arxiv
    prof = arxiv.build_profile(None, log=lambda *_: None)
    if not prof:
        return BAD, "empty — set ELICITER_INTERESTS in .env"
    top = ", ".join(w for w, _ in sorted(prof.items(), key=lambda kv: -kv[1])[:5])
    return OK, f"{len(prof)} term(s), {len(prof.stated)} stated; heaviest: {top}"


def c_queue():
    from eliciterlib import status
    q = status.Queue()
    if not q.papers:
        return MEH, "empty — run scripts/arxiv-digest.sh"
    return OK, (f"{len(q.active())} waiting, {len(q.by_status('read'))} read, "
                f"{len(q.by_status('rejected'))} rejected")


def c_arxiv():
    req = urllib.request.Request(
        "https://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=1",
        headers={"User-Agent": "eliciter/1.0 preflight"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    if r.status != 200 or b"<entry" not in body:
        return BAD, f"HTTP {r.status}, {len(body)} bytes, no entries"
    return OK, "export.arxiv.org reachable over HTTPS"


def main():
    p = argparse.ArgumentParser(prog="doctor", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-network", action="store_true")
    a = p.parse_args()

    print("eliciter preflight\n")
    checks = [("config", c_config), ("indexia graph", c_graph),
              ("read-only gate", c_gate), ("indexia moves", c_moves),
              ("perceptua posts", c_posts), ("interest profile", c_profile),
              ("reading queue", c_queue)]
    if not a.no_network:
        checks.append(("arxiv", c_arxiv))

    results = [check(label, fn) for label, fn in checks]
    print()
    if all(results):
        print("all sources readable, and read-only.")
        return 0
    print("some checks failed — see above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
