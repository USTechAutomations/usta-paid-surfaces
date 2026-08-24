#!/usr/bin/env python3
"""Prove the URL harness works, without touching the live site.

    python3 scripts/check_urls_selftest.py

The live site is still serving the previous build, so running the harness at it
today would tell us about the old estate and nothing about this one. It is also
the wrong way to find out whether the harness itself is right: a probe that has
only ever seen one answer has not been shown to tell answers apart.

So this stands up a small server on this machine, serves the built pages out of
dist/, and makes it give a deliberately wrong answer in two places -- one page
missing, one page moved. Then it points the harness at a port with nothing
behind it at all. The harness has to reach all four verdicts and pick the right
exit code for each:

    every address answered 200        -> 0
    something answered 404            -> 1
    something answered 301            -> 1
    nothing answered at all           -> 2, and the word "unknown", never "down"

That last one is the one worth the trouble. A harness that calls our own broken
network an outage on their server is worse than no harness, because it produces
a confident wrong answer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PY = sys.executable

MISSING = "/feeds/quakes/texas"          # served as 404
MOVED = "/feeds/recalls/texas"           # served as 301


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the rehearsal quiet
        pass

    def do_GET(self):
        path = self.path.rstrip("/") or "/feeds"
        if path == MISSING:
            self.send_error(404, "Not Found")
            return
        if path == MOVED:
            self.send_response(301)
            self.send_header("Location", "https://ustechautomations.com" + path + "/")
            self.end_headers()
            return
        rel = path[len("/feeds"):].strip("/")
        f = (DIST / rel / "index.html") if rel else (DIST / "index.html")
        if not f.is_file():
            self.send_error(404, "Not Found")
            return
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([PY, str(ROOT / "scripts" / "check_urls.py"), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def summary(out: str, out_file: Path) -> dict:
    return json.loads(out_file.read_text(encoding="utf-8"))


def main() -> None:
    if not (ROOT / "urls.json").is_file():
        raise SystemExit("urls.json is missing. Run: python3 scripts/url_manifest.py")
    rows = json.loads((ROOT / "urls.json").read_text(encoding="utf-8"))["rows"]
    paths = [r["path"] for r in rows]
    for p in (MISSING, MOVED):
        assert p in paths, f"{p} is not in the manifest; pick another rehearsal page"

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    tmp = ROOT / ".selftest-run.json"
    failures = []

    def check(name: str, want_code: int, want: dict, args: list[str]) -> None:
        code, out = run(args + ["--out", str(tmp), "--quiet"])
        got = summary(out, tmp)
        got_small = {k: got[k] for k in want}
        if code != want_code or got_small != want:
            failures.append(f"{name}: exit {code} (wanted {want_code}), "
                            f"{got_small} (wanted {want})\n{out}")
        else:
            print(f"  PASS  {name}: exit {code}, {got_small}")

    print("rehearsing against a local copy of the built site, never the live one\n")

    # The subsets are driven by --limit over the real manifest rather than by a
    # second hand-written one: a rehearsal against a list nobody else uses does
    # not prove anything about the list that will actually be run.
    first_missing = paths.index(MISSING) + 1
    first_moved = paths.index(MOVED) + 1

    check("a run with nothing wrong in it", 0,
          {"ok": 3, "not_200": 0, "redirects": 0, "other_status": 0, "unknown": 0},
          ["--base", base, "--pace", "0", "--limit", "3"])

    check("a missing page is a finding, not a pass", 1,
          {"ok": first_missing - 1, "not_200": 1, "other_status": 1, "redirects": 0,
           "unknown": 0},
          ["--base", base, "--pace", "0", "--limit", str(first_missing)])

    n = max(first_missing, first_moved)
    check("a moved page is reported apart from a broken one", 1,
          {"ok": n - 2, "not_200": 2, "redirects": 1, "other_status": 1, "unknown": 0},
          ["--base", base, "--pace", "0", "--limit", str(n)])

    # 2. Nothing listening: must be unknown, must not be called a failure.
    srv.shutdown()
    srv.server_close()
    check("nothing listening is unknown, not down", 2,
          {"ok": 0, "not_200": 0, "redirects": 0, "other_status": 0, "unknown": 3},
          ["--base", base, "--pace", "0", "--limit", "3"])

    code, out = run(["--base", base, "--pace", "0", "--limit", "1", "--quiet"])
    if "unknown" not in out.lower() or "down" in out.lower().split("unknown")[0]:
        failures.append("the unreachable report does not use the word 'unknown'")

    tmp.unlink(missing_ok=True)

    print()
    if failures:
        for f in failures:
            print("FAIL  " + f)
        raise SystemExit(1)
    print("all four verdicts reached, and each one picked the right exit code.")


if __name__ == "__main__":
    main()
