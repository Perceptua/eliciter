#!/usr/bin/env python3
"""Save, list and decide the tweets you finalize in a session; check and install the voice.

  scripts/tweets.sh show                       # drafts waiting, and recent topics
  scripts/tweets.sh draft --title "…" --source arxiv:2609.00075v1 --text "…"
  scripts/tweets.sh topic --title "…" --source misc:"x.txt" --outcome passed --note "why"
  scripts/tweets.sh revise 3 --text "…"        # change a draft before it goes out
  scripts/tweets.sh revise 3 --title "…"       # …or its topic label
  scripts/tweets.sh posted 3 --id <id|link>   # it went out as drafted — saved to tweets/
  scripts/tweets.sh posted 3 --id … --text "…" # …or what went out, if you changed it
  scripts/tweets.sh reject 3                   # not posting it after all
  scripts/tweets.sh reopen 3                   # undo either
  scripts/tweets.sh voice-check                # validate state/voice.next.md; write nothing
  scripts/tweets.sh voice-save                 # validate it, stamp it, install as voice.md

**Tweets are composed in a conversation, not generated.** A session (the `elicit-tweets`
skill) pitches a topic from your recent reading and writing; you pass or engage; you work
the sentence together. `draft` is called only when you have said a tweet is done — it
validates the length and the sources and appends it to `state/tweets.json`, where the
Tweets tab shows it. `topic` records every topic pitched and what became of it, so the next
session does not pitch a topic you turned down.

`--source` is `<source>:<ref>` (repeatable), with an optional `|title`:
`--source "tweets:2021-09-29-1443267727976710150.md|a historian of the 28th century"`.

Each open draft also sits in `tweets/drafts/` until it goes out. `posted` takes the post's
X id (or its link) and saves the text into `tweets/` as `YYYY-MM-DD-<id>.md` — the same
name an archive import gives it — so what you posted becomes source material, and voice
evidence, on the next gather. A draft posted before ids were required can be given its id
the same way.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import run, tweetrun, tweets, voice                 # noqa: E402
from eliciterlib.signals import TWEET_STATUSES                       # noqa: E402

DECIDE = {"posted": "posted", "reject": "rejected", "reopen": "open"}
MARK = {"open": " ", "posted": "✓", "rejected": "✗"}


def main():
    p = argparse.ArgumentParser(prog="tweets", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", default="show",
                   choices=("show", "draft", "topic", "revise", *DECIDE, "voice-check", "voice-save"))
    p.add_argument("n", nargs="?", type=int, help="which draft, for revise/posted/reject/reopen")
    p.add_argument("--title", help="the topic, as a short label")
    p.add_argument("--source", action="append", default=[], help="<source>:<ref>[|title]")
    p.add_argument("--text", help="the tweet (draft), its new text (revise), or what went out (posted)")
    p.add_argument("--id", help="posted: the post's X id, or its link")
    p.add_argument("--because", default="", help="draft: why the topic was live")
    p.add_argument("--outcome", choices=tweetrun.TOPIC_OUTCOMES, help="topic: what became of it")
    p.add_argument("--note", default="", help="topic: why you passed, in a few words")
    a = p.parse_args()

    try:
        if a.action in ("voice-check", "voice-save"):
            n_now = tweets.count()
            if a.action == "voice-check":
                draft = voice._read(voice.draft_path())
                if draft is None:
                    raise voice.InvalidVoice(f"no draft at {voice.draft_path()}")
                voice.check(draft, voice._read(voice.path()))
                print(f"[voice] {voice.draft_path()} is valid — `voice-save` installs it")
            else:
                print(f"[voice] installed {voice.install(n_now)} (built from {n_now} tweets)")
            return 0

        if a.action == "draft":
            d = tweetrun.add_draft(a.text, a.title, tweetrun.parse_sources(a.source),
                                   because=a.because)
            print(f"[tweets] saved draft {d['n']} ({d['length']}/{tweetrun.LIMIT}) — "
                  "it is on the Tweets tab")
            return 0

        if a.action == "topic":
            if not a.outcome:
                raise SystemExit("--outcome is required: drafted, passed or skipped")
            e = tweetrun.log_topic(a.title, tweetrun.parse_sources(a.source), a.outcome,
                                   note=a.note)
            print(f"[tweets] topic logged: {e['title']} — {e['outcome']}")
            return 0

        if a.action == "revise":
            if a.n is None:
                raise SystemExit("which draft? e.g. `bash scripts/tweets.sh revise 3 --text \"…\"`")
            d = tweetrun.revise(a.n, text=a.text, title=a.title)
            print(f"[tweets] revised draft {d['n']} ({d['length']}/{tweetrun.LIMIT}) — "
                  f"{d['title'][:50]}\n        {d['text']}")
            return 0

        if a.action in DECIDE:
            if a.n is None:
                raise SystemExit(f"which draft? e.g. `bash scripts/tweets.sh {a.action} 3`")
            if a.action == "posted":
                if not a.id:
                    raise SystemExit("--id is required: the post's X id or its link, e.g. "
                                     f"`bash scripts/tweets.sh posted {a.n} --id https://x.com/you/status/1857…`")
                d, path = tweetrun.post(a.n, a.id, text=a.text)
                print(f"✓ {a.n}. {d.get('title', '')[:58]} — posted, saved to {path}")
                return 0
            marked = tweetrun.decide(a.n, DECIDE[a.action])
            st = run.status_of(marked, TWEET_STATUSES)
            print(f"{MARK[st]} {a.n}. {marked.get('title', '')[:58]} — "
                  + ("back on offer" if st == "open" else st))
            return 0
    except (tweetrun.InvalidTweets, voice.InvalidVoice) as e:
        raise SystemExit(f"[tweets] {e}")
    except (KeyError, ValueError) as e:
        raise SystemExit(str(e.args[0]) if e.args else str(e))

    # show
    r = run.tweet_run()
    if not r.prompts:
        print("no drafts yet — open a session here and say you want to write tweets")
    for d in r.prompts:
        st = run.status_of(d, TWEET_STATUSES)
        print(f"  {d['n']:>2}. {MARK[st]} [{d.get('length', '?'):>3}] {d.get('title', '')[:50]}")
        print(f"        {d.get('posted_text') or d.get('text', '')}")
    topics = r.meta.get("topics") or []
    if topics:
        print("\nrecent topics:")
        for t in topics[-10:]:
            print(f"  {t['at'][:10]}  {t['outcome']:<8} {t['title'][:60]}"
                  + (f" — {t['note']}" if t.get("note") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
