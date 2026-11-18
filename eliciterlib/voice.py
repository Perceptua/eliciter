"""The voice profile: how you sound, written down so drafted tweets can sound like it.

`state/voice.md` is written by a Claude session (the `elicit-tweets` skill), the same way
`state/prompts.json` is: the script gathers, the session judges. It is built from your
tweets, which set the register, and from your notes, perceptua posts and misc writing,
which supply the vocabulary and preoccupations. It is gitignored with the rest of `state/`.

This module does only what a script can do reliably:

  * **say when the profile is stale.** The file carries a machine-readable stamp — when it
    was built and how many tweets it was built from. If the number of tweets has changed
    since (an import, or a posted draft saved back), it is stale. Counting rather than
    comparing dates matters: an imported archive is full of *old* tweets that are new to
    the profile.
  * **check a rebuild before it replaces the old one.** Every section must be present, and
    the `## Yours` section — the part you write by hand — must come through byte for byte.
    A session rebuilding the profile cannot quietly drop your edits.
  * **stamp it.** `install()` writes the provenance line and the stamp itself, so a session
    never has to get a timestamp or a count right.

Nothing rebuilds it on a schedule. A session rebuilds it when it is stale, as part of a
tweets run, or when you ask.
"""
import os
import re
from datetime import datetime, timezone

from . import config

NAME = "voice.md"
DRAFT = "voice.next.md"

# The sections a profile must have, in order. `Yours` is the user's; the rest are the
# session's and are rewritten on every rebuild.
SECTIONS = ("Register", "Vocabulary", "Preoccupations", "What lands", "Examples", "Yours")

_STAMP = re.compile(r"<!--\s*voice:\s*built_at=(\S+)\s+tweets=(\d+)\s*-->")
_PROVENANCE = re.compile(r"^_Built .*_\s*$", re.M)


class InvalidVoice(ValueError):
    """A rebuilt profile that would lose something. The message says what."""


def path():
    return os.path.join(config.out_dir("state"), NAME)


def draft_path():
    return os.path.join(config.out_dir("state"), DRAFT)


def _read(p):
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def stamp(text):
    """`(built_at, n_tweets)` from a profile's stamp, or `(None, None)`."""
    m = _STAMP.search(text or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def load(n_tweets=None):
    """The current profile, and whether it is stale against `n_tweets`.

    `n_tweets` is the number of tweets there are now; pass None to skip the staleness
    judgement (it is then reported as unknown rather than guessed).
    """
    text = _read(path())
    built_at, built_from = stamp(text)
    out = {"exists": text is not None, "built_at": built_at or "",
           "built_from": built_from, "text": text or ""}
    if n_tweets is not None:
        out["tweets_now"] = n_tweets
        out["tweets_since"] = (n_tweets - built_from) if built_from is not None else n_tweets
        out["stale"] = text is None or built_from is None or built_from != n_tweets
    return out


def sections(text):
    """`{heading: body}` for every `## ` section. The stamp is not part of any section —
    it trails the file, so without this it would read as the end of `## Yours`."""
    out, current, buf = {}, None, []
    for line in _STAMP.sub("", text or "").splitlines():
        if line.startswith("## "):
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current, buf = line[3:].strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


def yours(text):
    """The hand-written section, exactly as it stands."""
    return sections(text).get("Yours", "")


def check(new_text, old_text=None):
    """Raise `InvalidVoice` unless `new_text` is a complete profile that keeps `## Yours`."""
    if not (new_text or "").strip():
        raise InvalidVoice("the profile is empty")
    got = sections(new_text)
    missing = [s for s in SECTIONS if s not in got]
    if missing:
        raise InvalidVoice(f"missing section(s): {', '.join('## ' + s for s in missing)}")
    for s in SECTIONS[:-1]:
        if not got[s]:
            raise InvalidVoice(f"## {s} is empty")
    if old_text is not None and yours(old_text) != got["Yours"]:
        raise InvalidVoice(
            "## Yours changed — that section is written by hand and must be carried over "
            "exactly. Copy it from state/voice.md into the rebuild unchanged.")
    return got


def install(n_tweets, now=None):
    """Validate `state/voice.next.md` against the current profile, stamp it, and move it
    into place. Returns the installed path."""
    draft = _read(draft_path())
    if draft is None:
        raise InvalidVoice(f"no draft at {draft_path()} — write the rebuild there first")
    old = _read(path())
    check(draft, old)

    now = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (f"_Built {now} by a Claude session from {n_tweets} tweets plus notes, perceptua "
            "and misc. Rebuilt when the tweets change; `## Yours` is never touched._")
    # Derived, not trusted: drop whatever provenance and stamp the session wrote, then put
    # the real ones in — the line under the title, the stamp at the end.
    lines = _PROVENANCE.sub("", _STAMP.sub("", draft)).strip().splitlines()
    if not lines or not lines[0].startswith("# "):
        lines = ["# Voice"] + lines
    rest = "\n".join(lines[1:]).strip("\n")
    body = "\n".join([lines[0], "", line, "", rest]).rstrip()
    body += f"\n\n<!-- voice: built_at={now} tweets={n_tweets} -->\n"

    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp, path())
    os.remove(draft_path())
    return path()
