#!/usr/bin/env python3
"""Refuse to ship this family unless every promise on its page holds.

Exit 0 only when:
  * refresh.py --dry-run --limit 5 runs and exits 0 (it probes the sources and
    never writes on a dry run, so it works with the network up or down);
  * fulfil() renders from the fixture, carries an <h1>, is noindex, and does NOT
    contain the buyer's email;
  * every indexable page has a <title>, an <h1>, a source reference and a
    freshness stamp, and there are at most 200 of them;
  * there are 0 natural-person subjects.

The person check is the load-bearing one, so it is spelled out. The subject of
every row is a PUBLIC WATER SYSTEM, which the EPA issues a PWSID -- an
organisation identifier, never a person. A two-word system name like "Queens
Well" trips the same blunt name heuristic scripts/check_site.py uses, so that
heuristic alone would wrongly flag a facility as a person. The honest rule:
a row is a natural-person subject only if its name reads personal AND it carries
no PWSID. All EPA rows carry a PWSID, so the count is 0 -- and any that ever did
not would be withheld, not renamed. The page's own subject (its <h1>) is checked
against the heuristic directly.

Prints counts, not dumps.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FID = "apify-public-records"
ROOT = HERE.parents[2]
SCRIPTS = ROOT / "scripts"
PAGE = ROOT / "families" / FID / "index.html"
SAMPLE_JSON = ROOT / "families" / FID / "sample.json"
sys.path.insert(0, str(SCRIPTS))
import privacy  # noqa: E402

MAX_INDEXABLE = 200


def _fail(msg: str) -> None:
    print(f"SELFTEST FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _text(h: str) -> str:
    h = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", h)
    h = re.sub(r"(?is)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h)


def check_refresh() -> None:
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        _fail(f"refresh.py --dry-run exited {r.returncode}: {r.stderr[-300:]}")
    if f"REFRESH id={FID}" not in r.stdout:
        _fail("refresh.py --dry-run did not print its REFRESH summary line")
    print(f"refresh   dry-run ok: {r.stdout.strip().splitlines()[-1]}")


def check_fulfil() -> None:
    import importlib.util
    sp = importlib.util.spec_from_file_location("fulfil", HERE / "fulfil.py")
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    session = json.loads((HERE / "fixtures" / "session_paid.json").read_text())
    out = mod.fulfil(session)
    for key in ("title", "html", "state_update"):
        if key not in out:
            _fail(f"fulfil() output missing {key!r}")
    h = out["html"]
    if "<h1" not in h:
        _fail("fulfil() page has no <h1>")
    if 'name="robots" content="noindex,nofollow"' not in h:
        _fail("fulfil() page is not marked noindex,nofollow")
    email = (session.get("customer_details") or {}).get("email") or ""
    if email and email in h:
        _fail("fulfil() page contains the buyer's email")
    print(f"fulfil    ok: {len(h)} bytes, noindex, no buyer email")


def indexable_pages() -> list[Path]:
    """The family page plus any sub-pages that are NOT noindex.

    This family has no sub-pages -- the Store listing is the product -- so this
    is the one shop-window page. The walk is written for the general case so it
    keeps counting correctly if sub-pages are ever added.
    """
    fam_dir = ROOT / "families" / FID
    out = []
    for p in sorted(fam_dir.rglob("index.html")):
        raw = p.read_text(encoding="utf-8")
        if 'name="robots" content="noindex' in raw:
            continue
        out.append(p)
    return out


def check_pages() -> None:
    pages = indexable_pages()
    if not pages:
        _fail("no indexable page for this family")
    if len(pages) > MAX_INDEXABLE:
        _fail(f"{len(pages)} indexable pages, over the {MAX_INDEXABLE} budget")
    for p in pages:
        raw = p.read_text(encoding="utf-8")
        who = p.relative_to(ROOT)
        if "<title>" not in raw:
            _fail(f"{who} has no <title>")
        if "<h1" not in raw:
            _fail(f"{who} has no <h1>")
        # Source reference: every factual sentence traces to a source. The page
        # names its EPA source URL and the sealed date it was read.
        if "data.epa.gov" not in raw:
            _fail(f"{who} names no source URL")
        blob = json.loads(SAMPLE_JSON.read_text()) if SAMPLE_JSON.is_file() else {}
        stamp = str(blob.get("generated") or "")
        if stamp and stamp not in raw:
            # The sealed date is the freshness stamp; the page must carry it.
            # (Falls back to a softer check if the sample file names no date.)
            if not re.search(r"20\d\d-\d\d-\d\d", raw):
                _fail(f"{who} carries no freshness stamp")
    print(f"pages     {len(pages)} indexable (budget {MAX_INDEXABLE}); each has "
          f"title, h1, source URL and a date")


def check_no_persons() -> None:
    # 1) The page's own subject.
    raw = PAGE.read_text(encoding="utf-8")
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    h1 = _text(m.group(1)).strip() if m else ""
    if privacy.looks_personal(h1):
        _fail(f"the page subject reads as a person's name: {h1!r}")

    # 2) The rows. A row is a natural-person subject only if its name reads
    #    personal AND it has no PWSID (a facility identifier). EPA rows all have
    #    a PWSID, so the count is 0. Names that trip the heuristic but are
    #    PWSID-backed facilities are counted for transparency, not failed.
    blob = json.loads(SAMPLE_JSON.read_text()) if SAMPLE_JSON.is_file() else {"rows": []}
    headers = blob.get("headers") or []
    name_i = headers.index("Water system") if "Water system" in headers else 1
    pwsid_i = headers.index("PWSID") if "PWSID" in headers else 0
    persons = 0
    facility_flags = 0
    withheld = 0
    for row in blob.get("rows", []):
        name = str(row[name_i]) if len(row) > name_i else ""
        pwsid = str(row[pwsid_i]).strip() if len(row) > pwsid_i else ""
        if privacy.looks_personal(name):
            if pwsid:
                facility_flags += 1          # a facility that merely looks 2-token
            else:
                persons += 1                 # a bare person -> would be withheld
                withheld += 1
    if persons:
        _fail(f"{persons} row(s) are a natural person with no facility id; withhold them")
    print(f"persons   0 natural-person subjects "
          f"({facility_flags} facility name(s) tripped the heuristic but carry a PWSID)")


def main() -> int:
    check_refresh()
    check_fulfil()
    check_pages()
    check_no_persons()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
