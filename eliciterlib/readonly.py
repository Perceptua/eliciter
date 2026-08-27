"""The read-only gate. Every source in this project is reached through here.

eliciter reads two corpora it does not own — the indexia graph and the perceptua posts —
and it must not be able to change either. "Must not" is enforced by code in this module
rather than by discipline elsewhere: the rest of the project has no access to a writable
handle, because the gated objects never expose one.

Three layers, because one is not enough:

1. **No write method exists.** `ReadOnlyGraph` has `query` and nothing else. It does not
   subclass `notelib.Arcade`, it *wraps* one and keeps it private, so `command`,
   `transaction` and `atomically` are not reachable by inheritance.
2. **Unknown attributes are refused, loudly.** `__getattr__` turns `db.command(...)` into
   a `ReadOnlyViolation` naming what was attempted, instead of an `AttributeError` some
   caller might catch and route around.
3. **The statement itself is checked.** Even `query` refuses SQL that is not a read.
   ArcadeDB's `/query` endpoint is not a guarantee of harmlessness, and this also catches
   the honest mistake of building a mutating statement and sending it down the read path.

The same shape applies to files: `ReadOnlyDir` can list and read inside one directory and
has no method that writes, creates, or deletes.

`verify_no_write_paths()` closes the loop by checking that the *rest of the project* only
imports the gate — see `tests/test_readonly.py`, which fails the build if a module reaches
for `notelib.Arcade` directly.
"""
import os
import re

import notelib


class ReadOnlyViolation(RuntimeError):
    """Raised when something tries to write through a gated handle."""


# Statements that change data or schema. Checked against the SQL with string literals
# removed, so a note whose body contains the word "delete" cannot trip the gate, and a
# statement that actually deletes cannot hide inside quotes.
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|REBUILD|IMPORT|"
    r"BACKUP|RESTORE|SET\s|UPSERT|MOVE\s+VERTEX)\b", re.IGNORECASE)

# A read starts with one of these. Anything else is refused outright rather than scanned,
# so an unrecognized statement form fails closed.
_READ_PREFIX = re.compile(r"^\s*(SELECT|MATCH|TRAVERSE|EXPLAIN|PROFILE)\b", re.IGNORECASE)

_LITERAL = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


def assert_read_only(sql):
    """Raise `ReadOnlyViolation` unless `sql` is a read. Public so tests can hit it."""
    if not isinstance(sql, str) or not sql.strip():
        raise ReadOnlyViolation(f"not a statement: {sql!r}")
    bare = _LITERAL.sub("''", sql)
    if not _READ_PREFIX.match(bare):
        raise ReadOnlyViolation(
            f"refused: a read must begin with SELECT/MATCH/TRAVERSE — got {sql.strip()[:80]!r}")
    hit = _WRITE_KEYWORDS.search(bare)
    if hit:
        raise ReadOnlyViolation(
            f"refused: {hit.group(1).upper()} is a write — {sql.strip()[:80]!r}")
    return sql


class ReadOnlyGraph:
    """A read-only handle on the indexia graph.

    Accepts anything that takes a `db` with `.query()` — which is every notelib move and
    `analytics.common.Corpus`, all of which are reads. Pass this where indexia's own code
    expects an `Arcade` and it will work; try to write through it and it will not.
    """

    __slots__ = ("_db",)

    def __init__(self, db=None):
        # Built here rather than accepted from a caller by default, so the only Arcade in
        # the process is the one this object has wrapped and hidden.
        object.__setattr__(self, "_db", db if db is not None else notelib.Arcade())

    def query(self, sql, params=None):
        assert_read_only(sql)
        return self._db.query(sql, params)

    # -- everything else is refused ------------------------------------------
    def __getattr__(self, name):
        # Dunders get the ordinary AttributeError. Raising ReadOnlyViolation for them
        # breaks `dir()`, `copy`, and anything that probes for an optional protocol — none
        # of which is an attempt to write, and all of which would be confusing to debug.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise ReadOnlyViolation(
            f"{name!r} is not available: eliciter reads indexia through a read-only gate "
            "(eliciterlib/readonly.py). Writing a note is something you do in indexia.")

    def __setattr__(self, name, value):
        raise ReadOnlyViolation(f"cannot set {name!r} on a read-only graph handle")

    def __repr__(self):
        return "<ReadOnlyGraph indexia>"


class ReadOnlyDir:
    """A read-only handle on a directory of files.

    Reads are confined to `root`: every path is resolved and checked to still be inside it,
    so a crafted name cannot walk out via `..` or a symlink. There is no method here that
    creates, writes, moves or removes anything.
    """

    __slots__ = ("_root",)

    def __init__(self, root):
        real = os.path.realpath(os.path.expanduser(root))
        if not os.path.isdir(real):
            raise SystemExit(f"not a directory: {root}")
        object.__setattr__(self, "_root", real)

    @property
    def root(self):
        return self._root

    def _resolve(self, name):
        path = os.path.realpath(os.path.join(self._root, name))
        if path != self._root and not path.startswith(self._root + os.sep):
            raise ReadOnlyViolation(f"path escapes {self._root}: {name!r}")
        return path

    def names(self):
        """Filenames directly inside the directory, sorted. No recursion, no directories."""
        return sorted(n for n in os.listdir(self._root)
                      if os.path.isfile(os.path.join(self._root, n)))

    def read(self, name):
        with open(self._resolve(name), encoding="utf-8") as fh:
            return fh.read()

    def __setattr__(self, key, value):
        raise ReadOnlyViolation(f"cannot set {key!r} on a read-only directory handle")

    def __repr__(self):
        return f"<ReadOnlyDir {self._root}>"


def graph():
    """The gated indexia handle. The only way this project reaches the database."""
    return ReadOnlyGraph()


def posts_dir(path):
    """The gated perceptua handle. The only way this project reaches the posts."""
    return ReadOnlyDir(path)
