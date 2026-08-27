---
name: eliciter-ui
description: Serve and use eliciter's local web UI — the reading queue with status, the writing prompts with their sources, ad-hoc arxiv search, and the handoff to a writing session. Use when the user asks to open/start/serve the eliciter UI, wants a visual or browser view of their queue or prompts, or asks to search arxiv for a specific paper and add it to the queue.
---

# The local UI

```bash
bash scripts/ui.sh            # http://127.0.0.1:8473
bash scripts/ui.sh --open     # and open a browser
bash scripts/ui.sh --port 8474
```

Stdlib `http.server`, one HTML file, no dependencies — consistent with the rest of the
project. Loopback only, Ctrl-C to stop, nothing daemonized.

**Do not background it and walk away.** It is a foreground server; if the user wants it
running while you do other things, tell them to start it in their own terminal. A forgotten
instance holds a stale view of a queue the CLI may have changed underneath it.

To stop one, resolve the pid — never `pkill -f scripts/ui.py`, which also matches the shell
invocation asking the question and will kill the caller (indexia's `lib.sh` documents this
hazard; it has happened here):

```bash
ps -eo pid,args | awk '/python3? .*ui\.py/ && !/awk/ {print $1}' | xargs -r kill
```

## Four tabs

- **Prompts** — every elicitation with its source, register, length and target project.
  "Write this →" opens the brief.
- **Queue** — unread papers, with score and the terms that matched. ✓ Read / ✗ Reject.
  Marking one read is also what makes it eligible for a writing prompt.
- **Decided** — read and rejected, with "↺ Back to queue" to undo.
- **Search** — ad-hoc arxiv results, with "+ Add to queue".

The header runs the three operations: **Sweep arxiv**, **Elicit prompts**, and a search box.

## Search vs sweep

They answer different questions and behave differently:

| | sweep | search |
|---|---|---|
| question | what came out this week in my categories | find me *that* paper |
| interest gate | applied — must match a stated interest | **not applied** |
| date window | `ELICITER_ARXIV_LOOKBACK_DAYS` | none |
| queue cap | respected; tops up to 10 | **bypassed** — a manual add is a decision |

So search is how the user gets a paper the profile would have filtered out, or re-adds one
they rejected. Plain words are wrapped in `all:`; a query using an arxiv field prefix
(`ti:`, `au:`, `abs:`, `cat:`) is passed through untouched.

## Session spawning is a copy, not a click

The browser cannot hand over a terminal, and `claude` is an interactive terminal program.
So "Write this →" shows the **full brief** and the exact command
(`cd <project> && bash scripts/write.sh <n>`) with a copy button. The user pastes it into a
terminal. That is the honest boundary — do not add a launch button that half-works.

## Safety posture

Loopback bind, no auth — indexia's posture, for the same reason. Two cheap protections
against a hostile page in the user's own browser:

- the **Host header** must be localhost (defeats DNS rebinding), and
- mutating requests need **`X-Eliciter: 1`**, which a cross-origin page cannot set without
  a CORS preflight this server does not answer.

If either is missing the request gets a 403. When testing endpoints with `curl`, pass
`-H 'X-Eliciter: 1'` on POSTs.

## It does not bypass the gate

The UI calls `corpus.connect()` like everything else — it reads indexia and cannot write to
it, and `scripts/test.sh` scans `webui.py` along with every other module to prove it. What
it writes is eliciter's own state: the reading queue, and the rendered prompts.
