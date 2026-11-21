"""Source — the books you are reading outside arxiv, read through the gate.

One `.md` per book in `ELICITER_BOOKS_DIR` (default `books/` at the repo root,
gitignored). A book gets there one way: you say you want to add it in a session, the
session asks for what it needs, and `scripts/books.sh add` saves it through
`bookstore.py` — the one module allowed to write here. This module only reads.

A file is a short front matter block and then a summary of the book:

    ---
    title: The Tempest
    author: William Shakespeare
    status: finished
    started: 2026-10-02
    finished: 2026-10-09
    added: 2026-11-21T15:04:05Z
    ---
    A short account of what the book is and what it is about.

`started` may be in the future (a planned read); `finished` is optional until you know it.
**The summary is for sessions, not for you** — it is what lets a session writing prompts or
pitching tweets connect a book to the rest of your material without having read it. So the
books card on the Sources tab lists every field except it, and `state/material.json` carries it in full.

The front matter is `key: value` lines and nothing more, the same as tweets — no YAML
dependency for six scalars.
"""
import re
from datetime import date

from . import config, readonly

EXTENSION = ".md"

# What can be true of a book on your list. `planned` has a start date (possibly in the
# future) and no finish; `reading` is under way; `finished` and `abandoned` are the two ways
# a read ends, and either may carry an end date.
STATUSES = ("planned", "reading", "finished", "abandoned")
OPEN = ("planned", "reading")

FIELDS = ("title", "author", "status", "started", "finished", "added")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value, field="date"):
    """`YYYY-MM-DD` → the same string, validated; empty → "". Raises ValueError otherwise."""
    v = str(value or "").strip()
    if not v:
        return ""
    if not _DATE.match(v):
        raise ValueError(f"{field} {value!r} is not a date — use YYYY-MM-DD")
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"{field} {value!r} is not a real date")
    return v


def parse(raw):
    """File text → (front matter dict, summary). A file with no block is all summary."""
    meta, body = {}, raw
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end != -1:
            for line in raw[4:end].splitlines():
                k, sep, v = line.partition(":")
                if sep and k.strip():
                    meta[k.strip().lower()] = v.strip()
            body = raw[end + 4:].lstrip("\n")
    return meta, body.strip()


def _row(name, meta, summary):
    return {
        "ref": name,
        "title": meta.get("title") or name[:-len(EXTENSION)].replace("-", " "),
        "author": meta.get("author", ""),
        "status": meta.get("status", "") if meta.get("status") in STATUSES else "",
        "started": meta.get("started", ""),
        "finished": meta.get("finished", ""),
        "added": meta.get("added", ""),
        "demo": meta.get("demo", "").lower() == "true",
        "summary": summary,
    }


def sort_key(b):
    """Newest read first, by end date.

    A book with no end date that is still open — being read, or planned — leads the list,
    since it is the most current thing you are reading; `reading` before `planned`, then by
    start date. Everything else orders by its end date, or its start date when the end date
    was never recorded. Used with `reverse=True`.
    """
    if not b["finished"] and b["status"] in OPEN:
        return (2 if b["status"] == "reading" else 1, b["started"])
    return (0, b["finished"] or b["started"])


def load(root=None):
    """Every book, in display order (see `sort_key`), each with its summary."""
    gate = readonly.books_dir(root or config.books_dir())
    out = []
    for name in gate.names():
        if not name.endswith(EXTENSION):
            continue
        meta, summary = parse(gate.read(name))
        out.append(_row(name, meta, summary))
    out.sort(key=sort_key, reverse=True)
    return out


def find(ref, root=None):
    """One book by its filename, with or without `.md`. KeyError if there is none."""
    ref = (ref or "").strip()
    want = ref if ref.endswith(EXTENSION) else ref + EXTENSION
    for b in load(root):
        if b["ref"] == want:
            return b
    raise KeyError(f"no book {ref!r} in the reading list")
