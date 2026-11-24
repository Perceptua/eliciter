"""The interest profile: the terms a sweep orders arxiv by, kept where they can be tuned.

`state/interests.json` holds three lists — **interests**, what you care about;
**exclude**, the counterweight that pushes the field's sense of a shared word down the list;
and **categories**, the arxiv categories a sweep pulls from. It replaced the
`ELICITER_INTERESTS`, `ELICITER_EXCLUDE` and `ELICITER_ARXIV_CATEGORIES` settings in `.env`
(2026-11-24), which no longer exist, because these are meant to move: a `.env` line has no
history and no reason attached, and it is a file sessions are not allowed to read.

Tuning follows the project's one idiom — **a script gathers, a session judges, a script
commits** — with the user in the middle:

  * `gather()` collects the evidence: papers marked read (what an interest should catch),
    papers rejected (what an exclude should sink, with the terms that matched them), and
    the recent reading and writing every other source has.
  * a session (the `tune-interests` skill) reads it and writes a proposal to
    `state/interests.next.json` — terms to add and drop, each with a reason.
  * the user approves it, and `apply()` validates it against the profile, applies it, and
    appends it to the profile's history. Nothing is applied without that approval, and
    nothing runs on a schedule.

`config.interests()`, `config.exclude()` and `config.categories()` read the profile when it
exists and fall back to the built-in `config.DEFAULT_*` lists when it does not, so a fresh
checkout still sweeps.
"""
import json
import os
import re
from datetime import datetime, timezone

from . import config

NAME = "interests.json"
DRAFT = "interests.next.json"
MATERIAL = "interests-material.json"
LISTS = ("interests", "exclude", "categories")
TERM_LISTS = ("interests", "exclude")          # the two the ranker scores abstracts on
CHANGES = ("add", "drop")
# An arxiv category: an archive (`cs`, `q-bio`, `quant-ph`) and, usually, a subject class.
CATEGORY_RE = re.compile(r"^[a-z][a-z\-]*(\.[A-Za-z][A-Za-z\-]*)?$")


class InvalidProposal(ValueError):
    """A proposal that cannot be applied as written. The message says why."""


def path():
    return os.path.join(config.out_dir("state"), NAME)


def draft_path():
    return os.path.join(config.out_dir("state"), DRAFT)


def material_path():
    return os.path.join(config.out_dir("state"), MATERIAL)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p):
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"{p} is unreadable ({e}) — fix it or move it aside")


def _write_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)              # atomic: a crash mid-write cannot truncate the profile
    return p


def _key(term):
    """Terms compare case- and space-insensitively: `Active  Inference` is `active inference`."""
    return " ".join(str(term).split()).casefold()


def load():
    """The profile, or None when there is none yet (config then uses its built-in defaults).

    A profile from before categories moved in has none; it gets the built-in default here,
    and keeps it once a tuning writes the profile back."""
    data = _read_json(path())
    if data is None:
        return None
    if data.get("categories") is None:
        data["categories"] = list(config.DEFAULT_CATEGORIES)
    for name in LISTS:
        if not isinstance(data.get(name), list):
            raise SystemExit(f"{path()} has no `{name}` list — fix it or move it aside")
    data.setdefault("history", [])
    return data


def init(interests, exclude, categories, now=None):
    """Write a first profile from these lists. Refuses to overwrite an existing one."""
    if os.path.isfile(path()):
        raise SystemExit(f"{path()} already exists — tune it rather than re-seeding it")
    clean = {"interests": _dedupe(interests), "exclude": _dedupe(exclude),
             "categories": _dedupe(categories)}
    for name in ("interests", "categories"):
        if not clean[name]:
            raise SystemExit(f"refusing to seed a profile with no {name}")
    now = now or _now()
    return _write_json(path(), {
        "updated_at": now,
        **clean,
        "history": [{"at": now, "seeded": True,
                     "note": f"seeded with {len(clean['interests'])} interest(s), "
                             f"{len(clean['exclude'])} exclude term(s) and "
                             f"{len(clean['categories'])} categories"}],
    })


def _dedupe(terms):
    out, seen = [], set()
    for t in terms:
        t = " ".join(str(t).split())
        if t and _key(t) not in seen:
            seen.add(_key(t))
            out.append(t)
    return out


def check(proposal, profile):
    """Validate a proposal against the profile. Returns the normalised changes:
    `{list: {"add": [{term, why}], "drop": [{term, why}]}}`. Raises InvalidProposal."""
    if not isinstance(proposal, dict):
        raise InvalidProposal("a proposal is a JSON object with `interests`, `exclude` "
                              "and/or `categories`")
    stray = [k for k in proposal if k not in LISTS + ("note",)]
    if stray:
        raise InvalidProposal(f"unexpected key(s): {', '.join(stray)} — a proposal has "
                              "`interests`, `exclude`, `categories` and an optional `note`")
    current = {name: {_key(t): t for t in profile[name]} for name in LISTS}
    out, added = {}, {}
    for name in LISTS:
        block = proposal.get(name) or {}
        if not isinstance(block, dict) or any(k not in CHANGES for k in block):
            raise InvalidProposal(f"`{name}` takes only `add` and `drop` lists")
        out[name] = {}
        for change in CHANGES:
            rows = block.get(change) or []
            if not isinstance(rows, list):
                raise InvalidProposal(f"`{name}.{change}` must be a list")
            seen, clean = set(), []
            for r in rows:
                if not isinstance(r, dict):
                    raise InvalidProposal(f"`{name}.{change}` entries are "
                                          '{"term": …, "why": …} objects')
                term = " ".join(str(r.get("term") or "").split())
                why = str(r.get("why") or "").strip()
                where = f"{name}.{change} {term!r}"
                if not term:
                    raise InvalidProposal(f"an entry in `{name}.{change}` has no term")
                if "," in term:
                    raise InvalidProposal(f"{where}: a term cannot contain a comma — "
                                          "propose each term separately")
                if name == "categories" and not CATEGORY_RE.match(term):
                    raise InvalidProposal(f"{where}: not an arxiv category name — "
                                          "e.g. `quant-ph`, `physics.hist-ph`, `cs.AI`")
                if not why:
                    raise InvalidProposal(f"{where}: every change needs a `why` — the user "
                                          "approves reasons, not bare terms")
                k = _key(term)
                if k in seen:
                    raise InvalidProposal(f"{where} appears twice")
                seen.add(k)
                if change == "add" and k in current[name]:
                    raise InvalidProposal(f"{where}: already in {name}")
                if change == "drop" and k not in current[name]:
                    raise InvalidProposal(f"{where}: not in {name}, so there is nothing to drop")
                clean.append({"term": current[name].get(k, term) if change == "drop" else term,
                              "why": why})
            out[name][change] = clean
        added[name] = {_key(r["term"]) for r in out[name]["add"]}

    if not any(out[n][c] for n in LISTS for c in CHANGES):
        raise InvalidProposal("the proposal changes nothing")
    # A term can be an interest or an exclusion, not both: it would score itself to zero.
    for name, other in (TERM_LISTS, TERM_LISTS[::-1]):
        kept = (set(current[other]) - {_key(r["term"]) for r in out[other]["drop"]}) | added[other]
        clash = sorted(added[name] & kept)
        if clash:
            raise InvalidProposal(f"{', '.join(clash)} would be in both interests and exclude")
    for name in ("interests", "categories"):
        left = len(profile[name]) - len(out[name]["drop"]) + len(out[name]["add"])
        if left <= 0:
            raise InvalidProposal(f"the proposal would leave no {name}")
    return out


def describe(changes):
    """The proposal as the user should see it before approving: one line per change."""
    lines = []
    for name in LISTS:
        for change, mark in (("add", "+"), ("drop", "−")):
            for r in changes[name][change]:
                lines.append(f"  {mark} {name:<10} {r['term']}  — {r['why']}")
    return "\n".join(lines)


def apply(now=None):
    """Validate `state/interests.next.json`, apply it to the profile, record it in the
    history, and remove the draft. Returns `(profile_path, changes)`.

    Only call this once the user has approved the proposal as described."""
    profile = load()
    if profile is None:
        raise InvalidProposal(f"no profile at {path()} — seed one with `interests.sh init`")
    proposal = _read_json(draft_path())
    if proposal is None:
        raise InvalidProposal(f"no proposal at {draft_path()} — write it there first")
    changes = check(proposal, profile)

    for name in LISTS:
        drop = {_key(r["term"]) for r in changes[name]["drop"]}
        profile[name] = ([t for t in profile[name] if _key(t) not in drop]
                         + [r["term"] for r in changes[name]["add"]])
    now = now or _now()
    profile["updated_at"] = now
    entry = {"at": now, **{name: changes[name] for name in LISTS}}
    if str(proposal.get("note") or "").strip():
        entry["note"] = proposal["note"].strip()
    profile["history"].append(entry)

    _write_json(path(), profile)
    os.remove(draft_path())
    return path(), changes


def last_tuned(profile):
    """When a tuning last changed the profile, or "" if it never has.

    Seeding does not count: it copied the old lists in and judged nothing, so every paper
    decided before the first tuning is still new evidence to that tuning."""
    tuned = [h for h in (profile or {}).get("history") or [] if not h.get("seeded")]
    return tuned[-1]["at"] if tuned else ""


def gather(log=print):
    """The evidence a tuning session reads, as one dict.

    Everything `material.gather()` collects (recent notes, posts, misc, tweets, books and audua
    sessions), plus the papers you read, what only tuning needs: the profile itself and the
    papers you **rejected**, each with the terms that matched it — a rejected paper's
    `matched` list is the plainest evidence of which interest pulled the wrong paper in.
    Papers decided since the last tuning are marked, since those are the new evidence.
    """
    from . import material, status    # material imports config, which imports this lazily

    profile = load()
    since = last_tuned(profile)
    stated = {name: getattr(config, name)() for name in TERM_LISTS}
    # Papers come from the queue below, with rejections and since-last-tuning marks, so
    # material's own read-papers section would only be a second copy.
    data = material.gather(log=log, want_papers=False)
    q = status.Queue()

    def row(p):
        decided = p.get("changed_at") or ""
        return {"ref": p.get("id"), "title": p.get("title", ""),
                "primary_category": p.get("primary_category", ""),
                "decided_on": decided[:10],
                "since_last_tuning": not since or decided[:19] > since[:19],
                "matched": p.get("matched") or [],
                # Which profile terms caught this paper, matched exactly as the ranker
                # matches them (a phrase as a phrase). `matched` is the ranker's fuller
                # view, from when the paper was swept — corpus words included.
                "profile_hits": _hits(p.get("title", "") + " " + p.get("abstract", ""), stated),
                "why_queued": p.get("why") or "",
                "text": p.get("abstract", "")}

    def newest(status_name):
        return [row(p) for p in sorted(q.by_status(status_name),
                                       key=lambda p: p.get("changed_at") or "", reverse=True)]

    # Tweet-run bookkeeping and earlier prompt asks are material's for its own skills;
    # they say nothing about what a sweep should look for.
    for k in ("voice", "previous_tweets", "tweet_lessons", "previous_prompts"):
        data.pop(k, None)
    data["profile"] = {
        "exists": profile is not None,
        "source": "state/interests.json" if profile else "built-in defaults",
        "interests": config.interests(),
        "exclude": config.exclude(),
        "categories": config.categories(),
        "last_tuned": since,
        "history": (profile or {}).get("history", [])[-5:],
    }
    data["papers_read"] = newest("read")
    data["papers_rejected"] = newest("rejected")
    swept = _swept()
    data["term_stats"] = _term_stats(stated, q, swept)
    data["category_stats"] = _category_stats(q, swept)
    return data


def _swept():
    """The papers of the last `sweep.sh fetch` (`state/candidates.json`), or [] if none."""
    from . import candidates
    try:
        return candidates.load()["candidates"]
    except SystemExit:
        return []


def _text(p):
    return f"{p.get('title', '')} {p.get('abstract', '')}"


def _hits(text, stated):
    """`{list: [terms present in text]}`, matched the way the ranker matches: a single word
    as that exact word, a phrase as those words in a row (`rank.contains`)."""
    from . import rank
    return {name: [t for t in terms if rank.contains(text, t)] for name, terms in stated.items()}


def _term_stats(stated, q, swept):
    """For every profile term: how many read, rejected and freshly swept papers it matches.

    The swept count (the last sweep's candidates) is the firehose test: an interest in
    hundreds of a week's abstracts lifts most of the week, and an exclusion there sinks most
    of it. Read vs rejected is the precision test. Counts a script can make; what they mean
    is the session's call.
    """
    from . import rank
    groups = {"read": [_text(p) for p in q.by_status("read")],
              "rejected": [_text(p) for p in q.by_status("rejected")],
              "swept": [_text(p) for p in swept]}
    out = {name: {t: {g: sum(rank.contains(x, t) for x in texts)
                      for g, texts in groups.items()}
                  for t in terms}
           for name, terms in stated.items()}
    out["totals"] = {g: len(texts) for g, texts in groups.items()}
    return out


def _category_stats(q, swept):
    """Per primary category: read, rejected and swept counts, and whether it is swept now.

    Read papers in a category the profile does not sweep came in by search (or by a sweep
    under an older category list) — the clearest sign of a category worth adding. A swept
    category with many papers and nothing read or queued from it is the case for dropping
    one. Counts are by *primary* category, and a sweep fetches cross-listed papers too, so
    `swept` is non-zero for categories that were never asked for; those are left out unless
    a paper you decided on came from them."""
    from collections import Counter
    current = set(config.categories())
    read = Counter(p.get("primary_category") or "?" for p in q.by_status("read"))
    rejected = Counter(p.get("primary_category") or "?" for p in q.by_status("rejected"))
    sw = Counter(p.get("primary_category") or "?" for p in swept)
    cats = sorted(set(read) | set(rejected) | current,
                  key=lambda c: (-read[c], -sw[c], c))
    return {c: {"in_profile": c in current, "read": read[c], "rejected": rejected[c],
                "swept": sw[c]} for c in cats}


def write_material(data):
    return _write_json(material_path(), data)
