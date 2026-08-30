---
name: eliciter-ui
description: Serve and use eliciter's local web UI — the reading queue with status, the writing prompts with their sources, ad-hoc arxiv search, and the handoff to a writing session. Use when the user asks to open/start/serve the eliciter UI, wants a visual or browser view of their queue or prompts, or asks to search arxiv for a specific paper and add it to the queue.
---

# The local UI

```bash
bash scripts/ui.sh                  # foreground at http://127.0.0.1:8473, Ctrl-C to stop
bash scripts/ui.sh run --open       # foreground, and open a browser
bash scripts/ui.sh run --port 8474

bash scripts/ui.sh start            # detached; survives the shell — logs to ~/.eliciter/ui.log
bash scripts/ui.sh stop
bash scripts/ui.sh status
```

**The subcommand is not optional except for `run`.** `ui.sh --open` is a usage error, not a
foreground start with a browser — flags go after `run`/`start`. (`make ui`, `make ui-up`,
`make ui-down`, `make ui-status`, `make ui-restart` wrap these.)

Stdlib `http.server`, one HTML file, no dependencies — consistent with the rest of the
project. Loopback only by default.

## Backgrounding it is supported

`start` detaches with `setsid`, records a pid in `~/.eliciter/ui.pid`, and logs to
`~/.eliciter/ui.log`. Use it freely — **do not** launch the foreground `run` as a background
job of your own and walk away from it.

A backgrounded UI does **not** go stale: every request re-reads `state/papers.json` and
`state/prompts.json` off disk, and the page polls `/api/state` on an interval and on
refocus. A sweep or elicit run from the CLI shows up in an open tab without a reload.

Three things `start` guarantees, each of which was once a real failure:

- It **waits for the server to report its URL** before claiming success, and prints the URL
  the server itself printed. A start that dies — busy port, bad flag — is reported as a
  failure, with the log tail and a non-zero exit, instead of "started (pid N)".
- The server runs under `python3 -u`, so the log is actually written. Block-buffered, the
  banner sat in a buffer that never filled and `ui.log` stayed empty for days.
- `status`, and `start` when it declines to start a second one, report the URL of the
  **running process**, read from its own argv — not a guess from the flags of the command
  asking. The guess said `http://127.0.0.1:8473/` about a daemon started with `--port 8474`.

So when the user reports "it says it's running but the page won't load", trust `ui.sh
status` and check `~/.eliciter/ui.log`; both are now honest.

To stop one, use `bash scripts/ui.sh stop`. Never `pkill -f scripts/ui.py`, which also
matches the shell invocation asking the question and will kill the caller (indexia's
`lib.sh` documents this hazard; it has happened here). If you must resolve a pid by hand:

```bash
ps -eo pid,args | awk '/python3? .*ui\.py/ && !/awk/ {print $1}' | xargs -r kill
```

## --tailscale trades away the loopback guarantee

`bash scripts/ui.sh start --tailscale` binds this machine's Tailscale IP and serves HTTPS
with a tailscale-issued cert, so another tailnet device reaches the UI at a trusted
`https://` URL. **This is a deliberate widening, not a convenience** — the tailnet becomes
the trust boundary in place of loopback, and there is still no login. Do not pass it unless
the user asks for it. The exact URL comes from the tailnet at runtime, so it is in the log,
not predictable by the wrapper.

## Five tabs

- **Prompts** — every elicitation with its source, register, length and target project.
  The material is shown in place as prose (clipped, with "show the rest"), not hidden behind
  a disclosure triangle. "Write this →" opens the brief; "Open the source" opens the whole
  post, transcript, note or abstract in the reader.
- **Queue** — unread papers, with score and the terms that matched. ✓ Read / ✗ Reject.
  Marking one read is also what makes it eligible for a writing prompt.
- **Decided** — read and rejected, with "↺ Back to queue" to undo.
- **Sources** — everything eliciter can read, in four columns: recent indexia notes,
  perceptua posts, audua recordings (flagged when already offered), and the paper queue.
  Every row opens in the reader. This is the tab for reviewing material without going
  through a prompt.
- **Search** — ad-hoc arxiv results, with "+ Add to queue".

The header runs the two deterministic operations: **Sweep arxiv** and a search box.

**There is no "Elicit prompts" button, deliberately.** Prompts are written by a Claude
session that has read `state/material.json` (the `elicit-writing` skill) — a browser cannot
start one, the same reason "Write this →" hands over a command instead of launching. The
page shows prompts and opens their material; it does not make them. If the user wants new
prompts, the answer is "ask me for them here" — the skill gathers and judges in one move —
not a button. Nothing regenerates on a schedule either, so what the Prompts tab shows is
what was last deliberately written.

## Reading source material

Anything the page names, it can open. A prompt's own source, a **connection** in its margin
("shares `agent`, `exchange` with …"), a **member** of a cross-source confluence, and every
row in Sources all use the same reader: full text, plus the real path on disk (or the arxiv
URL), because the point is that the user can go the rest of the way themselves.

Two endpoints back it, both pure reads through the gate:

| | |
|---|---|
| `GET /api/sources` | the catalogue — metadata and a preview line, no bodies |
| `GET /api/source?source=&ref=` | one item in full, with `where` |

They are **deliberately not part of `/api/state`**, which the page polls every 20s. The
catalogue reads every post and transcript off disk; folding it into the poll would do that
three times a minute for a tab that may never be opened. If you add to the page, keep that
split — fetch source material on demand.

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

Under `--tailscale` the Host check widens to also accept the tailnet MagicDNS name, and
loopback is no longer the boundary. Both protections above only stop a hostile *page in a
browser*; a device on the tailnet can send `X-Eliciter: 1` directly, and there is still no
login. See the tradeoff spelled out in `eliciterlib/webui.py`.

## It does not bypass the gate

The UI calls `corpus.connect()` like everything else — it reads indexia and cannot write to
it, and `scripts/test.sh` scans `webui.py` along with every other module to prove it. What
it writes is eliciter's own state: the reading queue, and the rendered prompts.
