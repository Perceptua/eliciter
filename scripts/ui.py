#!/usr/bin/env python3
"""Serve the local eliciter UI.

  scripts/ui.sh                 # http://127.0.0.1:8473
  scripts/ui.sh --port 8474
  scripts/ui.sh --open          # and open a browser

Loopback only, no auth — the same posture as indexia's UI, for the same reason: this is a
single-user tool reading a single-user corpus, and a login screen would be ceremony over a
socket nobody else can reach. Cross-origin protections are in `eliciterlib/webui.py`.

Ctrl-C to stop. Nothing is daemonized: a UI you forgot was running is a UI holding a stale
view of a queue you changed from the CLI.
"""
import argparse
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliciterlib import config                       # noqa: E402

config.bootstrap()

from eliciterlib import webui                        # noqa: E402


def main():
    p = argparse.ArgumentParser(prog="ui", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, help="default from ELICITER_UI_PORT")
    p.add_argument("--open", action="store_true", help="open a browser at the URL")
    a = p.parse_args()

    try:
        httpd, port = webui.serve(port=a.port)
    except OSError as e:
        raise SystemExit(
            f"cannot bind {a.port or config.i('ELICITER_UI_PORT')} ({e}) — something else "
            "is on that port; pass --port or set ELICITER_UI_PORT")

    url = f"http://127.0.0.1:{port}/"
    print(f"[ui] eliciter at {url}  (Ctrl-C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ui] stopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
