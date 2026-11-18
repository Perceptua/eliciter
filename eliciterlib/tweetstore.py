"""The one module that writes into `tweets/`.

Every other source eliciter reads is read-only to it, enforced by `readonly.py` and by
`tests/test_readonly.py`. `tweets/` is the deliberate exception, the same kind of exception
`scan-misc` is for `misc/`: the folder holds your own writing, and the two things that put
writing there are acts *you* take —

  * importing your X archive (`scripts/import-tweets.sh`), and
  * marking a drafted tweet **posted** on the Tweets tab or with `scripts/tweets.sh posted`,
    which saves the text you actually posted so the next gather (and the voice profile)
    sees it.

So the write path is narrow on purpose. It creates one file per tweet, **never
overwrites** — an existing file means that tweet is already here, and the answer is to
leave it alone — and refuses any name that would land outside the tweets folder. Tests
assert that no other module writes under this directory.
"""
import os
import re
from datetime import datetime, timezone

from . import config

_SAFE = re.compile(r"[^a-z0-9]+")


class TweetStoreError(ValueError):
    """A tweet that cannot be saved as asked — empty, or a name escaping the folder."""


def _slug(text, n=40):
    return _SAFE.sub("-", text.lower()).strip("-")[:n].rstrip("-") or "tweet"


def filename(date, text, id=None):
    """`YYYY-MM-DD-<id>.md` for an imported tweet; `YYYY-MM-DD-HHMMSS-<slug>.md` for one
    saved before it has an id. Both sort by date in a plain directory listing."""
    day = date.strftime("%Y-%m-%d")
    if id:
        return f"{day}-{_SAFE.sub('', str(id))}.md"
    return f"{day}-{date.strftime('%H%M%S')}-{_slug(text)}.md"


def render(text, date, id=None, url=None, likes=None, retweets=None):
    lines = ["---", f"date: {date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"]
    if id:
        lines.append(f"id: {id}")
    if url:
        lines.append(f"url: {url}")
    if likes is not None:
        lines.append(f"likes: {int(likes)}")
    if retweets is not None:
        lines.append(f"retweets: {int(retweets)}")
    lines += ["---", text.strip(), ""]
    return "\n".join(lines)


def save(text, date=None, id=None, url=None, likes=None, retweets=None, root=None,
         dry_run=False):
    """Write one tweet. Returns `(path, created)`; `created` is False if it was already
    there, in which case nothing was touched."""
    text = (text or "").strip()
    if not text:
        raise TweetStoreError("an empty tweet is not a tweet")
    date = date or datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    folder = os.path.realpath(root or config.tweets_dir())
    path = os.path.realpath(os.path.join(folder, filename(date, text, id)))
    if not path.startswith(folder + os.sep):
        raise TweetStoreError(f"refusing to write outside {folder}: {path}")
    if os.path.exists(path):
        return path, False
    if dry_run:
        return path, True

    # O_EXCL: if two saves race for the same name, the second fails rather than clobbering.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(render(text, date, id=id, url=url, likes=likes, retweets=retweets))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        os.remove(tmp)
        return path, False
    os.close(fd)
    os.replace(tmp, path)
    ts = date.timestamp()
    os.utime(path, (ts, ts))
    return path, True
