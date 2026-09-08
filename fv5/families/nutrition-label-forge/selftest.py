#!/usr/bin/env python3
"""Prove this family is safe to ship, in counts rather than dumps.

Exit 0 only when all of these hold:

  * refresh.py --dry-run --limit 5 runs on the cached raw and prints its line;
  * fulfil() renders from the paid fixture, the wrapped page is noindex, and the
    buyer's email from the fixture appears nowhere in it;
  * every page carries a <title>, an <h1>, a data-source-url and, on the free
    sub-pages, the freshness meta and the catalog price in visible text;
  * the indexable page count is <= 200;
  * no page's subject reads as a natural person (the same privacy test
    scripts/check_site.py uses);
  * THE VERDICT GATE: no page, free or paid, contains a sentence that decides
    something for the reader -- whether an exemption covers them, whether a
    label passes. The list below is the common one plus the ones this domain
    invites, and it is a blunt substring test on purpose;
  * every data/citations.json row has a url, a quote and a fetched date;
  * browser_test.py passes: the real page in a real browser, both fixtures.

    python3 selftest.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FAMILY = "nutrition-label-forge"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
FAM_DIR = REPO / "families" / FAMILY
FIXTURE = HERE / "fixtures" / "session_paid.json"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "fv5" / "lib"))

INDEX_BUDGET = 200

# The common list from the fv6 contract, then the ones this domain invites. A
# page that says any of these has stopped selling a file and started giving an
# answer we are not qualified to give.
VERDICTS = [
    "you are an employee", "you are an independent contractor", "this worker is",
    "is an employee", "is a contractor", "likely employee", "likely contractor",
    "you are compliant", "you are exempt", "you do not need", "you are covered",
    "this label is compliant", "this journal satisfies",
    # nutrition labelling
    "you are not exempt", "you qualify for the exemption", "you don't need a label",
    "you do not need a label", "no panel is required", "no label is required",
    "your label is compliant", "this panel is compliant", "this panel complies",
    "your panel meets", "your product is exempt", "your product is not exempt",
    "this recipe is safe", "safe for people with", "free from allergens",
    "allergen free", "fda approved", "fda-approved", "approved by fda",
    "meets fda requirements", "your label meets",
]


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _h1_text(raw: str) -> str:
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    return re.sub(r"(?s)<[^>]+>", "", m.group(1)).strip() if m else ""


def _visible(raw: str) -> str:
    """The page with its script, style and tags stripped, lowercased."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).lower()


def _our_words(raw: str) -> str:
    """The page minus the blocks that hold the regulation's own words.

    The verdict gate is a blunt substring test and it stays blunt, but it has to
    be pointed at what WE wrote. 21 CFR 101.9(g)(8) contains the phrase "an FDA
    approved database"; quoting that paragraph is the whole point of the page it
    is on, and a gate that fails on it would teach us to stop quoting the rule,
    which is the opposite of what it is for. So the tables and blockquotes --
    the only two places a page carries verbatim regulation -- come out first,
    and everything left is ours: the title, the lede, the facts, the limits and
    the offer.
    """
    t = re.sub(r"(?is)<table[^>]*>.*?</table>", " ", raw)
    t = re.sub(r"(?is)<blockquote[^>]*>.*?</blockquote>", " ", t)
    return _visible(t)


def price_string() -> str:
    cat = json.loads(_text(REPO / "catalog.json"))
    fams = cat["families"] if isinstance(cat, dict) else cat
    for f in fams:
        if f["id"] == FAMILY:
            return f.get("price", "")
    return ""


def check_refresh() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    line = next((ln for ln in out.splitlines() if ln.startswith("REFRESH")),
                "no summary line")
    ok = r.returncode == 0 and f"REFRESH id={FAMILY}" in out and "source_ok=" in out
    return ok, line


def check_fulfil() -> tuple[bool, str]:
    import fulfil as F
    import ppp
    session = json.loads(_text(FIXTURE))
    email = (session.get("customer_details") or {}).get("email", "")
    out = F.fulfil(session)
    frag = out.get("html") or ""
    page = ppp.wrap_private_page(FAMILY, out.get("title", ""), frag)
    noindex = "noindex" in page
    has_title = bool(re.search(r"(?is)<title>.+?</title>", page))
    leak = bool(email) and (email in page or "@" in _visible(frag))
    state_ok = out.get("state_update") is None
    named = "Harvest Oat Granola" in frag
    ok = bool(frag) and noindex and has_title and not leak and state_ok and named
    return ok, (f"{len(frag)} byte fragment, {len(page)} byte page, noindex={noindex}, "
                f"title={has_title}, email_leak={leak}, state_update_none={state_ok}, "
                f"product_named={named}")


def check_pages() -> tuple[bool, dict]:
    import privacy
    price = price_string()
    stats = {"subpages": 0, "indexable": 0, "personal_subjects": 0,
             "missing_element": 0, "no_price": 0, "verdicts": 0}
    if not (FAM_DIR / "index.html").is_file():
        return False, {**stats, "why": "family page not built yet"}
    fam_page = FAM_DIR / "index.html"
    subpages = sorted(FAM_DIR.glob("*/index.html"))
    stats["subpages"] = len(subpages)
    if not subpages:
        return False, {**stats, "why": "no free sub-pages built yet"}

    problems: list[str] = []
    for p in [fam_page] + subpages:
        raw = _text(p)
        is_sub = p != fam_page
        if "noindex" not in raw:
            stats["indexable"] += 1
        needs = [("<title", "<title" in raw.lower()),
                 ("<h1", "<h1" in raw.lower()),
                 ("data-source-url", "data-source-url" in raw)]
        if is_sub:
            needs.append(("freshness stamp",
                          'name="data-newest"' in raw
                          and 'name="data-cadence-days"' in raw))
        for label, present in needs:
            if not present:
                stats["missing_element"] += 1
                problems.append(f"{p.parent.name}: missing {label}")
        vis = _visible(raw)
        ours = _our_words(raw)
        if is_sub and price and price.lower() not in vis:
            stats["no_price"] += 1
            problems.append(f"{p.parent.name}: the price {price} is not in visible text")
        for v in VERDICTS:
            if v in ours:
                stats["verdicts"] += 1
                problems.append(f"{p.parent.name}: says {v!r}")
        if privacy.looks_personal(_h1_text(raw)):
            stats["personal_subjects"] += 1
            problems.append(f"{p.parent.name}: h1 reads as a natural person")

    stats["indexable_ok"] = stats["indexable"] <= INDEX_BUDGET
    ok = (stats["missing_element"] == 0 and stats["personal_subjects"] == 0
          and stats["indexable_ok"] and stats["no_price"] == 0
          and stats["verdicts"] == 0)
    if problems:
        stats["problems"] = problems[:10]
    return ok, stats


def check_paid_verdicts() -> tuple[bool, str]:
    """The gate again, on the page a buyer gets, which no site check ever sees."""
    import fulfil as F
    frag = F.fulfil(json.loads(_text(FIXTURE)))["html"]
    vis = _visible(frag)
    bad = [v for v in VERDICTS if v in vis]
    return not bad, (f"{len(vis)} visible chars, {len(bad)} verdict phrase(s)"
                     + (f": {bad[:3]}" if bad else ""))


def check_citations() -> tuple[bool, str]:
    rows = json.loads(_text(HERE / "data" / "citations.json"))
    if isinstance(rows, dict):
        rows = rows.get("citations", [])
    bad = [r.get("key", "?") for r in rows
           if not (r.get("url") and r.get("quote") and r.get("fetched"))]
    drifted = [r.get("key") for r in rows if r.get("status") == "drifted"]
    ok = not bad
    note = f"{len(rows)} cited rules, {len(bad)} incomplete, {len(drifted)} drifted"
    if bad:
        note += f" -- incomplete: {bad[:5]}"
    return ok, note


def check_browser() -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(HERE / "browser_test.py")],
                       capture_output=True, text=True, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    line = next((ln for ln in out.splitlines() if ln.startswith("BROWSER")),
                "no BROWSER line")
    return r.returncode == 0 and "good=ok" in out and "bad=ok" in out, line


def main() -> int:
    all_ok = True
    for label, fn in (("refresh --dry-run --limit 5", check_refresh),
                      ("fulfil from fixture", check_fulfil),
                      ("verdict gate on the paid page", check_paid_verdicts),
                      ("citations", check_citations),
                      ("browser test", check_browser)):
        ok, note = fn()
        all_ok &= ok
        print(f"[{'ok' if ok else 'FAIL'}] {label}: {note}")

    ok, stats = check_pages()
    all_ok &= ok
    print(f"[{'ok' if ok else 'FAIL'}] pages: {stats.get('subpages')} sub-pages, "
          f"{stats.get('indexable')} indexable (<= {INDEX_BUDGET}: "
          f"{stats.get('indexable_ok')}), {stats.get('missing_element')} missing "
          f"elements, {stats.get('no_price')} without a price, "
          f"{stats.get('verdicts')} verdict phrases, "
          f"{stats.get('personal_subjects')} personal subjects")
    for prob in stats.get("problems", []):
        print(f"       - {prob}")
    if "why" in stats:
        print(f"       - {stats['why']}")

    print("SELFTEST", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
