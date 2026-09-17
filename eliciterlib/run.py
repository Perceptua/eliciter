"""The standing run of prompts, and what you have decided about each one.

`state/prompts.json` is the one artifact a session produces; everything else about prompts
is derived from it. This module is the only writer of that file after the session has
written it, and what it writes is one field per prompt: **did you write this, or is it not
for you?**

That decision is a fact about you, not about the corpus — the same kind of thing
`status.py` keeps for papers, and it is kept the same way: in eliciter's own state, never
in indexia or perceptua.

**Why the status lives in `prompts.json` rather than a file of its own.** A prompt has no
identity outside the run it belongs to. Its number is its position in this run, its ask was
written against this week's material, and when a session writes a new run the old prompts
are gone — so a separate ledger would be a set of decisions about things that no longer
exist, keyed by something (a hash of the ask?) that changes the moment a prompt is reissued
with new material folded in. Keeping the status beside the prompt means a decision lives
exactly as long as the thing it is about.

It also puts the decisions where the next session will read them. `material.py` hands the
standing run to the next session as `previous_prompts`; with a status on each one, a run
you rejected outright comes back as *rejected* rather than as an ask that "has not been
written yet", which are very different things to be told when deciding what to ask next.

The cost, which is deliberate: replacing a run drops its decisions. The asks survive in
`prompts/YYYY-MM-DD.md`, but the record that you turned one down does not outlive the run
it was made in. That is the same trade the run itself makes — a run is a standing offer,
not an archive.
"""
import json
import os
from datetime import datetime, timezone

from . import config
from .signals import PROMPT_STATUSES

NAME = "prompts.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


class StaleRun(LookupError):
    """The prompt being marked is not the prompt the caller was looking at.

    Raised when a caller passes the title it saw and the run has been replaced since —
    which is exactly the window the UI is exposed to, since it holds a painted list of
    prompts between polls. Marking by number alone would silently decide about whichever
    prompt now happens to be third.
    """


class Run:
    """The standing run, loaded from and saved back to `state/prompts.json`.

    The path is injectable for tests. Everything else about the file is left alone: the
    prompts are written back exactly as they were read, plus the status, so this can never
    reshape what a session wrote (that is `render.validate`'s job, on render).
    """

    def __init__(self, path=None):
        self.path = path or os.path.join(config.out_dir("state"), NAME)
        self.meta = {}
        self.prompts = []
        self._load()

    def _load(self):
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            raise SystemExit(f"{self.path} is unreadable ({e}) — "
                             "re-render it with `bash scripts/prompts.sh render`")
        if isinstance(data, list):                  # a bare list is a valid thing to write
            data = {"prompts": data}
        self.prompts = data.get("prompts") or []
        self.meta = {k: v for k, v in data.items() if k != "prompts"}

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**self.meta, "prompts": self.prompts}, fh, indent=2,
                      ensure_ascii=False)
        os.replace(tmp, self.path)      # atomic: a crash mid-write cannot truncate the run
        return self.path

    # -- reading it ----------------------------------------------------------
    def find(self, n):
        for p in self.prompts:
            if p.get("n") == int(n):
                return p
        return None

    def counts(self):
        out = {s: 0 for s in PROMPT_STATUSES}
        for p in self.prompts:
            out[status_of(p)] = out.get(status_of(p), 0) + 1
        return out

    # -- deciding ------------------------------------------------------------
    def mark(self, n, status, expect_title=None):
        """Record what you did with prompt `n`. Returns the prompt.

        `expect_title` is the staleness guard described on :class:`StaleRun`: pass what you
        were looking at and a replaced run is refused rather than mis-decided.
        """
        # ValueError, not SystemExit: unlike the paper queue this is reached from the UI as
        # well as the CLI, and a bad status posted by a browser is a bad request, not a
        # reason for the server to report the queue unreachable.
        if status not in PROMPT_STATUSES:
            raise ValueError(f"unknown status {status!r} — "
                             f"one of {', '.join(PROMPT_STATUSES)}")
        p = self.find(n)
        if p is None:
            raise KeyError(f"no prompt {n} — there are {len(self.prompts)}")
        if expect_title and str(expect_title).strip() != str(p.get("title") or "").strip():
            raise StaleRun(
                f"prompt {n} is now {p.get('title')!r} — the run was replaced while you "
                "were looking at it; refresh and decide again")
        if status == "open":
            p.pop("status", None)
            p.pop("decided_at", None)
        else:
            p["status"] = status
            p["decided_at"] = _now()
        return p


def status_of(prompt):
    """A prompt's status, defaulting to open.

    Absent means open, so a run a session just wrote needs no status field at all and
    every older `prompts.json` keeps working. An unrecognised value reads as open rather
    than raising: a bad status is a prompt you have not decided about yet, which is true
    and harmless, where a crash here would take down the whole listing.
    """
    st = str((prompt or {}).get("status") or "open").strip().lower()
    return st if st in PROMPT_STATUSES else "open"
