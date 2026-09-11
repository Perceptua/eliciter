---
name: read-only-sources
description: How eliciter reads indexia, audua, perceptua, and misc without being able to write to any of them, and the rules for adding code that touches a source. Use when adding or changing anything that queries the indexia graph, reads audua session transcripts, reads perceptua posts, or reads the misc folder, when a ReadOnlyViolation is raised, when the read-only tests fail, or when the user asks whether eliciter can modify their notes, recordings, posts, or dropped writing.
---

# The read-only gate

eliciter reads four corpora — three it does not own, plus `misc/`, which lives inside this
repo but holds the user's own dropped writing rather than anything eliciter authors. It must
not be able to change any of them, and that is enforced by code in `eliciterlib/readonly.py`
rather than by discipline.

## The rule for new code

**Never construct a client or open a source file directly.** Use the gate:

```python
from . import readonly

db = readonly.graph()                      # or corpus.connect()
rows = notelib.rows(db.query("SELECT id, title FROM Note"))

gate = readonly.posts_dir(config.posts_dir())
text = gate.read(gate.names()[0])

gate = readonly.audua_dir(config.audua_root())
sessions = gate.dirs()                      # one YYMMDD_NNNN folder per recording
text = gate.read(f"{sessions[0]}/summary.md")

gate = readonly.misc_dir(config.misc_dir())
text = gate.read(gate.names()[0])
mtime = gate.mtime(gate.names()[0])
```

`notelib` may be imported for its read helpers (`rows`, `first_row`, the `moveN_candidates`
functions) — those take a `db` and only call `.query()`, so a gated handle satisfies them.
What is forbidden is `notelib.Arcade()`, `.command(...)`, `.atomically(...)`,
`notelib.Ingestor`, and any `notelib.insert_*`.

## Why three layers

1. **No write method exists.** `ReadOnlyGraph` has `query` and nothing else. It *wraps* an
   `Arcade` and keeps it private rather than subclassing, so the write API is not reachable
   by inheritance.
2. **Unknown attributes are refused loudly.** `db.command` raises `ReadOnlyViolation`
   naming what was attempted, not an `AttributeError` a caller might catch and route around.
   (Dunders are exempt, so `dir()` and `copy` still behave.)
3. **The statement is checked.** `query` refuses SQL that is not a read — it must begin
   `SELECT`/`MATCH`/`TRAVERSE` and contain no write keyword, checked with string literals
   stripped so a note body containing the word "delete" cannot trip it.

`ReadOnlyDir` is the same shape for files: `names()`, `dirs()`, `read()`, and `mtime()` (a
timestamp, not content), path traversal refused, nothing that writes. `posts_dir()`,
`audua_dir()`, and `misc_dir()` all hand out a `ReadOnlyDir` — `dirs()` is what lets a caller
enumerate audua's one-folder-per-session layout, and `read()` already accepts a relative
path into a subdirectory (`read("<stem>/summary.md")`), since the traversal check only
requires the resolved path stay under `root`.

## The tests are the guarantee

`bash scripts/test.sh` runs `tests/test_readonly.py`, which does two things:

- tests that the gate refuses writes, and
- **scans this project's own source** and fails if any module reaches around the gate.

The second half is the important one — a perfect gate is worth nothing if `corpus.py` can
quietly build its own `Arcade`. It has already caught one real bypass in `doctor.py`. If you
add a module that touches a source, that scan is what will tell you if you did it wrong.

`bash scripts/doctor.sh` asserts the same property at runtime against the live database.

## What this means for the user

eliciter cannot add a note, stage a link, log an `Op`, touch `_posts/`, touch anything under
audua's output directory, or touch a file in `misc/`. When writing is called for,
`scripts/write.sh` opens a session **in the target project**, which has the tools that do
write. Committing is always an act the user performs there — so the `Op` log stays a record
of things a human did.

The one exception in spirit, not in code: the `scan-misc` skill *does* write into `misc/` —
it is the thing that turns a scanned image into the markdown this project reads. That is not
a hole in the gate; `scan-misc` is a separate tool that runs outside `eliciter*`'s own code
path and never imports `readonly` or `notelib`, the same way `write.sh` opening a session in
indexia is not eliciter writing a note. `material.gather()` still only ever reads `misc/`
through `readonly.misc_dir()`.

If a user asks eliciter to save a note for them, the answer is to run
`bash scripts/write.sh <n>` and do it in indexia — not to add a write path here.

eliciter writes nothing about audua at all — which sessions are eligible to prompt is
computed statelessly from each session's date against a recency window (`audua.is_recent`),
not tracked in a file. Contrast `state/papers.json`, which *does* record a fact about your
reading of the corpus (marked read/rejected) because there is no other way to know it.
