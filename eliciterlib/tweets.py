"""Source — your tweets, read through the gate.

One `.md` per tweet in `ELICITER_TWEETS_DIR` (default `tweets/` at the repo root,
gitignored). They get there two ways: `scripts/import-tweets.sh` turns an X archive into
files, and marking a drafted tweet *posted* on the Tweets tab saves the text you actually
posted. Both go through `tweetstore.py`, the one module allowed to write here; this module
only reads.

A file is a short front matter block and then the tweet, verbatim:

    ---
    date: 2024-03-05T14:02:11Z
    id: 1765432109876543210
    url: https://x.com/i/status/1765432109876543210
    likes: 41
    retweets: 6
    ---
    the tweet text

Every field is optional, and so is the block itself: a bare `.md` or `.txt` dropped in by
hand is read too, dated from a `YYYY-MM-DD` filename prefix or else its mtime. The front
matter is `key: value` lines and nothing more — no YAML dependency for five scalars.

Tweets serve two readers. A session writing prompts or pitching tweet topics may cite one like any
other piece of your writing, and the session that builds the voice profile (`voice.py`)
reads all of them as the evidence for how you sound when you are being brief.
"""
import re
from datetime import datetime, timezone

from . import config, readonly

EXTENSIONS = (".md", ".markdown", ".txt")
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_INT_FIELDS = ("likes", "retweets")


def parse(raw):
    """File text → (front matter dict, body). A file with no block is all body."""
    meta, body = {}, raw
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end != -1:
            for line in raw[4:end].splitlines():
                k, sep, v = line.partition(":")
                if sep and k.strip():
                    meta[k.strip().lower()] = v.strip()
            body = raw[end + 4:].lstrip("\n")
    for k in _INT_FIELDS:
        try:
            meta[k] = int(meta[k]) if k in meta else None
        except ValueError:
            meta[k] = None
    return meta, body.strip()


def _parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def count(root=None):
    """How many tweet files there are — a listing, no reads. This is the number the voice
    profile is stamped with, and the one that decides whether it is stale."""
    gate = readonly.tweets_dir(root or config.tweets_dir())
    return sum(1 for n in gate.names() if n.lower().endswith(EXTENSIONS))


def load(root=None):
    """Every tweet, newest first."""
    gate = readonly.tweets_dir(root or config.tweets_dir())
    out = []
    for name in gate.names():
        if not name.lower().endswith(EXTENSIONS):
            continue
        meta, text = parse(gate.read(name))
        if not text:
            continue
        date = _parse_date(meta.get("date"))
        if date is None:
            m = _DATE_PREFIX.match(name)
            date = (_parse_date(m.group(1)) if m else None) or \
                datetime.fromtimestamp(gate.mtime(name), tz=timezone.utc)
        out.append({
            "file": name, "date": date, "text": text,
            "id": meta.get("id") or "", "url": meta.get("url") or "",
            "likes": meta.get("likes"), "retweets": meta.get("retweets"),
        })
    out.sort(key=lambda t: t["date"], reverse=True)
    return out
