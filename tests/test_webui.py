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
unreachable (the indexia container down) must not fail it: `sources_payload` reports that
in `errors` and still returns 200, and that behaviour is itself worth pinning.
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
        for key in ("papers", "prompts", "config"):
            self.assertIn(key, data)

    def test_sources_catalogue(self):
        """The route whose helpers were deleted out from under it."""
        code, body = self.get("/api/sources")
        self.assertEqual(code, 200, body[:400])
        data = json.loads(body)
        for key in ("posts", "sessions", "notes", "papers", "errors"):
            self.assertIn(key, data)

    def test_source_reader_round_trip(self):
        """Open the first thing the catalogue offers. Skips only if there is nothing."""
        data = json.loads(self.get("/api/sources")[1])
        for kind in ("posts", "sessions", "notes", "papers"):
            rows = data.get(kind) or []
            if not rows:
                continue
            source = {"posts": "perceptua", "sessions": "audua",
                      "notes": "indexia", "papers": "arxiv"}[kind]
            ref = urllib.parse.quote(str(rows[0]["ref"]))
            code, body = self.get(f"/api/source?source={source}&ref={ref}")
            self.assertEqual(code, 200, f"{source}: {body[:300]}")
            self.assertTrue(json.loads(body).get("body"), f"{source} returned no text")

    # -- failures are 404s, never 500s ---------------------------------------
    def test_unknown_source_is_404(self):
        for path in ("/api/source?source=twitter&ref=x",
                     "/api/source?source=perceptua&ref=nope.md",
                     "/api/source?source=perceptua&ref=",
                     "/api/brief?n=999999",
                     "/api/nothing-here"):
            code, body = self.get(path)
            self.assertEqual(code, 404, f"{path} → {code} {body[:200]}")

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
