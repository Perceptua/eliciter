"""The week's arxiv sweep, held for a reader.

The same split the prompts took: **fetching is a script, judging is a session.** This
module fetches and holds; `scripts/sweep.py` is its CLI; the `reading-queue` skill decides
what actually reaches the queue.

What was wrong with deciding here. The old sweep scored every abstract against the interest
profile, dropped anything that matched no *stated* interest, and topped the queue up with
the ten highest. Measured on one real week: **1160 papers swept, 518 past the gate, ten
queued.** Two separate problems in that, and only one of them is fixable by tuning.

The gate is a recall problem. A paper on regeneration in planaria need never use the word
`morphogenesis`; it scores zero and nobody ever sees it. 642 papers went in that bin and no
human read a word of any of them.

The ranking is a precision problem, and worse. Bag-of-words cannot tell your sense of
`agent` from cs.AI's, so the top ten that week mixed papers that were genuinely about
collective behaviour with an LLM tool-calling framework. `ELICITER_EXCLUDE` exists to push
back on exactly that and it is an arms race you lose slowly.

Both dissolve if a reader is the second stage, so the funnel is now:

    ~1160 swept  →  every title, ordered by overlap  →  a session picks ~60 to open
                 →  those abstracts  →  a session picks what the queue can hold

Every title is about 17k tokens; sixty abstracts is another 16k. That is the whole cost of
the change, once a week, and it buys a shortlist nothing was silently cut from.

**Ordering is a hint, not a verdict.** `rank.overlap` scores every candidate without the
gate, purely so the likely material is at the top of a long list. Nothing is dropped for
scoring badly, and a session is told to read past the point where the scores go quiet.

**Already-decided papers never appear.** A paper in the queue, read, or rejected is filtered
out here, so a rejected paper cannot come back — the one queue rule that has to survive any
change to how papers are chosen.
"""
import json
import os
from datetime import datetime, timezone

from . import arxiv, config, rank, status

NAME = "candidates.json"


def path():
    return os.path.join(config.out_dir("state"), NAME)


def fetch(db=None, categories=None, lookback_days=None, log=print):
    """Sweep arxiv and return the candidate set, newest week first, ordered by overlap.

    A pure read of the network plus the queue: nothing is added, nothing is decided, and
    running it twice costs two sweeps and changes nothing.
    """
    log = log or (lambda *_: None)
    papers = arxiv.sweep(categories=categories, lookback_days=lookback_days, log=log)
    prof = arxiv.build_profile(db, log=log)

    queue = status.Queue()
    fresh, already = [], 0
    for p in papers:
        if queue.seen(p["id"]):
            already += 1
            continue
        sc, matched = rank.overlap(f"{p['title']}. {p['abstract']}", prof)
        fresh.append(dict(p, score=round(sc, 4), matched=matched[:12]))
    fresh.sort(key=lambda p: -p["score"])

    log(f"[sweep] {len(papers)} swept, {already} already decided, {len(fresh)} candidate(s)")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "swept": len(papers),
        "already_decided": already,
        "lookback_days": (lookback_days if lookback_days is not None
                          else config.i("ELICITER_ARXIV_LOOKBACK_DAYS")),
        "categories": categories or config.categories(),
        "interests": config.interests(),
        "exclude": config.exclude(),
        "queue_cap": config.i("ELICITER_ARXIV_KEEP"),
        "queue_waiting": len(queue.active()),
        "free_slots": max(0, config.i("ELICITER_ARXIV_KEEP") - len(queue.active())),
        "candidates": fresh,
    }


def write(data, log=print):
    dest = path()
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, dest)
    if log:
        log(f"[sweep] {dest} ({os.path.getsize(dest) // 1024}KB)")
    return dest


def load():
    p = path()
    if not os.path.isfile(p):
        raise SystemExit(f"no candidates yet — run `bash scripts/sweep.sh fetch` ({p})")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"{p} is unreadable ({e}) — re-run `bash scripts/sweep.sh fetch`")


def by_id(data):
    return {c["id"]: c for c in data.get("candidates", [])}


def title_lines(data, per_group=None):
    """Every candidate as one line, grouped by primary category, smallest group first.

    Deliberately not the abstracts. The point of the two passes is that a title costs
    fifteen tokens and an abstract costs three hundred, so the cheap pass covers everything
    and the expensive one covers only what the cheap pass flagged.

    **Smallest group first, and that is the important part.** On a real week: cs.LG 330 and
    cs.AI 288, against math.HO 3, physics.hist-ph 4, q-bio.NC 5, nlin.AO 5. The small
    groups are the specialised venues — they are where a paper on basal cognition or the
    foundations of mathematics actually appears, and they are short enough to read
    exhaustively. The two big ones are where the machine-learning firehose lives, and are
    for skimming. A flat list ordered by term overlap buries the first inside the second,
    which is what the ordering did before: its top forty were almost entirely LLM-agent
    papers, because `agent` is the heaviest term in the profile and cs.AI says it constantly.

    The groups come in two blocks: **the categories you asked to sweep**, then everything
    else, which is here only because papers cross-list. A week produces a long tail of
    singleton categories — astro-ph.CO, cond-mat.mes-hall, cs.MM — and sorting purely by
    size floats all of those above q-bio.NC and math.HO, which is exactly backwards.

    Within a group the ordering is still overlap, descending. `per_group` caps each group,
    which is how to skim the firehose without hiding any of the small venues.
    """
    groups = {}
    for c in data.get("candidates", []):
        groups.setdefault(c.get("primary_category") or "(none)", []).append(c)

    configured = [c for c in (data.get("categories") or []) if c in groups]
    rest = [c for c in groups if c not in set(configured)]
    order = (sorted(configured, key=lambda k: (len(groups[k]), k)),
             sorted(rest, key=lambda k: (len(groups[k]), k)))

    out = []
    for block, cats in zip(("your categories", "cross-listed from elsewhere"), order):
        if not cats:
            continue
        out += ["", f"# {block} — {sum(len(groups[c]) for c in cats)} paper(s)"]
        for cat in cats:
            rows = sorted(groups[cat], key=lambda c: -c["score"])
            shown = rows[:per_group] if per_group else rows
            out.append("")
            out.append(f"## {cat} — {len(rows)}"
                       + (f", showing {len(shown)}" if len(shown) < len(rows) else ""))
            out += [f"{c['score']:>6.2f}  {c['id']:<13} {c['title']}" for c in shown]
    return out[1:] if out else out


def detail(c):
    authors = ", ".join(c.get("authors") or [])
    matched = ", ".join(c.get("matched") or [])
    return "\n".join([
        f"### {c['title']}",
        f"{c['id']} · {c.get('primary_category', '')} · {c.get('published', '')[:10]}",
        f"authors: {authors}" if authors else "",
        f"overlap {c['score']:.2f} on: {matched}" if matched else "overlap 0.00",
        "",
        c.get("abstract", ""),
        f"<{c.get('url', '')}>",
    ])


class InvalidPicks(ValueError):
    """What a session wrote is not a pick list. The message names the offending entry."""


def validate(raw, data):
    """Session output → the papers to queue, in the order given.

    Refuses an id that is not in the candidate set. That is the check that matters: a
    hallucinated arxiv id would enter the reading queue as a paper that does not exist, and
    would sit there looking exactly like a real one.
    """
    if not isinstance(raw, list):
        raise InvalidPicks(f"expected a list of picks, got {type(raw).__name__}")
    index = by_id(data)
    out, seen = [], set()
    for i, item in enumerate(raw, 1):
        if isinstance(item, str):
            item = {"id": item}
        if not isinstance(item, dict):
            raise InvalidPicks(f"pick {i}: expected an object or an id, got {type(item).__name__}")
        pid = str(item.get("id") or "").strip()
        if not pid:
            raise InvalidPicks(f"pick {i}: id is required")
        if pid not in index:
            raise InvalidPicks(
                f"pick {i}: {pid!r} is not in this sweep's candidates — "
                "ids must be copied from the candidate list, never composed")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(dict(index[pid], why=str(item.get("why") or "").strip()))
    return out
