---
name: reading-queue
description: Manage the eliciter arxiv reading queue — sweep for new papers, see what is waiting, and mark papers read or rejected. Use when the user asks what they should read, what is in the queue, to run or refresh the weekly arxiv sweep, or says they have read / are done with / want to reject a paper. For turning the queue into things to write use the elicit-writing skill.
---

# The reading queue

eliciter replaces the old weekly Claude Desktop arxiv task. A sweep ranks the week's papers
against the user's interest profile and **tops up a persistent queue** capped at
`ELICITER_ARXIV_KEEP` (10). The queue is the point: a paper waits there until the user says
what became of it.

    unread    waiting; this is what the digest shows — what to read next
    read      they read it — leaves the queue, and this is what prompts are generated from
    rejected  not for them — leaves the queue and is never offered again

Marking a paper read is therefore not just bookkeeping: it is what turns the paper into
something to write about, since the claim a note wants only exists after the reading. If the
user wants a writing prompt for a paper, mark it read — see the `elicit-writing` skill.

## Commands

```bash
bash scripts/arxiv-digest.sh              # sweep and top up the queue (~12s)
bash scripts/arxiv-digest.sh --explain    # show the interest profile, sweep nothing
bash scripts/arxiv-digest.sh --dry-run    # sweep and rank, change nothing
bash scripts/arxiv-digest.sh --lookback 30  # wider window, after a gap

bash scripts/papers.sh                    # what is waiting
bash scripts/papers.sh list --all         # including read and rejected
bash scripts/papers.sh read 2608.24545    # or by queue position: read 3
bash scripts/papers.sh reject 3
bash scripts/papers.sh reset 2608.24545   # back to unread
```

For ad-hoc search ("find me that paper") rather than the weekly sweep, use the UI's Search
tab — see the `eliciter-ui` skill. Search ignores the interest gate and the queue cap, so it
is also how a rejected paper gets re-added.

Papers can be named by arxiv id, a unique prefix, or their **queue position**. Positions
move as the queue changes, so prefer the id when writing anything down.

The rendered queue is `digest/latest.md`; the state is `state/papers.json`. The UI
(`bash scripts/ui.sh`) shows the same queue with one-click read/reject.

## When the user says they have read something

Mark it. That is the whole feedback loop — a read paper frees a slot for the next sweep and
*starts* generating prompts, so the next `scripts/elicit.sh` will ask them for the claim
they took from it. If they mention a paper by title rather than id, run
`bash scripts/papers.sh list` and match it yourself rather than asking them for the id.

If they say a paper was not interesting or not relevant, that is `reject`, not `read` —
rejection is permanent and is what keeps the same off-target paper from returning every
week.

## Tuning what surfaces

Relevance is term overlap, and the digest prints the terms that matched under each title.
That is the feedback loop — read the matched terms, then edit `.env`:

- `ELICITER_INTERESTS` — a paper must match at least one of these to appear at all.
- `ELICITER_EXCLUDE` — each excluded term an abstract contains costs it points.

If the user complains that the queue is full of LLM-tooling papers, the fix is almost always
`ELICITER_EXCLUDE`, because *agents* means something different to them than to cs.AI.
Confirm with `--explain` before and after.

## Boundaries

The sweep needs outbound HTTPS and nothing else — no GPU, no Ollama, and it works with the
indexia container down (the corpus only enriches the profile). eliciter never writes to
indexia or perceptua; see the `read-only-sources` skill.
