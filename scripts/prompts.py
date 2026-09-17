#!/usr/bin/env python3
"""Validate and render the prompts a session wrote.

  scripts/prompts.sh render       # state/prompts.json → prompts/latest.md + the dated copy
  scripts/prompts.sh check        # validate only; write nothing
  scripts/prompts.sh show         # what is on offer, one line each
  scripts/prompts.sh written 3    # you wrote it — it stops being on offer
  scripts/prompts.sh reject 3     # not for you — stays in the run, marked
  scripts/prompts.sh reopen 3     # undo either one

A session writes `state/prompts.json` — a list of prompts, having read
`state/material.json` — and then runs `render`. The markdown is never written by hand: it
is derived here, so the numbers in `prompts/latest.md` and the numbers `scripts/write.sh`
resolves cannot disagree about which prompt is 3.

`check` is the same validation without the write, which is what to run while drafting.
Everything derivable is derived rather than trusted — `length` and `project` come from the
register, `n` from position — so a session only has to get right the things only it can.

`written`, `reject` and `reopen` record what you did with a prompt. They are the CLI half of
the same buttons in the UI, writing the same field in the same file (`eliciterlib/run.py`),
so it never matters which one you had open. They do not re-render the markdown: the dated
file is what a run *asked*, on the day it asked it, and rewriting it on a Tuesday under
Friday's date would file today's decisions under the wrong day. Run `render` when you want
the marks folded into `prompts/latest.md`.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import render, run                                  # noqa: E402

# The CLI verb → the stored status. `written` rather than `done`: what is recorded is that
# the writing exists, not that you are finished thinking about it.
DECIDE = {"written": "written", "reject": "rejected", "reopen": "open"}
MARK = {"open": " ", "written": "✓", "rejected": "✗"}


def state_path():
    return os.path.join(config.out_dir("state"), "prompts.json")


def load():
    path = state_path()
    if not os.path.isfile(path):
        raise SystemExit(
            f"no prompts yet ({path}).\n"
            "Gather the material with `bash scripts/gather.sh`, then open a session here "
            "and ask for prompts — the elicit-writing skill writes that file.")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path} is not readable JSON ({e})")
    if isinstance(data, list):                 # a bare list is a reasonable thing to write
        return {"prompts": data}
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected an object or a list, got {type(data).__name__}")
    return data


def validated(data):
    try:
        return render.validate(data.get("prompts"))
    except render.InvalidPrompts as e:
        raise SystemExit(f"{state_path()}: {e}")


def main():
    p = argparse.ArgumentParser(prog="prompts", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", default="show",
                   choices=("render", "check", "show", *DECIDE))
    p.add_argument("n", nargs="?", type=int,
                   help="which prompt, for written/reject/reopen")
    a = p.parse_args()

    # Deciding is a write to the same file `load()` reads, so it happens first and on its
    # own: validating and re-deriving here would rewrite the run as a side effect of
    # ticking one prompt off it.
    if a.action in DECIDE:
        if a.n is None:
            raise SystemExit(f"which prompt? e.g. `bash scripts/prompts.sh {a.action} 3`")
        r = run.Run()
        try:
            marked = r.mark(a.n, DECIDE[a.action])
        except KeyError as e:
            raise SystemExit(str(e.args[0]) if e.args else "no such prompt")
        r.save()
        st = run.status_of(marked)
        print(f"{MARK[st]} {a.n}. {marked.get('title', '')[:58]} — "
              + ("back on offer" if st == "open" else st))
        return 0

    data = load()
    prompts = validated(data)

    def listing(rows):
        for x in rows:
            print(f"  {x['n']:>2}. {MARK[run.status_of(x)]} [{x['length']:<5} "
                  f"{x['project']:<9}] {x['title'][:58]}")

    if a.action == "check":
        print(f"[prompts] {len(prompts)} prompt(s), valid")
        listing(prompts)
        return 0

    if a.action == "show":
        if not prompts:
            print("no prompts — gather, then ask a session for them")
            return 0
        open_ = [x for x in prompts if run.status_of(x) == "open"]
        print("on offer:\n")
        listing(prompts)
        decided = len(prompts) - len(open_)
        if decided:
            print(f"\n{len(open_)} still open · {decided} decided "
                  "(`prompts.sh reopen <n>` puts one back)")
        print("\nwrite one with:  bash scripts/write.sh <n>")
        return 0

    text = render.render(prompts, stats={"gathered_at": data.get("gathered_at", ""),
                                         "quiet": data.get("quiet", "")})
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = config.out_dir("prompts")
    for name in (f"{day}.md", "latest.md"):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    # Rewrite the state file in canonical form: numbered, with length and project derived.
    # `write.sh` reads this rather than the markdown, so it has to be the validated version
    # and not whatever shape the session happened to produce.
    with open(state_path(), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "gathered_at": data.get("gathered_at", ""),
                   "prompts": prompts}, fh, indent=2, ensure_ascii=False)

    print(f"[prompts] {len(prompts)} prompt(s) → {os.path.join(out, 'latest.md')}")
    print("  write one with:  bash scripts/write.sh <n>")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
