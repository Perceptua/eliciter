"""Source — audua clip transcripts, read through the gate.

audua turns a run-length recording into a batch of VAD-segmented clips, transcribes each
with faster-whisper, and writes one `summary.md` per session: a synthesized narrative,
footnoted back to the clips it drew on, plus — when the model found any — a "Threads left
open" section naming what was left unresolved. That summary, not the raw clips, is what
this module reads: the clips are audua's working material, the summary is already the
digested form a writing prompt wants, and reading forty small transcript files per session
for detail `render.py` would truncate anyway is work with no payoff.

A session is a directory under `ELICITER_AUDUA_ROOT` named `YYMMDD_NNNN` — audua's own
naming, which sorts chronologically as a plain string, so no date parsing is needed to
order sessions by recency.

**Seen-once, not a queue.** audua produces new sessions indefinitely, like the arxiv sweep,
but unlike arxiv there is no per-item "read" action to hang persistence on — nobody is
going to click through forty transcripts one at a time to mark them. So instead of a status
you set, `state/audua.json` just remembers which sessions have already been *offered*: once
a session has appeared in a rendered run, it does not come back. `mark_seen()` is the write
side of that, and it is called by the orchestrator (`scripts/elicit.py`, `webui.run_elicit`)
once `prompts.build()` has decided what actually made the final, limited list — not by
`signals()` itself, which stays a pure read like every other source. A session emitted as a
candidate but crowded out by the per-run limit is *not* marked, and is offered again next
run; a session that actually made it into a rendered file is retired for good. That is the
correct side to be wrong on: silently losing a session because a busier run outscored it
would be worse than occasionally seeing one twice.

Read-only for the same reason indexia and perceptua are: eliciter did not record this audio
and has no business rewriting audua's output. Access is through `readonly.audua_dir()`,
which can list and read inside `ELICITER_AUDUA_ROOT` and has no method that writes.
"""
import json
import os
import re
from datetime import date, datetime, timezone

from . import config, readonly
from .signals import Signal

SESSION_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})_(\d+)$")
HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)
# The footnote appendix (`[^1]: **00:00:03 ...`) follows the last section directly, with no
# `## ` heading of its own — so a section that happens to be last in the file needs this as
# its own stop, or "Threads left open" swallows every footnote in the summary.
FOOTNOTE_RE = re.compile(r"^\[\^\d+\]:", re.MULTILINE)

# At most this many unseen sessions become prompts in one run. An hour of transcript is
# dense material, and — like perceptua — this source should not crowd out the reading.
MAX_SIGNALS = 2

STATE_NAME = "audua.json"


# ---- state: which sessions have already been offered ------------------------

def _state_path():
    return os.path.join(config.out_dir("state"), STATE_NAME)


def _load_seen():
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("seen", {})
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path} is unreadable ({e}) — move it aside to start over")


def _save_seen(seen):
    path = _state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"updated_at": datetime.now(timezone.utc).isoformat(), "seen": seen},
                  fh, indent=2)
    os.replace(tmp, path)          # atomic: a crash mid-write cannot corrupt the file
    return path


def seen():
    """Which session stems have already been offered — the public read of `state/audua.json`,
    for `scripts/doctor.py` and anything else that wants to inspect it without reaching into
    the loader `signals()` and `mark_seen()` share."""
    return _load_seen()


def mark_seen(prompts):
    """Persist that these audua-sourced prompts were offered, so they never resurface.

    Called by the orchestrator, after `prompts.build()` — see the module docstring for why
    this is not done inside `signals()`.
    """
    stems = {p.signal.ref for p in prompts if p.signal.source == "audua"}
    if not stems:
        return
    seen = _load_seen()
    now = datetime.now(timezone.utc).isoformat()
    for stem in stems:
        seen[stem] = now
    _save_seen(seen)


# ---- reading sessions ---------------------------------------------------------

def _section(text, heading):
    """The body of one `## heading` section, or "" if the summary has none by that name.

    Not every summary has every section — audua's summarizer includes "Threads left open"
    only when it found one, and this module must never be the reason a run fails on a
    session that happens not to have it.
    """
    m = re.search(rf"^##\s+{re.escape(heading)}\b.*$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    stops = [x.start() for x in (HEADING_RE.search(rest), FOOTNOTE_RE.search(rest)) if x]
    return rest[:min(stops) if stops else None].strip()


def _excerpt(text, max_chars=700):
    """Trim to whole lines, like perceptua's — a summary cut mid-sentence reads as broken
    rather than as a shorter quotation."""
    if len(text) <= max_chars:
        return text
    kept, used = [], 0
    for line in text.splitlines():
        if used + len(line) + 1 > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept).rstrip() + "\n…"


def sessions(root=None):
    """Every audua session with a summary.md, most recent first.

    Tolerant by design: a session directory audua is still writing to (no summary.md yet)
    is silently skipped rather than raising, the same posture `posts.load()` takes toward a
    post with no front matter.
    """
    gate = readonly.audua_dir(root or config.audua_root())
    out = []
    for stem in gate.dirs():
        m = SESSION_RE.match(stem)
        if not m:
            continue                                   # _batches, .certs, and friends
        try:
            summary = gate.read(f"{stem}/summary.md")
        except OSError:
            continue
        yy, mo, dd, _seq = m.groups()
        out.append({
            "stem": stem,
            "date": date(2000 + int(yy), int(mo), int(dd)),
            "summary": summary,
            "intro": _section(summary, "What's in this recording"),
            "threads": _section(summary, "Threads left open"),
        })
    out.sort(key=lambda s: s["stem"], reverse=True)
    return out


def _detail(session):
    """The material quoted into the prompt. Threads come first when there are any — that
    is the concrete, actionable thing the prompt asks about, and `_excerpt`'s character cap
    should spend its budget there before the scene-setting intro, not after."""
    parts = ["Threads left open:\n" + session["threads"]] if session["threads"] else []
    if session["intro"]:
        parts.append(session["intro"])
    return _excerpt("\n\n".join(parts) or session["summary"])


def signals(root=None, log=print):
    """Unseen audua sessions, as Signals — the single definition, used by the CLI and the
    web UI. A pure read; see `mark_seen()` for where the state actually changes."""
    log = log or (lambda *_: None)
    all_sessions = sessions(root)
    if not all_sessions:
        log("[audua] no sessions found")
        return []

    seen = _load_seen()
    unseen = [s for s in all_sessions if s["stem"] not in seen]

    out = []
    for i, s in enumerate(unseen[:MAX_SIGNALS]):
        out.append(Signal(
            source="audua", kind="session",
            title=f"Audua — {s['date'].isoformat()}",
            detail=_detail(s),
            ref=s["stem"],
            # Ordering within the source is recency alone — the most recently recorded
            # unseen session is the one still fresh enough to write against.
            score=max(0.1, 1.0 - 0.1 * i),
            meta={"session": s}))

    log(f"[audua] {len(all_sessions)} session(s); {len(unseen)} unseen; {len(out)} signal(s)")
    return out
