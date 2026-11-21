"""The reading list: what `bookstore` accepts and refuses, and the order the tab shows.

Every test runs against a temp folder, never the real `books/`.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import books, bookstore             # noqa: E402


class TestBookStore(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.root = self._d.name

    def tearDown(self):
        self._d.cleanup()

    def add(self, title, status="finished", started="2026-01-01", finished="", **kw):
        return bookstore.add(title, kw.pop("author", "W. Shakespeare"), status, started,
                             finished=finished, root=self.root, **kw)

    def test_round_trip(self):
        name, _ = self.add("Hamlet", started="2026-01-04", finished="2026-01-18",
                           summary="A prince delays.")
        self.assertEqual(name, "hamlet-w-shakespeare.md")
        b = books.find("hamlet-w-shakespeare", self.root)
        self.assertEqual((b["title"], b["author"], b["status"], b["started"], b["finished"],
                          b["summary"], b["demo"]),
                         ("Hamlet", "W. Shakespeare", "finished", "2026-01-04", "2026-01-18",
                          "A prince delays.", False))
        self.assertTrue(b["added"])

    def test_refuses_bad_input(self):
        bad = [dict(title=""), dict(title="X", status="skimmed"),
               dict(title="X", started=""), dict(title="X", started="Jan 4"),
               dict(title="X", started="2026-02-30"),
               dict(title="X", started="2026-03-01", finished="2026-02-01"),
               dict(title="X", status="reading", finished="2026-02-01"),
               dict(title="X\nY")]
        for kw in bad:
            with self.assertRaises(bookstore.BookStoreError, msg=kw):
                self.add(**kw)
        self.assertEqual(os.listdir(self.root), [])

    def test_future_start_and_no_end_date_are_fine(self):
        self.add("Julius Caesar", status="planned", started="2099-01-01")
        self.add("Twelfth Night", status="finished")           # end date unknown

    def test_duplicate_is_refused_not_clobbered(self):
        self.add("Hamlet", summary="first")
        with self.assertRaises(bookstore.BookStoreError):
            self.add("Hamlet", summary="second")
        self.assertEqual(books.find("hamlet-w-shakespeare", self.root)["summary"], "first")
        self.assertEqual(os.listdir(self.root), ["hamlet-w-shakespeare.md"])

    def test_update_keeps_the_name_and_unchanged_fields(self):
        self.add("Coriolanus", status="reading", started="2026-11-03", summary="Rome.")
        with self.assertRaises(bookstore.BookStoreError):     # reading + end date
            bookstore.update("coriolanus-w-shakespeare", finished="2026-11-20", root=self.root)
        b = bookstore.update("coriolanus-w-shakespeare.md", status="finished",
                             finished="2026-11-20", title="The Tragedy of Coriolanus",
                             root=self.root)
        self.assertEqual((b["status"], b["finished"], b["summary"], b["started"]),
                         ("finished", "2026-11-20", "Rome.", "2026-11-03"))
        self.assertEqual(os.listdir(self.root), ["coriolanus-w-shakespeare.md"])
        bookstore.update("coriolanus-w-shakespeare", finished="", status="reading",
                         root=self.root)
        self.assertEqual(books.find("coriolanus-w-shakespeare", self.root)["finished"], "")
        with self.assertRaises(KeyError):
            bookstore.update("nope", status="finished", root=self.root)

    def test_clear_demo_removes_only_samples(self):
        self.add("Hamlet", demo=True)
        self.add("Middlemarch", author="George Eliot")
        with open(os.path.join(self.root, "notes.txt"), "w") as fh:
            fh.write("mine")
        self.assertEqual(bookstore.clear_demo(self.root), ["hamlet-w-shakespeare.md"])
        self.assertEqual(sorted(os.listdir(self.root)),
                         ["middlemarch-george-eliot.md", "notes.txt"])

    def test_order_newest_read_first_open_books_lead(self):
        self.add("Old", started="2025-01-01", finished="2025-02-01")
        self.add("New", started="2026-03-01", finished="2026-04-01")
        self.add("Mid", status="abandoned", started="2025-06-01", finished="2025-07-01")
        self.add("NoEnd", status="finished", started="2026-02-01")     # orders by start
        self.add("Next", status="planned", started="2026-12-01")
        self.add("Now", status="reading", started="2026-11-01")
        self.assertEqual([b["title"] for b in books.load(self.root)],
                         ["Now", "Next", "New", "NoEnd", "Mid", "Old"])


if __name__ == "__main__":
    unittest.main()
