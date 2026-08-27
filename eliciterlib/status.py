"""The reading queue: which papers are waiting, read, or rejected.

The digest is not a fresh list each week — it is a **queue that persists**, capped at
`ELICITER_ARXIV_KEEP` (10). A sweep does not replace it; it tops it up. So a paper you have
not got to yet is still there next week, and one you rejected never comes back.

That is the whole reason status is stored rather than derived. Three facts have to survive
a sweep, and none of them is recoverable from arxiv:

  * **unread** — in the queue, waiting. This is the digest: what to read next.
  * **read** — you read it. It leaves the queue, freeing a slot, and **starts being
    prompted**: `signals()` below draws on read papers only.
  * **rejected** — not for you. It leaves the queue and is never offered again, however
    well it scores on a later sweep.

Reading and writing are deliberately not the same stage (changed 2026-08-26). Prompting an
unread paper asks for the one claim you would take from something you have not read, which
is either a guess from the abstract or nothing at all. Marking it read is the signal that
there is now a claim to write down, so that is when the prompt appears.

State lives in `state/papers.json`, which is eliciter's own file. Nothing here writes to
indexia or perceptua — the queue is a fact about *your reading*, not about either corpus.
"""
import json
import os
from datetime import datetime, timezone

from . import config
from .signals import Signal

ACTIVE = ("unread",)
STATUSES = ("unread", "read", "rejected")


def _now():
    return datetime.now(timezone.utc).isoformat()


class Queue:
    """The paper queue, loaded from and saved to `state/papers.json`."""

    def __init__(self, path=None):
        self.path = path or os.path.join(config.out_dir("state"), "papers.json")
        self.papers = {}
        self._load()

    def _load(self):
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            raise SystemExit(f"{self.path} is unreadable ({e}) — move it aside to start over")
        self.papers = data.get("papers", {})

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"updated_at": _now(), "papers": self.papers}, fh, indent=2)
        os.replace(tmp, self.path)      # atomic: a crash mid-write cannot truncate the queue
        return self.path

    # -- reading the queue ---------------------------------------------------
    def active(self):
        """Papers still awaiting you, best-scoring first — the digest, in order."""
        out = [p for p in self.papers.values() if p.get("status") in ACTIVE]
        out.sort(key=lambda p: -float(p.get("score") or 0.0))
        return out

    def by_status(self, status):
        return [p for p in self.papers.values() if p.get("status") == status]

    def seen(self, arxiv_id):
        """True if this paper has ever been in the queue, whatever its status now.

        Matched on the version-stripped id, so `2608.24545v2` next week is the same paper
        as `2608.24545v1` this week and a rejected paper does not return as a new revision.
        """
        return _base_id(arxiv_id) in {_base_id(k) for k in self.papers}

    def find(self, needle):
        """Resolve a user-typed id to a paper. Accepts the full id, the version-stripped
        id, or a unique prefix — nobody should have to type `2608.24545v1` exactly."""
        needle = needle.strip()
        if needle in self.papers:
            return self.papers[needle]
        base = _base_id(needle)
        hits = [p for k, p in self.papers.items()
                if _base_id(k) == base or k.startswith(needle)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            return None
        raise SystemExit(f"{needle!r} matches {len(hits)} papers — be more specific")

    # -- changing it ---------------------------------------------------------
    def refill(self, candidates, limit=None):
        """Top the queue up to `limit` with the best unseen candidates.

        Returns (added, skipped_seen). Existing entries are never touched: a paper already
        in the queue keeps its status, its score and the day it first appeared, so "how
        long has this been sitting there" stays answerable.
        """
        limit = limit if limit is not None else config.i("ELICITER_ARXIV_KEEP")
        room = max(0, limit - len(self.active()))
        added, skipped = [], 0
        for c in candidates:
            if room <= 0:
                break
            if self.seen(c["id"]):
                skipped += 1
                continue
            self.papers[c["id"]] = {
                "id": c["id"],
                "title": c.get("title", ""),
                "abstract": c.get("abstract", ""),
                "authors": c.get("authors", []),
                "url": c.get("url", ""),
                "primary_category": c.get("primary_category", ""),
                "published": c.get("published", ""),
                "score": c.get("score", 0.0),
                "matched": c.get("matched", []),
                "status": "unread",
                "first_seen": _now(),
                "changed_at": _now(),
            }
            added.append(self.papers[c["id"]])
            room -= 1
        return added, skipped

    def add(self, paper):
        """Put one paper in the queue by hand, ignoring the cap.

        The cap governs *automatic* top-up — how many papers a sweep is allowed to push at
        you. A paper you went and found yourself is a decision, not a suggestion, so it
        goes in even when the queue is full. Returns (entry, was_already_there).
        """
        existing = self.find(paper["id"])
        if existing is not None:
            return existing, True
        self.papers[paper["id"]] = {
            "id": paper["id"],
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": paper.get("authors", []),
            "url": paper.get("url", ""),
            "primary_category": paper.get("primary_category", ""),
            "published": paper.get("published", ""),
            "score": paper.get("score", 0.0),
            "matched": paper.get("matched", []),
            "status": "unread",
            "added_by": "search",
            "first_seen": _now(),
            "changed_at": _now(),
        }
        return self.papers[paper["id"]], False

    def mark(self, needle, status):
        if status not in STATUSES:
            raise SystemExit(f"unknown status {status!r} — one of {', '.join(STATUSES)}")
        p = self.find(needle)
        if p is None:
            raise SystemExit(f"no paper matching {needle!r} in the queue")
        p["status"] = status
        p["changed_at"] = _now()
        return p


def signals(queue=None, log=None):
    """Read papers, as signals — the single definition, used by the CLI and the web UI.

    **Read, not unread.** A prompt asks for the claim you took from a paper, which only
    exists once you have read it; an unread paper is a reading suggestion and the digest
    already is one.

    Ordered by most recently read. Papers never leave `papers.json`, so the read set only
    grows, and score order would hand you the same two all-time favourites every week until
    you rejected them. Recency instead means what you just finished is what gets asked
    about, and a paper you read months ago falls below the round-robin cut on its own. The
    relevance score still rides along on the signal — it orders the papers *within* a
    rendered run, once this ordering has decided which ones make it in.
    """
    log = log or (lambda *_: None)
    papers = sorted(queue.by_status("read") if queue is not None else Queue().by_status("read"),
                    key=lambda p: (p.get("changed_at") or "", float(p.get("score") or 0.0)),
                    reverse=True)
    out = [Signal(source="arxiv", kind="paper",
                  title=p.get("title", ""), detail=p.get("abstract", ""),
                  ref=p.get("id", ""), score=float(p.get("score") or 0.0),
                  meta={"paper": p})
           for p in papers]
    log(f"[papers] {len(out)} read, most recent first")
    return out


def _base_id(arxiv_id):
    """`2608.24545v2` → `2608.24545`. Version is presentation, not identity."""
    return str(arxiv_id).rsplit("v", 1)[0] if "v" in str(arxiv_id) else str(arxiv_id)
