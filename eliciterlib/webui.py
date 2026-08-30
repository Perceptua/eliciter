"""The local UI — a small JSON API over the same operations the scripts expose.

No framework and no dependencies: `http.server` from the stdlib, one HTML file, and JSON.
That is not minimalism for its own sake — this project has zero dependencies everywhere
else, and a UI that dragged in a web stack would be the heaviest thing in it by an order of
magnitude, for a page that shows two lists and runs four commands.

**Nothing here reaches around the read-only gate.** The UI calls `corpus.connect()` like
everything else, so it can read indexia and cannot write to it. What it *does* write is
eliciter's own state — the reading queue — which is a record of your decisions, not a change
to either corpus.

Safety posture, matching indexia's (loopback-only, single-user, no auth):

  * **Binds 127.0.0.1 only, by default.** Never a routable interface.
  * **Host header is checked.** A DNS-rebinding attack resolves an attacker's domain to
    127.0.0.1 so a page in your browser can reach this server; requiring the Host to be
    localhost defeats it, because the rebound request carries the attacker's hostname.
  * **Mutating requests need `X-Eliciter: 1`.** A cross-origin page cannot set a custom
    header without a CORS preflight, and this server answers no preflight — so a hostile
    page cannot make your browser sweep arxiv or mark your papers read.

**`--tailscale` deliberately trades away the loopback guarantee.** It binds this
machine's Tailscale IP, serves HTTPS with a tailscale-issued cert, and widens the Host
check to also accept the tailnet's MagicDNS name (see `allowed_host` below). The DNS-
rebinding and CORS-preflight defenses above only stop a hostile *page in a browser* —
they say nothing about a device on the tailnet itself, which can send `X-Eliciter: 1`
directly. There is still no login. The tailnet becomes the trust boundary: this is safe
exactly as long as you trust every device on it, the same tradeoff nomotactic's mobile
client already makes against nomothetic's API.

Session spawning is the one thing the browser genuinely cannot do: `claude` is an
interactive terminal program and there is no terminal here. So `/api/brief` returns the
exact command plus the full brief, and the page gives you both to copy. That is the honest
boundary rather than a launch button that half-works.
"""
import json
import os
import ssl
import threading
import traceback
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import arxiv, audua, config, corpus, posts, prompts, render, status

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "ui.html")

# Sweeps and elicit runs mutate shared state and are slow enough to overlap if you click
# twice. One lock across all of them keeps the queue consistent without any finer scheme.
_lock = threading.Lock()


def _profile(db):
    return arxiv.build_profile(db, log=lambda *_: None)


def state_payload():
    """Everything the page renders, in one round trip."""
    q = status.Queue()
    prompts_path = os.path.join(config.out_dir("state"), "prompts.json")
    listed = []
    if os.path.isfile(prompts_path):
        with open(prompts_path, encoding="utf-8") as fh:
            listed = json.load(fh).get("prompts", [])
    return {
        "papers": {
            "unread": q.active(),
            "read": q.by_status("read"),
            "rejected": q.by_status("rejected"),
            "cap": config.i("ELICITER_ARXIV_KEEP"),
        },
        "prompts": listed,
        "config": {
            "interests": config.interests(),
            "exclude": config.exclude(),
            "categories": config.categories(),
            "lookback": config.i("ELICITER_ARXIV_LOOKBACK_DAYS"),
        },
    }


def run_sweep():
    with _lock:
        db = _safe_db()
        papers = arxiv.sweep(log=lambda *_: None)
        ranked = arxiv.score(papers, db, log=lambda *_: None)
        q = status.Queue()
        added, skipped = q.refill(ranked)
        q.save()
        return {"swept": len(papers), "matched": len(ranked),
                "added": len(added), "skipped": skipped, "waiting": len(q.active())}


def run_elicit():
    with _lock:
        db = _safe_db()
        signals = []
        if db is not None:
            signals += corpus.signals(db, log=lambda *_: None)
        # Read papers, via the same helper the CLI uses — the two ran off separate copies
        # of this loop once, which is exactly how the UI would keep prompting unread papers
        # after the CLI stopped.
        signals += status.signals(status.Queue())
        try:
            signals += posts.signals(profile=_profile(db), log=lambda *_: None)
        except SystemExit:
            pass
        try:
            signals += audua.signals(log=lambda *_: None)
        except SystemExit:
            pass
        built = prompts.build(signals, limit=config.i("ELICITER_MAX_PROMPTS"))
        audua.mark_seen(built)          # same rule as the CLI: only what actually rendered
        text = render.render(built, stats={"sources": {}})
        idx = render.index(built)
        # Both files, same as the CLI writes: the dated one is the history, `latest.md` is
        # the stable path. A UI run that wrote only one would leave a gap in the record
        # depending on which way you happened to invoke it.
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out = config.out_dir("prompts")
        for name in (f"{day}.md", "latest.md"):
            with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(config.out_dir("state"), "prompts.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"prompts": idx}, fh, indent=2)
        return {"count": len(built), "prompts": idx}


def _safe_db():
    """The gated graph, or None. The UI stays usable with the container down."""
    try:
        return corpus.connect()
    except SystemExit:
        return None


def brief_for(n):
    """The session brief for prompt `n`, plus the command that opens it.

    Imported from the script that owns it so there is exactly one wording of the brief;
    duplicating it here is how the two would drift.
    """
    import importlib.util
    path = os.path.join(os.path.dirname(HERE), "scripts", "write.py")
    spec = importlib.util.spec_from_file_location("_eliciter_write", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for p in mod.load_prompts():
        if p["n"] == n:
            return {"n": n, "project": p["project"], "brief": mod.seed_text(p),
                    "command": f"bash scripts/write.sh {n}",
                    "cwd": mod.PROJECT_DIRS[p["project"]]()}
    raise KeyError(n)


class Handler(BaseHTTPRequestHandler):
    server_version = "eliciter"

    # Set by serve() when running with --tailscale: the one extra Host value
    # to accept beyond loopback. None means loopback-only (the default).
    allowed_host = None

    def log_message(self, fmt, *args):      # quieter than the default access log
        pass

    # -- guards --------------------------------------------------------------
    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host in ("localhost", "127.0.0.1", "[::1]", "::1", ""):
            return True
        return self.allowed_host is not None and host == self.allowed_host

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        # No CORS headers at all: a cross-origin page must not be able to read these.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    # -- routes --------------------------------------------------------------
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "bad host", "text/plain")
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                with open(PAGE, "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self._json(200, state_payload())
            if url.path == "/api/search":
                term = (q.get("q") or [""])[0]
                results = arxiv.search(term, max_results=int((q.get("n") or [20])[0]),
                                       log=lambda *_: None)
                queue = status.Queue()
                for r in results:
                    r["in_queue"] = queue.seen(r["id"])
                return self._json(200, {"query": term, "results": results})
            if url.path == "/api/brief":
                return self._json(200, brief_for(int((q.get("n") or [0])[0])))
            return self._send(404, "not found", "text/plain")
        except KeyError as e:
            return self._json(404, {"error": f"no such prompt {e}"})
        except SystemExit as e:                 # sources raise SystemExit for "unreachable"
            return self._json(503, {"error": str(e)})
        except Exception as e:                  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, "bad host", "text/plain")
        if self.headers.get("X-Eliciter") != "1":
            return self._json(403, {"error": "missing X-Eliciter header"})
        url = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        try:
            if url.path == "/api/sweep":
                return self._json(200, run_sweep())
            if url.path == "/api/elicit":
                return self._json(200, run_elicit())
            if url.path == "/api/status":
                with _lock:
                    qq = status.Queue()
                    qq.mark(body["id"], body["status"])
                    qq.save()
                return self._json(200, state_payload())
            if url.path == "/api/add":
                with _lock:
                    qq = status.Queue()
                    entry, existed = qq.add(body["paper"])
                    qq.save()
                return self._json(200, {"added": not existed, "paper": entry})
            return self._send(404, "not found", "text/plain")
        except SystemExit as e:
            return self._json(503, {"error": str(e)})
        except Exception as e:                  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


def serve(port=None, host="127.0.0.1", tls=None, allowed_host=None):
    """Bind and return ``(httpd, port)``, unstarted.

    ``tls``, if given, is a ``(cert_path, key_path)`` pair — see
    :mod:`eliciterlib.tailscale`. ``allowed_host`` is the extra Host value
    ``Handler._host_ok`` should accept beyond loopback (the tailnet FQDN).
    """
    port = port or config.i("ELICITER_UI_PORT")
    Handler.allowed_host = allowed_host
    httpd = ThreadingHTTPServer((host, port), Handler)
    if tls is not None:
        cert_path, key_path = tls
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd, port
