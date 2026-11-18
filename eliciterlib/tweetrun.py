"""Tweet drafts: the tweets you finalized in a session, waiting to be posted.

**Nothing here writes a tweet.** The first version of the Tweets tab had a session batch
out two or three drafts per topic in your voice. They read as pastiche and the design was
dropped (2026-11-17). Tweets are now composed in a conversation (the `elicit-tweets`
skill):

  1. the session pitches a topic from your recent reading and writing;
  2. you pass or engage;
  3. the two of you work your sentence until you call it done;
  4. only then is it saved here, as a draft, through `scripts/tweets.sh draft`.

So a draft in `state/tweets.json` is always something you finalized. The Tweets tab shows
it with Copy and Posted / Not this one, exactly like before. Each open draft also sits in
`tweets/drafts/` as a file (`sync`), so you can see what is waiting from the folder.

Beside the drafts sits the **topic log**: every topic a session pitched, and what became
of it — `drafted`, `passed` (you turned it down), or `skipped` (the session ran out of
time or you wrapped early). The next session reads it, so a topic you passed on is not
pitched again unless something new has landed on it.

A draft can be revised before it is posted (`revise`, `scripts/tweets.sh revise`). It
keeps its number, and each earlier text is kept under `revisions`.

Both lists only ever grow. Drafts are numbered by arrival (`n` is never reused), so the
number on a card means the same draft for as long as the file exists.

**Length is counted the way X counts it, roughly.** Every URL costs 23 characters
whatever its length, and everything else costs one. X also weights CJK and some emoji as
two; that is not modelled here.
"""
import os
import re
from datetime import datetime, timezone

from . import run, tweetstore
from .render import InvalidPrompts, sources_for
from .run import status_of
from .signals import TWEET_STATUSES

LIMIT = 280
URL_COST = 23
TOPIC_OUTCOMES = ("drafted", "passed", "skipped")

_URL = re.compile(r"https?://\S+")


class InvalidTweets(InvalidPrompts):
    """A draft or topic that cannot be saved as given. The message says which field."""


def weighted_length(text):
    """Characters as X counts them, minus the CJK/emoji weighting (see module doc)."""
    urls = _URL.findall(text)
    return len(_URL.sub("", text)) + URL_COST * len(urls)


def _now():
    return datetime.now(timezone.utc).isoformat()


def parse_sources(specs):
    """`["arxiv:2609.00075v1", "misc:Some file.txt"]` → `[{source, ref}]`.

    Split on the first colon only, so a ref may contain colons; a title can follow a
    second `|` (`"tweets:2021-…md|a historian of the 28th century"`).
    """
    out = []
    for spec in specs or []:
        src, sep, rest = str(spec).partition(":")
        if not sep:
            raise InvalidTweets(f"source {spec!r} should be <source>:<ref>")
        ref, _, title = rest.partition("|")
        out.append({"source": src.strip(), "ref": ref.strip(), "title": title.strip()})
    return out


def _check_text(text):
    text = (text or "").strip()
    if not text:
        raise InvalidTweets("the tweet is empty")
    n = weighted_length(text)
    if n > LIMIT:
        raise InvalidTweets(f"{n} characters (URLs count as {URL_COST}) — the limit is {LIMIT}")
    return text


def add_draft(text, title, sources, because="", r=None):
    """Save one finalized tweet as a draft. Returns the stored draft (with its `n`)."""
    r = r or run.tweet_run()
    title = (title or "").strip()
    if not title:
        raise InvalidTweets("a draft needs a title — the topic it came from")
    try:
        srcs = sources_for({"sources": sources}, "draft")
    except InvalidPrompts as e:
        raise InvalidTweets(str(e)) from None
    text = _check_text(text)
    n = max([d.get("n", 0) for d in r.prompts] or [0]) + 1
    draft = {"n": n, "title": title, "text": text, "length": weighted_length(text),
             "sources": srcs, "because": (because or "").strip(), "created_at": _now()}
    r.prompts.append(draft)
    r.save()
    sync(r)
    return draft


def revise(n, text=None, title=None, r=None):
    """Change draft `n` before it goes out: its text, its title, or both. Returns the draft.

    The draft keeps its number, sources and status. Each earlier text is kept under
    `revisions` (`{text, at}`, oldest first): what changed between "done" in a session and
    the moment of posting is exactly what the next session should learn from.

    A posted draft is refused. What went out is recorded as it went out; if the posted text
    differed from the draft, that is `post(n, text=…)`, not a revision.
    """
    r = r or run.tweet_run()
    draft = r.find(n)
    if draft is None:
        raise KeyError(f"no draft {n} — there are {len(r.prompts)}")
    if status_of(draft, TWEET_STATUSES) == "posted":
        raise ValueError(f"draft {n} is already posted — what went out is "
                         f"{draft.get('posted_file', 'in tweets/')}; it cannot be revised")
    if text is None and title is None:
        raise InvalidTweets("nothing to revise — give a new text, a new title, or both")
    if title is not None:
        title = str(title).strip()
        if not title:
            raise InvalidTweets("a draft needs a title — the topic it came from")
    if text is not None:
        text = _check_text(text)
    changed = False
    if text is not None and text != draft.get("text"):
        draft.setdefault("revisions", []).append(
            {"text": draft.get("text", ""), "at": draft.get("revised_at")
             or draft.get("created_at", "")})
        draft["text"], draft["length"] = text, weighted_length(text)
        changed = True
    if title is not None and title != draft.get("title"):
        draft["title"] = title
        changed = True
    if not changed:
        raise InvalidTweets(f"draft {n} already says that — nothing changed")
    draft["revised_at"] = _now()
    r.save()
    sync(r)
    return draft


def sync(r=None, root=None):
    """Make `tweets/drafts/` hold exactly the open drafts. Called after every change; safe to
    call any time. Returns `(written, removed)`."""
    r = r or run.tweet_run()
    return tweetstore.sync_drafts(
        [d for d in r.prompts if status_of(d, TWEET_STATUSES) == "open"], root=root)


def decide(n, status, title=None, r=None):
    """Mark draft `n` rejected or open again (posting is `post`), and keep drafts/ in step:
    a rejected draft leaves the folder, one put back on offer returns to it."""
    if status == "posted":
        raise ValueError("posting needs the post's X id — use post(n, id)")
    r = r or run.tweet_run()
    marked = r.mark(n, status, expect_title=title)
    r.save()
    sync(r)
    return marked


def log_topic(title, sources, outcome, note="", r=None):
    """Record a pitched topic and what became of it. Returns the entry."""
    if outcome not in TOPIC_OUTCOMES:
        raise InvalidTweets(f"outcome {outcome!r} is not one of {', '.join(TOPIC_OUTCOMES)}")
    title = (title or "").strip()
    if not title:
        raise InvalidTweets("a topic needs a title")
    try:
        srcs = sources_for({"sources": sources}, "topic")
    except InvalidPrompts as e:
        raise InvalidTweets(str(e)) from None
    r = r or run.tweet_run()
    entry = {"title": title, "sources": srcs, "outcome": outcome,
             "note": (note or "").strip(), "at": _now()}
    r.meta.setdefault("topics", []).append(entry)
    r.save()
    return entry


def post(n, id, text=None, title=None, r=None):
    """Mark draft `n` posted and save what went out to tweets/. Returns `(draft, path)`.

    Shared by `scripts/tweets.sh posted` and the web UI's "Posted this", so the two cannot
    disagree about what posting means. `id` is the post's X id, or its link: the tweet is
    saved as `YYYY-MM-DD-<id>.md`, dated by the id, which is the same name an archive import
    gives it — so importing later never saves it twice. `text` is what you actually posted,
    if you changed it on the way out; otherwise the draft's own text. It is saved before the
    draft is marked, so a failed save never leaves a draft marked posted with no file
    behind it. If the file is already there (the archive got there first), it is left as
    it is and the draft simply points at it.

    A draft already posted is refused rather than saved twice — unless it was posted before
    posts carried ids, in which case this attaches the id to it. Reopening one does not
    delete its file — tweets/ only ever grows by your hand, never shrinks by eliciter's.
    """
    r = r or run.tweet_run()
    draft = r.find(n)
    if draft is None:
        raise KeyError(f"no draft {n} — there are {len(r.prompts)}")
    if title is not None and str(title).strip() != str(draft.get("title") or "").strip():
        raise run.StaleRun(f"draft {n} is now {draft.get('title')!r} — the list changed "
                           "while you were looking at it; refresh and decide again")
    try:
        tid = tweetstore.parse_id(id)
    except tweetstore.TweetStoreError as e:
        raise InvalidTweets(str(e)) from None
    already = status_of(draft, TWEET_STATUSES) == "posted"
    if already and draft.get("posted_id"):
        raise ValueError(f"draft {n} is already posted ({draft.get('posted_file', '')})")
    default = draft.get("posted_text") if already else draft.get("text")
    text = _check_text(text if text and str(text).strip() else default)
    path, _ = tweetstore.save(text, id=tid, url=f"https://x.com/i/status/{tid}")
    extra = {"posted_text": text, "posted_file": os.path.basename(path), "posted_id": tid}
    if already:
        draft.update(extra)
    else:
        r.mark(n, "posted", expect_title=title, extra=extra)
    r.save()
    sync(r)
    return draft, path
