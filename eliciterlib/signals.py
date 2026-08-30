"""The two things that flow through eliciter: a Signal and a Prompt.

A **Signal** is something a source noticed — a paper waiting in the queue, a theme with no
hub note, a poem nothing has answered. Sources emit signals and know nothing about writing.

A **Prompt** is a signal turned into an ask. `prompts.py` does that turn, and the
register/form it chooses comes from the signal's source. Nothing else decides register.

Keeping these apart is what lets a fourth source be added without touching prompt
generation, and a register be retuned without touching any source.
"""
from dataclasses import dataclass, field

# Registers, and which of the two lengths each belongs to. The short/long split is how the
# rendered file is organised, because "have I got a short thing and a long thing to write
# today" is the question actually being asked of it.
REGISTERS = ("note", "verse", "essay", "journal")
LENGTH = {"note": "short", "verse": "short", "essay": "long", "journal": "long"}

# Source order, and it is the *first* thing a run is sorted by — above length, above
# register. Your own material leads: the graph first, then the posts, then audua, and the
# papers last. The reasoning is that indexia, perceptua and audua prompts are about work
# only you can continue, while a paper prompt is available to anyone who read the paper;
# when a run is long enough that you only get through the top of it, the part that should
# survive is the part nobody else could write. audua comes after perceptua: a poem already
# published is finished material asking for a reply, where an audua session is still raw
# and unreviewed — the graph's and perceptua's unfinished business outrank it. Length
# grouping still happens, but *within* a source now.
SOURCES = ("indexia", "perceptua", "audua", "arxiv")


def source_rank(source):
    """Position in `SOURCES`; an unknown source sorts last rather than raising."""
    try:
        return SOURCES.index(source)
    except ValueError:
        return len(SOURCES)


# Where the writing gets done. `scripts/write.sh` reads this to open a session in the right
# project, so it has to be the directory name, not a label.
PROJECT = {"note": "indexia", "essay": "indexia", "journal": "indexia", "verse": "perceptua"}


@dataclass
class Signal:
    """Something a source thinks is worth writing about.

    source      — 'arxiv' | 'indexia' | 'perceptua'; decides the register
    kind        — source-specific discriminator ('move4', 'orphan', 'post-response', …)
    title       — short human label
    detail      — the material, quoted into the prompt as context
    ref         — provenance a reader can follow: a note id, a post filename, an arxiv id
    score       — 0..1 salience, comparable *within* a source only
    meta        — anything the prompt builder needs; never rendered directly
    """
    source: str
    kind: str
    title: str
    detail: str = ""
    ref: str = ""
    score: float = 0.0
    meta: dict = field(default_factory=dict)


@dataclass
class Prompt:
    """An ask, ready to render.

    register/form   — what to write and in what shape ('note'/'atomic claim')
    ask             — the imperative put to the writer; the one line that matters
    because         — why this was surfaced now, in the writer's own material
    signal          — what it came from, for provenance and for sorting
    commit          — where the result goes
    """
    register: str
    form: str
    ask: str
    because: str
    signal: Signal
    commit: str = ""

    @property
    def length(self):
        return LENGTH.get(self.register, "short")

    @property
    def project(self):
        return PROJECT.get(self.register, "indexia")

    @property
    def rank(self):
        """Sort key: source order, then short before long, then register, then salience.

        Source leads, so a run reads as *your corpus, your posts, then your reading* rather
        than as a pile sorted by shape. Grouping still keeps it readable — the remaining
        keys mean one source's prompts arrive as three notes and an essay, not four
        interleaved moods — but the grouping is now nested under the source.

        `render.py` walks prompts in exactly this order and emits a heading whenever the
        source or register changes, so the printed order and this key cannot drift apart.
        """
        try:
            r = REGISTERS.index(self.register)
        except ValueError:
            r = len(REGISTERS)
        return (source_rank(self.signal.source),
                0 if self.length == "short" else 1, r, -self.signal.score)
