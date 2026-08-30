---
name: reading-queue
description: Sweep arxiv and choose the week's best papers for the user's reading queue, see what is waiting, and mark papers read or rejected. Use when the user asks what they should read, what is in the queue, to run or refresh the weekly arxiv sweep, or says they have read / are done with / want to reject a paper. For turning the queue into things to write use the elicit-writing skill.
---

# The reading queue

eliciter replaces the old weekly Claude Desktop arxiv task. A sweep pulls the week — **on a
real week, about 1160 papers** — and a persistent queue capped at `ELICITER_ARXIV_KEEP` (10)
holds what is worth reading. The queue is the point: a paper waits there until the user says
what became of it.

    unread    waiting; this is what the digest shows — what to read next
    read      they read it — leaves the queue, and this is what prompts are generated from
    rejected  not for them — leaves the queue and is never offered again

Marking a paper read is therefore not just bookkeeping: it is what turns the paper into
something to write about, since the claim a note wants only exists after the reading.

## You choose the papers

**There is no ranking that picks for you.** The sweep used to score every abstract against
the interest profile, drop anything matching no stated interest, and queue the top ten.
Measured on one real week: 1160 swept, **642 dropped without a human seeing a word of
them**, and the ten that survived were mostly LLM-agent papers, because `agent` is the
heaviest term in the profile and cs.AI says it constantly. `ELICITER_EXCLUDE` was an arms
race against that, and it was being lost slowly.

So the funnel is now two passes with you in the middle:

```
  ~1160 swept  →  sweep.sh titles   (every title, ~17k tokens)
               →  sweep.sh show …   (the ~40–60 worth opening, ~300 tokens each)
               →  state/picks.json  →  sweep.sh accept  →  the queue
```

### The loop

1. **`bash scripts/sweep.sh fetch`** — network, about 90 seconds, writes
   `state/candidates.json`. Papers already in the queue, read, or rejected are filtered out
   here, so a rejected paper can never come back.
2. **`bash scripts/sweep.sh titles`** — read it. All of it.
   - Grouped by primary category, **your configured categories first, smallest group
     first**. That ordering is doing real work: math.HO, physics.hist-ph, q-bio.NC and
     nlin.AO run to three or five papers a week and are where the foundations-of-maths and
     basal-cognition material actually appears. **Read those exhaustively.** cs.AI (≈290)
     and cs.LG (≈330) are the firehose — skim, and use `--top 40` to cap them.
   - The score is term overlap. **It orders; it does not filter.** A 0.00 is not a verdict:
     "Reflections on the Millennium Problems" scored 0.00 on a week where it was one of the
     more plausible papers in the sweep. Read past the point where the scores go quiet.
3. **`bash scripts/sweep.sh show <id> <id> …`** — full abstracts for the shortlist. Be
   generous here; this is the cheap step relative to queuing the wrong paper.
4. **Write `state/picks.json`**, best first — the order is your ranking, and the cap decides
   where the line falls.
5. **`bash scripts/sweep.sh accept`** — validates every id against the candidate set, fills
   the free slots in that order, reports anything that did not fit, and rewrites
   `digest/latest.md`.

```json
{"picks": [
  {"id": "2608.22572v2",
   "why": "One line: what this is, and why it is for them and not the four hundred others."}
]}
```

`why` is required in practice even though the validator does not enforce it — it is printed
in bold above each paper in `digest/latest.md`, and it is the thing that makes the queue
trustworthy. The overlap score rides underneath as provenance, not as the reason.

### What to pick

The user's interests are in `state/candidates.json` (`interests`, `exclude`) and in
`sweep.sh explain`. Read them, then use judgement — that is the whole point of your being
here rather than a scorer.

- **`agency`, `agents`, `alignment` mean Levin and basal cognition, not cs.AI.** A paper
  about LLM tool-calling, agent harnesses, GUI agents or multi-agent LLM frameworks is not
  what they mean, however high it scores. This is the single most common failure.
- Prefer papers that would **change what they think**, not ones that confirm the profile.
  Foundations of mathematics, philosophy of science, collective behaviour in real
  organisms, morphogenesis, self-organization, causal emergence.
- A paper that matches no stated interest but is obviously theirs is a **good** pick. That
  case is the reason you are reading the whole list.
- **Fill the free slots, no more.** `free_slots` is in the candidate file. If only three
  slots are free, pick the three best rather than ten and let seven overflow.
- If the week is genuinely thin, say so and queue fewer. A padded queue is worse than a
  short one — every slot taken by a mediocre paper is a slot the next sweep cannot use.

## Commands

```bash
bash scripts/sweep.sh fetch                 # sweep the week → state/candidates.json
bash scripts/sweep.sh fetch --lookback 30   # wider window, after a gap
bash scripts/sweep.sh titles                # every candidate, grouped
bash scripts/sweep.sh titles --top 40       # cap each category; small venues stay whole
bash scripts/sweep.sh show <id> [<id>…]     # full abstracts
bash scripts/sweep.sh accept                # picks.json → the queue  (--dry-run to preview)
bash scripts/sweep.sh explain               # what the interest profile contains

bash scripts/papers.sh                      # what is waiting
bash scripts/papers.sh list --all           # including read and rejected
bash scripts/papers.sh read 2608.24545      # or by queue position: read 3
bash scripts/papers.sh reject 3
bash scripts/papers.sh reset 2608.24545     # back to unread
```

For ad-hoc search ("find me that paper") rather than the weekly sweep, use the UI's Search
tab — see the `eliciter-ui` skill. Search ignores the queue cap, so it is also how a
rejected paper gets re-added.

Papers can be named by arxiv id, a unique prefix, or their **queue position**. Positions
move as the queue changes, so prefer the id when writing anything down.

The rendered queue is `digest/latest.md`; the state is `state/papers.json`. The UI shows the
same queue with one-click read/reject, but **cannot sweep** — choosing papers is a
judgement, and a browser cannot start a session.

## When the user says they have read something

Mark it. That is the whole feedback loop — a read paper frees a slot for the next sweep and
*starts* being prompt material, so the next gather hands it to a session, which will ask for
the claim they took from it. If they mention a paper by title rather than id, run
`bash scripts/papers.sh list` and match it yourself rather than asking them for the id.

If they say a paper was not interesting or not relevant, that is `reject`, not `read` —
rejection is permanent and is what keeps the same off-target paper from returning.

## Tuning what surfaces

`ELICITER_ARXIV_CATEGORIES` is now the setting that matters most, because it decides both
what is swept and what leads the grouped list. `ELICITER_INTERESTS` and `ELICITER_EXCLUDE`
still weight the ordering, but **they no longer decide what you get to see**, so a complaint
about the queue is no longer fixed by editing them — it is fixed by picking better. Treat an
excluded term as a hint about taste, not an instruction.

## Boundaries

The sweep needs outbound HTTPS and nothing else — no GPU, no Ollama, and it works with the
indexia container down (the corpus only enriches the ordering). eliciter never writes to
indexia or perceptua; see the `read-only-sources` skill.
