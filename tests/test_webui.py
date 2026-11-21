"""Every route answers — the regression test for a handler calling a name that is gone.

This exists because of a specific bug. Removing the sweep route from `webui.py` took the
neighbouring `sources_payload` and `source_detail` with it — the handler still referenced
them, so `/api/sources` raised `NameError` and the Sources tab was dead. Nothing caught it:
the module imported fine, the page loaded fine, and the only broken thing was a route
nobody re-tested after the edit.

So this asks the cheapest question that would have failed: **does every route still
answer?** It is a smoke test, not a contract test — it asserts status codes and the shape
of the guards, not payload contents, because the payloads legitimately change and the point
here is to catch a 500, a missing name, or a guard that stopped guarding.

It runs the real server against the real corpus, like `doctor.py` does. A source being
unreachable (the indexia container down) must not fail it: that kind answers 503 with the
reason, the other kinds still answer 200, and that behaviour is itself worth pinning.
"""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import webui                        # noqa: E402


class TestRoutes(unittest.TestCase):
    """One server for the class: binding is the slow part, and every test is a read."""

    @classmethod
    def setUpClass(cls):
        # Port 0 lets the OS pick a free one — a fixed port would collide with the UI the
        # user actually has running, which is exactly when they would run the tests.
        cls.httpd, _ = webui.serve(port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body=None, headers=None):
        h = {"Content-Type": "application/json", "X-Eliciter": "1"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path,
                                     data=json.dumps(body or {}).encode(),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # -- the routes that must answer -----------------------------------------
    def test_page_loads(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"<title>eliciter</title>", body)

    def test_state(self):
        code, body = self.get("/api/state")
        self.assertEqual(code, 200)
        data = json.loads(body)
        for key in ("papers", "prompts", "tweets", "voice", "config"):
            self.assertIn(key, data)

    def test_sources_every_kind_answers(self):
        """The route whose helpers were deleted out from under it — now one kind at a time.
        Every kind answers 200, or 503 when its source is unreachable (indexia down), never
        500; and the page shape holds."""
        for kind in webui.SOURCE_KINDS:
            code, body = self.get(f"/api/sources?kind={kind}")
            self.assertIn(code, (200, 503), f"{kind}: {body[:400]}")
            if code != 200:
                continue
            data = json.loads(body)
            for key in ("kind", "source", "items", "total", "offset", "next"):
                self.assertIn(key, data, kind)
            self.assertLessEqual(len(data["items"]), 10, kind)
            self.assertEqual(data["next"] is None, len(data["items"]) >= data["total"], kind)
        self.assertEqual(self.get("/api/sources?kind=nope")[0], 404)
        self.assertEqual(self.get("/api/sources")[0], 404)
        self.assertEqual(self.get("/api/sources?kind=posts&offset=abc")[0], 400)

    def test_sources_pages_join_up(self):
        """Page two starts where page one stopped, with nothing repeated or skipped."""
        for kind in ("posts", "tweets", "sessions"):
            first = json.loads(self.get(f"/api/sources?kind={kind}&limit=3")[1])
            if first["next"] is None:
                continue
            second = json.loads(self.get(f"/api/sources?kind={kind}&offset=3&limit=3")[1])
            both = json.loads(self.get(f"/api/sources?kind={kind}&limit=6")[1])
            self.assertEqual([r["ref"] for r in first["items"] + second["items"]],
                             [r["ref"] for r in both["items"]], kind)

    def test_source_reader_round_trip(self):
        """Open the newest item of every kind. Skips a kind only if it is empty or down."""
        for kind, (source, _) in webui.SOURCE_KINDS.items():
            code, body = self.get(f"/api/sources?kind={kind}&limit=1")
            rows = json.loads(body)["items"] if code == 200 else []
            if not rows:
                continue
            ref = urllib.parse.quote(str(rows[0]["ref"]))
            code, body = self.get(f"/api/source?source={source}&ref={ref}")
            self.assertEqual(code, 200, f"{source}: {body[:300]}")
            self.assertTrue(json.loads(body).get("body"), f"{source} returned no text")

    def test_prompt_decision_round_trip(self):
        """Mark a prompt, see it in /api/state, then put it back exactly as it was.

        This is the one test here that writes, and it writes to the run the user is
        actually looking at — so it restores the prompt's original status in a finally,
        including the case where it was already decided.
        """
        prompts = json.loads(self.get("/api/state")[1])["prompts"]
        if not prompts:
            self.skipTest("no standing run to decide about")
        p = prompts[0]
        before = p.get("status") or "open"
        try:
            code, body = self.post("/api/prompt",
                                   {"n": p["n"], "status": "rejected", "title": p["title"]})
            self.assertEqual(code, 200, body[:300])
            back = next(x for x in json.loads(body)["prompts"] if x["n"] == p["n"])
            self.assertEqual(back["status"], "rejected")
            self.assertTrue(back.get("decided_at"))
        finally:
            self.post("/api/prompt", {"n": p["n"], "status": before, "title": p["title"]})
        after = json.loads(self.get("/api/state")[1])["prompts"]
        self.assertEqual((next(x for x in after if x["n"] == p["n"]).get("status")
                          or "open"), before)

    def test_stale_decision_is_refused(self):
        """A title that does not match means the run changed under the page: 409, no write."""
        prompts = json.loads(self.get("/api/state")[1])["prompts"]
        if not prompts:
            self.skipTest("no standing run to decide about")
        n = prompts[0]["n"]
        code, _ = self.post("/api/prompt",
                            {"n": n, "status": "written", "title": "not this prompt"})
        self.assertEqual(code, 409)
        after = next(x for x in json.loads(self.get("/api/state")[1])["prompts"]
                     if x["n"] == n)
        self.assertEqual(after.get("status") or "open",
                         prompts[0].get("status") or "open")

    def test_tweet_post_round_trip(self):
        """Posting from the page, against a temp run and a temp tweets/ — the server runs
        in this process, so pointing both at a temp dir keeps the real ones untouched."""
        import tempfile
        from unittest import mock
        from eliciterlib import run, tweetrun
        with tempfile.TemporaryDirectory() as d:
            path, root = os.path.join(d, "tweets.json"), os.path.join(d, "tweets")
            os.makedirs(root)
            tweetrun.add_draft("one", "A", [{"source": "misc", "ref": "x.md"}],
                               r=run.tweet_run(path))
            with mock.patch.object(run, "tweets_path", lambda: path), \
                    mock.patch.dict(os.environ, {"ELICITER_TWEETS_DIR": root}):
                link = "https://x.com/me/status/1990486787850289209"
                tops = lambda: [n for n in os.listdir(root)
                                if os.path.isfile(os.path.join(root, n))]
                code, _ = self.post("/api/tweet", {"n": 1, "status": "posted",
                                                   "title": "not A", "id": link})
                self.assertEqual(code, 409)
                code, _ = self.post("/api/tweet", {"n": 1, "status": "posted",
                                                   "title": "A"})
                self.assertEqual(code, 400)                    # no id, nothing saved
                self.assertEqual(tops(), [])
                code, body = self.post("/api/tweet", {"n": 1, "status": "posted",
                                                      "text": "one!", "title": "A", "id": link})
                self.assertEqual(code, 200, body[:300])
                card = json.loads(body)["tweets"][0]
                self.assertEqual((card["status"], card["posted_text"], card["posted_id"]),
                                 ("posted", "one!", "1990486787850289209"))
                self.assertEqual(tops(), [card["posted_file"]])
                self.assertTrue(card["posted_file"].endswith("-1990486787850289209.md"))
                self.assertEqual(self.post("/api/tweet", {"n": 1, "status": "open",
                                                          "title": "A"})[0], 200)
                self.assertEqual(self.post("/api/tweet", {"n": 1, "status": "written"})[0], 400)
                self.assertEqual(self.post("/api/tweet", {"n": 9, "status": "rejected"})[0], 404)
                self.assertEqual(self.post("/api/tweet", {"n": 1, "status": "rejected"},
                                           headers={"X-Eliciter": ""})[0], 403)

    def test_books_pages(self):
        """The books card, against a temp books/: ten at a time, newest read first, no
        summary, and `next` running out exactly at the end."""
        import tempfile
        from unittest import mock
        from eliciterlib import bookstore
        with tempfile.TemporaryDirectory() as d:
            for i in range(12):
                bookstore.add(f"Play {i}", "W. S.", "finished", f"2026-01-{i + 1:02d}",
                              finished=f"2026-03-{i + 1:02d}", summary="s", root=d)
            with mock.patch.dict(os.environ, {"ELICITER_BOOKS_DIR": d}):
                code, body = self.get("/api/sources?kind=books")
                self.assertEqual(code, 200, body[:300])
                first = json.loads(body)
                self.assertEqual((len(first["items"]), first["total"], first["next"]),
                                 (10, 12, 10))
                self.assertEqual(first["items"][0]["title"], "Play 11")
                self.assertNotIn("summary", first["items"][0])
                rest = json.loads(self.get(
                    f"/api/sources?kind=books&offset={first['next']}&limit=10")[1])
                self.assertEqual((len(rest["items"]), rest["next"]), (2, None))
                self.assertEqual(rest["items"][-1]["title"], "Play 0")
                ref = urllib.parse.quote(first["items"][0]["ref"])
                code, body = self.get(f"/api/source?source=books&ref={ref}")
                self.assertEqual((code, json.loads(body)["body"]), (200, "s"))
                self.assertEqual(self.get("/api/source?source=books&ref=nope")[0], 404)

    # -- failures are 404s, never 500s ---------------------------------------
    def test_unknown_source_is_404(self):
        for path in ("/api/source?source=twitter&ref=x",
                     "/api/source?source=perceptua&ref=nope.md",
                     "/api/source?source=perceptua&ref=",
                     "/api/brief?n=999999",
                     "/api/nothing-here"):
            code, body = self.get(path)
            self.assertEqual(code, 404, f"{path} → {code} {body[:200]}")
        # A prompt that does not exist is a 404 too; a status that does not exist is a 400.
        self.assertEqual(self.post("/api/prompt",
                                   {"n": 999999, "status": "written"})[0], 404)
        self.assertEqual(self.post("/api/prompt",
                                   {"n": 1, "status": "finished"})[0], 400)

    def test_removed_routes_are_gone(self):
        """Elicit and sweep were removed on purpose — judgement is a session's, not a
        button's. If either comes back it should be a deliberate change, not a leftover."""
        for path in ("/api/elicit", "/api/sweep"):
            self.assertEqual(self.post(path)[0], 404, path)

    # -- the guards still guard ----------------------------------------------
    def test_mutating_request_needs_the_header(self):
        code, _ = self.post("/api/status", {"id": "x", "status": "read"},
                            headers={"X-Eliciter": ""})
        self.assertEqual(code, 403)

    def test_foreign_host_is_refused(self):
        """DNS rebinding: an attacker's domain resolved to 127.0.0.1 carries their Host."""
        code, _ = self.get("/api/state", headers={"Host": "evil.example.com"})
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
