"""The Tweets tab's moving parts, against temp folders — never the real tweets/ or state/.

  * the archive importer keeps what it should and cleans what it keeps;
  * tweetstore never overwrites and never writes outside its folder;
  * a tweet run is validated the way X will judge it (280, URLs at 23);
  * a voice rebuild cannot drop a section or touch `## Yours`, and its stamp drives
    staleness;
  * posting a card saves the text and marks the card, once.
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

from eliciterlib import run, tweetrun, tweets, tweetstore, voice   # noqa: E402

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
    _tw(5, "look at this https://t.co/pic", entities={"urls": [], "media": [{"id": 1}]}),
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
        self.assertEqual((c["imported"], c["reply"], c["retweet"], c["media"]), (2, 2, 1, 1))
        got = {t["id"]: t for t in tweets.load(self.root)}
        self.assertEqual(set(got), {"1", "6"})
        self.assertEqual(got["1"]["text"], "an original thought & a second one")
        self.assertEqual(got["6"]["text"], "read this https://example.org/p")
        self.assertEqual((got["1"]["likes"], got["1"]["retweets"]), (4, 1))
        self.assertEqual(got["1"]["date"], datetime(2024, 3, 5, 14, 2, 11, tzinfo=timezone.utc))

    def test_second_run_imports_nothing(self):
        js = self.write_js()
        import_tweets.run(js, root=self.root, log=None)
        c = import_tweets.run(js, root=self.root, log=None)
        self.assertEqual((c["imported"], c["already had"]), (0, 2))

    def test_dry_run_writes_nothing(self):
        c = import_tweets.run(self.write_js(), root=self.root, dry_run=True, log=None)
        self.assertEqual(c["imported"], 2)
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


class TestValidate(unittest.TestCase):
    def card(self, **kw):
        c = {"title": "t", "site": "s", "sources": SRC, "drafts": ["one", "two"]}
        c.update(kw)
        return c

    def test_valid_and_derived(self):
        [c] = tweetrun.validate([self.card()])
        self.assertEqual((c["n"], c["lengths"]), (1, [3, 3]))

    def test_length(self):
        tweetrun.validate([self.card(drafts=["a" * 280, "b"])])
        with self.assertRaises(tweetrun.InvalidTweets):
            tweetrun.validate([self.card(drafts=["a" * 281, "b"])])
        # A long URL costs 23, so this fits although it is 300+ characters raw.
        url = "https://example.org/" + "x" * 200
        self.assertEqual(tweetrun.weighted_length("a " + url), 25)
        tweetrun.validate([self.card(drafts=["a" * 250 + " " + url, "b"])])

    def test_draft_count_and_duplicates(self):
        for drafts in (["one"], ["1", "2", "3", "4"], ["same", "same"], ["ok", ""]):
            with self.assertRaises(tweetrun.InvalidTweets, msg=drafts):
                tweetrun.validate([self.card(drafts=drafts)])

    def test_sources_required_and_known(self):
        for sources in ([], [{"source": "twitter", "ref": "x"}]):
            with self.assertRaises(tweetrun.InvalidTweets):
                tweetrun.validate([self.card(sources=sources)])

    def test_decision_survives(self):
        [c] = tweetrun.validate([self.card(status="posted", decided_at="2026-11-17",
                                           posted_text="one", posted_draft=1)])
        self.assertEqual((c["status"], c["posted_text"]), ("posted", "one"))
        self.assertIn("✓ posted", tweetrun.render([c]))


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
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"cards": tweetrun.validate([
                {"title": "A", "site": "s", "sources": SRC, "drafts": ["one", "two"]}])}, fh)
        p = mock.patch.dict(os.environ, {"ELICITER_TWEETS_DIR": self.root})
        p.start()
        self.addCleanup(p.stop)

    def test_post_saves_then_marks_once(self):
        r = run.tweet_run(self.path)
        with self.assertRaises(run.StaleRun):
            tweetrun.post(1, draft=1, title="not A", r=r)
        self.assertEqual(os.listdir(self.root), [])

        tweetrun.post(1, draft=2, text="two, but better", title="A", r=r)
        [t] = tweets.load(self.root)
        self.assertEqual(t["text"], "two, but better")
        c = run.tweet_run(self.path).find(1)
        self.assertEqual((c["status"], c["posted_draft"], c["posted_file"]),
                         ("posted", 2, t["file"]))
        with self.assertRaises(ValueError):
            tweetrun.post(1, draft=1, r=run.tweet_run(self.path))
        self.assertEqual(len(os.listdir(self.root)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
