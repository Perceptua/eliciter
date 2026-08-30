"""Relevance: which swept papers are worth your attention.

Scoring is **term overlap against an interest profile**, and there is no embedding
anywhere in it. That is a deliberate reversal, and the reason is measured rather than
assumed: on this machine mxbai-embed-large runs on CPU at roughly 0.6s per token, so one
arxiv abstract costs 1–3 minutes and a modest weekly sweep is a half-hour to hour-long
job. What that bought was catching papers that share meaning but not vocabulary —
generalized from a four-note corpus, which is not enough to generalize from. The cost was
certain and the benefit was speculative, so it went.

What replaced it is better in two ways beyond being instant. The profile is **explicit**
(`ELICITER_INTERESTS`), so you can state an interest before you have written a note about
it — a cold-start the corpus-similarity version could not do at all. And the score is
**legible**: the digest can name the terms that matched, which says why a paper surfaced
far more usefully than a cosine number.

If the embedder ever gets a GPU, semantic ranking is worth revisiting as a second pass
over the top of this one. It is not worth it as the only pass.
"""
import math
import re

# Common English plus academic-abstract boilerplate. These carry no signal about what a
# paper is *about*, and left in they dominate the overlap — every abstract "presents a
# novel approach" and would score alike.
#
# The last two lines were added 2026-08-30, after the perceptua prompts started reporting
# a poem as matching on `whose`, `too` and `because`. That is a real overlap and a useless
# one, and it was visible because `because` lines *name* the matched terms — the legibility
# `rank.py` was built for catching a defect in `rank.py`. Nothing here is subject matter in
# any source, so removing them only ever takes noise out of a score.
STOPWORDS = frozenset("""
a an and are as at be been but by can could do does for from had has have how i if in into is it
its may might must no not of on or our should so than that the their then there these they this
to up was we were what when which while who will with would you your us more most other such
paper papers show shows study studies result results method methods approach approaches propose
proposed present presents using use used new novel model models work works based via framework
task tasks data datasets experiments experimental performance state art also however first second
one two three both each also many much well often within without under over between across
after against all am another any anything because been before being below beyond does done
during either else enough even ever every everything far few further get give go had having
here him his her hers hence i'm into itself just least less let like little made make many
me mine my nor now off once only onto or others out own per rather same she since some
someone something still such take than themselves therefore thing things those though
through thus too toward towards until upon very via what whatever when where whereas
whether which while who whom whose why yet you your yours nothing anyone nobody everyone
cannot them their theirs him himself herself myself ourselves yourself itself was wasn't
isn't don't doesn't didn't won't can't couldn't wouldn't shouldn't it's that's there's
""".split())

WORD_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")

# An explicitly stated interest outweighs a word that merely appears in a note, and by a
# lot. The first run without this gap put an agent-payments security paper and a histology
# model in the top five: they matched eight corpus words each — `system`, `language`,
# `capacity`, `structure`, `supervision` — and eight generic hits at ~0.7 outscored two
# real ones. Corpus terms are a tie-breaker among papers that are already relevant, not a
# way to become relevant.
INTEREST_WEIGHT = 3.0
CORPUS_WEIGHT = 0.4

# Each distinct excluded term an abstract contains costs it this much. A penalty rather
# than a hard drop, because the words that mark a paper as off-topic for you — `benchmark`,
# `retrieval` — also appear in passing in papers that are on-topic. One mention is survivable;
# a paper *about* the excluded thing accumulates several and sinks, which is the intent.
EXCLUDE_WEIGHT = 2.0


def terms(text):
    return [w for w in WORD_RE.findall((text or "").lower()) if w not in STOPWORDS]


def profile(notes=(), interests=(), exclude=()):
    """Build term → weight from what you care about: stated interests, plus your notes.

    Two inputs, deliberately unequal:
      * `interests` — stated outright in `.env`. Fixed weight, and works from cold.
      * `notes`     — indexia note titles and bodies, weighted `log(1 + occurrences)` so a
                      word used constantly does not swamp one used precisely.

    **perceptua is deliberately not an input.** Its keywords are poetic forms — `verse`,
    `poetry`, `sestina` — and feeding seventeen posts' worth of them in made them the
    heaviest terms in the profile, which is exactly backwards for ranking arxiv. The posts
    source earns its own prompts elsewhere; what it does not get to do is decide which
    papers are interesting.

    Multi-word interests ("collective intelligence") contribute their words individually,
    since scoring is bag-of-words. That slightly over-credits a paper matching only half a
    phrase, which is the acceptable direction to be wrong in for a shortlist.
    """
    weights, stated = {}, set()
    for phrase in interests:
        for w in terms(phrase):
            weights[w] = weights.get(w, 0.0) + INTEREST_WEIGHT
            stated.add(w)

    tf = {}
    for n in notes:
        for w in terms(f"{n.get('title') or ''} {n.get('body') or ''}"):
            tf[w] = tf.get(w, 0) + 1
    for w, c in tf.items():
        weights[w] = weights.get(w, 0.0) + CORPUS_WEIGHT * math.log(1 + c)

    banned = {w for phrase in exclude for w in terms(phrase)}
    # An exclusion always wins: if a word is both stated and excluded, the exclusion is the
    # more specific, more recent instruction, and silently ignoring it would be baffling.
    for w in banned:
        weights.pop(w, None)
        stated.discard(w)
    return Profile(weights, stated, banned)


class Profile:
    """Term weights, which of them you stated outright, and which are disqualifying.

    The split is what lets scoring *gate* on interests while still *ranking* with the
    corpus — two different jobs that a single flat dict cannot tell apart.
    """

    def __init__(self, weights, stated, banned=frozenset()):
        self.weights = weights
        self.stated = stated
        self.banned = banned

    def __len__(self):
        return len(self.weights)

    def __bool__(self):
        return bool(self.weights)

    def items(self):
        return self.weights.items()


def overlap(text, prof):
    """→ (score, matched terms), **with no interest gate**. Ordering, not judgement.

    `score()` below refuses anything that matches no stated interest, and that gate is
    right when term overlap is the *only* filter — it is what stops a payments-protocol
    paper reaching the queue on eight generic hits. It is wrong when a reader is the second
    stage. Measured on one real week: 1160 papers swept, 518 past the gate. Whatever was in
    the other 642, no human ever saw it, and "shares no vocabulary with your stated
    interests" is not the same fact as "is not for you" — a paper on regeneration in
    planaria need never say `morphogenesis`.

    So this is the ordering function for a shortlist a session will actually read: every
    paper keeps a score, nothing is dropped, and the score is a hint about where to look
    first rather than a verdict about what exists.
    """
    seen = set(terms(text))
    if not seen or not prof:
        return 0.0, []
    matched = sorted((w for w in seen if w in prof.weights), key=lambda w: -prof.weights[w])
    if not matched:
        return 0.0, []
    total = sum(prof.weights[w] for w in matched)
    total -= EXCLUDE_WEIGHT * len(seen & prof.banned)
    # Exclusions can drive this negative, and a negative is meaningful here where it was
    # not before: it says the paper is *about* something you ruled out. Kept rather than
    # zeroed so the ordering puts it below a paper that merely matched nothing.
    return total / math.sqrt(len(seen)), matched


def score(text, prof):
    """→ (score, matched terms). Higher is more relevant; 0.0 means "not for you".

    **A paper must match at least one stated interest to score at all.** Matching only
    corpus vocabulary is not enough, because every ML abstract shares vocabulary with any
    corpus about learning agents — that is what made the first version return a payments
    protocol paper. The gate is what `ELICITER_INTERESTS` is *for*; the corpus terms then
    order what got through.

    Distinct terms only — an abstract saying "agent" thirty times is not thirty times more
    relevant — and normalized by the square root of its own vocabulary size, so a long
    abstract cannot out-score a short one on sheer volume. The square root rather than the
    length itself: dividing by the full count over-punishes long abstracts, which is how
    survey papers, often exactly what you want, get buried.
    """
    seen = set(terms(text))
    if not seen or not prof:
        return 0.0, []
    matched = sorted((w for w in seen if w in prof.weights), key=lambda w: -prof.weights[w])
    if not any(w in prof.stated for w in matched):
        return 0.0, []
    total = sum(prof.weights[w] for w in matched)
    total -= EXCLUDE_WEIGHT * len(seen & prof.banned)
    if total <= 0.0:
        return 0.0, []
    return total / math.sqrt(len(seen)), matched
