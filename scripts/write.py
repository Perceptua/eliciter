#!/usr/bin/env python3
"""Open a writing session in indexia or perceptua, seeded with a prompt.

eliciter is read-only over both projects, so the writing happens *there*, in a session that
has that project's own tools, skills and conventions. This is the handoff: it resolves a
prompt number, works out which project it belongs to, and starts a Claude Code session in
that directory with the prompt as the opening context.

  scripts/write.sh              # list what is on offer
  scripts/write.sh 3            # write prompt 3, in whichever project it belongs to
  scripts/write.sh indexia      # open a session in indexia with no particular prompt
  scripts/write.sh 3 --print    # show the seed text and the command, launch nothing

The seed text tells the session what to write and where it goes, and says plainly that the
material was gathered read-only — so the session does the writing and the committing, which
is the half eliciter deliberately cannot do.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

PROJECT_DIRS = {
    "indexia": lambda: os.environ["ELICITER_INDEXIA_ROOT"],
    # posts live at <repo>/_posts, so the project root is its parent.
    "perceptua": lambda: os.path.dirname(os.path.abspath(config.posts_dir())),
}


def load_prompts():
    path = os.path.join(config.out_dir("state"), "prompts.json")
    if not os.path.isfile(path):
        raise SystemExit(
            "no prompts yet — `bash scripts/gather.sh`, then ask a session for prompts")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("prompts", [])


def seed_text(p):
    """What the new session is told. Deliberately a brief, not a draft.

    It states the ask, the material it came from, and where the result goes, and stops.
    eliciter does not write the thing and does not suggest what it should say — that
    boundary is the point of the project, and it would be odd to hold it everywhere except
    at the moment of handoff.

    The prompt itself was written by a session that had read the whole corpus; this one has
    not, so every source is named with its ref and the session is told to go and read them.
    A prompt that draws on three things is not summarized down to one here.
    """
    lines = [
        f"I want to write this. It came from eliciter (prompt {p['n']}).",
        "",
        f"**{p['ask']}**",
        "",
        f"- form: {p['form']} ({p['length']} form)",
    ]
    if p.get("because"):
        lines += [f"- why it surfaced: {p['because']}"]
    if p.get("commit"):
        lines += [f"- where it goes: {p['commit']}"]

    sources = p.get("sources") or []
    if sources:
        lines += ["", "What it draws on — read these before drafting:", ""]
        for srec in sources:
            line = f"- **{srec.get('title') or srec.get('ref')}** " \
                   f"({srec.get('source', '')} · `{srec.get('ref', '')}`)"
            if srec.get("why"):
                line += f" — {srec['why']}"
            lines += [line]
        lines += ["",
                  "You can read any of them from this repo: notes are in indexia, posts in "
                  "perceptua/_posts, recordings in audua's output as summary.md, papers on "
                  "arxiv. eliciter reads all of them read-only."]

    if p.get("material"):
        lines += ["", "The part that prompted it:", "", "```", p["material"].strip(), "```"]

    lines += [
        "",
        "Help me write it here. eliciter gathered this read-only and cannot commit "
        "anything; this project's own tools do that. Ask me what I actually think before "
        "drafting — the claim should be mine.",
    ]
    return "\n".join(lines)


def launch(project, text, dry):
    cwd = PROJECT_DIRS[project]()
    if not os.path.isdir(cwd):
        raise SystemExit(f"{project} is not at {cwd} — check .env")
    claude = shutil.which("claude")
    if dry or not claude:
        if not claude and not dry:
            print("claude CLI not found on PATH; showing the session brief instead.\n",
                  file=sys.stderr)
        print(f"# cd {cwd} && claude\n")
        print(text)
        return 0
    print(f"[write] opening a session in {project} ({cwd})", file=sys.stderr)
    # Hand the terminal over. The session is interactive and belongs to the user, so this
    # replaces the process rather than capturing it.
    return subprocess.call([claude, text], cwd=cwd)


def main():
    p = argparse.ArgumentParser(prog="write", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", nargs="?",
                   help="a prompt number, or a project name (indexia|perceptua)")
    p.add_argument("--print", dest="dry", action="store_true",
                   help="show the brief and the command; launch nothing")
    a = p.parse_args()

    if a.target in PROJECT_DIRS:
        return launch(a.target, f"I want to do some writing in {a.target}.", a.dry)

    prompts = load_prompts()
    if a.target is None:
        if not prompts:
            print("no prompts — gather, then ask a session for them")
            return 0
        print("on offer:\n")
        for p_ in prompts:
            print(f"  {p_['n']:>2}. [{p_['length']:<5} {p_['project']:<9}] "
                  f"{p_['title'][:58]}")
        print("\nwrite one with:  bash scripts/write.sh <n>")
        return 0

    if not a.target.isdigit():
        raise SystemExit(f"{a.target!r} is neither a prompt number nor a project name")
    match = next((x for x in prompts if x["n"] == int(a.target)), None)
    if match is None:
        raise SystemExit(f"no prompt {a.target} — there are {len(prompts)}")
    return launch(match["project"], seed_text(match), a.dry)


if __name__ == "__main__":
    sys.exit(main() or 0)
