---
name: elicit-writing
description: Read the user's gathered source material and write their numbered writing prompts, then open a writing session in the right project. Use when the user asks what they should write, wants prompts or elicitations, asks to respond to a paper, a recorded run, or their own earlier work, or says they want to start writing / drafting / editing in indexia or perceptua. For managing which papers are queued use the reading-queue skill.
---

# Eliciting writing

**You write the prompts. There is no prompt generator any more.**

Until 2026-08-30 `prompts.py` turned each source's signals into an ask by rule, and a
cross-source pass found "what recurs" by term overlap. Both are gone. The rules were legible
and the prompts were mediocre: bag-of-words cannot tell the user's sense of a word from the
field's, so the strongest cross-source theme it ever proposed was `mathematics · hills ·
road` across a pantoum and a run recording — one is prosody, one is a hill on a five-mile
run. What it needed was a reader, so the split moved — **gathering is a script, judging is
you.**

```
                        one move, when the user asks for it
        ┌──────────────────────────────────────────────────────────┐
        │  scripts/gather.sh → state/material.json → YOU → state/prompts.json
        └──────────────────────────────────────────────────────────┘
                                                         ↓
                                            scripts/prompts.sh render
                                                         ↓
                                   prompts/latest.md  +  scripts/write.sh <n>
```

## The loop

**Gathering and judging are one move.** Nothing runs on a schedule — there is no cron job,
deliberately — so a run of prompts stays exactly as it is until the user asks for new ones.
When they do, you do the whole thing: read the sources *now*, then judge what you read. An
old `state/material.json` is never a reason to skip the gather; a snapshot from Tuesday
would mean judging Friday against a corpus that has moved.

1. **Ask before replacing a run that is still standing.** If `prompts/latest.md` exists and
   the user has not clearly asked for a fresh set — "regenerate", "new prompts", "start
   over" — show them what is currently on offer (`bash scripts/prompts.sh show`) and check
   before going further. Rendering overwrites `prompts/latest.md`, overwrites the dated file
   if it is the same day, and **retires every audua session the new prompts cite**. That is
   fine when it is wanted and annoying when it is not, and prompts they have not acted on
   yet are the whole point of the file.
2. **Gather.** `bash scripts/gather.sh`. Always, as part of the same move. It is a read —
   nothing is retired, nothing is decided, and it takes a couple of seconds.
3. **Read `state/material.json`.** All of it. ~110KB; it is meant to be read, not grepped.
   If a source shows up under `unavailable` (the indexia container is often down), say so
   plainly rather than quietly writing a run with a corpus missing.
4. **Write `state/prompts.json`** — schema below.
5. **`bash scripts/prompts.sh check`** until it passes, then **`bash scripts/prompts.sh
   render`**. Never hand-write `prompts/latest.md`; it is derived, and `render` is also what
   retires the audua sessions you used.
6. Show the user the numbered list and stop. Opening one is a separate move, below.

## What is in the material

| key | what it is |
|---|---|
| `notes.flagged` | indexia moves 4–7: unnamed themes, ratified contradictions, orphans, anniversaries, structural debt. Each has `text` — the actual note prose, not a label. |
| `notes.recent` | the last 25 notes in full. What they have been thinking about lately. |
| `posts` | **every** perceptua post, full text. `adjacent_to_current_reading` is a term-overlap hint from `rank.py` — a hint, not a shortlist. Ignore it when you disagree. |
| `sessions` | audua run recordings. Unseen ones carry the whole `summary.md`; ones already offered carry `intro` only, as context. |
| `papers.read` | papers marked read, with abstracts. **These are the ones that prompt.** |
| `papers.waiting` | the unread queue — context on where their attention is going, not prompt material. |
| `interests` / `exclude` | what they have said they care about, independent of what they have written. |
| `previous_prompts` | **what you asked last time. Do not ask it again.** Because nothing regenerates on a schedule, a standing run may be days old — treat these as things the user has had in front of them and not yet written. |

## The rule that has not changed

**The machine proposes the site; the human writes.** Every `ask` names a site and a shape
and then stops. None of them says what to argue, what a paper implies, or what a poem
should be about.

This is indexia's spec §8.2 boundary, and it is the whole reason the project exists. You
have now read the corpus, so you are *more* able to violate it than the old rule-based
generator was, and the temptation is real: you will see the connection and want to state
it. Don't. Name where the writing goes and what shape it takes, and leave the claim to
them. **If a prompt contains a thesis, it is wrong** — even a good thesis, even an obvious
one.

Concretely:

- ✅ "You corrected yourself here and kept both. Write the essay that holds them together."
- ❌ "Write the essay showing that agency is really about boundary maintenance."
- ✅ "These four notes lean on an idea you have never stated outright — write the note that
  states it."
- ❌ "Write the note that says intelligence is bounded by learnable novelty."

`because` is the same discipline: say what you observed and when, not what it means.
*"Recorded 2026-08-27; nothing has answered it"* — not *"this recording anticipates your
later note"*.

**And say so when there is nothing.** A quiet corpus is a real answer. Four thin prompts
padding a run to seven is worse than two good ones, and much worse than saying "the queue
is clear and nothing is owed". Write fewer.

## What makes a prompt worth writing

This is the judgement the old pipeline could not make. Aim for **5–7** prompts.

- **Cross-source prompts are the point of reading everything.** A prompt whose `sources`
  name a note *and* a recording *and* a paper is the one thing no single source could have
  produced. Lead with them when they are real.
- **Real means the connection survives reading both.** The old version proposed
  `mathematics · hills · road` across a pantoum and a run recording because the words
  co-occurred. You can see that one is prosody and one is a hill on a five-mile run. If the
  overlap is a pun, do not make it a prompt — silently drop it, and do not write a prompt
  that "asks whether the connection is real". That was the old version apologising for
  itself.
- **Prefer live over structural.** A note from last week that the recordings keep circling
  beats a technically-orphaned note from June that nobody misses.
- **Don't repeat `previous_prompts`.** If something genuinely still needs writing, ask it
  from a different angle and say in `because` that it is still open.

## Registers, and what routes where

The register is yours to choose — this is the one rule that genuinely changed, and it
changed because deriving it from the source was always crude. A recording is not
automatically a journal entry. But the *closed set* is fixed, because `write.sh` routes on
it and `render.validate` rejects anything else. `length` and `project` are derived from it;
never write them yourself.

| register | length | goes to | for |
|---|---|---|---|
| `note` | short | indexia | one claim, standing alone, in their own words |
| `essay` | long | indexia | something argued, holding several things together |
| `journal` | long | indexia | dated, personal, against a day or a recording |
| `verse` | short | perceptua | a poem — almost always a response to another poem |

Two standing conventions, both still true:

- **Papers prompt once they are marked read, never while queued.** A prompt asks for the
  claim they took from something, which does not exist until they have read it. Never write
  a prompt about `papers.waiting`.
- **An audua session is offered once.** `prompts.sh render` retires every session your
  prompts cite. A session you read and chose not to use stays available for next time — so
  do not cite one just to use it up.

## The schema

Write `state/prompts.json`. Order is preserved exactly: put the run in the order you want
it read.

```json
{
  "prompts": [
    {
      "register": "essay",
      "form": "reconciliation",
      "title": "short label, shown as the heading",
      "ask": "The imperative. One or two sentences. A site and a shape, then stop.",
      "because": "What you observed that made this surface now. Past tense, factual.",
      "material": "optional — the lines worth quoting into the prompt",
      "commit": "optional — where it goes. A destination, not a command: the `write.sh <n>` line is rendered for you. A note gets an indexia staging id automatically.",
      "sources": [
        {"source": "indexia", "ref": "20260807T194938347Z",
         "title": "An agent's border is determined by the size of its goals",
         "why": "optional — what this one contributes"}
      ]
    }
  ]
}
```

`sources` is **required and must be real.** Every `ref` has to be one you saw in
`state/material.json` — a note id, a post filename, an audua stem, an arxiv id. They are
what the UI opens and what `write.sh` puts in the brief, so an invented ref is a citation to
nothing. `render.validate` checks the `source` names but it cannot check that a ref exists;
that one is on you.

Derived for you, so leave them out: `n`, `length`, `project`, and a note's staging id.

## Opening a writing session

```bash
bash scripts/write.sh          # list what is on offer
bash scripts/write.sh 3        # open a session on prompt 3, in the right project
bash scripts/write.sh indexia  # a session there with no particular prompt
bash scripts/write.sh 3 --print  # show the brief and the command, launch nothing
```

`write.sh` resolves the prompt, works out whether it belongs to indexia (notes, essays,
journal) or perceptua (verse), and starts a Claude Code session there seeded with a brief:
the ask, every source with its ref, and where the result goes. That session has *not* read
the corpus — you did — which is why naming the sources properly matters.

**Do not draft the writing here.** eliciter's job ends at the prompt. The writing happens in
the target project, in a session with that project's own tools and skills, and the claim
should be the user's. If the user asks you to write the note for them, ask what they
actually think first.

## Committing

eliciter cannot commit anything — that is enforced, not conventional. Note prompts carry the
exact `indexia/staging/<id>.md` filename and header to write into, so committing is a copy
followed by indexia's own `ingest-staging`. Verse goes to `perceptua/_posts/`. Both are acts
the user performs in those projects.
