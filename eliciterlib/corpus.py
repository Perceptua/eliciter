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
