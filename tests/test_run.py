"""Deciding about a prompt: the status survives, and it survives a re-render.

Two things are worth pinning here, and the second is the one that would actually break.

`Run.mark` is small enough to read, but it is the only writer of `state/prompts.json` after
a session has written it, so "open is the absence of the field" and "reopen removes it
again" are the contract everything else reads through.

The re-render case is the trap. `prompts.sh render` rebuilds every prompt from the session's
JSON, deriving `n`, `length` and `project` rather than trusting them — and a field it does
not know about is a field it drops. Rendering a run you had already marked would have
quietly put every rejected prompt back on offer, and nothing would have said so.

These run against a temp file, never the real run.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import render, run                  # noqa: E402

PROMPTS = [
    {"register": "note", "title": "A claim", "ask": "Write the note that states it.",
     "sources": [{"source": "indexia", "ref": "20260905T014545161Z", "title": "x"}]},
    {"register": "essay", "title": "An argument", "ask": "Write the essay.",
     "sources": [{"source": "audua", "ref": "260910_0006", "title": "y"}]},
]


class TestRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "prompts.json")
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"generated_at": "2026-09-17T16:00:00+00:00",
                       "prompts": render.validate(PROMPTS)}, fh)

    def reload(self):
        return run.Run(self.path)

    def test_open_by_default(self):
        r = self.reload()
        self.assertEqual([run.status_of(p) for p in r.prompts], ["open", "open"])
        self.assertNotIn("status", r.prompts[0])

    def test_mark_round_trip(self):
        r = self.reload()
        r.mark(1, "written")
        r.mark(2, "rejected")
        r.save()

        r2 = self.reload()
        self.assertEqual(run.status_of(r2.find(1)), "written")
        self.assertEqual(run.status_of(r2.find(2)), "rejected")
        self.assertTrue(r2.find(1)["decided_at"])
        self.assertEqual(r2.counts(), {"open": 0, "written": 1, "rejected": 1})

        r2.mark(1, "open")
        r2.save()
        self.assertNotIn("status", self.reload().find(1))

    def test_meta_is_preserved(self):
        """Saving a decision must not drop what the session wrote around the prompts."""
        r = self.reload()
        r.mark(1, "written")
        r.save()
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["generated_at"], "2026-09-17T16:00:00+00:00")

    def test_status_survives_a_re_render(self):
        """The one that would silently un-reject a whole run."""
        r = self.reload()
        r.mark(2, "rejected")
        r.save()
        again = render.validate(self.reload().prompts)
        self.assertEqual(run.status_of(again[1]), "rejected")
        self.assertTrue(again[1]["decided_at"])
        self.assertEqual(run.status_of(again[0]), "open")

    def test_rendered_markdown_says_so(self):
        r = self.reload()
        r.mark(2, "rejected")
        r.save()
        text = render.render(render.validate(self.reload().prompts))
        self.assertIn("✗ rejected", text)
        self.assertIn("1 rejected", text)
        # A decided prompt does not advertise the command that writes it.
        self.assertNotIn("scripts/write.sh 2", text)
        self.assertIn("scripts/write.sh 1", text)

    def test_bad_status_and_missing_prompt(self):
        r = self.reload()
        with self.assertRaises(ValueError):
            r.mark(1, "finished")
        with self.assertRaises(KeyError):
            r.mark(99, "written")

    def test_stale_run_is_refused(self):
        """The UI's window: the run was replaced between painting and clicking."""
        r = self.reload()
        with self.assertRaises(run.StaleRun):
            r.mark(1, "written", expect_title="Some prompt from last week")
        self.assertEqual(run.status_of(self.reload().find(1)), "open")
        r.mark(1, "written", expect_title="A claim")     # the title it really has


class TestPostRegister(unittest.TestCase):
    """`post` routes to misc/ and gets a file there, the way a note gets a staging id."""

    def test_post_is_derived_short_and_misc(self):
        [p] = render.validate([
            {"register": "post", "title": "Thought as motion: a reading note!",
             "ask": "Present it.",
             "sources": [{"source": "misc", "ref": "thought-as-motion-in-the-soul.md"}]}])
        self.assertEqual((p["length"], p["project"]), ("short", "misc"))
        self.assertRegex(p["commit"],
                         r"^misc/post-\d{4}-\d{2}-\d{2}-thought-as-motion-a-reading-note\.md")

    def test_a_given_commit_wins(self):
        [p] = render.validate([
            {"register": "post", "title": "t", "ask": "a", "commit": "misc/mine.md",
             "sources": [{"source": "misc", "ref": "x.md"}]}])
        self.assertEqual(p["commit"], "misc/mine.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
