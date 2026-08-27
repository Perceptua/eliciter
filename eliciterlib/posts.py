"""Source — perceptua posts, read through the gate.

The published site: Eleventy, YAML front matter, one file per post under `_posts/`, named
`YYYY-MM-DD-slug.md`. Almost all of it is verse.

Posts are here as **your own related work** — material to write *back* to. A post surfaces
when its vocabulary overlaps what you have been reading and noting, which is what makes the
prompt a response rather than a nudge; if nothing overlaps, the earliest post surfaces
instead, on the grounds that the oldest unanswered thing is the one most owed a reply.

Access is through `readonly.ReadOnlyDir`: this module can list and read inside `_posts/`
and has no method that writes. Drafting a poem is something you do in perceptua.

An earlier version also emitted "you have used this form once" and "you have not posted in
N days" prompts. Both were dropped: they ask for writing but not for a *response* to
anything, which is outside what this project is for.
"""
import re
from datetime import date

from . import config, rank, readonly
from .signals import Signal

FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+?)\.(?:md|markdown)$")

# At most this many posts become prompts in one run. Posts are the quietest source and
# should not crowd out the reading.
MAX_SIGNALS = 2


def _split_front_matter(text):
    """Return (front_matter_dict, body). Tolerant by design: a post with no front matter
    is still a post, and this module must never be the reason a run fails."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip().lower()] = v
    return fm, parts[2].lstrip("\n")


def _keywords(fm):
    kw = fm.get("keywords", "")
    items = kw if isinstance(kw, list) else [k.strip() for k in str(kw).split(",")]
    return [k.lower() for k in items if k]


def load(posts_dir=None):
    """Every post, oldest first. Reads through the gate; never opens a file directly."""
    gate = readonly.posts_dir(posts_dir or config.posts_dir())
    out = []
    for name in gate.names():
        m = FILENAME_RE.match(name)
        if not m:
            continue                       # _posts.11tydata.js and friends
        fm, body = _split_front_matter(gate.read(name))
        cats = fm.get("categories", [])
        out.append({
            "file": name,
            "slug": m.group(4),
            "date": date(int(m.group(1)), int(m.group(2)), int(m.group(3))),
            "title": fm.get("title") or m.group(4).replace("-", " "),
            "categories": cats if isinstance(cats, list) else [str(cats)],
            "keywords": _keywords(fm),
            "description": fm.get("description", ""),
            "body": body,
        })
    return out


def plain_text(post):
    """The poem with its markup taken off. The site wraps lines in `<p class="hanging">`,
    so raw bodies read badly and score wrongly — the tag repeats once per line."""
    txt = re.sub(r"<[^>]+>", "", post["body"])
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def _excerpt(text, max_chars=600):
    """Trim to whole lines. A poem cut mid-word reads as a rendering bug, and in verse the
    line is the unit — a half line is not a shorter quotation, it is a wrong one."""
    if len(text) <= max_chars:
        return text
    kept, used = [], 0
    for line in text.splitlines():
        if used + len(line) + 1 > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept).rstrip() + "\n…"


def signals(profile=None, log=print):
    """Posts worth answering, as Signals.

    `profile` is the interest/corpus profile from `rank.profile`. Posts that share
    vocabulary with it are surfaced first — those are the ones genuinely adjacent to
    current thinking. With no profile or no overlap, the earliest post is surfaced.
    """
    posts = load()
    if not posts:
        log("[perceptua] no posts found")
        return []

    scored = []
    if profile:
        for p in posts:
            sc, matched = rank.score(f"{p['title']} {plain_text(p)}", profile)
            if sc > 0:
                scored.append((sc, matched, p))
        scored.sort(key=lambda t: -t[0])

    out = []
    for sc, matched, p in scored[:MAX_SIGNALS]:
        out.append(Signal(
            source="perceptua", kind="post-response",
            title=p["title"],
            detail=_excerpt(plain_text(p)),
            ref=p["file"],
            score=min(1.0, sc),
            meta={"post": p, "matched": matched, "reason": "overlap"}))

    if not out:
        p = min(posts, key=lambda p: p["date"])
        out.append(Signal(
            source="perceptua", kind="post-response",
            title=p["title"],
            detail=_excerpt(plain_text(p)),
            ref=p["file"],
            score=0.3,
            meta={"post": p, "matched": [], "reason": "earliest"}))

    log(f"[perceptua] {len(posts)} post(s); {len(out)} signal(s)")
    return out
