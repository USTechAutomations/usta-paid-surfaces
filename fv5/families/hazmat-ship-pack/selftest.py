#!/usr/bin/env python3
"""Prove the hazmat road pack before it ships. Exit 0 only if every check passes.

    python3 selftest.py            # prints counts, one line per check
    python3 selftest.py --no-browser

The checks, in the order they run:

  1. refresh --dry-run --limit 5 exits 0 on the copy already on disk.
  2. fulfil renders the paid fixture; no e-mail address reaches the page, and the
     page carries noindex once ppp has wrapped it.
  3. fulfil renders the known-bad fixture as a real "not found" page, never None.
  4. Every free sub-page (indexable and overflow) has a title, an <h1>, a
     data-source-url, a freshness stamp and the price in visible text.
  5. At most 200 pages are indexable; every overflow page says noindex.
  6. No page makes a natural person its subject (privacy.looks_personal).
  7. THE VERDICT GATE: no page, free or paid, tells the buyer what their own
     shipment is, needs, or is excused from.
  8. Every citation row has a url, a quote and a fetch date.
  9. browser_test.py drives the search box in real Chromium.

It prints counts. It never dumps a page.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FAMILY = "hazmat-ship-pack"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
PUB = REPO / "families" / FAMILY
DATA = HERE / "data"
PRICE = "$49"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

# The gate. The first block is the common list every fv6 family carries; the
# second is this family's own, because a hazmat page fails in its own dialect.
# Every phrase is a sentence that would tell the buyer what THEIR shipment is,
# needs, or is excused from -- which is the shipper's call and never ours.
VERDICT_PHRASES = [
    "you are an employee", "you are an independent contractor", "this worker is",
    "is an employee", "is a contractor", "likely employee", "likely contractor",
    "you are compliant", "you are exempt", "you do not need", "you are covered",
    "this label is compliant", "this journal satisfies",
    # hazmat dialect
    "your shipment is", "your package is", "your material is",
    "you may ship", "you can ship", "you are allowed to ship",
    "safe to ship", "legal to ship", "you are not required",
    "this shipment qualifies", "you qualify", "this qualifies as a limited quantity",
    "is exempt from", "no label is required", "you need no",
    "you do not have to label", "you do not have to placard",
    "you do not have to declare", "you do not have to use",
    "this is a shipping paper", "use this as your shipping paper",
    "is compliant", "meets the requirements", "satisfies the requirement",
    "you may use this label", "this label may be used",
]

fails: list[str] = []
lines: list[str] = []


def ok(label: str, detail: str) -> None:
    lines.append(f"  ok   {label:<22} {detail}")


def bad(label: str, detail: str) -> None:
    fails.append(f"{label}: {detail}")
    lines.append(f"  FAIL {label:<22} {detail}")


def text_of(html: str) -> str:
    s = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", html)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


def verdict_hits(html: str) -> list[str]:
    t = text_of(html).lower()
    return [p for p in VERDICT_PHRASES if p in t]


# --- 1. refresh -------------------------------------------------------------
r = subprocess.run([sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
                   capture_output=True, text=True, cwd=str(REPO))
if r.returncode == 0 and "REFRESH id=" in r.stdout:
    m = re.search(r"rows=(\d+)", r.stdout)
    ok("refresh --dry-run", f"exit 0, rows={m.group(1) if m else '?'}")
else:
    bad("refresh --dry-run", f"exit {r.returncode} {r.stderr.strip()[:120]}")

# --- 2 & 3. fulfil ----------------------------------------------------------
import fulfil as F  # noqa: E402

sys.path.insert(0, str(REPO / "fv5" / "lib"))
try:
    import ppp  # noqa: E402
except Exception:  # noqa: BLE001
    ppp = None

paid = json.loads((HERE / "fixtures" / "session_paid.json").read_text(encoding="utf-8"))
good = json.loads((HERE / "fixtures" / "known_good.json").read_text(encoding="utf-8"))
bad_fx = json.loads((HERE / "fixtures" / "known_bad.json").read_text(encoding="utf-8"))

out = F.fulfil(paid)
page = out["html"]
if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text_of(page)):
    bad("fulfil no e-mail", "an e-mail address reached the paid page")
else:
    ok("fulfil no e-mail", f"{len(page):,} bytes, no address")

if ppp is not None:
    wrapped = ppp.wrap_private_page(FAMILY, F.PRODUCT_NAME, page, paid.get("created"))
    n_noindex = wrapped.lower().count('name="robots" content="noindex')
    if n_noindex == 1:
        ok("fulfil noindex", "wrapped page carries noindex once")
    else:
        bad("fulfil noindex", f"{n_noindex} robots noindex lines after wrapping")
else:
    bad("fulfil noindex", "could not import fv5/lib/ppp.py")

missing = [s for s in good["expect"]["fulfil_html_contains"] if s not in page]
if out["title"] == good["expect"]["fulfil_title"] and not missing:
    ok("fulfil known_good", f"title matches, all {len(good['expect']['fulfil_html_contains'])} markers present")
else:
    bad("fulfil known_good", f"title={out['title']!r} missing={missing}")

bad_sess = dict(paid, custom_fields=[
    {"key": "un_number", "type": "text", "text": {"value": bad_fx["input"]["un_number"]}}])
bout = F.fulfil(bad_sess)
bpage = bout["html"]
miss = [s for s in bad_fx["expect"]["fulfil_html_contains"] if s not in bpage]
leak = [s for s in bad_fx["expect"]["fulfil_html_excludes"] if s in bpage]
if bout["title"] == bad_fx["expect"]["fulfil_title"] and not miss and not leak:
    ok("fulfil known_bad", "not-found page, no None, refund line present")
else:
    bad("fulfil known_bad", f"title={bout['title']!r} missing={miss} leaked={leak}")

for label, p in (("paid page", page), ("not-found page", bpage)):
    hits = verdict_hits(p)
    if hits:
        bad("verdict gate", f"{label} says {hits[:3]}")

# --- 4, 5, 6, 7. the free estate -------------------------------------------
import privacy  # noqa: E402

idx_pages = sorted(p for p in PUB.glob("*/index.html") if p.parent.name != "p")
over_pages = sorted(PUB.glob("p/*/index.html"))
fam_page = PUB / "index.html"
all_pages = ([fam_page] if fam_page.is_file() else []) + idx_pages + over_pages

if not idx_pages:
    bad("sub-pages exist", "no indexable sub-pages built yet")
else:
    ok("sub-pages exist", f"{len(idx_pages)} indexable, {len(over_pages)} overflow")

if len(idx_pages) <= 200:
    ok("index budget", f"{len(idx_pages)} indexable pages, cap 200")
else:
    bad("index budget", f"{len(idx_pages)} indexable pages, cap 200")

bad_shape: list[str] = []
no_noindex: list[str] = []
verdicts: list[str] = []
persons: list[str] = []
name_shaped: list[str] = []
big: list[str] = []

# Every proper shipping name the federal table publishes, lowercased. Used to
# tell a regulated material from a person when the name reads like both.
_hmt = json.loads((DATA / "hmt.json").read_text(encoding="utf-8")) \
    if (DATA / "hmt.json").is_file() else {"entries": {}, "columns": []}
_ci = [c["key"] for c in _hmt.get("columns", [])].index("name") \
    if any(c["key"] == "name" for c in _hmt.get("columns", [])) else 1
HMT_NAMES = {r[_ci].strip().lower()
             for rows in _hmt.get("entries", {}).values() for r in rows if r[_ci]}
STAMP = re.compile(r"\b20\d\d-\d\d-\d\d\b")
for p in idx_pages + over_pages:
    h = p.read_text(encoding="utf-8")
    t = text_of(h)
    why = []
    if "<title>" not in h:
        why.append("title")
    if "<h1" not in h:
        why.append("h1")
    if "data-source-url" not in h:
        why.append("source")
    if not STAMP.search(t):
        why.append("stamp")
    if PRICE not in t:
        why.append("price")
    if why:
        bad_shape.append(f"{p.parent.name}({','.join(why)})")
    if p in over_pages and 'name="robots" content="noindex' not in h:
        no_noindex.append(p.parent.name)
    if verdict_hits(h):
        verdicts.append(p.parent.name)
    size = len(h.encode("utf-8"))
    if size > 300_000:
        big.append(f"{p.parent.name}={size//1024}KB")
    m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    if m:
        subj = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", "", m.group(1))).strip()
        if privacy.looks_personal(subj):
            persons.append(subj)
        # The subject of every page is an identification number, which carries
        # digits and so can never read as a person. The name beside it is the
        # federal table's proper shipping name, and privacy.looks_personal was
        # written to be generous about company registers: it reads "Consumer
        # commodity" and "Chemical kit" as people. So the name is checked too,
        # and where it fires we prove it is a material rather than waving it
        # through -- the exact string has to appear in § 172.101 as a published
        # proper shipping name. A name that is NOT in the table still fails.
        nm = re.sub(r"^(UN|NA|ID)\d+\s*", "", subj)
        nm = re.split(r"\s+[\u2014-]\s+", nm)[0].strip(" ,.")
        if privacy.looks_personal(nm):
            if nm.lower() in HMT_NAMES:
                name_shaped.append(nm)
            else:
                persons.append(nm)

if fam_page.is_file():
    fh = fam_page.read_text(encoding="utf-8")
    if verdict_hits(fh):
        verdicts.append("index")
    fsize = len(fh.encode("utf-8"))
    if fsize > 900_000:
        big.append(f"family={fsize//1024}KB")
    ok("family page", f"{fsize//1024} KB, cap 900 KB")
else:
    bad("family page", "families/hazmat-ship-pack/index.html is missing")

if bad_shape:
    bad("sub-page shape", f"{len(bad_shape)} bad, first: {bad_shape[:3]}")
elif idx_pages:
    ok("sub-page shape", f"{len(idx_pages) + len(over_pages)} pages have title, h1, source, stamp, {PRICE}")
if no_noindex:
    bad("overflow noindex", f"{len(no_noindex)} overflow pages are missing noindex")
elif over_pages:
    ok("overflow noindex", f"all {len(over_pages)} say noindex,follow")
if verdicts:
    bad("verdict gate", f"{len(verdicts)} pages state a conclusion, first: {verdicts[:3]}")
else:
    ok("verdict gate", f"{len(all_pages)} free pages + 2 paid pages clean")
if persons:
    bad("no person subjects", f"{len(persons)} pages, first: {persons[:2]}")
else:
    ok("no person subjects",
       f"0 of {len(idx_pages) + len(over_pages)} sub-pages; {len(name_shaped)} "
       f"shipping names read as people and every one is published in § 172.101")
if big:
    bad("page size", f"over cap: {big[:3]}")
elif all_pages:
    ok("page size", f"every page under its cap")

# --- 8. citations -----------------------------------------------------------
cites = json.loads((DATA / "citations.json").read_text(encoding="utf-8")) \
    if (DATA / "citations.json").is_file() else []
thin = [c.get("section", "?") for c in cites
        if not (c.get("url") and c.get("quote") and c.get("fetched"))]
if cites and not thin:
    drifted = [c["section"] for c in cites if c.get("status") == "drifted"]
    ok("citations", f"{len(cites)} rows, all url+quote+fetched"
       + (f", {len(drifted)} drifted" if drifted else ", 0 drifted"))
elif not cites:
    bad("citations", "data/citations.json is empty or missing")
else:
    bad("citations", f"{len(thin)} rows missing url/quote/fetched: {thin[:3]}")

# --- 9. browser -------------------------------------------------------------
if "--no-browser" in sys.argv:
    lines.append("  skip browser                 --no-browser")
else:
    b = subprocess.run([sys.executable, str(HERE / "browser_test.py")],
                       capture_output=True, text=True, cwd=str(REPO))
    first = (b.stdout.strip().splitlines() or [""])[0]
    if b.returncode == 0 and "good=" in first:
        ok("browser", first)
    else:
        bad("browser", f"exit {b.returncode} {first or b.stderr.strip()[:120]}")

print(f"SELFTEST id={FAMILY} checks={len(lines)} failed={len(fails)}")
for l in lines:
    print(l)
raise SystemExit(1 if fails else 0)
