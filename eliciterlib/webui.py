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

**The UI does not decide anything any more.** It had two buttons that did — "Elicit
prompts" over `/api/elicit`, and "Sweep arxiv" over `/api/sweep` — from when prompts and
paper relevance were both settled by term overlap. Both judgements are a Claude session's
now (`state/material.json` → `state/prompts.json`; `state/candidates.json` →
`state/picks.json`), and a browser cannot start a session, which is the same boundary
"Write this →" has always had.

What is left is everything that is genuinely a fact or a decision *you* make: the queue and
its statuses, the prompts and their material, the source catalogue, and ad-hoc arxiv search
with a one-click add — searching for a paper by name and queuing it is your call, not a
ranking. So the page shows, opens, and records; it does not choose.

**Source material is served separately from state.** `/api/state` is polled every twenty
seconds and has to stay cheap, so it carries prompts and the queue and nothing else.
`/api/sources` (the catalogue: every post, every recording, the recent notes, the papers)
and `/api/source` (one item, in full) are fetched only when you ask to look at something.
That is the difference between a page that idles at two JSON reads and one that reads
seventeen poems and three transcripts off disk three times a minute.

Session spawning is the one thing the browser genuinely cannot do: `claude` is an
interactive terminal program and there is no terminal here. So `/api/brief` returns the
exact command plus the full brief, and the page gives you both to copy. That is the honest
boundary rather than a launch button that half-works — and it is now the boundary for
generating prompts as well as for writing them.
"""
import json
import os
import ssl
import threading
import traceback
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import arxiv, audua, config, corpus, posts, status

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "ui.html")

# Marking a paper and adding one both rewrite the queue file, and a double click can
# overlap them. One lock across the mutating routes keeps it consistent with no finer scheme.
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


# ---- source material: the catalogue, and one item in full --------------------
#
# Both of these are pure reads through the same gate everything else uses. Nothing here
# can change a post, a recording or a note — see `eliciterlib/readonly.py`. What they add
# is *access*: before this, the only way to see the material behind a prompt was the
# excerpt the prompt quoted, and checking whether a connection was real meant leaving the
# page and opening three files by hand.

def _first_lines(text, n=2, width=180):
    """A one-glance preview for a catalogue row."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return " / ".join(lines[:n])[:width]


def sources_payload():
    """Everything eliciter can read, as metadata — no bodies.

    Deliberately not part of `/api/state`: this reads seventeen posts and every session
    summary off disk, and `/api/state` is polled on a timer. A source that is unreachable
    contributes an empty list and a note in `errors` rather than failing the whole
    catalogue — the queue is still worth showing when the graph is down.
    """
    out = {"errors": {}}

    def attempt(name, fn, default):
        try:
            out[name] = fn()
        except Exception as e:                      # noqa: BLE001
            out[name] = default
            out["errors"][name] = f"{type(e).__name__}: {e}"

    attempt("posts", lambda: [
        {"ref": p["file"], "title": p["title"], "date": p["date"].isoformat(),
         "categories": p["categories"], "keywords": p["keywords"],
         "preview": _first_lines(posts.plain_text(p))}
        for p in sorted(posts.load(), key=lambda p: p["date"], reverse=True)], [])

    attempt("sessions", lambda: [
        {"ref": s["stem"], "title": f"Audua — {s['date'].isoformat()}",
         "date": s["date"].isoformat(), "seen": s["stem"] in audua.seen(),
         "threads": bool(s["threads"]),
         "preview": _first_lines(s["intro"] or s["summary"])}
        for s in audua.sessions()], [])

    def _notes():
        db = corpus.connect()
        return [{"ref": n.get("id"), "title": n.get("title") or "(untitled)",
                 "date": (n.get("created_at") or "")[:10],
                 "source_ref": n.get("source_ref") or "",
                 "preview": _first_lines(n.get("body"))}
                for n in corpus.recent_notes(db, limit=40)]
    attempt("notes", _notes, [])

    q = status.Queue()
    out["papers"] = [
        {"ref": p.get("id"), "title": p.get("title", ""), "date": (p.get("published") or "")[:10],
         "status": p.get("status"), "url": p.get("url", ""),
         "matched": p.get("matched") or [], "why": p.get("why", ""),
         "preview": _first_lines(p.get("abstract"))}
        for p in sorted(q.papers.values(),
                        key=lambda p: (p.get("changed_at") or ""), reverse=True)]
    return out


def source_detail(source, ref):
    """One piece of source material, in full, with where it lives on disk.

    `where` is a real path (or an arxiv URL) rather than a label, because the point of the
    reader is that you can go the rest of the way yourself — open the post in your editor,
    play the recording, read the paper. A viewer that could only ever show you its own
    rendering of a thing would be a worse version of the file it is rendering.
    """
    ref = (ref or "").strip()
    if not ref:
        raise KeyError("no ref given")

    if source == "perceptua":
        for p in posts.load():
            if p["file"] == ref or p["slug"] == ref:
                return {"source": source, "ref": p["file"], "title": p["title"],
                        "subtitle": f"{p['date'].isoformat()} · {', '.join(p['categories'])}",
                        "body": posts.plain_text(p),
                        "where": os.path.join(config.posts_dir(), p["file"])}
        raise KeyError(f"no perceptua post {ref!r}")

    if source == "audua":
        for sess in audua.sessions():
            if sess["stem"] == ref:
                return {"source": source, "ref": ref,
                        "title": f"Audua — {sess['date'].isoformat()}",
                        "subtitle": "run recording · summary.md",
                        "body": sess["summary"],
                        "where": os.path.join(config.audua_root(), ref, "summary.md")}
        raise KeyError(f"no audua session {ref!r}")

    if source == "indexia":
        db = corpus.connect()
        # A move-5 ref is `new+old`: two notes, and the pair is the point. Splitting here
        # rather than making the caller know that keeps the ref opaque everywhere else.
        chunks, titles = [], []
        for part in [x for x in ref.split("+") if x]:
            row = corpus.note(db, part)
            if not row:
                continue
            titles.append(row.get("title") or "(untitled)")
            chunks.append(f"# {titles[-1]}\n`{row.get('id')}`"
                          + (f" · source_ref: {row.get('source_ref')}"
                             if row.get("source_ref") else "")
                          + f"\n\n{row.get('body') or ''}")
        if not chunks:
            raise KeyError(f"no indexia note {ref!r}")
        return {"source": source, "ref": ref,
                "title": titles[0] if len(titles) == 1 else " ⟂ ".join(titles),
                "subtitle": f"indexia · {ref}",
                "body": "\n\n---\n\n".join(chunks),
                "where": f"indexia note {ref}"}

    if source == "arxiv":
        p = status.Queue().find(ref)
        if not p:
            raise KeyError(f"no paper {ref!r} in the queue")
        authors = ", ".join(p.get("authors") or [])
        return {"source": source, "ref": p.get("id"), "title": p.get("title", ""),
                "subtitle": f"{p.get('primary_category', '')} · {authors}",
                "body": p.get("abstract", ""), "where": p.get("url", "")}

    raise KeyError(f"{source!r} is not a readable source")


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
    raise KeyError(f"no prompt {n}")


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
            if url.path == "/api/sources":
                return self._json(200, sources_payload())
            if url.path == "/api/source":
                return self._json(200, source_detail((q.get("source") or [""])[0],
                                                     (q.get("ref") or [""])[0]))
            if url.path == "/api/brief":
                return self._json(200, brief_for(int((q.get("n") or [0])[0])))
            return self._send(404, "not found", "text/plain")
        except KeyError as e:
            return self._json(404, {"error": str(e.args[0]) if e.args else "not found"})
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
    # `is None`, not `or`: 0 is the standard way to ask the OS for a free port, and a
    # falsy check silently turned that into the configured one — which is in use exactly
    # when it matters, since the tests run while the UI is up.
    port = config.i("ELICITER_UI_PORT") if port is None else port
    Handler.allowed_host = allowed_host
    httpd = ThreadingHTTPServer((host, port), Handler)
    if tls is not None:
        cert_path, key_path = tls
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd, port
