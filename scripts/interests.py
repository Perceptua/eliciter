#!/usr/bin/env python3
"""The interest profile — the categories a sweep pulls and the terms it orders them by — and its tuning.

  scripts/interests.sh                  # show the profile and when it was last tuned
  scripts/interests.sh init             # seed state/interests.json from the built-in defaults
  scripts/interests.sh gather           # evidence for a tuning → state/interests-material.json
  scripts/interests.sh check            # validate state/interests.next.json; write nothing
  scripts/interests.sh save             # apply it — only after the user has approved it
  scripts/interests.sh history          # every change, with its reasons

The judgement in between `gather` and `save` is a session's: the `tune-interests` skill
reads the material, proposes terms to add and drop with a reason for each, and asks the
user before anything is saved. Nothing here runs on a schedule.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import interests                    # noqa: E402


def cmd_show(_a):
    prof = interests.load()
    if prof is None:
        print("no profile yet — the sweep is using the built-in defaults.\n"
              "  seed one: scripts/interests.sh init")
    else:
        print(f"{interests.path()} · last tuned {interests.last_tuned(prof) or 'never'} · "
              f"{len(prof['history'])} change(s)")
    for name in interests.LISTS:
        terms = getattr(config, name)()
        print(f"\n{name} ({len(terms)}):")
        for t in terms:
            print(f"  {t}")
    return 0


def cmd_init(_a):
    dest = interests.init(config.interests(), config.exclude(), config.categories())
    prof = interests.load()
    print(f"[interests] seeded {dest} with {len(prof['interests'])} interest(s), "
          f"{len(prof['exclude'])} exclude term(s) and {len(prof['categories'])} categories.\n"
          "  tune it with the tune-interests skill.")
    return 0


def cmd_gather(a):
    log = (lambda *_: None) if a.quiet else (lambda m: print(m, file=sys.stderr))
    data = interests.gather(log=log)
    dest = interests.write_material(data)
    new_read = sum(p["since_last_tuning"] for p in data["papers_read"])
    new_rej = sum(p["since_last_tuning"] for p in data["papers_rejected"])
    print(f"[interests] {len(data['papers_read'])} read ({new_read} since last tuning) · "
          f"{len(data['papers_rejected'])} rejected ({new_rej} since) · "
          f"last tuned {data['profile']['last_tuned'] or 'never'}\n  {dest}")
    for name, why in (data.get("unavailable") or {}).items():
        print(f"[interests] {name} unavailable — {why}", file=sys.stderr)
    return 1 if data.get("unavailable") else 0


def _proposal():
    prof = interests.load()
    if prof is None:
        raise interests.InvalidProposal("no profile yet — run `scripts/interests.sh init`")
    raw = interests._read_json(interests.draft_path())
    if raw is None:
        raise interests.InvalidProposal(f"no proposal at {interests.draft_path()}")
    return interests.check(raw, prof)


def cmd_check(_a):
    changes = _proposal()
    print(f"[interests] {interests.draft_path()} is valid:\n{interests.describe(changes)}\n"
          "  `save` applies it — once the user has approved it")
    return 0


def cmd_save(_a):
    dest, changes = interests.apply()
    print(f"[interests] applied to {dest}:\n{interests.describe(changes)}")
    return 0


def cmd_history(_a):
    prof = interests.load()
    if prof is None:
        print("no profile yet")
        return 0
    for h in prof["history"]:
        print(f"{h['at']}  {h.get('note', '')}".rstrip())
        if not h.get("seeded"):
            print(interests.describe({n: h.get(n) or {"add": [], "drop": []}
                                      for n in interests.LISTS}))
    return 0


def main():
    p = argparse.ArgumentParser(prog="interests", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("show")
    sub.add_parser("init")
    g = sub.add_parser("gather")
    g.add_argument("--quiet", action="store_true")
    sub.add_parser("check")
    sub.add_parser("save")
    sub.add_parser("history")
    a = p.parse_args()
    fn = {"show": cmd_show, "init": cmd_init, "gather": cmd_gather, "check": cmd_check,
          "save": cmd_save, "history": cmd_history}.get(a.cmd or "show")
    try:
        return fn(a)
    except interests.InvalidProposal as e:
        print(f"[interests] not applied: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
