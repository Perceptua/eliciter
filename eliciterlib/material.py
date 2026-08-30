"""Everything the sources have to say, collected in one file for a session to read.

This replaced `prompts.py` on 2026-08-30, and the reason is the whole argument of the
change. That module turned each source's signals into prompts by rule: the source decided
the register, and an ask was assembled from a template. A cross-source pass was tried on top
of it — term overlap to find what recurred across the corpora — and it is what settled the
question. The rules were legible and the prompts were mediocre: bag-of-words cannot tell
your sense of a word from the field's, so the strongest theme it ever proposed was
`mathematics · hills · road` across a pantoum and a run recording, one of which is prosody
and one a hill on a five-mile run. No amount of stopword tuning fixes that. What it needed
was a reader.

So the split moved. **Gathering is a script; judging is a session.** This module does the
half a script is actually good at: reach into four corpora through the read-only gate,
pull out the whole of what is there, and write it down. What any of it *means* — what
recurs, what is worth writing, in what register — is decided by the `elicit-writing` skill
in a Claude session that has read the material. Nothing here scores, ranks by theme, or
proposes an ask.

Term overlap did not disappear from the project; it moved back to the one job it was
always good at. `rank.py` still decides which of ~300 swept abstracts reach the reading
queue and which post is nearest to current reading, because those are shortlists over
material nobody has read yet, and a cheap explicit filter beats no filter. It just no
longer decides what you should write.

**Read-only, like everything else here.** Every read goes through `corpus`, `posts`,
`audua` and `status`, which go through `readonly.py`. The only thing this writes is
`state/material.json`, which is eliciter's own scratch.

`state/material.json` is a **snapshot, not a record**: overwritten on every run, with the
run's timestamp inside it. The record of what was asked is `prompts/YYYY-MM-DD.md`, which
is a hundredth the size and the thing you would actually go back and read.

Nothing calls this on a schedule. Gathering and judging are one move, made when the user
asks for prompts — so a run of prompts stays put until it is deliberately replaced, and the
material behind it was read at the moment it was judged rather than at seven that morning.
"""
import json
import os
from datetime import datetime, timezone

from . import arxiv, audua, config, corpus, posts, status

NAME = "material.json"

# How many recent notes ride along beyond the ones a move flagged. The moves say what is
# structurally unfinished; these say what you have been thinking about lately, which is a
# different and equally useful question for a reader deciding what is live.
RECENT_NOTES = 25

# Posts are short — the whole of perceptua is around 25KB — so all of them go in, and the
# session sees the actual corpus rather than the two the profile picked. `flagged` marks
# which ones `posts.signals` thought were adjacent to current reading; that is a hint, not
# a shortlist, and the skill is free to ignore it.
#
# audua is the opposite: one session summary is 14KB, so only the unseen ones go in full
# and the rest appear as a line each.
MAX_SESSIONS_FULL = 4


def path():
    return os.path.join(config.out_dir("state"), NAME)


def _prompt_history(limit=3):
    """The asks of the last few runs, so a session does not re-ask them.

    Read from `state/prompts.json` plus the dated markdown filenames beside it. This is the
    one piece of context the old pipeline had no way to use: it built each run from the
    sources alone, so a note that stayed orphaned got the same prompt every week until you
    wrote something. A reader can simply not do that.
    """
    out = []
    state = os.path.join(config.out_dir("state"), "prompts.json")
    if os.path.isfile(state):
        try:
            with open(state, encoding="utf-8") as fh:
                data = json.load(fh)
            for p in data.get("prompts", []):
                out.append({"generated_at": data.get("generated_at", ""),
                            "ask": p.get("ask", ""), "title": p.get("title", ""),
                            "source": p.get("source", ""), "ref": p.get("ref", "")})
        except (OSError, ValueError):
            pass
    return out[:limit * 8]


def _signal_dicts(signals):
    """Signals → plain dicts, keeping the full text each source handed over.

    `meta["text"]` is the whole material (the note bodies behind a move, the full poem, the
    whole session summary); `detail` is the excerpt a prompt used to quote. Both go in — the
    excerpt is what the source thought was the salient part, which is worth knowing even
    when you have the whole thing.
    """
    out = []
    for s in signals:
        meta = s.meta or {}
        out.append({
            "source": s.source, "kind": s.kind, "title": s.title,
            "ref": s.ref, "excerpt": s.detail,
            "text": meta.get("text") or "",
            "score": round(float(s.score or 0.0), 3),
        })
    return out


def gather(log=print, want_papers=True, want_graph=True, want_posts=True, want_audua=True):
    """Read every source and return the material, plus a note of what failed.

    A source that is unreachable is recorded in `unavailable` and skipped rather than
    aborting the run: the indexia container is often down, and three sources' worth of
    material plus an honest note about the fourth beats nothing at all. The session reading
    the snapshot is told to say so out loud rather than quietly writing a run with a corpus
    missing — a silent gap is the one failure mode that would look like a settled corpus.
    """
    log = log or (lambda *_: None)
    now = datetime.now(timezone.utc)
    out = {
        "generated_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "unavailable": {},
        "interests": config.interests(),
        "exclude": config.exclude(),
        "previous_prompts": _prompt_history(),
    }

    def attempt(name, fn, default):
        try:
            out[name] = fn()
        except SystemExit as e:                      # sources raise SystemExit for "unreachable"
            out[name] = default
            out["unavailable"][name] = str(e)
            log(f"[gather] {name} unavailable — {e}")
        except Exception as e:                       # noqa: BLE001
            out[name] = default
            out["unavailable"][name] = f"{type(e).__name__}: {e}"
            log(f"[gather] {name} failed — {type(e).__name__}: {e}")

    db = None
    if want_graph:
        try:
            db = corpus.connect()
        except SystemExit as e:
            out["unavailable"]["indexia"] = str(e)
            log(f"[gather] indexia unavailable — {e}")

    out["notes"] = {"flagged": [], "recent": []}
    if db is not None:
        attempt("notes", lambda: {
            "flagged": _signal_dicts(corpus.signals(db, log=log)),
            "recent": [{"id": n.get("id"), "title": n.get("title") or "(untitled)",
                        "body": n.get("body") or "",
                        "created_at": n.get("created_at") or "",
                        "source_ref": n.get("source_ref") or ""}
                       for n in corpus.recent_notes(db, limit=RECENT_NOTES)],
        }, {"flagged": [], "recent": []})

    if want_posts:
        def _posts():
            every = posts.load()
            profile = arxiv.build_profile(db, log=lambda *_: None)
            flagged = {s.ref for s in posts.signals(profile=profile, log=lambda *_: None)}
            return [{"ref": p["file"], "title": p["title"],
                     "date": p["date"].isoformat(),
                     "categories": p["categories"], "keywords": p["keywords"],
                     "description": p["description"],
                     "text": posts.plain_text(p),
                     "adjacent_to_current_reading": p["file"] in flagged}
                    for p in sorted(every, key=lambda p: p["date"], reverse=True)]
        attempt("posts", _posts, [])

    if want_audua:
        def _audua():
            every = audua.sessions()
            seen = audua.seen()
            rows = []
            unseen_full = 0
            for s in every:
                is_seen = s["stem"] in seen
                row = {"ref": s["stem"], "date": s["date"].isoformat(),
                       "already_offered": is_seen,
                       "has_open_threads": bool(s["threads"])}
                # The whole summary only for sessions that have never been offered. A
                # session you have already been asked about is context, not material.
                if not is_seen and unseen_full < MAX_SESSIONS_FULL:
                    row["text"] = s["summary"]
                    unseen_full += 1
                else:
                    row["intro"] = s["intro"]
                rows.append(row)
            return rows
        attempt("sessions", _audua, [])

    if want_papers:
        def _papers():
            q = status.Queue()
            return {
                "read": [{"ref": p.get("id"), "title": p.get("title", ""),
                          "authors": p.get("authors") or [],
                          "published": p.get("published", ""),
                          "read_on": (p.get("changed_at") or "")[:10],
                          "url": p.get("url", ""),
                          "matched": p.get("matched") or [],
                          "text": p.get("abstract", "")}
                         for p in sorted(q.by_status("read"),
                                         key=lambda p: p.get("changed_at") or "",
                                         reverse=True)],
                # Unread papers are not prompt material — a prompt asks for the claim you
                # took from something, which does not exist until you have read it. They
                # are here as context: what you are about to read says something about what
                # you are currently thinking about.
                "waiting": [{"ref": p.get("id"), "title": p.get("title", ""),
                             "matched": p.get("matched") or []}
                            for p in q.active()],
            }
        attempt("papers", _papers, {"read": [], "waiting": []})

    return out


def write(data, log=print):
    """Write the snapshot atomically, and return where it went."""
    dest = path()
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, dest)          # atomic: a session cannot read a half-written snapshot
    if log:
        log(f"[gather] {dest} ({os.path.getsize(dest) // 1024}KB)")
    return dest


def load():
    """The current snapshot, or a SystemExit telling you to run the gather."""
    p = path()
    if not os.path.isfile(p):
        raise SystemExit(f"no material yet — run `bash scripts/gather.sh` first ({p})")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"{p} is unreadable ({e}) — re-run `bash scripts/gather.sh`")


def summarize(data):
    """One line per source: what a gather actually found. For the CLI and doctor."""
    notes = data.get("notes") or {}
    papers = data.get("papers") or {}
    return {
        "flagged notes": len(notes.get("flagged") or []),
        "recent notes": len(notes.get("recent") or []),
        "posts": len(data.get("posts") or []),
        "sessions": len(data.get("sessions") or []),
        "unseen sessions": sum(1 for s in (data.get("sessions") or [])
                               if not s.get("already_offered")),
        "papers read": len(papers.get("read") or []),
        "papers waiting": len(papers.get("waiting") or []),
    }
