"""Source — the indexia graph, read through the gate.

indexia already knows what is unfinished in its own corpus: seven generativity moves, six
in `notelib` and move 7 in `analytics/debt.py`. eliciter calls them rather than
reimplementing them, and turns their output into Signals.

The division of labour: **indexia's digest proposes links, eliciter proposes writing.** So
moves 1–3 are ignored here — their output is a bind, and a bind is a judgement, not an
essay. Moves 4–7 all end in "you should write something", and those are the four this reads.

Everything goes through `readonly.graph()`. This module never constructs a `notelib.Arcade`,
and the handle it holds has no method that writes — see `eliciterlib/readonly.py`. The moves
themselves are reads (`Corpus` and every `moveN_candidates` only call `db.query`), which is
why passing them a gated handle works at all.
"""
import re

import notelib
from analytics import common, debt

from . import readonly
from .signals import Signal

# Move 4 clusters notes with no hub. Below this many members a "theme" is a coincidence,
# and asking for a hub note over two notes just asks you to restate one of them.
MIN_THEME = 3


def connect():
    """The gated graph handle. There is no ungated one in this project."""
    return readonly.graph()


def _title(row):
    return row.get("title") or "(untitled)"


def recent_notes(db, limit=12):
    """Most recent notes, newest first — the writer's current material."""
    return notelib.rows(db.query(
        "SELECT id, title, body, created_at, source_ref FROM Note "
        f"WHERE status = 'active' ORDER BY created_at DESC LIMIT {int(limit)}"))


def all_notes(db):
    return notelib.rows(db.query(
        "SELECT id, title, body FROM Note WHERE status = 'active'"))


# Note ids are indexia spec §4 timestamps — `20260807T194938347Z`. Nothing else in a
# signal's meta looks like one, which is what makes the scrape in `_attach_text` below
# safe to run over arbitrary move output without knowing each move's shape.
NOTE_ID_RE = re.compile(r"\b\d{8}T\d{9}Z\b")


def bodies(db, ids):
    """→ {id: "title\n\nbody"} for the given note ids, in one query.

    The moves return *labels* — a title, sometimes a snippet — because that is all a
    provocation digest needs to print. A session reading `state/material.json` needs the
    actual prose, or it is judging four notes by their titles. This is
    the one extra read that buys that, and it is a read: `db` is the gated handle and the
    statement is a SELECT, so it goes through `readonly.assert_read_only` like every other.
    """
    ids = [i for i in dict.fromkeys(ids) if NOTE_ID_RE.fullmatch(str(i))]
    if not ids:
        return {}
    # Ids are format-checked against NOTE_ID_RE above, so they cannot carry a quote — but
    # they are still interpolated rather than parameterized because notelib's query takes
    # params positionally and the moves themselves build IN-lists the same way.
    listed = ", ".join(f"'{i}'" for i in ids)
    rows = notelib.rows(db.query(
        f"SELECT id, title, body FROM Note WHERE id IN [{listed}]"))
    return {r.get("id"): f"{r.get('title') or ''}\n\n{r.get('body') or ''}".strip()
            for r in rows}


def note(db, note_id):
    """One note in full, for the UI's source reader — or None if there is no such id.

    The UI shows a prompt's material as an excerpt and then offers to open the whole
    thing; for an indexia prompt "the whole thing" is the note itself, which no other read
    in this module returns (the moves return labels, `recent_notes` returns a window).
    """
    if not NOTE_ID_RE.fullmatch(str(note_id or "")):
        return None
    rows = notelib.rows(db.query(
        "SELECT id, title, body, created_at, source_ref, status FROM Note "
        f"WHERE id = '{note_id}'"))
    return rows[0] if rows else None


def _attach_text(db, out):
    """Give every signal the full prose of the notes it is about, as `meta["text"]`.

    Done once for the whole batch rather than inside each move: the moves stay as thin as
    they are, and four moves that each mention the same note cost one query between them
    instead of four. A failure here is not fatal — the signals are still perfectly good
    prompts, they are just themed on their titles alone.
    """
    wanted = {}
    for s in out:
        found = set(NOTE_ID_RE.findall(f"{s.ref} {s.detail} {s.meta}"))
        if found:
            wanted[id(s)] = found
    every = sorted({i for ids in wanted.values() for i in ids})
    if not every:
        return out
    text = bodies(db, every)
    for s in out:
        got = [text[i] for i in sorted(wanted.get(id(s), ())) if i in text]
        if got:
            s.meta["text"] = "\n\n".join(got)
    return out


def signals(db, log=print):
    """Moves 4–7, as Signals. A move that finds nothing contributes nothing; a move that
    raises is reported and skipped, so one failing move cannot take down a run."""
    out = []
    for name, fn in (("move4", _move4), ("move5", _move5),
                     ("move6", _move6), ("move7", _move7)):
        try:
            found = fn(db)
            out.extend(found)
            log(f"[indexia] {name}: {len(found)} signal(s)")
        except readonly.ReadOnlyViolation:
            raise                                   # a gate breach is never "just skip it"
        except Exception as e:                      # noqa: BLE001 — one move must not sink the run
            log(f"[indexia] {name}: skipped ({type(e).__name__}: {e})")
    try:
        _attach_text(db, out)
    except Exception as e:                          # noqa: BLE001
        log(f"[indexia] note bodies unavailable ({type(e).__name__}: {e})")
    return out


def _move4(db):
    """Implicit theme with no hub note → write the hub."""
    out = []
    for theme in notelib.move4_candidates(db, min_theme=MIN_THEME) or []:
        members = theme.get("members") or []
        if len(members) < MIN_THEME:
            continue
        listed = "\n".join(f"  - `{m.get('id')}` · {_title(m)}" for m in members)
        out.append(Signal(
            source="indexia", kind="move4",
            title=f"{len(members)} notes circling one unnamed idea",
            detail=listed,
            ref=str(theme.get("seed") or (members[0].get("id") if members else "")),
            # A bigger cluster is a louder absence: more notes leaning on a thing you
            # have never stated. Saturates at 8 so one huge cluster cannot monopolize a run.
            score=min(1.0, len(members) / 8.0),
            meta={"members": members}))
    return out


def _move5(db):
    """A ratified `inhibits` pair → write the reconciliation.

    The edge points from the correction to what it corrects, so `new` is what you think
    now and `old` is what you thought. Both are still corpus — nothing dies (spec §6) —
    which is exactly why the pair is worth an essay rather than a deletion.
    """
    out = []
    for pair in notelib.move5_candidates(db) or []:
        new_t = pair.get("new_title") or "(untitled)"
        old_t = pair.get("old_title") or "(untitled)"
        out.append(Signal(
            source="indexia", kind="move5",
            title=f"{new_t} ⟂ {old_t}",
            detail=(f"  - now: `{pair.get('new')}` · {new_t}\n"
                    f"    {pair.get('new_snippet') or ''}\n"
                    f"  - then: `{pair.get('old')}` · {old_t}\n"
                    f"    {pair.get('old_snippet') or ''}\n"
                    f"  - you wrote, correcting it: {pair.get('reason') or '(no rationale)'}"),
            ref=f"{pair.get('new')}+{pair.get('old')}",
            # You ratified this contradiction by hand. Nothing else in the corpus is a
            # stronger signal that you know two things you hold are not compatible yet.
            score=0.9,
            meta=dict(pair)))
    return out


def _move6(db):
    """Re-encounter: orphans want the next note; an anniversary wants a dated entry."""
    out = []
    buckets = notelib.move6_candidates(db) or {}
    for n in (buckets.get("orphans") or [])[:4]:
        out.append(Signal(
            source="indexia", kind="orphan",
            title=_title(n), detail=n.get("snippet") or "",
            ref=n.get("id") or "", score=0.5, meta={"note": n}))
    for n in (buckets.get("on_this_day") or [])[:2]:
        out.append(Signal(
            source="indexia", kind="on-this-day",
            title=_title(n), detail=n.get("snippet") or "",
            ref=n.get("id") or "", score=0.6, meta={"note": n}))
    return out


def _move7(db):
    """Structural debt: a note the corpus grew out of that you stopped attending to."""
    out = []
    corpus = common.Corpus(db)
    for row in debt.report(corpus) or []:
        # debt rows carry `label` (Corpus.label), not `title` — they are built from the
        # in-memory Corpus, not from a Note row.
        out.append(Signal(
            source="indexia", kind="move7",
            title=row.get("label") or "(untitled)",
            detail=debt.prompt(row),
            ref=row.get("id") or "",
            # debt is an unbounded ratio; 10 is "a subtree of ten hangs off this and you
            # never came back", which is already as loud as this move gets.
            score=min(1.0, float(row.get("debt", 0.0)) / 10.0),
            meta={"row": row}))
    return out
