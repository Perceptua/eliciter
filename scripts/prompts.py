#!/usr/bin/env python3
"""Validate and render the prompts a session wrote.

  scripts/prompts.sh render       # state/prompts.json → prompts/latest.md + the dated copy
  scripts/prompts.sh check        # validate only; write nothing
  scripts/prompts.sh show         # what is on offer, one line each

A session writes `state/prompts.json` — a list of prompts, having read
`state/material.json` — and then runs `render`. The markdown is never written by hand: it
is derived here, so the numbers in `prompts/latest.md` and the numbers `scripts/write.sh`
resolves cannot disagree about which prompt is 3.

`check` is the same validation without the write, which is what to run while drafting.
Everything derivable is derived rather than trusted — `length` and `project` come from the
register, `n` from position — so a session only has to get right the things only it can.

Rendering is also what **retires an audua session**: a recording that has appeared in a
rendered run does not come back. That happens here, at the moment the file is actually
written, and not at gather time — gathering is a pure read, and a gather you ran to see
what was there should not silently burn through the queue of unheard recordings.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import audua, render                                # noqa: E402


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
    p.add_argument("action", nargs="?", default="show", choices=("render", "check", "show"))
    a = p.parse_args()

    data = load()
    prompts = validated(data)

    if a.action == "check":
        print(f"[prompts] {len(prompts)} prompt(s), valid")
        for x in prompts:
            print(f"  {x['n']:>2}. [{x['length']:<5} {x['project']:<9}] {x['title'][:58]}")
        return 0

    if a.action == "show":
        if not prompts:
            print("no prompts — gather, then ask a session for them")
            return 0
        print("on offer:\n")
        for x in prompts:
            print(f"  {x['n']:>2}. [{x['length']:<5} {x['project']:<9}] {x['title'][:58]}")
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

    retired = audua.mark_seen(prompts)
    print(f"[prompts] {len(prompts)} prompt(s) → {os.path.join(out, 'latest.md')}"
          + (f"; retired {retired} audua session(s)" if retired else ""))
    print("  write one with:  bash scripts/write.sh <n>")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
