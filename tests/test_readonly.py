"""The read-only guarantee, tested.

Two halves, and both matter. The first tests that the gate *refuses* writes. The second
scans this project's own source and fails if any module reaches around the gate — because a
perfect gate is worth nothing if `corpus.py` can quietly construct a `notelib.Arcade` of its
own. That scan is the reason the guarantee is structural rather than a convention.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import readonly                     # noqa: E402

LIB = os.path.join(config.ROOT, "eliciterlib")
SCRIPTS = os.path.join(config.ROOT, "scripts")

# Only readonly.py may construct a raw client or touch the write API.
GATE_FILE = "readonly.py"
FORBIDDEN = [
    (re.compile(r"notelib\.Arcade\s*\("), "constructs a raw ArcadeDB client"),
    (re.compile(r"\.command\s*\("), "calls the mutating .command() API"),
    (re.compile(r"\.atomically\s*\("), "opens a write transaction"),
    (re.compile(r"notelib\.Ingestor"), "uses the note-writing Ingestor"),
    (re.compile(r"notelib\.insert_\w+"), "calls a notelib insert"),
]


_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def _code(line):
    """A source line with comments and string literals removed.

    Both have to go. Without stripping comments the scanner trips on prose about writing;
    without stripping literals it trips on its own error messages — `doctor.py` says the
    words ".command()" in a diagnostic, which is talk about a write, not a write.
    """
    return _LITERAL.sub("''", line).split("#", 1)[0]


def _sources():
    for d in (LIB, SCRIPTS):
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                yield name, os.path.join(d, name)


class TestStatementGate(unittest.TestCase):
    def test_allows_reads(self):
        for sql in ("SELECT id FROM Note",
                    "  select count(*) as n from Note where status = 'active'",
                    "MATCH {type: Note, as: n} RETURN n",
                    "SELECT body FROM Note WHERE body = 'we should delete this'"):
            self.assertEqual(readonly.assert_read_only(sql), sql)

    def test_refuses_writes(self):
        for sql in ("DELETE FROM Note",
                    "INSERT INTO Note SET id = 'x'",
                    "UPDATE Note SET title = 'x' WHERE id = 'y'",
                    "CREATE VERTEX Note",
                    "DROP TYPE Note",
                    "TRUNCATE TYPE Note"):
            with self.assertRaises(readonly.ReadOnlyViolation, msg=sql):
                readonly.assert_read_only(sql)

    def test_refuses_write_hidden_after_a_read(self):
        """A statement that starts like a read but is not one."""
        with self.assertRaises(readonly.ReadOnlyViolation):
            readonly.assert_read_only("SELECT 1; DELETE FROM Note")

    def test_refuses_empty_and_nonsense(self):
        for bad in ("", "   ", None, 42, "EXPLODE"):
            with self.assertRaises(readonly.ReadOnlyViolation):
                readonly.assert_read_only(bad)

    def test_literal_containing_a_keyword_is_not_a_write(self):
        """A note body may legitimately contain the word 'drop'."""
        readonly.assert_read_only("SELECT id FROM Note WHERE title = 'drop the anchor'")


class _FakeArcade:
    """Stands in for notelib.Arcade so the gate can be tested with no database up."""

    def __init__(self):
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append(sql)
        return {"result": []}

    def command(self, sql, params=None):
        raise AssertionError("command() must never be reached through the gate")


class TestGraphHandle(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeArcade()
        self.db = readonly.ReadOnlyGraph(self.fake)

    def test_query_passes_through(self):
        self.db.query("SELECT id FROM Note")
        self.assertEqual(self.fake.queries, ["SELECT id FROM Note"])

    def test_write_sql_never_reaches_the_client(self):
        with self.assertRaises(readonly.ReadOnlyViolation):
            self.db.query("DELETE FROM Note")
        self.assertEqual(self.fake.queries, [])

    def test_command_is_not_reachable(self):
        for attr in ("command", "atomically", "transaction", "_request"):
            with self.assertRaises(readonly.ReadOnlyViolation, msg=attr):
                getattr(self.db, attr)

    def test_cannot_be_given_new_attributes(self):
        with self.assertRaises(readonly.ReadOnlyViolation):
            self.db.command = lambda *a, **k: None

    def test_has_no_write_methods_at_all(self):
        public = {n for n in dir(self.db) if not n.startswith("_")}
        self.assertEqual(public, {"query"})


class TestDirHandle(unittest.TestCase):
    def setUp(self):
        self.gate = readonly.ReadOnlyDir(config.posts_dir())

    def test_lists_and_reads(self):
        names = self.gate.names()
        self.assertTrue(names, "expected posts in the perceptua _posts dir")
        self.assertIsInstance(self.gate.read(names[0]), str)

    def test_refuses_path_traversal(self):
        for bad in ("../../../etc/passwd", "../README.md", "/etc/passwd"):
            with self.assertRaises(readonly.ReadOnlyViolation, msg=bad):
                self.gate.read(bad)

    def test_has_no_write_methods(self):
        public = {n for n in dir(self.gate) if not n.startswith("_")}
        self.assertEqual(public, {"names", "dirs", "read", "root"})


class TestAuduaDirHandle(unittest.TestCase):
    def setUp(self):
        self.gate = readonly.audua_dir(config.audua_root())

    def test_lists_session_dirs_and_reads_into_them(self):
        stems = self.gate.dirs()
        self.assertTrue(stems, "expected session directories under ELICITER_AUDUA_ROOT")
        # At least one session should have a summary.md readable through a nested path.
        readable = [s for s in stems if os.path.isfile(
            os.path.join(config.audua_root(), s, "summary.md"))]
        self.assertTrue(readable, "expected at least one session with a summary.md")
        text = self.gate.read(f"{readable[0]}/summary.md")
        self.assertIsInstance(text, str)

    def test_refuses_path_traversal(self):
        for bad in ("../../../etc/passwd", "../README.md", "/etc/passwd"):
            with self.assertRaises(readonly.ReadOnlyViolation, msg=bad):
                self.gate.read(bad)

    def test_has_no_write_methods(self):
        public = {n for n in dir(self.gate) if not n.startswith("_")}
        self.assertEqual(public, {"names", "dirs", "read", "root"})


class TestProjectUsesOnlyTheGate(unittest.TestCase):
    """The other half: nothing in this project may reach around `readonly.py`."""

    def test_no_module_bypasses_the_gate(self):
        offences = []
        for name, path in _sources():
            if name == GATE_FILE:
                continue                      # the gate is allowed to hold the raw client
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    code = _code(line)
                    for pattern, why in FORBIDDEN:
                        if pattern.search(code):
                            offences.append(f"{name}:{lineno} {why} — {line.strip()}")
        self.assertEqual(offences, [], "\n" + "\n".join(offences))

    def test_gate_is_the_only_importer_of_arcade(self):
        """`notelib` may be imported for its read helpers; `Arcade` may not be built."""
        offences = []
        for name, path in _sources():
            if name == GATE_FILE:
                continue
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if "Arcade(" in _code(line):
                        offences.append(f"{name}:{lineno} {line.strip()}")
        self.assertEqual(offences, [], "\n" + "\n".join(offences))

    def test_nothing_writes_into_the_source_projects(self):
        """No open(..., 'w') aimed at an indexia or perceptua path.

        Comments are stripped but literals are *not*: the mode argument this looks for is
        itself a literal, so `_code` would erase the very thing being detected.
        """
        roots = ("ELICITER_INDEXIA_ROOT", "ELICITER_PERCEPTUA_POSTS", "ELICITER_AUDUA_ROOT",
                 "posts_dir(", "audua_dir(", "indexia_root")
        pattern = re.compile(r"open\s*\([^)]*[\"'][wax]")
        offences = []
        for name, path in _sources():
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    code = line.split("#", 1)[0]
                    if pattern.search(code) and any(r in code for r in roots):
                        offences.append(f"{name}:{lineno} {line.strip()}")
        self.assertEqual(offences, [], "\n" + "\n".join(offences))

    def test_the_scanner_actually_catches_a_bypass(self):
        """The enforcement scan is only worth having if it fails when it should.

        A guard that always passes is indistinguishable from a guard that works, so this
        feeds it a known-bad line and insists it objects.
        """
        bad = "    db = notelib.Arcade()\n"
        self.assertTrue(any(p.search(_code(bad)) for p, _ in FORBIDDEN))
        self.assertFalse(any(p.search(_code('    msg = "call .command() here"\n'))
                             for p, _ in FORBIDDEN))


if __name__ == "__main__":
    unittest.main()
