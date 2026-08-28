# eliciter

Reads what you've been reading, and asks you to write.

It replaces the weekly Claude Desktop arxiv task with a local sweep, keeps a **reading
queue** of at most ten papers whose status you control, and turns that queue — together
with your indexia notes and perceptua posts — into numbered writing prompts. When you want
to write one, it opens a session in the project where the writing belongs.

It **cannot write to indexia or perceptua**. That is enforced by code and by tests, not by
convention. See [Read-only, structurally](#read-only-structurally).

```bash
make ui        # the local UI in the foreground at http://127.0.0.1:8473
make ui-up     # same, detached in the background          (make ui-down to stop)
make doctor    # is every source readable, and read-only?
make digest    # sweep arxiv, top up the queue        (~12s, weekly)
make queue     # what is waiting to be read
make elicit    # render writing prompts               → prompts/latest.md
make write     # list prompts; then scripts/write.sh <n>
make test      # the read-only gate must never regress
```

---

## The UI

```bash
bash scripts/ui.sh          # foreground, http://127.0.0.1:8473, Ctrl-C to stop
bash scripts/ui.sh run --open

bash scripts/ui.sh start    # same, detached — logs to ~/.eliciter/ui.log
bash scripts/ui.sh stop
bash scripts/ui.sh status
```

Four tabs — **Prompts** (with source, register and target project), **Queue** (unread, with
the terms that matched, one click to read/reject), **Decided** (with undo), **Search**
(ad-hoc arxiv, one click to add). The header runs the sweep, the elicit, and the search.

Stdlib `http.server`, one HTML file, no dependencies — the same zero-dependency posture as
the rest of the project. Loopback only, no auth.

**Backgroundable, and kept fresh rather than cached.** Every request re-reads
`state/papers.json` and `state/prompts.json` off disk — nothing is held in memory between
requests — and the page itself polls `/api/state` on an interval and on refocus. So `make
ui-up` and forgetting about the tab does not mean looking at a stale queue: a sweep or elicit
run from the CLI (or cron) shows up in the browser without a manual reload.

Two cheap protections against a hostile page in your own browser: the **Host header** must
be localhost (defeating DNS rebinding, where an attacker's domain resolves to 127.0.0.1 so
their page can reach this server), and mutating requests need **`X-Eliciter: 1`**, which a
cross-origin page cannot set without a CORS preflight this server does not answer.

**Session spawning is a copy, not a click.** A browser cannot hand over a terminal, and
`claude` is an interactive terminal program. "Write this →" shows the full brief and the
exact command with a copy button; you paste it into a terminal. That is the honest boundary
rather than a launch button that half-works.

The UI does not bypass the read-only gate — it calls `corpus.connect()` like everything
else, and `make test` scans `webui.py` to prove it.

---

## The five operations

### 1. Replace the weekly arxiv digest

`scripts/arxiv-digest.sh` sweeps the configured categories over a lookback window, ranks
against your interest profile, and tops up the queue. Seconds, no GPU, works with the
indexia container down. Run it weekly — by hand, by cron, or by a `/loop`.

The old Claude Desktop task can be turned off; nothing here depends on it. Its output lived
in a claude.ai conversation, which nothing on this machine could read — that is why this
exists.

### 2. At most ten papers, with status you control

The digest is not a fresh list each week. It is a **queue that persists**, capped at
`ELICITER_ARXIV_KEEP` (10), and a sweep tops it up rather than replacing it.

| status | meaning |
|---|---|
| `unread` | waiting. This is what the digest shows — what to read next. |
| `read` | you read it. Leaves the queue, freeing a slot, and **this is what prompts come from**. |
| `rejected` | not for you. Leaves the queue and **is never offered again**. |

Reading and writing are separate stages. A prompt asks for the claim you took from a paper,
and that claim only exists once you have read it — so marking a paper read is what turns it
into something to write. Read papers are offered most-recently-read first, so what you just
finished is what gets asked about.

```bash
bash scripts/papers.sh                    # what is waiting
bash scripts/papers.sh list --all         # including read and rejected
bash scripts/papers.sh read 2608.24545    # or by queue position: read 3
bash scripts/papers.sh reject 3
bash scripts/papers.sh reset 2608.24545
```

**Ad-hoc search** is the counterpart to the sweep, in the UI's Search tab. The sweep answers
"what came out this week in my categories"; search answers "find me *that* paper" — so it
applies no interest gate, no date window, and bypasses the queue cap, because a paper you
went and found is a decision rather than a suggestion. It is also how you re-add something
you rejected.

Papers resolve by arxiv id, unique prefix, or queue position — and by *version-stripped* id,
so a paper you rejected does not come back next week as `v2`. State is `state/papers.json`.

### 3. Read-only over your posts and notes

See [below](#read-only-structurally). This is the constraint the architecture is built
around, not a footnote.

### 4. Prompt short- and long-form responses

`scripts/elicit.sh` renders numbered prompts to `prompts/latest.md`, in three sections —
**your notes, then your writing, then your reading**. Every prompt is a request for a
**response** — to a note the corpus is leaning on, to a poem nothing has answered, to a
paper you have read.

| Source | Length | Register | The ask |
|---|---|---|---|
| move 4 — unnamed theme | short | note | name it; write the hub note |
| move 6 — orphan | short | note | the next note, or why it is a dead end |
| move 6 — on this day | long | journal | today's entry, as a reply |
| move 5 — ratified contradiction | long | essay | the essay that holds both together |
| move 7 — structural debt | long | essay | what came of the note the subtree hangs off |
| perceptua post | short | verse | the piece that answers this one |
| paper you have read | short | note | the one claim you took from it |

**The source decides the register.** Nothing decides it from content — a prompt never reads
an abstract and concludes it would make a good poem. That is indexia's spec §8.2 boundary
kept here: *the machine proposes the site, the human writes*. Every `ask` names a site and a
shape and stops. If one starts suggesting a thesis, that is a bug in `prompts.py`.

Sources are **interleaved, not ranked flat**. Measured: eight papers against a limit of
seven left no room for the graph or the posts at all, which silently deleted the half of the
brief about responding to your own work. So a run takes prompts from each source in turn.

**The order of those turns, and of the rendered sections, is `indexia` → `perceptua` →
`arxiv`** (`signals.SOURCES`). Your own material leads: an indexia or perceptua prompt
continues work only you can continue, while a paper prompt is available to anyone who read
the paper — so when you only get through the top of a run, the part that survives is the
part nobody else could write. Length has not gone; it orders prompts *within* a source, and
the summary line still says how many short and long you have. It is just no longer the
first thing you see.

### 5. Spawn a session where the writing belongs

```bash
bash scripts/write.sh          # list what is on offer
bash scripts/write.sh 3        # open a session on prompt 3, in the right project
bash scripts/write.sh indexia  # a session there, no particular prompt
bash scripts/write.sh 3 --print  # show the brief and command; launch nothing
```

It resolves the prompt, works out whether it belongs to **indexia** (note, essay, journal)
or **perceptua** (verse), and starts a Claude Code session in that directory seeded with a
brief: the ask, the material, where the result goes. Then it stops — the drafting and the
committing happen there, with that project's own tools.

Note prompts render the exact `indexia/staging/<id>.md` filename and header, so committing
is a copy plus indexia's `ingest-staging`. Ids are minted from one base instant plus the
prompt index, so no two prompts in a run collide.

---

## Read-only, structurally

Three layers, in `eliciterlib/readonly.py`:

1. **No write method exists.** `ReadOnlyGraph` has `query` and nothing else. It *wraps* a
   `notelib.Arcade` and keeps it private rather than subclassing, so `command`,
   `transaction` and `atomically` are not reachable by inheritance.
2. **Unknown attributes are refused loudly.** `db.command` raises `ReadOnlyViolation`
   naming the attempt, not an `AttributeError` a caller might catch and route around.
3. **The statement is checked.** `query` refuses SQL that is not a read — must begin
   `SELECT`/`MATCH`/`TRAVERSE`, no write keyword, checked with string literals stripped so
   a note body containing "delete" cannot trip it.

`ReadOnlyDir` is the same shape for files: `names()`, `read()`, path traversal refused,
nothing that writes.

**The project may only use the gate.** `tests/test_readonly.py` scans this project's own
source and fails if any module constructs an `Arcade`, calls `.command(`, or opens a source
project for writing. A perfect gate is worth nothing if `corpus.py` can quietly build its
own client — that scan already caught a real bypass in `doctor.py`. `make doctor` asserts
the same property at runtime against the live database.

`notelib` is still imported for its *read* helpers: `rows`, `first_row`, and the
`moveN_candidates` functions, all of which take a `db` and only call `.query()`.

---

## How papers are ranked, and why there is no embedding

Ranking is **term overlap against an interest profile**. No embeddings — a reversal from the
first build, made on measurement.

That version embedded every abstract with indexia's `mxbai-embed-large` and ranked by cosine
similarity. On this machine that model runs on CPU at roughly **0.6s per token**: 11.6s for
16 tokens, 52.7s for 80, over 180s for a full abstract. A weekly sweep was half an hour to
an hour. It also failed badly — a 32-abstract batch blew Ollama's timeout, and the killed
request left an orphaned `llama-server` at 315% CPU for an hour, quietly skewing everything
measured after it. What it bought was catching vocabulary mismatches inferred from a
four-note corpus. Certain cost, speculative benefit.

The replacement is instant, works from cold (state an interest before writing a note about
it), and is legible — the digest names the terms that matched, so you can see why a paper is
there. If the embedder ever gets a GPU, semantic ranking is worth revisiting as a *second*
pass over this one, not as the only pass.

```
score = Σ weight(matched terms) / √(distinct terms in abstract) − 2.0 × (excluded terms)
```

**`ELICITER_INTERESTS`** (weight 3.0) — a paper must match **at least one** to score at all.
Corpus words alone are not enough: every ML abstract shares vocabulary with any corpus about
learning agents, and without this gate the first run put an agent-payments security paper
and a histology model in the top five. Note terms (weight 0.4) only break ties among papers
already relevant.

**`ELICITER_EXCLUDE`** — the counterweight. Bag-of-words cannot tell your sense of a word
from the field's: *agents* means Levin's cells to you and LLM tool-callers to most of cs.AI
in 2026. Each excluded term costs points, so a passing mention survives and a paper *about*
the thing sinks. This moved "SWE Refactor Bench" from 8th to last without touching the top.

Tune by reading the matched terms in `digest/latest.md`; `--explain` prints the whole
profile, marking which terms are gates.

---

## Configuration

All in `.env` (copy `.env.example`). **No secret is duplicated** — the ArcadeDB password is
read from `indexia/docker/.env` at run time, so rotating it there is enough.

| Setting | Default | |
|---|---|---|
| `ELICITER_INTERESTS` | Levin-adjacent agency terms | the main dial; also the relevance gate |
| `ELICITER_EXCLUDE` | `benchmark, refactor, payment, …` | seeded from real noise; tune it |
| `ELICITER_ARXIV_KEEP` | `10` | queue cap |
| `ELICITER_ARXIV_CATEGORIES` | `cs.AI, cs.LG, cs.NE, q-bio.NC, nlin.AO` | |
| `ELICITER_ARXIV_LOOKBACK_DAYS` | `7` | |
| `ELICITER_ARXIV_MAX_RESULTS` | `300` | see below |
| `ELICITER_MAX_PROMPTS` | `7` | prompts per run |
| `ELICITER_UI_PORT` | `8473` | loopback only; 8420 is indexia's UI |

### Known limits

- **The sweep cap binds.** 300 papers over 7 days across 5 categories is under the real
  volume — cs.LG alone runs to several hundred a week. Results arrive newest-first, so a 300
  cap samples the most recent day or two rather than the week. Raise
  `ELICITER_ARXIV_MAX_RESULTS`; it costs one request and 3s of politeness delay per 100.
- **A tiny corpus limits the graph moves.** With 4 notes and no ratified binds, moves 5–7
  are structurally silent (move 7 needs 3+ descendants; move 5 needs a ratified `inhibits`).
  Wired and tested; they fire as the corpus grows.
- **Queue positions move.** They are positions in the *unread* list, so they shift as you
  mark things. Ids are stable; prefer them in anything you write down.

---

## Layout

```
eliciterlib/
  readonly.py  the gate — the only path to either source
  config.py    bootstrap: paths, indexia's docker/.env, sys.path for notelib
  status.py    the reading queue: unread / read / rejected; read papers → signals
  arxiv.py     the Atom sweep, ranking, and the queue rendering
  rank.py      the interest profile and scoring — no embeddings, and why
  corpus.py    indexia adapter: moves 4–7 → Signals
  posts.py     perceptua adapter: posts worth answering
  signals.py   Signal (a source noticed) and Prompt (an ask)
  prompts.py   Signal → Prompt; the register rule lives here and only here
  render.py    Prompt → markdown, plus the addressable index
  webui.py     the JSON API behind the UI
  ui.html      the whole front end, one file
scripts/
  doctor.sh  test.sh  arxiv-digest.sh  papers.sh  elicit.sh  write.sh  ui.sh
.claude/skills/
  reading-queue  elicit-writing  read-only-sources  eliciter-ui
```

Sources emit signals and know nothing about writing; `prompts.py` knows about writing and
nothing about where signals came from. That is what lets a fourth source be added without
touching prompt generation, and a register be retuned without touching any source.
