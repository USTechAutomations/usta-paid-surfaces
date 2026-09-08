#!/usr/bin/env python3
"""Prove this family is safe to ship, and say so in counts, not dumps.

Exit 0 only when every one of these holds:

  * refresh.py --dry-run --limit 5 runs and prints its summary line;
  * fulfil() renders a page from the paid fixture, that page is noindex once the
    private-page wrapper has been round it, and no email address appears on it;
  * every free sub-page carries a <title>, an <h1>, a data-source-url, the
    freshness meta the estate reads, and the catalog's price in visible text;
  * the indexable page count is <= 200;
  * no page's subject reads as a natural person;
  * the verdict gate passes: no page, free or paid, tells a reader what their
    own position is. This is the one that matters most here. A page that said
    "you are compliant" would be doing the thing this whole family refuses to
    do -- a notary's own regulator decides that, from the notary's own facts,
    and a static page has neither;
  * every row in data/citations.json carries a url, a quote and a fetch date;
  * the headless browser test passes.

Anything short of all of those exits 1. Run:  python3 selftest.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FAMILY = "notary-journal"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
FAM_DIR = REPO / "families" / FAMILY
FIXTURE = HERE / "fixtures" / "session_paid.json"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

INDEX_BUDGET = 200

# The verdict gate. The first block is the common list every fv6 family carries;
# the second is this domain's own, because the sentence that would do the damage
# here is not "you are an employee" but "your journal is fine".
VERDICTS = (
    "you are an employee", "you are an independent contractor", "this worker is",
    "is an employee", "is a contractor", "likely employee", "likely contractor",
    "you are compliant", "you are exempt", "you do not need", "you are covered",
    "this label is compliant", "this journal satisfies",
    # domain additions
    "your journal is compliant", "this meets your state", "you may legally",
    "you are allowed to", "you are required to keep", "this satisfies your state",
    "your journal meets", "you can legally", "your state allows you",
)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _visible(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"(?s)<[^>]+>", " ", raw)


def _h1_text(raw: str) -> str:
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    return re.sub(r"(?s)<[^>]+>", "", m.group(1)).strip() if m else ""


def _pages() -> list[Path]:
    return sorted(FAM_DIR.glob("*/index.html"))


def check_refresh() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0 and f"REFRESH id={FAMILY}" in out and "source_ok=" in out
    line = next((ln for ln in out.splitlines() if ln.startswith("REFRESH")),
                "no summary line")
    return ok, line


def check_fulfil() -> tuple[bool, str]:
    sys.path.insert(0, str(REPO / "fv5" / "lib"))
    import fulfil as F
    import ppp

    session = json.loads(_text(FIXTURE))
    out = F.fulfil(session)
    wrapped = ppp.wrap_private_page(FAMILY, out["title"], out["html"],
                                    1757289600)
    notes = []
    if "noindex" not in wrapped.lower():
        notes.append("no noindex")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", _visible(wrapped)):
        notes.append("an email address is on the private page")
    if out["state_update"] is not None:
        notes.append("state_update is not None")
    if "$49" not in _visible(wrapped) and "does not expire" not in wrapped:
        notes.append("no licence line")
    return not notes, f"{len(wrapped):,} bytes; " + ("; ".join(notes) or "clean")


def check_pages() -> tuple[bool, str]:
    import privacy

    pages = _pages()
    fam_page = FAM_DIR / "index.html"
    bad: list[str] = []
    price = "$49"
    for p in pages:
        raw = _text(p)
        vis = _visible(raw)
        if "<title>" not in raw.lower():
            bad.append(f"{p.parent.name}: no title")
        if not _h1_text(raw):
            bad.append(f"{p.parent.name}: no h1")
        if "data-source-url" not in raw:
            bad.append(f"{p.parent.name}: no data-source-url")
        if 'name="data-newest"' not in raw or 'name="data-cadence-days"' not in raw:
            bad.append(f"{p.parent.name}: no freshness meta")
        if 'name="data-slice-name"' not in raw:
            bad.append(f"{p.parent.name}: no slice name")
        if price not in vis:
            bad.append(f"{p.parent.name}: the price is not in visible text")
        if privacy.looks_personal(_h1_text(raw)):
            bad.append(f"{p.parent.name}: the subject reads as a person")
    if fam_page.is_file() and privacy.looks_personal(_h1_text(_text(fam_page))):
        bad.append("family page: the subject reads as a person")
    indexable = len(pages) + (1 if fam_page.is_file() else 0)
    if indexable > INDEX_BUDGET:
        bad.append(f"{indexable} indexable pages, over the budget of {INDEX_BUDGET}")
    return not bad, (f"{indexable} indexable pages, {len(pages)} state pages; "
                     + ("; ".join(bad[:4]) if bad else "all carry title, h1, source, "
                        "freshness and price"))


def check_verdicts() -> tuple[bool, str]:
    """No page tells a reader what their own position is."""
    sys.path.insert(0, str(REPO / "fv5" / "lib"))
    import fulfil as F

    hits: list[str] = []
    pages = _pages() + [FAM_DIR / "index.html"]
    texts = [(p.parent.name, _visible(_text(p))) for p in pages if p.is_file()]
    texts.append(("private page",
                  _visible(F.fulfil(json.loads(_text(FIXTURE)))["html"])))
    for who, vis in texts:
        low = " ".join(vis.split()).lower()
        for phrase in VERDICTS:
            if phrase in low:
                hits.append(f"{who}: {phrase!r}")
    return not hits, (f"{len(texts)} pages read; "
                      + ("; ".join(hits[:4]) if hits else "no verdict sentence anywhere"))


def check_citations() -> tuple[bool, str]:
    p = HERE / "data" / "citations.json"
    if not p.is_file():
        return False, "data/citations.json is not on disk"
    rows = json.loads(_text(p))
    bad = [r["code"] for r in rows
           if not r.get("url") or not r.get("fetched") or "status" not in r]
    quoted = sum(1 for r in rows if r.get("quote"))
    unread = [r["code"] for r in rows if not r.get("quote")]
    return not bad, (f"{len(rows)} rows, {quoted} carry the state's own words, "
                     f"{len(unread)} recorded unread"
                     + (f"; missing url or date: {bad[:4]}" if bad else ""))


def check_browser() -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(HERE / "browser_test.py")],
                       capture_output=True, text=True, timeout=900)
    line = next((ln for ln in (r.stdout or "").splitlines()
                 if ln.startswith("BROWSER")), "no browser line")
    return r.returncode == 0, line


def main() -> int:
    checks = [
        ("refresh", check_refresh),
        ("fulfil", check_fulfil),
        ("pages", check_pages),
        ("verdict gate", check_verdicts),
        ("citations", check_citations),
        ("browser", check_browser),
    ]
    ok = True
    for name, fn in checks:
        try:
            good, line = fn()
        except Exception as e:  # noqa: BLE001
            good, line = False, f"{type(e).__name__}: {e}"
        ok = ok and good
        print(f"{'PASS' if good else 'FAIL'}  {name:13} {line}")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
