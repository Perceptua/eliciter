"""Signals → prompts. This is where the register rule lives, and only here.

**The rule (chosen 2026-08-26): the source decides.** Whatever surfaced a signal sets
what you are asked to write and in what shape. arxiv asks for notes, because that is
demonstrably what you do with a paper — every note in the corpus is one claim with a
`source_ref` pointing at a paper. The graph asks for whatever its move implies: a hub
note, a reconciling essay, a journal entry on an anniversary. perceptua asks for verse,
in the form the post itself names.

The source also sets the *order* — `signals.SOURCES`, indexia then perceptua then arxiv —
both here, where it decides who gets the last slot under the limit, and in `render.py`,
where it decides what you read first.

Nothing here decides register from *content*. A prompt never reads a paper's abstract
and concludes it would make a good poem — that would be the machine deciding what your
material is for, which is the boundary indexia's spec §8.2 draws and this project keeps:
**the machine proposes the site, the human writes.**

So every `ask` below states a site and a shape and then stops. None of them says what to
argue, what the paper implies, or what the poem should be about. If a prompt ever starts
suggesting a thesis, that is a bug in this file.
"""
from datetime import datetime, timedelta, timezone

from .signals import Prompt, source_rank

# A staging filename is a spec §4 id: a compact UTC timestamp to the millisecond. Rendering
# one into the prompt means committing the answer is `cat > staging/<that>.md`, with no
# detour through new-id.sh.
#
# Ids are minted from one base instant plus the prompt's index, so every prompt in a run
# gets a *distinct* id. Minting each independently from `now()` does not: the whole render
# happens inside a millisecond, so the first version handed every note prompt the same
# filename, and indexia — which refuses a duplicate id rather than overwriting — would have
# rejected the second thing you wrote.
_RUN_BASE = datetime.now(timezone.utc)


def _staging_id(index=0):
    dt = _RUN_BASE + timedelta(milliseconds=index)
    return dt.strftime("%Y%m%dT%H%M%S") + f"{dt.microsecond // 1000:03d}Z"


def _note_commit(index, source_ref=""):
    ref = f"\n   source_ref: {source_ref}" if source_ref else ""
    return (f"indexia/staging/{_staging_id(index)}.md — header then `---` then the body:\n"
            f"   title: <your claim, as a sentence>{ref}")


def build(signals, limit=None):
    """Turn signals into prompts, best first, capped at `limit`.

    Deduplicated by (source, ref): move 6 can surface a note as an orphan that move 7
    already surfaced as structural debt, and being asked twice about one note in one
    sitting reads as the tool being confused rather than emphatic. Highest-scoring signal
    for a given ref wins, since the list is sorted before the sweep.
    """
    by_source, seen = {}, set()
    for s in sorted(signals, key=lambda s: -s.score):
        key = (s.source, s.ref)
        if key in seen or (s.source, s.kind) not in _BUILDERS:
            continue
        seen.add(key)
        by_source.setdefault(s.source, []).append(s)

    # Round-robin across sources rather than a flat top-N by score. One source otherwise
    # takes every slot — measured: 8 papers against a limit of 7 left no room for the graph
    # or the posts at all, so the half of the brief about responding to *your own* work
    # silently vanished whenever you had been reading a lot.
    #
    # The rounds go in `SOURCES` order, not alphabetical, so when the limit falls mid-round
    # the leftover slot goes to indexia before perceptua before arxiv — the same priority
    # the rendered order states. Alphabetical happened to put arxiv first, which quietly
    # contradicted it.
    chosen, order = [], sorted(by_source, key=source_rank)
    while len(chosen) < (limit or len(seen)) and any(by_source.values()):
        for src in order:
            if by_source.get(src) and len(chosen) < (limit or len(seen)):
                chosen.append(by_source[src].pop(0))

    built = [_BUILDERS[(s.source, s.kind)](s, i)      # index → a unique staging id
             for i, s in enumerate(chosen)]
    built.sort(key=lambda p: p.rank)
    return built


# ---- arxiv → note -----------------------------------------------------------

def _arxiv(s, i):
    p = s.meta.get("paper", {})
    authors = p.get("authors") or []
    byline = authors[0].split()[-1] if authors else "anon"
    if len(authors) > 1:
        byline += " et al."
    year = (p.get("published") or "")[:4]
    ref = f"{byline} ({year}). {p.get('title', '')}"
    matched = ", ".join(f"`{m}`" for m in (p.get("matched") or [])[:6])
    # The prompt only exists because you marked it read, so it asks for the claim you *took*
    # from it — past tense, no instruction to go and read anything. Saying "read this" to
    # someone who just did is the tell that a tool is not tracking what you have done.
    read_on = (p.get("changed_at") or "")[:10]
    return Prompt(
        register="note", form="atomic claim",
        ask=("Write the one claim you took from this — a sentence that stands on its own, "
             "in your own words, with the paper as its source_ref."),
        because=(f"You marked it read{f' on {read_on}' if read_on else ''}"
                 + (f"; it came up on {matched}." if matched else ".")),
        signal=s, commit=_note_commit(i, ref))


# ---- indexia → whatever the move implies ------------------------------------

def _move4(s, i):
    n = len(s.meta.get("members") or [])
    return Prompt(
        register="note", form="hub note",
        ask=(f"Name it. These {n} notes are leaning on an idea you have never stated "
             "outright — write the note that states it, and bind them to it."),
        because="A tight semantic neighbourhood with no note at its centre (move 4).",
        signal=s, commit=_note_commit(i))


def _move5(s, i):
    return Prompt(
        register="essay", form="reconciliation",
        ask=("You corrected yourself here and kept both. Write the essay that holds them "
             "together — what the earlier claim got right, and what changed."),
        because="A ratified `inhibits` bind: a contradiction you made by hand (move 5).",
        signal=s, commit="indexia (essay, or a note if it lands short)")


def _orphan(s, i):
    return Prompt(
        register="note", form="continuation",
        ask=("Nothing binds to this note. Write the next one — the thought that follows "
             "from it — or say plainly why it is a dead end."),
        because="No ratified bind touches it (move 6, orphans).",
        signal=s, commit=_note_commit(i))


def _on_this_day(s, i):
    return Prompt(
        register="journal", form="dated entry",
        ask=("You wrote this on this day, in an earlier year. Read it and write today's "
             "entry against it — not a revision, a reply."),
        because="An anniversary (move 6, on this day).",
        signal=s, commit="a journal entry; commit to indexia if a claim falls out of it")


def _move7(s, i):
    return Prompt(
        register="essay", form="return",
        ask=("Go back to this note and write what came of it — the essay the subtree "
             "underneath it has been assembling without you."),
        because=s.detail,          # debt.prompt() already states the fact and stops
        signal=s, commit="indexia (essay); bind it back to the root when you commit")


# ---- perceptua → a response to your own earlier work ------------------------

def _post_response(s, i):
    post = s.meta.get("post", {})
    matched = ", ".join(f"`{m}`" for m in (s.meta.get("matched") or [])[:6])
    if s.meta.get("reason") == "overlap" and matched:
        because = (f"“{post.get('title', '')}” ({post.get('date')}) shares {matched} with "
                   "what you have been reading.")
    else:
        because = (f"“{post.get('title', '')}” ({post.get('date')}) is the earliest thing "
                   "on the site, and nothing has answered it.")
    return Prompt(
        register="verse", form="response",
        ask="Write the piece that answers this one.",
        because=because, signal=s,
        commit="perceptua — draft it there; `scripts/write.sh perceptua` opens a session")


_BUILDERS = {
    ("arxiv", "paper"): _arxiv,
    ("indexia", "move4"): _move4,
    ("indexia", "move5"): _move5,
    ("indexia", "orphan"): _orphan,
    ("indexia", "on-this-day"): _on_this_day,
    ("indexia", "move7"): _move7,
    ("perceptua", "post-response"): _post_response,
}
