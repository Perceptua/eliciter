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

**A recency window, not a queue.** audua produces new sessions indefinitely, like the arxiv
sweep, but unlike arxiv there is no per-item "read" action to hang persistence on — nobody
is going to click through forty transcripts one at a time to mark them. So instead of
tracking which sessions have been offered before, a session is simply eligible while it is
recent: anything recorded within `RECENT_DAYS` of today is fair game for a prompt, run after
run, and drops out on its own once it ages past the window. A recording the corpus keeps
circling can prompt more than once — that is the point, not a bug to guard against — and
there is no state file to fall out of sync with what has actually been offered.

Read-only for the same reason indexia and perceptua are: eliciter did not record this audio
and has no business rewriting audua's output. Access is through `readonly.audua_dir()`,
which can list and read inside `ELICITER_AUDUA_ROOT` and has no method that writes.
"""
import os
import re
from datetime import date, timedelta

from . import config, readonly
from .signals import Signal

SESSION_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})_(\d+)$")
HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)
# The footnote appendix (`[^1]: **00:00:03 ...`) follows the last section directly, with no
# `## ` heading of its own — so a section that happens to be last in the file needs this as
# its own stop, or "Threads left open" swallows every footnote in the summary.
FOOTNOTE_RE = re.compile(r"^\[\^\d+\]:", re.MULTILINE)

# A session recorded within this many days of today is eligible to prompt. Older sessions
# stay readable through `sessions()` but drop out of `signals()` on their own.
RECENT_DAYS = 30

# At most this many recent sessions become prompts in one run. An hour of transcript is
# dense material, and — like perceptua — this source should not crowd out the reading.
MAX_SIGNALS = 2


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


def is_recent(session_date, today=None):
    """Whether a session recorded on `session_date` is still within the eligible window —
    the single definition of "recent", shared by `signals()`, `material.py`, `webui.py`, and
    `scripts/doctor.py` so they cannot disagree about which sessions are current."""
    return (today or date.today()) - session_date <= timedelta(days=RECENT_DAYS)


def signals(root=None, log=print):
    """Recent audua sessions, as Signals — the single definition, used by the CLI and the
    web UI. A pure read; nothing about calling this changes what is eligible next time."""
    log = log or (lambda *_: None)
    all_sessions = sessions(root)
    if not all_sessions:
        log("[audua] no sessions found")
        return []

    recent = [s for s in all_sessions if is_recent(s["date"])]

    out = []
    for i, s in enumerate(recent[:MAX_SIGNALS]):
        out.append(Signal(
            source="audua", kind="session",
            title=f"Audua — {s['date'].isoformat()}",
            detail=_detail(s),
            ref=s["stem"],
            # Ordering within the source is recency alone — the most recently recorded
            # eligible session is the one still fresh enough to write against.
            score=max(0.1, 1.0 - 0.1 * i),
            # `detail` is threads-plus-intro, capped at 700 characters; `meta["text"]` is
            # the whole summary, which is what the aggregate pass reads. An hour of
            # transcript is the densest material in the project and themeing it on its
            # first paragraph would waste most of it — see `themes.text_of`.
            meta={"session": s, "text": s["summary"]}))

    log(f"[audua] {len(all_sessions)} session(s); {len(recent)} within {RECENT_DAYS}d; "
        f"{len(out)} signal(s)")
    return out
