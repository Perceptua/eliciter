"""The prompt file: validate what a session wrote, then render it to markdown.

**The direction of this module reversed on 2026-08-30.** It used to take `Prompt` objects
built by `prompts.py` and emit both the markdown and a JSON index beside it. There is no
`prompts.py` any more — a session writes the prompts now, having read `state/material.json`
— so `state/prompts.json` is the *input* here and the markdown is derived from it.

That ordering is deliberate and it is what keeps the numbers honest. The numbers are the
interface: `scripts/write.sh 3` opens a session on prompt 3. When two artifacts are written
independently they drift, and the first thing to drift is which prompt is 3. So there is one
artifact a session produces — the JSON — and the markdown is a rendering of it, produced
here, never by hand.

`validate()` is the other half of that contract. A session is a good writer and an unreliable
typist: it will produce a register that is not one of the four, or omit `project`, or number
the prompts from zero. Everything derivable is derived here rather than trusted — `length`
and `project` come from the register via `signals.py`, and `n` is assigned by position — so
the only things a session actually has to get right are the ones only it can: the ask, the
register, the material it points at, and why.

House style is indexia's `recent/*.md`: a title, an italic provenance line saying what
generated the file and when it is overwritten, then sections. A run that finds nothing says
*why* — "quiet" and "broken" look identical in an empty file, and only one is your problem.
"""
from datetime import datetime, timedelta, timezone

from .signals import LENGTH, PROJECT, REGISTERS, SOURCES

# A staging filename is an indexia spec §4 id: a compact UTC timestamp to the millisecond.
# Rendering one into a note prompt means committing the answer is `cat > staging/<that>.md`
# with no detour through new-id.sh, which is worth keeping from the old pipeline.
#
# Ids are minted from one base instant plus the prompt's index, so every note prompt in a
# run gets a *distinct* one. Minting each independently from `now()` does not: a whole
# render happens inside a millisecond, so the first version handed every note prompt the
# same filename, and indexia — which refuses a duplicate id rather than overwriting —
# would have rejected the second thing you wrote.
_RUN_BASE = datetime.now(timezone.utc)


def _staging_commit(index):
    dt = _RUN_BASE + timedelta(milliseconds=index)
    sid = dt.strftime("%Y%m%dT%H%M%S") + f"{dt.microsecond // 1000:03d}Z"
    return (f"indexia/staging/{sid}.md — header then `---` then the body:\n"
            "   title: <your claim, as a sentence>")

SOURCE_HEADINGS = {
    "across": "Across your sources — what keeps recurring",
    "indexia": "From your notes — indexia",
    "perceptua": "From your writing — perceptua",
    "audua": "From your recordings — audua",
    "arxiv": "From your reading — arxiv",
}


class InvalidPrompts(ValueError):
    """What a session wrote is not a prompt file. The message names the prompt and field."""


def _clean_sources(raw):
    """A prompt's `sources` list: [{source, ref, title}], deduped, provenance only.

    Every prompt names the material it came from, and a prompt may legitimately name
    several — that is what replaced the old `confluence` special case. A cross-source
    prompt is now just a prompt with three entries here, so nothing downstream needs to
    know the difference: `write.sh` lists them in the brief and the UI makes each one
    openable, whether there is one or five.
    """
    out, seen = [], set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source") or "").strip()
        ref = str(item.get("ref") or "").strip()
        if not src or (src, ref) in seen:
            continue
        seen.add((src, ref))
        out.append({"source": src, "ref": ref,
                    "title": str(item.get("title") or "").strip(),
                    "why": str(item.get("why") or "").strip()})
    return out


def validate(raw):
    """Session output → the canonical prompt list. Raises `InvalidPrompts` on anything
    it cannot fix by derivation.

    Order is preserved exactly as written: the session decided what leads a run, having
    read everything, and re-sorting it here on a rule would overrule the only judgement in
    the pipeline that has actually read the material.
    """
    if not isinstance(raw, list):
        raise InvalidPrompts(f"expected a list of prompts, got {type(raw).__name__}")

    out = []
    for i, p in enumerate(raw, 1):
        where = f"prompt {i}"
        if not isinstance(p, dict):
            raise InvalidPrompts(f"{where}: expected an object, got {type(p).__name__}")

        register = str(p.get("register") or "").strip().lower()
        if register not in REGISTERS:
            raise InvalidPrompts(
                f"{where}: register {register!r} is not one of {', '.join(REGISTERS)}")

        for field in ("ask", "title"):
            if not str(p.get(field) or "").strip():
                raise InvalidPrompts(f"{where}: {field} is required")

        sources = _clean_sources(p.get("sources"))
        if not sources:
            raise InvalidPrompts(
                f"{where}: at least one entry in `sources` — a prompt with no provenance "
                "is the machine making something up")
        unknown = [s["source"] for s in sources if s["source"] not in SOURCES]
        if unknown:
            raise InvalidPrompts(
                f"{where}: unknown source(s) {', '.join(sorted(set(unknown)))}; "
                f"expected one of {', '.join(SOURCES)}")

        out.append({
            "n": i,                                  # assigned here, never trusted
            "register": register,
            "length": LENGTH[register],              # derived, not chosen
            "project": PROJECT[register],            # derived, not chosen
            "form": str(p.get("form") or register).strip(),
            "title": str(p["title"]).strip(),
            "ask": str(p["ask"]).strip(),
            "because": str(p.get("because") or "").strip(),
            # A session may say where a thing goes; when it does not, a note gets the
            # staging path minted above and everything else gets nothing. Derived rather
            # than asked for, because a session cannot mint a *unique* id per prompt
            # without being told this rule, and getting it wrong loses a draft.
            "commit": (str(p.get("commit") or "").strip()
                       or (_staging_commit(i) if register == "note" else "")),
            "sources": sources,
            "material": str(p.get("material") or "").strip(),
        })
    return out


def _section(prompt):
    """Which section a prompt belongs under: its single source, or 'across'.

    Sections are still the sources — a run reads as *your notes, your writing, your
    recordings, your reading* — but a prompt that draws on more than one no longer needs a
    source of its own to live in. It leads the file, because a prompt that crosses two
    corpora is the one thing in a run that could not have come from reading one of them.
    """
    srcs = {s["source"] for s in prompt["sources"]}
    return srcs.pop() if len(srcs) == 1 else "across"


def render(prompts, stats=None):
    stats = stats or {}
    now = datetime.now(timezone.utc)
    L = [f"# Elicitations — {now.strftime('%Y-%m-%d')}", ""]
    L += ["_Written by a Claude session from `state/material.json`; rendered by "
          "`scripts/prompts.sh render` and overwritten on each run. Every prompt names a "
          "site and a shape and stops there — what it is about is yours. eliciter reads "
          "indexia, audua, and perceptua through a read-only gate and writes to none of "
          "them; `scripts/write.sh <n>` opens a session where the writing belongs._", ""]

    if stats.get("gathered_at"):
        L += [f"_From material gathered {stats['gathered_at']}._", ""]

    if not prompts:
        L += ["## Nothing to ask", "",
              stats.get("quiet") or
              "No source produced anything worth asking about. That is a real answer — the "
              "queue is clear, the corpus is settled, and nothing is owed.", ""]
        return "\n".join(L)

    n_short = sum(1 for p in prompts if p["length"] == "short")
    L += [f"_{n_short} short · {len(prompts) - n_short} long._", ""]

    # Walk the run in the order the session wrote it, opening a section whenever the
    # section changes. Grouping by filtering instead would reorder the run, and the order
    # is a judgement the session made on purpose.
    section = None
    for p in prompts:
        sec = _section(p)
        if sec != section:
            section = sec
            L += [f"## {SOURCE_HEADINGS.get(sec, sec)}", ""]
        L += [f"### {p['n']}. {p['title']}", "", f"**{p['ask']}**", ""]
        if p["because"]:
            L += [p["because"], ""]
        for s in p["sources"]:
            line = f"↳ **{s['title'] or s['ref']}** ({s['source']} · `{s['ref']}`)"
            L += [line + (f" — {s['why']}" if s["why"] else ""), ""]
        if p["material"]:
            L += ["<details><summary>the material</summary>", "",
                  _quote(p["material"]), "", "</details>", ""]
        L += ["— " + " · ".join([f"`{p['form']}`", p["register"], p["length"]]), ""]
        if p["commit"]:
            L += [f"→ {p['commit']}", ""]
        L += [f"→ `bash scripts/write.sh {p['n']}` to write it in {p['project']}", ""]
    return "\n".join(L)


def _quote(text):
    """Blockquote a block, keeping blank lines inside it part of the quote. A bare blank
    line would end the quote and dump the rest of a poem into the page body."""
    return "\n".join(f"> {ln}" if ln.strip() else ">" for ln in text.splitlines())
