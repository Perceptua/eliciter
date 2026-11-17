#!/usr/bin/env python3
"""Validate, render and decide the tweet cards a session wrote; check and install the voice.

  scripts/tweets.sh render                 # state/tweets.json → prompts/tweets-latest.md
  scripts/tweets.sh check                  # validate only; write nothing
  scripts/tweets.sh show                   # what is on offer, one line each
  scripts/tweets.sh posted 3 --draft 2     # you posted draft 2 of card 3 — saved to tweets/
  scripts/tweets.sh posted 3 --text "…"    # …or what you actually posted, after editing
  scripts/tweets.sh reject 3               # not this one
  scripts/tweets.sh reopen 3               # undo either
  scripts/tweets.sh voice-check            # validate state/voice.next.md; write nothing
  scripts/tweets.sh voice-save             # validate it, stamp it, install as state/voice.md

The tweets counterpart of `scripts/prompts.sh`, and built the same way: a session writes
`state/tweets.json` having read `state/material.json` and `state/voice.md`, and this
validates and renders it. Everything derivable is derived — card numbers, each draft's
length as X counts it.

`posted` does two things, and both are deliberate. It records the decision, the same field
the Tweets tab writes; and it saves the text into `tweets/` as one `.md`, so what you
posted becomes source material — and voice evidence — on the next gather. If you already
posted it some other way, `--text` takes what actually went out.

A rebuilt voice profile is written to `state/voice.next.md` and installed with
`voice-save`, which refuses a rebuild that is missing a section or that changed the
hand-written `## Yours` section, then stamps it with the time and the tweet count. That
stamp is what makes the next gather report the profile fresh or stale.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import run, tweetrun, tweets, voice                 # noqa: E402
from eliciterlib.signals import TWEET_STATUSES                      # noqa: E402

DECIDE = {"posted": "posted", "reject": "rejected", "reopen": "open"}
MARK = {"open": " ", "posted": "✓", "rejected": "✗"}


def load():
    path = run.tweets_path()
    if not os.path.isfile(path):
        raise SystemExit(
            f"no tweet cards yet ({path}).\n"
            "Open a session here and ask for tweets — the elicit-tweets skill writes that "
            "file.")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path} is not readable JSON ({e})")
    if isinstance(data, list):
        return {"cards": data}
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected an object or a list, got {type(data).__name__}")
    return data


def validated(data):
    try:
        return tweetrun.validate(data.get("cards"))
    except tweetrun.InvalidTweets as e:
        raise SystemExit(f"{run.tweets_path()}: {e}")


def main():
    p = argparse.ArgumentParser(prog="tweets", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", default="show",
                   choices=("render", "check", "show", *DECIDE, "voice-check", "voice-save"))
    p.add_argument("n", nargs="?", type=int, help="which card, for posted/reject/reopen")
    p.add_argument("--draft", type=int, help="which draft you posted (1-based)")
    p.add_argument("--text", help="what you actually posted, if you edited it")
    a = p.parse_args()

    if a.action in ("voice-check", "voice-save"):
        n_now = tweets.count()
        try:
            if a.action == "voice-check":
                draft = voice._read(voice.draft_path())
                if draft is None:
                    raise voice.InvalidVoice(f"no draft at {voice.draft_path()}")
                voice.check(draft, voice._read(voice.path()))
                print(f"[voice] {voice.draft_path()} is valid — `voice-save` installs it")
            else:
                dest = voice.install(n_now)
                print(f"[voice] installed {dest} (built from {n_now} tweets)")
        except voice.InvalidVoice as e:
            raise SystemExit(f"[voice] {e}")
        return 0

    if a.action in DECIDE:
        if a.n is None:
            raise SystemExit(f"which card? e.g. `bash scripts/tweets.sh {a.action} 3`")
        try:
            if a.action == "posted":
                card, path = tweetrun.post(a.n, draft=a.draft, text=a.text)
                print(f"✓ {a.n}. {card.get('title', '')[:58]} — posted, saved to {path}")
                return 0
            r = run.tweet_run()
            marked = r.mark(a.n, DECIDE[a.action])
            r.save()
        except (KeyError, ValueError) as e:
            raise SystemExit(str(e.args[0]) if e.args else str(e))
        st = run.status_of(marked, r.statuses)
        print(f"{MARK[st]} {a.n}. {marked.get('title', '')[:58]} — "
              + ("back on offer" if st == "open" else st))
        return 0

    data = load()
    cards = validated(data)

    def listing(rows):
        for c in rows:
            lens = "/".join(str(n) for n in c["lengths"])
            print(f"  {c['n']:>2}. {MARK[run.status_of(c, TWEET_STATUSES)]} "
                  f"[{lens:<11}] {c['title'][:58]}")

    if a.action == "check":
        print(f"[tweets] {len(cards)} card(s), valid")
        listing(cards)
        return 0

    if a.action == "show":
        if not cards:
            print("no cards — ask a session for tweets")
            return 0
        print("on offer (draft lengths in brackets):\n")
        listing(cards)
        print("\nonce one is out:  bash scripts/tweets.sh posted <n> --draft <k>")
        return 0

    v = voice.load()
    text = tweetrun.render(cards, stats={"gathered_at": data.get("gathered_at", ""),
                                         "quiet": data.get("quiet", ""),
                                         "voice_built_at": v["built_at"]})
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = config.out_dir("prompts")
    for name in (f"tweets-{day}.md", "tweets-latest.md"):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    with open(run.tweets_path(), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "gathered_at": data.get("gathered_at", ""),
                   "quiet": data.get("quiet", ""),
                   "cards": cards}, fh, indent=2, ensure_ascii=False)

    print(f"[tweets] {len(cards)} card(s) → {os.path.join(out, 'tweets-latest.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
