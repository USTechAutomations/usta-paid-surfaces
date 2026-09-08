#!/usr/bin/env python3
"""Re-read the primary sources, re-check every quote, rewrite data/*.json.

    python3 refresh.py [--dry-run] [--limit N]

Ordinary run: fetch each source we are allowed to fetch, keep the bytes under
~/.hermes/state/fv5/ai-disclosure-notice/raw/, check every quoted passage back
against the words that came down the wire, and write the four data files the
pages read. A quote that no longer appears in its own source is marked
"drifted" and sets the drift flag, which puts a dated banner on the delivered
page. Nothing is corrected silently.

--dry-run touches no network and writes nothing; it checks the quotes against
the bytes already on disk and prints the same summary line. That is the mode
selftest.py uses, so the tests do not depend on eight government websites being
up.

Walls this obeys: it fetches only the sources named in SOURCES, it does not
retry behind a bot challenge, and a refusal is written down as a refusal.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import notice_build as nb  # noqa: E402

FAMILY = nb.FAMILY
HERE = nb.HERE
DATA = nb.DATA
RAW_DIR = nb.RAW_DIR
REPO = HERE.parents[2]
MAX_DATA_BYTES = 2 * 1024 * 1024


def fetchable() -> list[str]:
    """The sources an ordinary HTTPS request is allowed to try.

    A source marked "browser" or "blocked" is not retried here. We recorded why
    it refuses this host; hammering it again would not change the answer and
    working around it is off limits.
    """
    return [sid for sid, s in nb.SOURCES.items() if s["fetch"] == "curl"]


def pull(limit: int | None, verbose: bool) -> tuple[dict[str, str], list[dict]]:
    """Fetch the sources, cache the bytes, and return their text plus a log."""
    got: dict[str, str] = {}
    log: list[dict] = []
    ids = fetchable()
    if limit is not None:
        ids = ids[:limit]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        src = nb.SOURCES[sid]
        status, body = nb.fetch_source(sid)
        row = {"source": sid, "url": src["url"], "status": str(status),
               "bytes": len(body) if body else 0}
        if body and status == 200:
            name = src["file"]
            if name.endswith(".txt") and src.get("pdf"):
                # The Utah source is a PDF; keep the bytes, and rebuild the text
                # layer only if pdftotext is on this host. If it is not, the
                # cached text stays and we say so rather than dropping the rows.
                (RAW_DIR / src["pdf"]).write_bytes(body)
                try:
                    subprocess.run(
                        ["pdftotext", "-layout", str(RAW_DIR / src["pdf"]),
                         str(RAW_DIR / name)],
                        check=True, capture_output=True, timeout=120)
                except (OSError, subprocess.SubprocessError):
                    row["note"] = "pdftotext unavailable; kept the cached text layer"
            else:
                (RAW_DIR / name).write_bytes(body)
            text = nb.read_source_text(sid)
            if text is not None:
                got[sid] = text
            row["ok"] = True
        else:
            row["ok"] = False
            row["note"] = "no usable body; the cached copy is used and the wall recorded"
        log.append(row)
        if verbose:
            print(f"  {sid:<18} {row['status']:<8} {row['bytes']:>8} bytes", file=sys.stderr)
    return got, log


def build_pages() -> int:
    """Regenerate the sub-pages through the slice module. Returns the count."""
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib
    mod = importlib.import_module("slice_ai_disclosure_notice")
    importlib.reload(mod)
    return len(mod.slices())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="no network, no writes; check the cached bytes")
    ap.add_argument("--limit", type=int, default=None,
                    help="fetch at most N sources")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    stamp = dt.date.today().isoformat()
    fetch_log: list[dict] = []
    fetched: dict[str, str] = {}

    if args.dry_run:
        source_ok = sum(1 for sid in nb.SOURCES
                        if nb.read_source_text(sid) is not None)
    else:
        fetched, fetch_log = pull(args.limit, args.verbose)
        source_ok = sum(1 for r in fetch_log if r["ok"])

    cites = nb.verify_quotes(fetched or None)
    cites_ok = sum(1 for c in cites if c["status"] == "ok")
    drifted = [c["id"] for c in cites if c["status"] == "drifted"]
    unchecked = [c["id"] for c in cites if c["status"] == "unchecked"]

    try:
        pages = build_pages()
    except Exception as e:  # the slice module is the thing under test elsewhere
        print(f"slice module not loadable: {e}", file=sys.stderr)
        pages = 0

    if not args.dry_run:
        DATA.mkdir(parents=True, exist_ok=True)
        payloads = {
            "citations.json": cites,
            "duties.json": {
                "duties": nb.DUTIES,
                "jurisdictions": nb.JURISDICTIONS,
                "channels": nb.CHANNELS,
                "regions": [{"key": k, "label": v} for k, v in nb.REGIONS],
                "uses": [{"key": k, "label": v} for k, v in nb.USES],
            },
            "notices.json": nb.NOTICES,
            "sources.json": [
                {"id": sid, **{k: v for k, v in s.items() if k != "file"}}
                for sid, s in nb.SOURCES.items()
            ],
            "status.json": {
                "family": FAMILY,
                "stamp": stamp,
                "drift": bool(drifted),
                "drifted": drifted,
                "unchecked": unchecked,
                "cite_checks": nb.cite_checks(),
                "counts": {
                    "duties": len(nb.DUTIES), "cites": len(cites),
                    "notices": len(nb.NOTICES), "sources": len(nb.SOURCES),
                    "pages": pages,
                },
                "fetch_log": fetch_log,
                "review_dates": nb.review_dates(),
            },
        }
        total = 0
        for name, obj in payloads.items():
            blob = json.dumps(obj, indent=1, ensure_ascii=False) + "\n"
            total += len(blob.encode())
            (DATA / name).write_text(blob, encoding="utf-8")
        if total > MAX_DATA_BYTES:
            print(f"data/ is {total} bytes, over the {MAX_DATA_BYTES} cap",
                  file=sys.stderr)
            return 1

    print(f"REFRESH id={FAMILY} rows={len(nb.DUTIES)} pages={pages} "
          f"source_ok={source_ok}/{len(nb.SOURCES)} "
          f"cites_ok={cites_ok}/{len(cites)} stamp={stamp}")
    if drifted:
        print(f"drifted: {', '.join(drifted)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
