"""The one module that writes into `books/`.

`books/` is your reading list outside arxiv. Like `tweets/`, it lives in this repo but
holds a record of *you* — what you read and when — so it is gitignored and has exactly one
writer, for acts you take in a session:

  * adding a book (`scripts/books.sh add`), and
  * updating one you already added — finishing it, abandoning it, fixing a date
    (`scripts/books.sh update`).

The write path is narrow. A book is one file, `<title>-<author>.md`, slugged; adding a book
that is already there is refused (update it instead); every path is checked to stay inside
the folder. The only thing that ever deletes is `clear_demo`, and it removes only files
whose front matter says `demo: true` — the sample entries `scripts/books.sh demo` writes
so the books card can be tried before there is a real list.

Every other module reads books through `books.py` and `readonly.books_dir()`.
`tests/test_readonly.py::test_only_bookstore_writes_into_books` fails if anything else
writes here.
"""
import os
import re
from datetime import datetime, timezone

from . import books, config

_SAFE = re.compile(r"[^a-z0-9]+")


class BookStoreError(ValueError):
    """A book that cannot be saved as asked — a missing field, a bad date or status, a
    duplicate, or a name escaping the folder."""


def slug(title, author):
    def s(x):
        return _SAFE.sub("-", (x or "").lower()).strip("-")
    base = "-".join(p for p in (s(title)[:60].rstrip("-"), s(author)[:30].rstrip("-")) if p)
    return (base or "book") + books.EXTENSION


def validate(fields):
    """Check a whole book (after any update is applied) and return it normalised."""
    out = {k: (str(fields.get(k) or "")).strip() for k in books.FIELDS}
    out["summary"] = (fields.get("summary") or "").strip()
    out["demo"] = bool(fields.get("demo"))
    for k in ("title", "author"):
        if not out[k]:
            raise BookStoreError(f"a book needs a {k}")
        if "\n" in out[k]:
            raise BookStoreError(f"{k} must be one line")
    if out["status"] not in books.STATUSES:
        raise BookStoreError(f"status {out['status']!r} is not one of "
                             f"{', '.join(books.STATUSES)}")
    try:
        out["started"] = books.parse_date(out["started"], "start date")
        out["finished"] = books.parse_date(out["finished"], "end date")
    except ValueError as e:
        raise BookStoreError(str(e))
    if not out["started"]:
        raise BookStoreError("a book needs a start date (past, or planned)")
    if out["finished"] and out["finished"] < out["started"]:
        raise BookStoreError(f"end date {out['finished']} is before the start date "
                             f"{out['started']}")
    if out["finished"] and out["status"] in books.OPEN:
        raise BookStoreError(f"a {out['status']} book has no end date yet — mark it "
                             "finished or abandoned, or leave the end date out")
    return out


def render(b):
    lines = ["---", f"title: {b['title']}", f"author: {b['author']}",
             f"status: {b['status']}", f"started: {b['started']}"]
    if b["finished"]:
        lines.append(f"finished: {b['finished']}")
    lines.append(f"added: {b['added']}")
    if b.get("demo"):
        lines.append("demo: true")
    lines += ["---", b["summary"], ""]
    return "\n".join(lines)


def _folder(root=None):
    return os.path.realpath(root or config.books_dir())


def _path(folder, name):
    path = os.path.realpath(os.path.join(folder, name))
    if not path.startswith(folder + os.sep):
        raise BookStoreError(f"refusing to write outside {folder}: {path}")
    return path


def _write(path, body):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, path)


def add(title, author, status, started, finished="", summary="", demo=False, root=None):
    """Save a new book. Returns `(filename, book)`. Refuses one already on the list."""
    b = validate({"title": title, "author": author, "status": status, "started": started,
                  "finished": finished, "summary": summary, "demo": demo,
                  "added": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    folder = _folder(root)
    name = slug(b["title"], b["author"])
    path = _path(folder, name)
    body = render(b)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    # O_EXCL: the same book added twice (or two adds racing) fails rather than clobbering.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        os.remove(tmp)
        raise BookStoreError(f"{b['title']} by {b['author']} is already on the list "
                             f"({name}) — update it instead")
    os.close(fd)
    os.replace(tmp, path)
    return name, b


def update(ref, root=None, **changes):
    """Change fields of a book already on the list (`status`, `started`, `finished`,
    `summary`, `title`, `author`). The file keeps its name, so a ref stays stable even if
    the title is corrected. `finished=""` clears the end date. Returns the book."""
    current = books.find(ref, root)
    unknown = set(changes) - {"status", "started", "finished", "summary", "title", "author"}
    if unknown:
        raise BookStoreError(f"cannot update {', '.join(sorted(unknown))}")
    merged = {**current, **{k: v for k, v in changes.items() if v is not None}}
    b = validate(merged)
    folder = _folder(root)
    _write(_path(folder, current["ref"]), render(b))
    return b


def clear_demo(root=None):
    """Remove the sample books (`demo: true`), and nothing else. Returns their filenames."""
    folder = _folder(root)
    gone = []
    for b in books.load(root):
        if b["demo"]:
            os.remove(_path(folder, b["ref"]))
            gone.append(b["ref"])
    return gone
