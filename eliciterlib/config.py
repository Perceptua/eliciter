"""Configuration, path wiring, and the one import that makes eliciter possible.

eliciter does not reimplement indexia's client. It puts `indexia/scripts` on the
path and imports `notelib` — the same module `add-note.sh` and the provocation
digest use — so a query here and a query there are the same query. `bootstrap()`
is what makes that import legal: notelib's `Arcade` reads BASE_URL / DB /
ARCADEDB_ROOT_PASSWORD from the environment and exits if any is missing, and
those come from indexia's `docker/.env`, which is the only place the password
is stored.

Read-only by construction, not by contract: nothing here hands out a writable handle.
`corpus.connect()` returns a gated `readonly.ReadOnlyGraph`, and `tests/test_readonly.py`
fails the build if any module in this project builds an `Arcade` of its own. What you write
in response to a prompt goes back through indexia's own workflows (`staging/`,
`add-note.sh`), which is where the Op log and embed-on-commit live.
See README §"Read-only, structurally".
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "ELICITER_INDEXIA_ROOT": "/home/aphorikles/indexia",
    "ELICITER_PERCEPTUA_POSTS": "/home/aphorikles/perceptua/perceptua/_posts",
    "ELICITER_ARXIV_CATEGORIES": "cs.AI,cs.LG,cs.NE,q-bio.NC,nlin.AO",
    "ELICITER_ARXIV_LOOKBACK_DAYS": "7",
    "ELICITER_ARXIV_MAX_RESULTS": "300",
    "ELICITER_ARXIV_DELAY": "3.0",
    "ELICITER_ARXIV_KEEP": "10",
    "ELICITER_INTERESTS": (
        "agency, agents, goal-directed behaviour, collective intelligence, basal cognition, "
        "morphogenesis, causal emergence, alignment, learnable novelty, autopoiesis, "
        "self-organization, active inference, developmental biology, cognitive boundaries"),
    "ELICITER_EXCLUDE": ("benchmark, leaderboard, refactor, payment, vulnerability, "
                         "malware, software engineering, code generation"),
    "ELICITER_MAX_PROMPTS": "7",
    # 8473 deliberately: 8420 is indexia's UI, and 8080/8765 are asked to stay free.
    "ELICITER_UI_PORT": "8473",
}


def _load_env_file(path):
    """Parse a KEY=value file into a dict. Deliberately minimal: no export, no
    interpolation, no quotes beyond a single surrounding pair — that is all
    indexia's docker/.env uses, and a fuller parser would be a second, subtly
    different reading of a file someone else owns."""
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def _apply(env, override=False):
    for k, v in env.items():
        if override or k not in os.environ:
            os.environ[k] = v


def bootstrap():
    """Load config, export what notelib needs, and put indexia/scripts on sys.path.

    Order matters and is the whole point: eliciter's own `.env` is read first but
    never overrides a variable already exported by the shell wrapper, then
    indexia's `docker/.env` supplies the secret and the port. Idempotent.
    """
    _apply(_load_env_file(os.path.join(ROOT, ".env")))
    _apply(DEFAULTS)

    indexia_root = os.environ["ELICITER_INDEXIA_ROOT"]
    scripts = os.path.join(indexia_root, "scripts")
    if not os.path.isdir(scripts):
        raise SystemExit(
            f"indexia not found at {indexia_root} — set ELICITER_INDEXIA_ROOT in "
            f"{os.path.join(ROOT, '.env')} to wherever the indexia repo lives")

    ix = _load_env_file(os.path.join(indexia_root, "docker", ".env"))
    if not ix.get("ARCADEDB_ROOT_PASSWORD"):
        raise SystemExit(
            f"no ARCADEDB_ROOT_PASSWORD in {indexia_root}/docker/.env — eliciter reads "
            "indexia's secret rather than keeping a second copy; fill that file in first")
    _apply(ix)

    # notelib.Arcade reads exactly these three.
    port = os.environ.get("INDEXIA_HTTP_PORT", "2480")
    os.environ.setdefault("BASE_URL", os.environ.get("INDEXIA_URL", f"https://localhost:{port}"))
    os.environ.setdefault("DB", os.environ.get("INDEXIA_DB", "indexia"))

    if scripts not in sys.path:
        sys.path.insert(0, scripts)


# ---- typed accessors --------------------------------------------------------
# Read after bootstrap(). Each coerces once, so a bad value fails at startup with
# the name of the setting rather than deep inside a scoring loop.

def _num(name, cast):
    raw = os.environ.get(name, DEFAULTS.get(name, ""))
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise SystemExit(f"{name}={raw!r} is not a valid {cast.__name__}")


def s(name):
    return os.environ.get(name, DEFAULTS.get(name, ""))


def i(name):
    return _num(name, int)


def f(name):
    return _num(name, float)


def categories():
    return [c.strip() for c in s("ELICITER_ARXIV_CATEGORIES").split(",") if c.strip()]


def interests():
    """What you have said you care about, independent of what you have written about.

    This is the one knob worth revisiting regularly: it is how a sweep learns about an
    interest before the corpus has a note on it.
    """
    return [t.strip() for t in s("ELICITER_INTERESTS").split(",") if t.strip()]


def exclude():
    """Terms that disqualify a paper. The counterweight to `interests()`.

    Needed because bag-of-words has no way to tell your sense of a word from the field's:
    `agents` means Levin's cells to you and LLM tool-callers to most of cs.AI in 2026, and
    the sweep cannot separate them without being told.
    """
    return [t.strip() for t in s("ELICITER_EXCLUDE").split(",") if t.strip()]


def posts_dir():
    return os.environ["ELICITER_PERCEPTUA_POSTS"]


def out_dir(name):
    """A writable output directory under the project root, created on demand."""
    d = os.path.join(ROOT, name)
    os.makedirs(d, exist_ok=True)
    return d
