# eliciter

Reads what you've been reading, and asks you to write.

It replaces the weekly Claude Desktop arxiv task with a local sweep, keeps a **reading
queue** of at most ten papers whose status you control, and turns that queue — together
with your indexia notes, perceptua posts, and audua run recordings — into numbered writing
prompts. **A script gathers; a Claude session judges.** Ask for prompts and everything the
sources have to say is collected into one file, then read and turned into prompts by a
session — not by a rule. Nothing runs on a schedule, so a run of prompts stays exactly as it
is until you decide to replace it. When you want to write one, it opens a session in the
project where the writing belongs.

It **cannot write to indexia, perceptua, or audua**. That is enforced by code and by tests,
not by convention. See [Read-only, structurally](#read-only-structurally).

```bash
make ui        # the local UI in the foreground at http://127.0.0.1:8473
make ui-up     # same, detached in the background          (make ui-down to stop)
make doctor    # every source readable and read-only; is the material fresh?
make sweep     # sweep arxiv               → state/candidates.json (~90s, weekly)
make queue     # what is waiting to be read
make gather    # read every source            → state/material.json  (the skill does this)
make prompts   # render what a session wrote  → prompts/latest.md
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

Five tabs — **Prompts** (with source, register and target project, the material shown in
place, and one click to open any source it names), **Queue** (unread, with the terms that
matched, one click to read/reject), **Decided** (with undo), **Sources** (everything
eliciter can read — every note, post, recording and paper — each openable in the reader),
**Search** (ad-hoc arxiv, one click to add). The header runs the sweep, the elicit, and the
search.

**Every source a prompt names is one click away.** A prompt's material is rendered as prose
rather than hidden behind a disclosure triangle, "Open the source" pulls up the whole post
or transcript or note in a reader, and the same is true of a connection in the margin or a
member of a cross-source theme — so checking whether a connection is real never means
leaving the page. The reader shows the file's path, because the point is that you can go the
rest of the way yourself. `/api/sources` and `/api/source` serve that, and are fetched only
when asked for: `/api/state` polls, and reading seventeen poems three times a minute to keep
an unopened tab warm is the wrong trade.

Stdlib `http.server`, one HTML file, no dependencies — the same zero-dependency posture as
the rest of the project. Loopback only, no auth, by default.

`bash scripts/ui.sh start --tailscale` widens that deliberately: binds this machine's
Tailscale IP and serves HTTPS with a tailscale-issued cert, so another device on the tailnet
can reach the UI at a trusted `https://` URL. This trades away the loopback guarantee below —
the tailnet becomes the trust boundary instead, with still no login. See the tradeoff spelled
out in `eliciterlib/webui.py`.

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

### 1. Replace the weekly arxiv digest, and read the whole week

`scripts/sweep.sh fetch` pulls everything submitted to the configured categories over the
lookback window — **on a real week, 1160 papers** — and writes them to
`state/candidates.json`. Then a session reads them and chooses. No GPU, works with the
indexia container down, about ninety seconds of network.

The old Claude Desktop task can be turned off; nothing here depends on it. Its output lived
in a claude.ai conversation, which nothing on this machine could read — that is why this
exists.

**The ranking used to choose, and it chose badly.** Every abstract was scored against the
interest profile, anything matching no *stated* interest was dropped, and the top ten were
queued. Measured on one week: 1160 swept, **642 dropped without a human seeing a word**, and
the survivors were mostly LLM-agent papers, because `agent` is the heaviest term in the
profile and cs.AI says it constantly. `ELICITER_EXCLUDE` was an arms race against that, and
it was being lost slowly. Two different failures — one of recall, one of precision — and
neither is fixable by tuning a bag of words.

Both dissolve with a reader in the middle, so the funnel is now two passes:

```
  ~1160 swept  →  sweep.sh titles   every title, grouped     (~17k tokens)
               →  sweep.sh show …   the ~40 worth opening    (~300 tokens each)
               →  state/picks.json  →  sweep.sh accept  →  the queue
```

**Nothing is dropped for scoring badly.** Term overlap survives as the *ordering* of a long
list — `rank.overlap`, the same profile without the gate — so likely material is near the
top and a 0.00 still appears. That matters: on the first week under this design a Trefethen
essay on the Millennium Problems scored exactly 0.00, and the old gate would have deleted it
unseen.

The titles are **grouped by category, your configured ones first, smallest group first**,
which is the part that makes 1160 readable. math.HO ran to 3 papers that week,
physics.hist-ph 4, q-bio.NC 5, nlin.AO 5 — the specialised venues, short enough to read
exhaustively and where the foundations-of-mathematics and basal-cognition material actually
is. cs.AI (288) and cs.LG (330) are the firehose; `--top 40` caps them.

Each queued paper then carries a **`why`** — one line on why this paper and not the other
four hundred — printed above its abstract in `digest/latest.md`. The overlap score rides
underneath as provenance. Before, the score *was* the reason, which is what made the queue
hard to trust.

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
applies no date window and bypasses the queue cap, because a paper you went and found is a
decision rather than a suggestion. It is also how you re-add something
you rejected.

Papers resolve by arxiv id, unique prefix, or queue position — and by *version-stripped* id,
so a paper you rejected does not come back next week as `v2`. State is `state/papers.json`.

### 3. Read-only over your posts, notes, and recordings

See [below](#read-only-structurally). This is the constraint the architecture is built
around, not a footnote.

### 4. Prompt short- and long-form responses

This is the half that stopped being a script on 2026-08-30, and the reason is worth stating
plainly because the old design was a reasonable idea that did not work.

`prompts.py` turned each source's signals into an ask by rule — *the source decides the
register* — and a cross-source pass over the same signals found "what recurs" by term
overlap. Both were legible, fast, and produced mediocre prompts. Bag-of-words cannot tell your sense of a word
from the field's, so the strongest theme it ever proposed was `mathematics · hills · road`
across a pantoum and a run recording: one is prosody, one is a hill on a five-mile run, and
no amount of stopword tuning distinguishes them. Worse, it could not see the connections
that *were* there — a note about the observer in information theory and a recording about
what wearing a microphone did to a run share no vocabulary at all.

So the split moved. **Gathering is a script; judging is a session.**

```
scripts/gather.sh  →  state/material.json  →  a Claude session  →  state/prompts.json
                                                                        ↓
                                                        scripts/prompts.sh render
                                                                        ↓
                                              prompts/latest.md  +  scripts/write.sh <n>
```

`gather.sh` reaches into all four corpora through the read-only gate and writes down the
*whole* of what is there — the note prose behind each flagged move, every post in full,
unseen session summaries entire, the abstracts of papers you have read, your stated
interests, and **the prompts from last time so a session does not repeat itself**. It
scores nothing and asks nothing. Around 90KB; it is meant to be read.

The `elicit-writing` skill is where the editorial rules now live, and they are the same
rules `prompts.py` held:

- **The machine proposes the site; the human writes** — indexia's spec §8.2 boundary. Every
  ask names a site and a shape and stops. A session has now read the corpus, so it is
  *more* able to state the thesis than the old generator was, and is told at length not to.
- **The four registers are a closed set** — `note`, `verse`, `essay`, `journal` — because
  `write.sh` routes on them. `length` and `project` are *derived* from the register in
  `render.validate`, never chosen, so there is no way to ask for verse and route to indexia.
  Which register a thing wants is now a judgement rather than a property of its source: a
  recording is not automatically a journal entry.
- **Papers prompt once marked read, never while queued.** A prompt asks for the claim you
  took from something, which does not exist until you have read it.
- **audua sessions are offered at most once.** `state/audua.json` remembers which have
  appeared in a rendered run; `prompts.sh render` is what retires them, at the moment the
  file is actually written — a gather you ran to see what was there does not burn the queue.
- **Say when there is nothing.** Four thin prompts padding a run to seven is worse than two
  good ones, and much worse than "the queue is clear and nothing is owed". There is no
  longer a target count to hit.

Every prompt cites its `sources` — one or several — and that list is mandatory: a prompt
with no provenance is the machine making something up. A prompt drawing on more than one
corpus heads the file under *Across your sources*, which is what replaced the old
`confluence` special case; everything else falls under its single source, in the order
**indexia → perceptua → audua → arxiv**. Your own material leads, because those prompts
continue work only you can continue while a paper prompt is available to anyone who read the
paper.

**Term overlap did not disappear — it moved back to the one job it was good at.** `rank.py`
still decides which of ~300 swept abstracts reach the reading queue and which post is
nearest to current reading, because those are shortlists over material nobody has read yet
and a cheap explicit filter beats no filter. It just no longer decides what you should
write.

#### What is checked, and what is trusted

`state/prompts.json` is the one artifact a session produces; `prompts/latest.md` is rendered
from it and never written by hand. That ordering is what keeps the numbers honest — the
numbers are the interface (`scripts/write.sh 3`), and two artifacts written independently
drift.

`render.validate` refuses a register outside the four, a prompt with no `sources`, a source
name that is not a real corpus, and a missing ask or title; it assigns `n` by position and
derives `length`, `project`, and a note's unique `indexia/staging/<id>.md` filename. What it
cannot check is that a `ref` exists — that one is on the session, and it is told so.

```bash
bash scripts/prompts.sh check     # validate, write nothing
bash scripts/prompts.sh render    # → prompts/latest.md + the dated copy; retires audua sessions
```

#### Gathering and judging are one move

There is **no scheduled run**, deliberately. Asking a session for prompts gathers first and
then judges what it gathered, in one go — so the material behind a run was read at the
moment it was judged, rather than at seven that morning.

The alternative was tried for about an hour: cron gathering every morning, prompts written
whenever you got to them. It splits a single act across a day for no benefit. Gathering is
two seconds and touches nothing, so pre-fetching buys nothing; and a snapshot taken hours
before the judgement is strictly worse than one taken at the moment of it. What it *cost*
was the property that matters most here — **a run of prompts stays put until you decide to
replace it.** Prompts you have read and not yet acted on are the whole point of the file,
and nothing should rebuild them underneath you.

So `make gather` exists for looking at what the sources currently say (`--stdout` writes
nothing), and is not a step you normally take yourself. Replacing a standing run is a
deliberate act: the skill checks first unless you have plainly asked for a fresh set, since
rendering overwrites `prompts/latest.md` and retires every audua session the new prompts
cite.

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

`ReadOnlyDir` is the same shape for files: `names()`, `dirs()`, `read()`, path traversal
refused, nothing that writes. `posts_dir()` gates perceptua's `_posts/`; `audua_dir()` gates
audua's per-session output the same way.

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
  readonly.py  the gate — the only path to any source
  config.py    bootstrap: paths, indexia's docker/.env, sys.path for notelib
  status.py    the reading queue: unread / read / rejected; read papers → signals
  arxiv.py     the Atom sweep, ranking, and the queue rendering
  rank.py      the interest profile — orders the sweep, no longer gates it
  candidates.py  the week's sweep, held for a session to read and choose from
  corpus.py    indexia adapter: moves 4–7 → Signals
  audua.py     audua adapter: unseen session summaries → Signals; state/audua.json
  posts.py     perceptua adapter: posts worth answering
  signals.py   Signal, the four registers, and what each one routes to
  material.py  every source → state/material.json, for a session to read
  render.py    validate what a session wrote → prompts/latest.md
  webui.py     the JSON API behind the UI
  ui.html      the whole front end, one file
scripts/
  doctor.sh  test.sh  papers.sh  ui.sh
  gather.sh  prompts.sh  write.sh  sweep.sh
.claude/skills/
  reading-queue  elicit-writing  read-only-sources  eliciter-ui
```

Sources emit signals and know nothing about writing; `material.py` serializes them and makes
no judgement; the judgement is a session, which knows the corpus and nothing about the
plumbing. That is what lets a fourth source be added without touching prompt generation —
it shows up in the snapshot and a reader takes it from there — and what makes retuning the
prompts an edit to a skill rather than to code.
