"""Tweet cards: validate what a session wrote, then render it to markdown.

**This is the one place eliciter drafts your writing.** Everywhere else the rule is that
the machine proposes the site and you write — a prompt with a thesis in it is wrong. The
Tweets tab is a deliberate, fenced exception: a card names a site, cites its sources like a
prompt does, and then carries **two or three drafted tweets in your voice** (see
`voice.py`). You pick one, edit it, post it, or turn the card down.

The shape mirrors `render.py` on purpose. A session writes `state/tweets.json`; this
module validates it and derives what is derivable (`n`, each draft's weighted length);
`scripts/tweets.sh render` writes the canonical JSON back and renders
`prompts/tweets-latest.md`. Decisions — posted, rejected — are kept beside each card by
`run.tweet_run()` and survive a re-render.

**Length is counted the way X counts it, roughly.** Every URL costs 23 characters
whatever its length, and everything else costs one. X also weights CJK and some emoji as
two; that is not modelled here, and a draft that leans on either should be checked in the
composer.
"""
import os
import re
from datetime import datetime, timezone

from . import run, tweetstore
from .render import InvalidPrompts, _quote, sources_for
from .run import status_of
from .signals import TWEET_STATUSES

LIMIT = 280
URL_COST = 23
MIN_DRAFTS, MAX_DRAFTS = 2, 3

_URL = re.compile(r"https?://\S+")


class InvalidTweets(InvalidPrompts):
    """What a session wrote is not a tweet run. The message names the card and field."""


def weighted_length(text):
    """Characters as X counts them, minus the CJK/emoji weighting (see module doc)."""
    urls = _URL.findall(text)
    return len(_URL.sub("", text)) + URL_COST * len(urls)


def validate(raw):
    """Session output → the canonical card list. Raises `InvalidTweets`."""
    if not isinstance(raw, list):
        raise InvalidTweets(f"expected a list of cards, got {type(raw).__name__}")
    out = []
    for i, c in enumerate(raw, 1):
        where = f"card {i}"
        if not isinstance(c, dict):
            raise InvalidTweets(f"{where}: expected an object, got {type(c).__name__}")
        for field in ("title", "site"):
            if not str(c.get(field) or "").strip():
                raise InvalidTweets(f"{where}: {field} is required")
        try:
            sources = sources_for(c, where)
        except InvalidPrompts as e:
            raise InvalidTweets(str(e)) from None

        drafts = c.get("drafts")
        if not isinstance(drafts, list):
            raise InvalidTweets(f"{where}: drafts must be a list of strings")
        drafts = [str(d).strip() for d in drafts]
        if any(not d for d in drafts):
            raise InvalidTweets(f"{where}: a draft is empty")
        if not MIN_DRAFTS <= len(drafts) <= MAX_DRAFTS:
            raise InvalidTweets(
                f"{where}: {len(drafts)} draft(s) — a card carries {MIN_DRAFTS}–{MAX_DRAFTS}")
        if len(set(drafts)) != len(drafts):
            raise InvalidTweets(f"{where}: two drafts are identical")
        for k, d in enumerate(drafts, 1):
            n = weighted_length(d)
            if n > LIMIT:
                raise InvalidTweets(
                    f"{where}, draft {k}: {n} characters (URLs count as {URL_COST}) — "
                    f"the limit is {LIMIT}")

        # Decisions survive a re-render, exactly as in `render.validate`.
        status = str(c.get("status") or "").strip().lower()
        decided = {}
        if status in TWEET_STATUSES and status != "open":
            decided = {"status": status, "decided_at": str(c.get("decided_at") or "").strip()}
            for k in ("posted_text", "posted_draft", "posted_file"):
                if c.get(k) not in (None, ""):
                    decided[k] = c[k]

        out.append({
            "n": i,
            "title": str(c["title"]).strip(),
            "site": str(c["site"]).strip(),
            "because": str(c.get("because") or "").strip(),
            "sources": sources,
            "drafts": drafts,
            "lengths": [weighted_length(d) for d in drafts],
            **decided,
        })
    return out


def render(cards, stats=None):
    stats = stats or {}
    now = datetime.now(timezone.utc)
    L = [f"# Tweets — {now.strftime('%Y-%m-%d')}", ""]
    L += ["_Drafted by a Claude session in your voice (`state/voice.md`) from "
          "`state/material.json`; rendered by `scripts/tweets.sh render` and overwritten "
          "on each run. This is the one place eliciter drafts — pick one, change it, or "
          "turn the card down. `scripts/tweets.sh posted <n> --draft <k>` saves what you "
          "posted into tweets/._", ""]
    if stats.get("gathered_at"):
        L += [f"_From material gathered {stats['gathered_at']}._", ""]
    if stats.get("voice_built_at"):
        L += [f"_Voice built {stats['voice_built_at']}._", ""]

    if not cards:
        L += ["## Nothing to post", "",
              stats.get("quiet") or "Nothing in the material is worth saying out loud "
              "right now. That is a real answer.", ""]
        return "\n".join(L)

    statuses = [status_of(c, TWEET_STATUSES) for c in cards]
    n_p, n_r = statuses.count("posted"), statuses.count("rejected")
    tally = [f"{len(cards)} card{'s' if len(cards) != 1 else ''}"]
    if n_p or n_r:
        tally += [f"{n_p} posted", f"{n_r} rejected", f"{len(cards) - n_p - n_r} still open"]
    L += ["_" + " · ".join(tally) + "._", ""]

    for c, st in zip(cards, statuses):
        mark = {"posted": "  ✓ posted", "rejected": "  ✗ rejected"}.get(st, "")
        L += [f"### {c['n']}. {c['title']}{mark}", "", f"**{c['site']}**", ""]
        if c["because"]:
            L += [c["because"], ""]
        for s in c["sources"]:
            line = f"↳ **{s['title'] or s['ref']}** ({s['source']} · `{s['ref']}`)"
            L += [line + (f" — {s['why']}" if s["why"] else ""), ""]
        for k, (d, n) in enumerate(zip(c["drafts"], c["lengths"]), 1):
            L += [f"**draft {k}** · {n}/{LIMIT}", "", _quote(d), ""]
        if st == "posted" and c.get("posted_text"):
            L += ["**posted:**", "", _quote(c["posted_text"]), ""]
        if st == "open":
            L += [f"→ `bash scripts/tweets.sh posted {c['n']} --draft <k>` once it is out", ""]
        else:
            when = (c.get("decided_at") or "")[:10]
            L += [f"— {st}{f' {when}' if when else ''} · "
                  f"`bash scripts/tweets.sh reopen {c['n']}` to put it back on offer", ""]
    return "\n".join(L)


def post(n, draft=None, text=None, title=None, r=None):
    """Mark card `n` posted and save the text to tweets/. Returns `(card, path)`.

    Shared by `scripts/tweets.sh posted` and the web UI's "Posted this", so the two cannot
    disagree about what posting means. The text is the edited one if given, else the
    chosen draft. It is saved before the card is marked, so a failed save never leaves a
    card marked posted with no file behind it.

    A card already posted is refused rather than saved twice. Reopening one does not delete
    its file — tweets/ only ever grows by your hand, never shrinks by eliciter's.
    """
    r = r or run.tweet_run()
    card = r.find(n)
    if card is None:
        raise KeyError(f"no card {n} — there are {len(r.prompts)}")
    if title is not None and str(title).strip() != str(card.get("title") or "").strip():
        raise run.StaleRun(f"card {n} is now {card.get('title')!r} — the run was replaced "
                           "while you were looking at it; refresh and decide again")
    if status_of(card, TWEET_STATUSES) == "posted":
        raise ValueError(f"card {n} is already posted ({card.get('posted_file', '')})")
    drafts = card.get("drafts") or []
    if text is None or not str(text).strip():
        if draft is None:
            raise ValueError("which draft? pass --draft <k>, or --text with what you posted")
        if not 1 <= int(draft) <= len(drafts):
            raise ValueError(f"card {n} has {len(drafts)} draft(s); no draft {draft}")
        text = drafts[int(draft) - 1]
    path, _ = tweetstore.save(str(text), datetime.now(timezone.utc))
    r.mark(n, "posted", expect_title=title, extra={
        "posted_text": str(text).strip(),
        "posted_draft": int(draft) if draft else None,
        "posted_file": os.path.basename(path)})
    r.save()
    return card, path
