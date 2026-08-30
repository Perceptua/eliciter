"""What flows through eliciter, and the vocabulary a prompt is written in.

A **Signal** is something a source noticed — a note the corpus is leaning on, a session
nothing has answered. Sources emit signals and know nothing about writing; `material.py`
serializes them into `state/material.json` for a session to read.

There used to be a `Prompt` here too, built by a `prompts.py` that turned each signal into
an ask by rule. That is gone (2026-08-30). A prompt is now written by a Claude session that
has read the material, and lives as JSON in `state/prompts.json`; `render.py` validates it
and renders it. So what is left of prompt-shape in this module is the small closed
vocabulary a session has to write *in* — the four registers, and what each one implies —
because those are the things `write.sh` routes on and they cannot be free text.

The registers are unchanged, and so is what they mean. What changed is who chooses.
"""
from dataclasses import dataclass, field

# The four registers, and which of the two lengths each belongs to. The short/long split is
# how the rendered file is summarized, because "have I got a short thing and a long thing to
# write today" is the question actually being asked of it.
REGISTERS = ("note", "verse", "essay", "journal")
LENGTH = {"note": "short", "verse": "short", "essay": "long", "journal": "long"}

# Where the writing gets done. `scripts/write.sh` reads this to open a session in the right
# project, so it has to be the directory name, not a label. **Derived from the register,
# never chosen** — a session picks the register and this settles the rest, so there is no
# way to write a prompt that asks for verse and routes to indexia.
PROJECT = {"note": "indexia", "essay": "indexia", "journal": "indexia", "verse": "perceptua"}

# The corpora a prompt may cite. `render.validate` refuses provenance outside this list: a
# prompt naming a source that does not exist is a prompt whose material cannot be opened,
# which is the shape a made-up citation takes here.
#
# The order is the order sections appear in a rendered run, for prompts that cite exactly
# one source. Your own material leads and the papers come last: an indexia, perceptua or
# audua prompt continues work only you can continue, while a paper prompt is available to
# anyone who read the paper, so when you only get through the top of a run the part that
# survives is the part nobody else could write. audua sits after perceptua because a
# published poem is finished material asking for a reply, where a recording is still raw.
#
# A prompt citing *several* sources is not in this list at all — it heads the file under
# "across", because crossing two corpora is the one thing reading one of them could not
# have produced.
SOURCES = ("indexia", "perceptua", "audua", "arxiv")


def source_rank(source):
    """Position in `SOURCES`; an unknown source sorts last rather than raising."""
    try:
        return SOURCES.index(source)
    except ValueError:
        return len(SOURCES)


@dataclass
class Signal:
    """Something a source thinks is worth a reader's attention.

    Note what this no longer claims. It used to carry a `score` that decided which signals
    became prompts, and sources competed on it. Now every signal a source produces reaches
    the session, and `score` is only the source's own note of salience — how loud move 7
    thinks a piece of structural debt is — passed along as one input among many rather than
    as a ranking anything is obliged to honour.

    source      — 'indexia' | 'perceptua' | 'audua' | 'arxiv'
    kind        — source-specific discriminator ('move4', 'orphan', 'post-response', …)
    title       — short human label
    detail      — the excerpt the source considers salient
    ref         — provenance a reader can follow: a note id, a post filename, an arxiv id
    score       — 0..1 salience, comparable *within* a source only
    meta        — the rest, including `meta["text"]`: the whole material, not the excerpt
    """
    source: str
    kind: str
    title: str
    detail: str = ""
    ref: str = ""
    score: float = 0.0
    meta: dict = field(default_factory=dict)
