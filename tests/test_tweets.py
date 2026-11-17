"""The Tweets tab's moving parts, against temp folders — never the real tweets/ or state/.

  * the archive importer keeps what it should (media tweets' text, not their media) and
    cleans what it keeps;
  * tweetstore never overwrites and never writes outside its folder;
  * a finalized tweet is saved as a draft only if X would take it (280, URLs at 23), and
    topics are logged;
  * a voice rebuild cannot drop a section or touch `## Yours`, and its stamp drives
    staleness;
  * posting a draft saves the text and marks the draft, once.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

import importlib.util                                # noqa: E402

from eliciterlib import material, run, tweetrun, tweets, tweetstore, voice  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_import_tweets", os.path.join(config.ROOT, "scripts", "import_tweets.py"))
import_tweets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_tweets)


def _tw(id_, text, **kw):
    t = {"id_str": str(id_), "full_text": text, "created_at": "Tue Mar 05 14:02:11 +0000 2024",
         "favorite_count": "4", "retweet_count": "1", "entities": {"urls": []}}
    t.update(kw)
    return {"tweet": t}


ARCHIVE = [
    _tw(1, "an original thought &amp; a second one"),
    _tw(2, "@someone no", in_reply_to_status_id_str="99"),
    _tw(3, "and the thread goes on", in_reply_to_status_id_str="1"),
    _tw(4, "RT @other: their words"),
    _tw(5, "the knots in these walls https://t.co/pic",
        entities={"urls": [], "media": [{"id": 1, "url": "https://t.co/pic"}]}),
    _tw(7, "https://t.co/only",
        extended_entities={"media": [{"id": 2, "url": "https://t.co/only"}]}),
    _tw(6, "read this https://t.co/abc",
        entities={"urls": [{"url": "https://t.co/abc", "expanded_url": "https://example.org/p"}]}),
]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "tweets")
        os.makedirs(self.root)


class TestImport(Tmp):
    def write_js(self):
        p = os.path.join(self.tmp.name, "tweets.js")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("window.YTD.tweets.part0 = " + json.dumps(ARCHIVE))
        return p

    def test_keeps_originals_and_cleans_them(self):
        c = import_tweets.run(self.write_js(), root=self.root, log=None)
        self.assertEqual((c["imported"], c["reply"], c["retweet"], c["media only"]),
                         (3, 2, 1, 1))
        got = {t["id"]: t for t in tweets.load(self.root)}
        self.assertEqual(set(got), {"1", "5", "6"})
        self.assertEqual(got["5"]["text"], "the knots in these walls")    # media link gone
        self.assertEqual(got["1"]["text"], "an original thought & a second one")
        self.assertEqual(got["6"]["text"], "read this https://example.org/p")
        self.assertEqual((got["1"]["likes"], got["1"]["retweets"]), (4, 1))
        self.assertEqual(got["1"]["date"], datetime(2024, 3, 5, 14, 2, 11, tzinfo=timezone.utc))

    def test_second_run_imports_nothing(self):
        js = self.write_js()
        import_tweets.run(js, root=self.root, log=None)
        c = import_tweets.run(js, root=self.root, log=None)
        self.assertEqual((c["imported"], c["already had"]), (0, 3))

    def test_dry_run_writes_nothing(self):
        c = import_tweets.run(self.write_js(), root=self.root, dry_run=True, log=None)
        self.assertEqual(c["imported"], 3)
        self.assertEqual(os.listdir(self.root), [])


class TestStore(Tmp):
    def test_never_overwrites(self):
        when = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        p, made = tweetstore.save("first", when, id="7", root=self.root)
        self.assertTrue(made)
        p2, made2 = tweetstore.save("changed", when, id="7", root=self.root)
        self.assertEqual((p2, made2), (p, False))
        self.assertEqual(tweets.load(self.root)[0]["text"], "first")

    def test_id_cannot_escape(self):
        p, _ = tweetstore.save("x", id="../../etc/passwd", root=self.root)
        self.assertTrue(os.path.realpath(p).startswith(os.path.realpath(self.root) + os.sep))

    def test_empty_is_refused(self):
        with self.assertRaises(tweetstore.TweetStoreError):
            tweetstore.save("   ", root=self.root)

    def test_bare_file_is_read(self):
        with open(os.path.join(self.root, "2023-01-02-hand.txt"), "w") as fh:
            fh.write("typed it in myself\n")
        [t] = tweets.load(self.root)
        self.assertEqual((t["text"], t["date"].date().isoformat(), t["likes"]),
                         ("typed it in myself", "2023-01-02", None))


SRC = [{"source": "tweets", "ref": "2024-03-05-1.md"}]


class TestDrafts(Tmp):
    """Saving a tweet you finalized, and logging a topic — the only writes a session makes."""

    def setUp(self):
        super().setUp()
        self.r = run.tweet_run(os.path.join(self.tmp.name, "tweets.json"))

    def test_add_and_number(self):
        d1 = tweetrun.add_draft("one", "Topic", SRC, r=self.r)
        d2 = tweetrun.add_draft("two", "Topic", SRC, r=self.r)
        self.assertEqual((d1["n"], d2["n"], d1["length"]), (1, 2, 3))
        again = run.tweet_run(self.r.path)
        self.assertEqual([d["text"] for d in again.prompts], ["one", "two"])

    def test_length(self):
        tweetrun.add_draft("a" * 280, "t", SRC, r=self.r)
        with self.assertRaises(tweetrun.InvalidTweets):
            tweetrun.add_draft("a" * 281, "t", SRC, r=self.r)
        # A long URL costs 23, so this fits although it is 300+ characters raw.
        url = "https://example.org/" + "x" * 200
        self.assertEqual(tweetrun.weighted_length("a " + url), 25)
        tweetrun.add_draft("a" * 250 + " " + url, "t", SRC, r=self.r)

    def test_required_fields_and_sources(self):
        for text, title, sources in (("", "t", SRC), ("x", "", SRC), ("x", "t", []),
                                     ("x", "t", [{"source": "twitter", "ref": "x"}])):
            with self.assertRaises(tweetrun.InvalidTweets, msg=(text, title, sources)):
                tweetrun.add_draft(text, title, sources, r=self.r)
        self.assertEqual(run.tweet_run(self.r.path).prompts, [])

    def test_source_specs(self):
        self.assertEqual(
            tweetrun.parse_sources(["arxiv:2609.00075v1", "misc:a: b.txt|A title"]),
            [{"source": "arxiv", "ref": "2609.00075v1", "title": ""},
             {"source": "misc", "ref": "a: b.txt", "title": "A title"}])
        with self.assertRaises(tweetrun.InvalidTweets):
            tweetrun.parse_sources(["no-colon"])

    def test_topic_log(self):
        tweetrun.log_topic("Fungal memory", SRC, "passed", note="not funny", r=self.r)
        with self.assertRaises(tweetrun.InvalidTweets):
            tweetrun.log_topic("x", SRC, "maybe", r=self.r)
        [t] = run.tweet_run(self.r.path).meta["topics"]
        self.assertEqual((t["title"], t["outcome"], t["note"]),
                         ("Fungal memory", "passed", "not funny"))


class TestDormantTopics(unittest.TestCase):
    """A passed topic stays down until something you read or wrote is newer than the pass."""

    def data(self, topics):
        return {
            "previous_tweets": {"topics": topics},
            "notes": {"recent": [{"id": "N1", "title": "old note",
                                  "created_at": "2026-10-01 09:00:00.000"},
                                 {"id": "N2", "title": "new note",
                                  "created_at": "2026-11-20 09:00:00.000"}]},
            "misc": [{"ref": "m.md", "title": "m", "date": "2026-10-02T00:00:00+00:00"}],
            "posts": [], "tweets": [],
            "papers": {"read": [{"ref": "2611.1", "title": "new paper",
                                 "read_on": "2026-11-21"}]},
        }

    def topic(self, title, outcome, at):
        return {"title": title, "outcome": outcome, "at": at, "sources": SRC, "note": ""}

    def test_newer_material_is_listed_and_older_is_not(self):
        [d] = material._dormant_topics(self.data(
            [self.topic("Fungi", "passed", "2026-11-17T19:00:00+00:00")]))
        self.assertEqual([e["ref"] for e in d["newer"]], ["2611.1", "N2"])

    def test_nothing_newer_means_nothing_listed(self):
        [d] = material._dormant_topics(self.data(
            [self.topic("Fungi", "passed", "2026-12-01T00:00:00+00:00")]))
        self.assertEqual(d["newer"], [])

    def test_latest_outcome_wins_and_skipped_is_not_dormant(self):
        out = material._dormant_topics(self.data([
            self.topic("Fungi", "passed", "2026-11-01T00:00:00+00:00"),
            self.topic("fungi", "drafted", "2026-11-02T00:00:00+00:00"),
            self.topic("Time", "skipped", "2026-11-03T00:00:00+00:00"),
            self.topic("Soul", "passed", "2026-11-04T00:00:00+00:00"),
        ]))
        self.assertEqual([d["title"] for d in out], ["Soul"])


PROFILE = """# Voice

## Register
short, lowercase.

## Vocabulary
agency.

## Preoccupations
borders.

## What lands
questions.

## Examples
> an original thought

## Yours
never use the word "delve".
"""


class TestVoice(Tmp):
    def setUp(self):
        super().setUp()
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(self.state)
        p = mock.patch.object(config, "out_dir", lambda name: self.state)
        p.start()
        self.addCleanup(p.stop)

    def draft(self, text):
        with open(voice.draft_path(), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_missing_section(self):
        with self.assertRaises(voice.InvalidVoice):
            voice.check(PROFILE.replace("## What lands\nquestions.\n", ""))

    def test_install_stamps_and_staleness_follows_the_count(self):
        self.assertTrue(voice.load(n_tweets=3)["stale"])           # no profile at all
        self.draft(PROFILE)
        voice.install(3)
        v = voice.load(n_tweets=3)
        self.assertEqual((v["built_from"], v["stale"]), (3, False))
        self.assertIn("_Built ", v["text"])
        self.assertFalse(os.path.exists(voice.draft_path()))
        v = voice.load(n_tweets=5)
        self.assertEqual((v["stale"], v["tweets_since"]), (True, 2))

    def test_yours_cannot_change(self):
        self.draft(PROFILE)
        voice.install(3)
        self.draft(PROFILE.replace('"delve"', '"tapestry"'))
        with self.assertRaises(voice.InvalidVoice):
            voice.install(4)
        self.draft(PROFILE.replace("short, lowercase.", "short; lowercase; no hashtags."))
        voice.install(4)
        self.assertIn('never use the word "delve".', voice.load()["text"])


class TestPost(Tmp):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp.name, "tweets.json")
        tweetrun.add_draft("one", "A", SRC, r=run.tweet_run(self.path))
        p = mock.patch.dict(os.environ, {"ELICITER_TWEETS_DIR": self.root})
        p.start()
        self.addCleanup(p.stop)

    def test_post_saves_then_marks_once(self):
        r = run.tweet_run(self.path)
        with self.assertRaises(run.StaleRun):
            tweetrun.post(1, title="not A", r=r)
        self.assertEqual(os.listdir(self.root), [])

        tweetrun.post(1, text="one, but better", title="A", r=r)
        [t] = tweets.load(self.root)
        self.assertEqual(t["text"], "one, but better")
        d = run.tweet_run(self.path).find(1)
        self.assertEqual((d["status"], d["posted_text"], d["posted_file"]),
                         ("posted", "one, but better", t["file"]))
        with self.assertRaises(ValueError):
            tweetrun.post(1, r=run.tweet_run(self.path))
        self.assertEqual(len(os.listdir(self.root)), 1)

    def test_post_defaults_to_the_draft(self):
        tweetrun.post(1, r=run.tweet_run(self.path))
        self.assertEqual(tweets.load(self.root)[0]["text"], "one")


if __name__ == "__main__":
    unittest.main(verbosity=2)
