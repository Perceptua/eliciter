#!/usr/bin/env python3
"""Import your tweets from an X/Twitter archive — one `.md` per tweet in tweets/.

  scripts/import-tweets.sh ~/Downloads/twitter-2026-11-17.zip
  scripts/import-tweets.sh ~/Downloads/twitter-archive/          # unzipped
  scripts/import-tweets.sh ~/Downloads/twitter-archive/data/tweets.js
  scripts/import-tweets.sh <any of those> --dry-run              # count, write nothing

Kept: your own original tweets, including quote tweets. Skipped, and counted:

  * **replies** — anything with `in_reply_to_status_id_str`, including replies to
    yourself, so the second and later tweets of a thread are skipped too.
  * **retweets** — they are someone else's words.
  * **media tweets** — anything with an attached photo, video or GIF. The text of these
    usually leans on the picture and does not stand alone.

The text is cleaned the way you would read it on the site: `&amp;` and friends are
unescaped, and every `t.co` link is replaced with the URL it points to.

Idempotent: a tweet already in tweets/ is left alone, so re-importing a newer archive
adds only what is new. The archive is read in memory, so nothing is extracted to disk.
Writing goes through `eliciterlib/tweetstore.py`, the one module allowed to write there.
"""
import argparse
import html
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import tweetstore                   # noqa: E402

# data/tweets.js, data/tweets-part1.js, … — and data/tweet.js in some older exports.
_PART = re.compile(r"(^|/)data/tweets?(-part\d+)?\.js$")
_ASSIGN = re.compile(r"^\s*window\.YTD\.[\w.]+\s*=\s*", re.S)


def _parts_from(path):
    """Yield the text of every tweets JS part in a zip, a directory, or a single file."""
    if os.path.isdir(path):
        data = os.path.join(path, "data") if os.path.isdir(os.path.join(path, "data")) else path
        names = sorted(n for n in os.listdir(data) if re.match(r"tweets?(-part\d+)?\.js$", n))
        if not names:
            raise SystemExit(f"no tweets.js found under {data}")
        for n in names:
            with open(os.path.join(data, n), encoding="utf-8") as fh:
                yield fh.read()
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if _PART.search(n))
            if not names:
                raise SystemExit(f"no data/tweets.js inside {path}")
            for n in names:
                yield z.read(n).decode("utf-8")
    elif os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            yield fh.read()
    else:
        raise SystemExit(f"not found: {path}")


def parse_part(js):
    """`window.YTD.tweets.part0 = [ … ]` → the list of tweet dicts."""
    items = json.loads(_ASSIGN.sub("", js, count=1))
    return [it.get("tweet", it) for it in items]


def classify(t):
    """Why a tweet is skipped, or None if it is kept."""
    if t.get("in_reply_to_status_id_str") or t.get("in_reply_to_status_id"):
        return "reply"
    text = t.get("full_text") or t.get("text") or ""
    if t.get("retweeted") or text.startswith("RT @"):
        return "retweet"
    if (t.get("entities") or {}).get("media") or (t.get("extended_entities") or {}).get("media"):
        return "media"
    return None


def clean_text(t):
    text = t.get("full_text") or t.get("text") or ""
    for u in (t.get("entities") or {}).get("urls") or []:
        short, full = u.get("url"), u.get("expanded_url")
        if short and full:
            text = text.replace(short, full)
    return html.unescape(text).strip()


def created(t):
    # e.g. "Tue Mar 05 14:02:11 +0000 2024"
    return datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def run(path, dry_run=False, root=None, log=print):
    counts = {"imported": 0, "already had": 0, "reply": 0, "retweet": 0, "media": 0}
    for js in _parts_from(path):
        for t in parse_part(js):
            why = classify(t)
            if why:
                counts[why] += 1
                continue
            tid = t.get("id_str") or str(t.get("id") or "")
            _, made = tweetstore.save(
                clean_text(t), created(t), id=tid,
                url=f"https://x.com/i/status/{tid}" if tid else None,
                likes=_int(t.get("favorite_count")), retweets=_int(t.get("retweet_count")),
                root=root, dry_run=dry_run)
            counts["imported" if made else "already had"] += 1
    return counts


def main():
    p = argparse.ArgumentParser(prog="import-tweets", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archive", help="the archive .zip, its unzipped folder, or a tweets.js")
    p.add_argument("--dry-run", action="store_true", help="count what would happen; write nothing")
    a = p.parse_args()

    c = run(os.path.expanduser(a.archive), dry_run=a.dry_run)
    verb = "would import" if a.dry_run else "imported"
    print(f"[tweets] {verb} {c['imported']} · already had {c['already had']} · "
          f"skipped {c['reply']} repl{'y' if c['reply'] == 1 else 'ies'}, "
          f"{c['retweet']} retweet(s), {c['media']} with media")
    print(f"  → {config.tweets_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
