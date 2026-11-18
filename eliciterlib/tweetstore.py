"""The one module that writes into `tweets/`.

Every other source eliciter reads is read-only to it, enforced by `readonly.py` and by
`tests/test_readonly.py`. `tweets/` is the deliberate exception, the same kind of exception
`scan-misc` is for `misc/`: the folder holds your own writing, and the things that put
writing there are acts *you* take —

  * importing your X archive (`scripts/import-tweets.sh`),
  * finalizing a tweet in a session (`scripts/tweets.sh draft`), which puts it in
    `tweets/drafts/` until it goes out, and
  * marking a draft **posted** on the Tweets tab or with `scripts/tweets.sh posted`, with
    the post's X id, which saves the text you actually posted so the next gather (and the
    voice profile) sees it.

The folder:

    tweets/YYYY-MM-DD-<id>.md          a tweet that went out — imported or marked posted
    tweets/drafts/YYYY-MM-DD-draft-<n>.md   an open draft, waiting to be posted
    tweets/archives/                   X archive downloads, for the import to read

**Every posted tweet is named by its X id**, whichever way it arrived, and dated by the id
too (X ids carry their own timestamp — see `id_date`). So a tweet marked posted and the
same tweet arriving later in an archive land on the same name, and the import leaves it
alone instead of saving it twice.

The write path for posted tweets is narrow on purpose. It creates one file per tweet,
never deletes one, and refuses any name that would land outside the tweets folder. It
overwrites only when asked to (`replace=True`), and only the archive import asks: the
archive is the record of what went out, with the latest likes and retweets, so it
supersedes a file saved when the tweet was marked posted, or by an earlier import. Marking a
draft posted never overwrites — an existing file means the tweet is already here. `drafts/` is different: it mirrors the open drafts in `state/tweets.json`, so a
revision rewrites a draft file and posting or rejecting removes it. Only files named
`*-draft-<n>.md` are touched there; anything else you put in `drafts/` is left alone. The
readers (`tweets.py`) list only the top level, so drafts and archives are never mistaken
for tweets. Tests assert that no other module writes under this directory.
"""
import os
import re
from datetime import datetime, timezone

from . import config

_SAFE = re.compile(r"[^a-z0-9]+")


class TweetStoreError(ValueError):
    """A tweet that cannot be saved as asked — empty, or a name escaping the folder."""


DRAFTS = "drafts"
ARCHIVES = "archives"

# X's snowflake ids: milliseconds since this epoch, shifted left 22 bits.
_TWEPOCH_MS = 1288834974657
_STATUS_URL = re.compile(r"^(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter)\.com/"
                         r"[^/?#]+/status(?:es)?/(\d+)")
_DRAFT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-draft-(\d+)\.md$")


def parse_id(value):
    """A post's X id, from the bare number or its link (x.com/…/status/<id>, twitter.com
    too, with or without query string). Raises TweetStoreError on anything else."""
    v = str(value or "").strip()
    m = _STATUS_URL.match(v)
    if m:
        v = m.group(1)
    if not v.isdigit() or len(v) > 20:
        raise TweetStoreError(f"{value!r} is not an X post id or link — it looks like "
                              "1857123456789012345 or https://x.com/you/status/1857…")
    return v


def id_date(id):
    """When a post went out, read from its id. Ids from before snowflakes (late 2010) do not
    carry a time; those return None."""
    n = int(id)
    if n < 2 ** 32:
        return None
    return datetime.fromtimestamp(((n >> 22) + _TWEPOCH_MS) / 1000, tz=timezone.utc)


def filename(date, id):
    """`YYYY-MM-DD-<id>.md` — every posted tweet, imported or marked posted."""
    return f"{date.strftime('%Y-%m-%d')}-{_SAFE.sub('', str(id))}.md"


def draft_filename(n, date):
    return f"{date.astimezone(timezone.utc).strftime('%Y-%m-%d')}-draft-{int(n)}.md"


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


def _folder(root=None):
    return os.path.realpath(root or config.tweets_dir())


def save(text, date=None, id=None, url=None, likes=None, retweets=None, root=None,
         dry_run=False, replace=False):
    """Write one posted tweet. Returns `(path, outcome)`, where outcome is "created",
    "unchanged" (the file was already there and was left alone), or — with `replace` —
    "updated" (the file was there with different content and has been rewritten).

    `id` is required: a tweet is named by it. `date` defaults to the one the id carries."""
    text = (text or "").strip()
    if not text:
        raise TweetStoreError("an empty tweet is not a tweet")
    if not _SAFE.sub("", str(id or "")):
        raise TweetStoreError("a tweet is saved under its X id — give the id of the post")
    if date is None and str(id).isdigit():
        date = id_date(id)
    if date is None:
        raise TweetStoreError(f"no date for tweet {id} — give one")
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    folder = _folder(root)
    path = os.path.realpath(os.path.join(folder, filename(date, id)))
    if not path.startswith(folder + os.sep):
        raise TweetStoreError(f"refusing to write outside {folder}: {path}")
    body = render(text, date, id=id, url=url, likes=likes, retweets=retweets)
    ts = date.timestamp()
    if os.path.exists(path):
        if not replace:
            return path, "unchanged"
        with open(path, encoding="utf-8") as fh:
            if fh.read() == body:
                return path, "unchanged"
        if dry_run:
            return path, "updated"
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
        os.utime(path, (ts, ts))
        return path, "updated"
    if dry_run:
        return path, "created"

    # O_EXCL: if two saves race for the same name, the second fails rather than clobbering.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        os.remove(tmp)
        return path, "unchanged"
    os.close(fd)
    os.replace(tmp, path)
    os.utime(path, (ts, ts))
    return path, "created"


# --- drafts/ ---------------------------------------------------------------------------

def _drafts_folder(root=None):
    return os.path.join(_folder(root), DRAFTS)


def draft_files(root=None):
    """`{n: filename}` for the draft files in drafts/ — only names this module writes."""
    d = _drafts_folder(root)
    if not os.path.isdir(d):
        return {}
    out = {}
    for name in sorted(os.listdir(d)):
        m = _DRAFT_NAME.match(name)
        if m:
            out[int(m.group(1))] = name
    return out


def sync_drafts(open_drafts, root=None):
    """Make drafts/ hold exactly these drafts (`[{n, text, created_at}]`): write each one
    whose file is missing or differs, and remove the file of any draft not listed — posted,
    rejected or gone. Returns `(written, removed)` filenames.

    Overwrites and deletes only `*-draft-<n>.md` files inside drafts/; never a posted tweet.
    """
    folder = _drafts_folder(root)
    have = draft_files(root)
    written, removed = [], []
    want = {}
    for d in open_drafts:
        text = (d.get("text") or "").strip()
        if not text:
            continue
        created = d.get("created_at") or ""
        try:
            date = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            date = datetime.now(timezone.utc)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        want[int(d["n"])] = (draft_filename(d["n"], date), text, date)
    for n, name in have.items():
        if n not in want or want[n][0] != name:
            os.remove(os.path.join(folder, name))
            removed.append(name)
    for n, (name, text, date) in want.items():
        path = os.path.realpath(os.path.join(folder, name))
        if not path.startswith(os.path.realpath(folder) + os.sep):
            raise TweetStoreError(f"refusing to write outside {folder}: {path}")
        body = "\n".join(["---", f"date: {date.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                          f"draft: {int(n)}", "---", text, ""])
        try:
            with open(path, encoding="utf-8") as fh:
                if fh.read() == body:
                    continue
        except FileNotFoundError:
            pass
        os.makedirs(folder, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
        written.append(name)
    return written, removed
