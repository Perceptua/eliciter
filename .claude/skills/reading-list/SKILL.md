---
name: reading-list
description: Add a book (or anything else the user is reading outside arxiv) to eliciter's reading list, or update one already on it — finished it, gave up on it, a date changed. Use when the user says they want to add a book to their reading list, started or finished reading something, plans to read something, or asks what is on their reading list. For arxiv papers use the reading-queue skill instead.
---

# The reading list

Books live in `books/` (gitignored), one `.md` per book, and show in the **books** card
of the UI's Sources tab, newest read first. The only writer is `eliciterlib/bookstore.py`, reached through
`scripts/books.sh` — never write a file in `books/` yourself.

## Adding a book

The user says they want to add a book. Collect five things, then save:

| field | notes |
|---|---|
| **title** | as the book has it |
| **author** | full name; several authors comma-separated |
| **start date** | past, or planned (future is fine) |
| **end date** | only if known — never guess one |
| **status** | `planned`, `reading`, `finished`, or `abandoned` |

1. **Ask only for what you don't have.** If they said "I just finished *Middlemarch*, started
   it in September", you have the title, a status and a rough start — ask for the day (or
   accept "the 1st" as what they mean), and offer to fill the author. One short message for
   everything missing, not one question per turn.
2. **Dates are `YYYY-MM-DD`.** Turn "last Tuesday" or "early October" into a date using
   today's date, and say which date you used. If they only know the month, use the 1st and
   say so. If you can infer the status from the dates (an end date in the past → finished),
   confirm rather than ask.
3. **Write the summary yourself.** Two to four plain sentences on what the book is and what
   it is about — the summary is for later sessions (prompts, tweet topics) to connect the
   book to the user's other material, not for the user to read, and the Sources tab does not
   list it. Write it from what you know of the book. If you don't know the book, say so and
   write only what the user told you about it; do not invent a plot. No verdict on the book
   and nothing about the user's opinion unless they gave one.
4. **Read back once, then save.** One line: *title — author, status, start → end*. On a yes:

   ```bash
   bash scripts/books.sh add --title "…" --author "…" --status reading \
     --started 2026-11-02 [--finished 2026-11-20] --summary "…"
   ```

   Then tell them it is in the books card on the Sources tab. If `add` says the book is already on the list,
   it is an update, not an add — see below.

## Updating a book

"I finished *Coriolanus* yesterday" is an update. Find its ref (the filename) with
`bash scripts/books.sh`, then:

```bash
bash scripts/books.sh update coriolanus-william-shakespeare --status finished --finished 2026-11-20
```

Only the flags given change. `--finished ""` clears an end date. A `planned` or `reading`
book cannot carry an end date — set the status in the same call. `show <ref>` prints one
book with its summary.

## Sample data

`bash scripts/books.sh demo` writes twelve Shakespeare plays flagged `demo: true`, so the
tab can be tried; `bash scripts/books.sh demo --clear` removes exactly those and nothing
else. Samples are never gathered into `state/material.json`. If the user starts adding real
books while samples are there, mention once that they are still in the list and how to
clear them.

## What books are for

`scripts/gather.sh` puts every book, summary included, into `state/material.json` under
`books`, and `books` is a source a prompt may cite (`{"source": "books", "ref":
"<filename>"}`). A finished book is like a read paper: what a prompt can ask for is the
claim the user took from it. A book they are still reading is context, not yet material.
