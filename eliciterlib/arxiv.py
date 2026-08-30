"""Source — arxiv, swept natively.

This replaces the weekly digest that ran as a Claude Desktop task. That task's output lived
in a claude.ai conversation, which nothing on this machine can read, so the sweep happens
here: query the arxiv Atom API for everything submitted to your categories in the lookback
window, and hand it to `candidates.py`.

**What is left here is transport, not judgement.** This module used to score every abstract
against the interest profile and drop anything that matched no stated interest — a gate
that, measured on one real week, decided 642 of 1160 papers were not worth showing anyone.
Deciding which papers reach the reading queue is now a session's job over the candidate set
(`eliciterlib/candidates.py`, and the `reading-queue` skill). `build_profile` stays, because
ordering a long list by term overlap is still worth doing and still legible; it just no
longer excludes anything.

API notes, learned the hard way:
  * **HTTPS only.** `http://export.arxiv.org` answers 301 with an empty body, which reads
    as a silent failure if you only check for an exception.
  * arxiv asks for roughly one request every three seconds. `ELICITER_ARXIV_DELAY` enforces
    it between pages; do not lower it.
  * `sortBy=submittedDate&sortOrder=descending` is what makes the lookback window cheap —
    results arrive newest first, so paging stops at the first page that falls off the back
    of the window instead of walking the whole category.
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import notelib

from . import config, rank

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
PAGE = 100          # results per request; arxiv's own docs recommend paging at this size
USER_AGENT = "eliciter/1.0 (local personal writing tool; contact via arxiv account)"


def _text(el, path):
    node = el.find(path, NS)
    return " ".join(node.text.split()) if node is not None and node.text else ""


def _get(url, timeout=60, tries=3, log=None):
    """GET with a couple of retries.

    export.arxiv.org drops the occasional TLS handshake — observed once in a handful of
    sweeps here — and a weekly job that gives up on one blip is a weekly job that silently
    skips a week. Backoff is linear off the politeness delay rather than aggressive:
    the failure mode to avoid is hammering a public API that is already unhappy.
    """
    last = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    raise SystemExit(f"arxiv returned HTTP {r.status} for {url}")
                return r.read()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"arxiv returned HTTP {e.code} — {e.reason}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt < tries:
                wait = attempt * 5
                if log:
                    log(f"[arxiv] {type(e).__name__} — retrying in {wait}s "
                        f"({attempt}/{tries - 1})")
                time.sleep(wait)
    raise SystemExit(
        f"cannot reach arxiv after {tries} attempts ({last}) — eliciter needs outbound "
        "HTTPS for the sweep; everything else it does is local")


def _parse(xml_bytes):
    """Atom entries → paper dicts. Entries missing an id, title or abstract are dropped
    rather than half-populated; there is nothing to rank or read without all three."""
    root = ET.fromstring(xml_bytes)
    papers = []
    for e in root.findall("a:entry", NS):
        abs_url = _text(e, "a:id")
        title = _text(e, "a:title")
        summary = _text(e, "a:summary")
        if not abs_url or not title or not summary:
            continue
        # http://arxiv.org/abs/2012.12104v1 → 2012.12104v1
        ident = abs_url.rsplit("/abs/", 1)[-1]
        # `find` must be compared to None: an Element with no children is falsy, so the
        # usual `find(...) or {}` idiom silently discards every primary_category there is.
        pc = e.find("arxiv:primary_category", NS)
        papers.append({
            "id": ident,
            "title": title,
            "abstract": summary,
            "authors": [_text(a, "a:name") for a in e.findall("a:author", NS)],
            "published": _text(e, "a:published"),
            "updated": _text(e, "a:updated"),
            "primary_category": pc.get("term", "") if pc is not None else "",
            "categories": [c.get("term", "") for c in e.findall("a:category", NS)],
            "url": abs_url,
            "comment": _text(e, "arxiv:comment"),
        })
    return papers


def _published_dt(paper):
    try:
        return datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return None


def sweep(categories=None, lookback_days=None, max_results=None, delay=None, log=print):
    """Pull everything submitted to `categories` within the lookback window.

    Returns papers newest-first, deduplicated by arxiv id — a cross-listed paper comes
    back once per matching category and would otherwise be scored and queued twice.
    """
    categories = categories or config.categories()
    lookback_days = lookback_days if lookback_days is not None else config.i("ELICITER_ARXIV_LOOKBACK_DAYS")
    max_results = max_results if max_results is not None else config.i("ELICITER_ARXIV_MAX_RESULTS")
    delay = delay if delay is not None else config.f("ELICITER_ARXIV_DELAY")

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    query = " OR ".join(f"cat:{c}" for c in categories)
    seen, out, start = set(), [], 0

    while start < max_results:
        params = urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": min(PAGE, max_results - start),
        })
        log(f"[arxiv] fetching {start}–{start + PAGE} of ≤{max_results} …")
        page = _parse(_get(f"{API}?{params}", log=log))
        if not page:
            break

        stale = False
        for p in page:
            dt = _published_dt(p)
            if dt and dt < cutoff:
                stale = True          # newest-first, so everything after this is older too
                continue
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            out.append(p)

        if stale or len(page) < PAGE:
            break
        start += PAGE
        time.sleep(delay)

    log(f"[arxiv] {len(out)} paper(s) submitted since {cutoff.date()} across {len(categories)} category(ies)")
    return out


FIELD_PREFIX = re.compile(r"^(all|ti|au|abs|co|jr|cat|rn|id):", re.IGNORECASE)


def search(query, max_results=25, log=print):
    """Free-text arxiv search — the deliberate counterpart to the scheduled sweep.

    The sweep answers "what came out this week in my categories"; this answers "find me
    that paper". No date window and no interest gate: you asked for it by name, so it is
    not the profile's business whether it matches.

    A query already using an arxiv field prefix (`ti:`, `au:`, `cat:` …) is passed through
    untouched; anything else is wrapped in `all:` so plain words search every field.
    """
    query = (query or "").strip()
    if not query:
        return []
    term = query if FIELD_PREFIX.match(query) else f'all:{query}'
    params = urllib.parse.urlencode({
        "search_query": term,
        "sortBy": "relevance",
        "sortOrder": "descending",
        "start": 0,
        "max_results": max(1, min(int(max_results), PAGE)),
    })
    papers = _parse(_get(f"{API}?{params}", log=log))
    log(f"[arxiv] search {term!r} → {len(papers)} result(s)")
    return papers


def build_profile(db=None, log=print):
    """The interest profile a sweep is scored against: stated interests + your corpus.

    Assembled here rather than in `score` so a caller can inspect it — `--explain` prints
    it, which is the difference between tuning `ELICITER_INTERESTS` deliberately and
    guessing at it.
    """
    notes = []
    if db is not None:
        try:
            notes = notelib.rows(db.query(
                "SELECT id, title, body FROM Note WHERE status = 'active'"))
        except SystemExit as e:
            log(f"[arxiv] corpus unreadable, using stated interests only — {e}")

    prof = rank.profile(notes=notes, interests=config.interests(),
                        exclude=config.exclude())
    log(f"[arxiv] profile: {len(prof)} term(s) from {len(config.interests())} stated "
        f"interest(s) and {len(notes)} note(s)"
        + (f", {len(prof.banned)} excluded" if prof.banned else ""))
    return prof


def render_queue(queue, day=None, swept=None):
    """The digest as a reading queue: what is waiting, and what you have decided.

    Rendered from the queue rather than from a sweep, because the queue is what persists.
    A paper sits here until you mark it, and `scripts/papers.sh` is how you do that.
    """
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active = queue.active()
    read = queue.by_status("read")
    rejected = queue.by_status("rejected")

    L = [f"# Reading queue — {day}", ""]
    L += [f"_{len(active)} paper(s) waiting, capped at {config.i('ELICITER_ARXIV_KEEP')}. "
          + (f"Last sweep looked at {swept}. " if swept is not None else "")
          + "Generated by `scripts/sweep.sh accept`; each paper is here because a session "
          "read the week and chose it. Mark them with `scripts/papers.sh read|reject "
          "<id>` — a rejected paper never comes back, and a read one frees a slot._", ""]

    if not active:
        L += ["_Nothing waiting. Sweep the week with `scripts/sweep.sh fetch` and ask a "
              "session to pick — see the reading-queue skill._", ""]

    for i, p in enumerate(active, 1):
        authors = ", ".join(p.get("authors", [])[:4])
        if len(p.get("authors", [])) > 4:
            authors += " et al."
        matched = ", ".join(f"`{m}`" for m in (p.get("matched") or [])[:8])
        L += [f"## {i}. {p['title']}",
              "",
              f"`{p['id']}` · {p.get('primary_category', '')} · {authors}",
              ""]
        # `why` is the session's one line on why this paper and not the four hundred
        # others; the overlap score and matched terms ride along underneath as provenance,
        # not as the reason. Before, the score *was* the reason, which is what made the
        # queue hard to trust.
        if p.get("why"):
            L += [f"**{p['why']}**", ""]
        L += [(f"_overlap {float(p.get('score', 0)):.2f} · {matched}_" if matched
               else f"_overlap {float(p.get('score', 0)):.2f}_"),
              "",
              p.get("abstract", ""),
              "",
              f"<{p.get('url', '')}>",
              "",
              f"→ `bash scripts/papers.sh read {p['id']}` · "
              f"`bash scripts/papers.sh reject {p['id']}`",
              ""]

    if read or rejected:
        L += ["---", "",
              f"_Decided: **{len(read)}** read, **{len(rejected)}** rejected. "
              "`scripts/papers.sh list --all` shows them._", ""]
    return "\n".join(L)
