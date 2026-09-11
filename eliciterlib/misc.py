"""Source — miscellaneous writing, read through the gate.

A catch-all for material that doesn't belong to indexia, perceptua, or audua: notes, drafts,
fragments dropped as `.txt` or `.md` files into `ELICITER_MISC_DIR` (default `misc/` at the
repo root, gitignored). It also holds markdown transcriptions of scanned handwritten pages —
made by the `scan-misc` skill, which reads an image dropped here and, after the human ratifies
the transcription, writes the `.md` file this module then reads. This module never touches
images itself; a `.jpg`/`.png`/`.pdf` sitting here un-transcribed is simply invisible to it.

No front matter, no filename convention. `title` is the filename stem and `date` is the
file's mtime — this source is meant to be as low-friction to add to as possible, which is
the opposite of asking for YAML front matter or a `YYYY-MM-DD-slug` name.

Everything here goes into a run in full, same posture as perceptua: the folder is meant to
stay small, and unlike audua there is no natural notion of a session aging out — a dropped
fragment is just as live a month later as the day it was dropped.

Read-only for the same reason indexia, perceptua and audua are: this project gathers and
judges, it does not author or edit the material it reads, even material that happens to live
inside its own repo. Access is through `readonly.misc_dir()`, which can list and read inside
`ELICITER_MISC_DIR` and has no method that writes.
"""
from datetime import datetime, timezone

from . import config, readonly
from .signals import Signal

EXTENSIONS = (".md", ".markdown", ".txt")


def load(root=None):
    """Every misc file, most recently modified first."""
    gate = readonly.misc_dir(root or config.misc_dir())
    out = []
    for name in gate.names():
        if not name.lower().endswith(EXTENSIONS):
            continue                       # images awaiting scan-misc, dotfiles, etc.
        text = gate.read(name)
        stem = name.rsplit(".", 1)[0]
        out.append({
            "file": name,
            "title": stem.replace("_", " ").replace("-", " ").strip() or name,
            "date": datetime.fromtimestamp(gate.mtime(name), tz=timezone.utc),
            "text": text.strip(),
        })
    out.sort(key=lambda m: m["date"] or datetime.min.replace(tzinfo=timezone.utc),
              reverse=True)
    return out


def _excerpt(text, max_chars=600):
    """Trim to whole lines — the same posture as perceptua and audua's excerpts."""
    if len(text) <= max_chars:
        return text
    kept, used = [], 0
    for line in text.splitlines():
        if used + len(line) + 1 > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept).rstrip() + "\n…"


def signals(root=None, log=print):
    """Every misc file, as Signals. There is no scoring or shortlist here — the folder is
    meant to stay small, so everything in it is worth a reader's attention, not just the
    top few."""
    log = log or (lambda *_: None)
    items = load(root)
    if not items:
        log("[misc] no files found")
        return []

    out = []
    for m in items:
        out.append(Signal(
            source="misc", kind="dropped",
            title=m["title"],
            detail=_excerpt(m["text"]),
            ref=m["file"],
            score=0.5,
            meta={"item": m, "text": m["text"]}))

    log(f"[misc] {len(items)} file(s); {len(out)} signal(s)")
    return out
