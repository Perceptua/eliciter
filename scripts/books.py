#!/usr/bin/env python3
"""Your reading list outside arxiv — add a book, update one, list them.

  scripts/books.sh                              # the list, newest read first
  scripts/books.sh add --title "…" --author "…" --status reading --started 2026-11-02 \\
                       [--finished 2026-11-20] --summary "…"
  scripts/books.sh update <ref> --status finished --finished 2026-11-20
  scripts/books.sh show <ref>                   # one book, summary included
  scripts/books.sh demo                         # write 10 sample books (demo: true)
  scripts/books.sh demo --clear                 # remove the sample books, and only them

**A book is added in a conversation** (the `reading-list` skill): you say you want to add
one, the session asks for the title, author, start date (past or planned), end date if you
know it, and status, writes a short summary for later sessions to use as context, and calls
`add`. Statuses: planned, reading, finished, abandoned. Dates are YYYY-MM-DD.

`<ref>` is the book's filename in books/, with or without `.md` — `list` prints it.
Each book is one file in books/ (gitignored), written only by `eliciterlib/bookstore.py`.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                                       # noqa: E402

config.bootstrap()

from eliciterlib import books, bookstore                              # noqa: E402

MARK = {"planned": "·", "reading": "▸", "finished": "✓", "abandoned": "✗"}

# Sample plays, so the books card has something to page through before there is a real list.
# Dated across 2026 so the order (and "load 10 more", with the two open ones) is visible.
DEMO = [
    ("Hamlet", "finished", "2026-01-04", "2026-01-18",
     "A Danish prince, told by his father's ghost that his uncle murdered the king, feigns "
     "madness while he tests the claim; delay, doubt and performance are the subject as much "
     "as revenge."),
    ("King Lear", "finished", "2026-01-25", "2026-02-12",
     "An old king divides his kingdom by flattery, banishes the one daughter who will not "
     "flatter him, and is stripped of everything; a parallel plot of Gloucester and his sons "
     "doubles the blindness."),
    ("Macbeth", "finished", "2026-02-20", "2026-03-01",
     "A general hears a prophecy that he will be king and, urged by his wife, makes it true "
     "by murder; the play follows what the act does to both of them."),
    ("Othello", "finished", "2026-03-10", "2026-03-24",
     "A Moorish general in Venetian service is turned against his wife by his ensign Iago, "
     "whose motives are never settled; jealousy built entirely from insinuation."),
    ("The Tempest", "finished", "2026-04-02", "2026-04-11",
     "Prospero, a deposed duke turned magician on an island, wrecks his enemies' ship to "
     "bring them under his power, then gives the power up; often read as Shakespeare's "
     "farewell to the stage."),
    ("A Midsummer Night's Dream", "finished", "2026-05-01", "2026-05-06",
     "Four lovers, a troupe of tradesmen rehearsing a play, and quarrelling fairy royalty "
     "cross in a wood outside Athens; a comedy about the arbitrariness of desire."),
    ("Twelfth Night", "abandoned", "2026-06-03", "2026-06-15",
     "Shipwrecked Viola disguises herself as a man in Illyria and is caught in a triangle of "
     "misdirected love; a comedy of mistaken identity with a sour subplot about Malvolio."),
    ("Much Ado About Nothing", "finished", "2026-07-08", "2026-07-19",
     "Two pairs of lovers: Claudio and Hero, parted by a slander, and Beatrice and Benedick, "
     "tricked into admitting they love each other; a comedy of overheard conversations."),
    ("The Winter's Tale", "finished", "2026-08-14", "2026-09-02",
     "A king's sudden jealousy destroys his family; sixteen years later the lost daughter is "
     "found and a statue comes to life. Tragedy turning into romance halfway through."),
    ("Antony and Cleopatra", "finished", "2026-09-20", "2026-10-15",
     "The Roman triumvir Antony and the Egyptian queen choose each other over Rome, and lose "
     "to Octavius; empire and appetite, across the whole Mediterranean."),
    ("Coriolanus", "reading", "2026-11-03", "",
     "A Roman general of great courage and greater contempt for the plebeians is banished by "
     "the city he saved and joins its enemy; politics as a failure of performance."),
    ("Julius Caesar", "planned", "2026-12-01", "",
     "Brutus joins the conspiracy to kill Caesar for the sake of the republic, and loses the "
     "war that follows to Antony and Octavius; the play turns on the funeral speeches."),
]


def show_list(items):
    if not items:
        print("[books] the list is empty — add one with `scripts/books.sh add`, "
              "or `scripts/books.sh demo` for samples")
        return
    for b in items:
        when = b["started"] + (f" → {b['finished']}" if b["finished"] else "")
        demo = "  (demo)" if b["demo"] else ""
        print(f"  {MARK.get(b['status'], '?')} {b['title']} — {b['author']}  "
              f"[{b['status']}] {when}{demo}\n      {b['ref']}")


def main():
    p = argparse.ArgumentParser(prog="books", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", nargs="?", default="list",
                   choices=("list", "add", "update", "show", "demo"))
    p.add_argument("ref", nargs="?", help="update/show: the book's filename in books/")
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--status", choices=books.STATUSES)
    p.add_argument("--started", help="YYYY-MM-DD — past, or planned")
    p.add_argument("--finished", help="YYYY-MM-DD, if known (update: \"\" clears it)")
    p.add_argument("--summary", help="a short account of the book, for later sessions")
    p.add_argument("--clear", action="store_true", help="demo: remove the sample books")
    a = p.parse_args()

    try:
        if a.action == "list":
            show_list(books.load())
        elif a.action == "show":
            if not a.ref:
                p.error("show needs a <ref>")
            b = books.find(a.ref)
            show_list([b])
            print(f"\n{b['summary'] or '(no summary)'}")
        elif a.action == "add":
            name, b = bookstore.add(a.title, a.author, a.status, a.started,
                                    finished=a.finished or "", summary=a.summary or "")
            print(f"[books] added {b['title']} — {b['author']} [{b['status']}] → books/{name}")
        elif a.action == "update":
            if not a.ref:
                p.error("update needs a <ref>")
            b = bookstore.update(a.ref, status=a.status, started=a.started,
                                 finished=a.finished, summary=a.summary,
                                 title=a.title, author=a.author)
            print(f"[books] updated {b['title']} — {b['author']} [{b['status']}]")
        elif a.action == "demo":
            if a.clear:
                gone = bookstore.clear_demo()
                print(f"[books] removed {len(gone)} sample book(s)")
            else:
                added = 0
                for title, status, started, finished, summary in DEMO:
                    try:
                        bookstore.add(title, "William Shakespeare", status, started,
                                      finished=finished, summary=summary, demo=True)
                        added += 1
                    except bookstore.BookStoreError:
                        pass                          # already there
                print(f"[books] wrote {added} sample book(s) to {config.books_dir()} — "
                      "`scripts/books.sh demo --clear` removes them")
    except (bookstore.BookStoreError, KeyError) as e:
        print(f"[books] {e.args[0] if e.args else e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
