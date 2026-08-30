---
name: elicit-writing
description: Generate writing prompts from the user's reading queue, indexia notes, perceptua posts, and audua run recordings, and open a writing session in the right project. Use when the user asks what they should write, wants prompts or elicitations, asks to respond to a paper, a recorded run, or their own earlier work, or says they want to start writing / drafting / editing in indexia or perceptua. For managing which papers are queued use the reading-queue skill.
---

# Eliciting writing

`scripts/elicit.sh` reads four sources and renders **numbered prompts** to
`prompts/latest.md`. Each prompt is a request for a *response*: to a note the corpus is
leaning on, to a poem nothing has answered, to a run they recorded and never wrote up, to a
paper they have read.

```bash
bash scripts/elicit.sh              # all sources → prompts/latest.md
bash scripts/elicit.sh --stdout     # print instead of writing
bash scripts/elicit.sh --no-papers  # graph + posts only, no read papers
bash scripts/elicit.sh --limit 3
```

The UI (`bash scripts/ui.sh`) does the same on a button, and its Prompts tab shows each
prompt with its source and target project — see the `eliciter-ui` skill.

It touches no network — sweeping is the `reading-queue` skill's job — and writes nothing to
indexia, perceptua, or audua.

## What produces a prompt

Listed in the order a run presents them.

| Source | Register | Ask |
|---|---|---|
| move 4 — unnamed theme | note (short) | name it; write the hub note |
| move 6 — orphan | note (short) | write the next note, or say why it is a dead end |
| move 6 — on this day | journal (long) | today's entry, as a reply to the old one |
| move 5 — ratified contradiction | essay (long) | the essay that holds both together |
| move 7 — structural debt | essay (long) | what came of the note the subtree hangs off |
| perceptua post | verse (short) | the piece that answers this one |
| audua session, unseen | journal (long) | pick an open thread and follow it up, or respond to the run generally |
| paper marked **read** | note (short) | the one claim they took from it |

**audua sessions are offered at most once**, not tracked with a status the user sets. A
session that has appeared in a rendered run (not a `--stdout` preview) is retired in
`state/audua.json` and does not come back — there is no `audua.sh mark` command, by design;
see `eliciterlib/audua.py`.

**Papers prompt once they are read, not while they are queued.** An unread paper is a
reading suggestion and the digest already is one; the claim a note wants only exists after
the reading. So if the user wants prompts for a paper, the move is to mark it read
(`bash scripts/papers.sh read <id>`, or the ✓ in the UI) — see the `reading-queue` skill.
Read papers are offered most-recently-read first.

**The source decides the register.** Nothing decides it from content — a prompt never reads
an abstract and concludes it would make a good poem. The machine proposes the site; the
human writes. If a prompt starts suggesting a thesis, that is a bug in
`eliciterlib/prompts.py`.

Sources are interleaved rather than ranked flat, so one source cannot take every slot and
crowd out the rest. The order — of the turns and of the rendered sections — is **indexia →
perceptua → audua → arxiv** (`signals.SOURCES`): the user's own material leads, because
those prompts continue work only they can continue, while a paper prompt is available to
anyone who read the paper. audua sits after perceptua: a published poem is finished material
asking for a reply, where a recording is still raw and unreviewed. Length (short/long)
orders prompts within a source and is reported as a count at the top; it is no longer the
top-level structure.

## Opening a writing session

```bash
bash scripts/write.sh          # list what is on offer
bash scripts/write.sh 3        # open a session on prompt 3, in the right project
bash scripts/write.sh indexia  # a session there with no particular prompt
bash scripts/write.sh 3 --print  # show the brief and the command, launch nothing
```

`write.sh` resolves the prompt, works out whether it belongs to indexia (notes, essays,
journal) or perceptua (verse), and starts a Claude Code session in that directory seeded
with a brief. The brief states the ask, the material and where the result goes — and stops.

**Do not draft the writing here.** eliciter's job ends at the prompt. The writing happens in
the target project, in a session with that project's own tools and skills, and the claim
should be the user's. If the user asks you to write the note for them, ask what they
actually think first.

## Committing

eliciter cannot commit anything — that is enforced, not conventional. Note prompts render
the exact `indexia/staging/<id>.md` filename and header to write into, so committing is a
copy followed by indexia's own `ingest-staging`. Verse goes to `perceptua/_posts/`. Both
are acts the user performs in those projects.
