#!/usr/bin/env python3
"""Prove this family is safe to ship, and say so in counts, not dumps.

Exit 0 only when every one of these holds:

  * refresh.py --dry-run --limit 5 runs on cached bytes and prints its summary;
  * fulfil() renders from the paid fixture, the wrapped page is noindex, and the
    buyer's email from the fixture is nowhere in it;
  * every free page carries a <title>, an <h1>, a data-source-url and (on the
    sub-pages) the freshness meta the estate reads, and shows the price;
  * the indexable page count is <= 200;
  * no page's subject reads as a natural person (privacy.looks_personal, the
    same test scripts/check_site.py uses);
  * every data/citations.json row has a url, a quote and a date read;
  * THE VERDICT GATE passes on every page, free and paid, and on the JSON and
    JavaScript inlined into them;
  * the in-page tool drives correctly in a real browser (browser_test.py).

## The verdict gate, and why it is built this way

A statute quote can legitimately contain the exact words we forbid ourselves.
California's own section says a person "shall be considered an employee rather
than an independent contractor unless...". If the gate simply banned the string,
we could never quote the law; if it exempted anything inside a quotation mark,
anyone could hide a conclusion inside one.

So the gate does two things at once:

  1. it removes from the page, before scanning, every string that appears WORD
     FOR WORD in data/citations.json -- the exact bytes we fetched from an
     official page, in their HTML-escaped and JSON-escaped forms as well;
  2. it then checks, separately, that every block on the page marked as a quote
     (data-quote="1") really is byte-identical to one of those citation rows.

Check 1 means our own sentences are always scanned. Check 2 means a quote mark
cannot be used to smuggle one in. A phrase survives only if the statute itself
says it, on a page we fetched, on a row we can point at.
"""
from __future__ import annotations

import html as H
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
LIB = REPO / "fv5" / "lib"
FAM_DIR = REPO / "families" / "contractor-audit-file"
FIXTURE = HERE / "fixtures" / "session_paid.json"
DATA = HERE / "data"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))

INDEX_BUDGET = 200
PRICE = "$49"

# The forbidden sentences. The first block is the common contract's list; the
# rest are this domain's own, because "employee" and "contractor" have many more
# ways of being asserted than a general list can carry.
BANNED = [
    "you are an employee", "you are an independent contractor", "this worker is",
    "is an employee", "is a contractor", "likely employee", "likely contractor",
    "you are compliant", "you are exempt", "you do not need", "you are covered",
    "this label is compliant", "this journal satisfies",
    # this family's own additions
    "the worker is an employee", "the worker is a contractor",
    "properly classified", "correctly classified", "misclassified",
    "you should classify", "you must classify", "should be classified",
    "would be classified", "will be classified", "we classify",
    "passes the abc test", "fails the abc test", "passes prong", "fails prong",
    "your worker is", "they are an employee", "they are a contractor",
    "counts as an employee", "counts as a contractor", "qualifies as an employee",
    "qualifies as a contractor", "you are safe", "you are at risk",
    "you are probably", "most likely an employee", "most likely a contractor",
    "we recommend", "you should reclassify", "no need to worry",
]

QUOTE_BLOCK = re.compile(
    r'<blockquote[^>]*data-quote="1"[^>]*>(.*?)</blockquote>', re.S | re.I)
SCRIPT = re.compile(r"(?is)<script\b[^>]*>.*?</script>")


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _h1_text(raw: str) -> str:
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    return re.sub(r"(?s)<[^>]+>", "", m.group(1)).strip() if m else ""


def _citation_quotes() -> list[str]:
    path = DATA / "citations.json"
    if not path.is_file():
        return []
    blob = json.loads(_text(path))
    return [r["quote"] for r in blob.get("citations", []) if r.get("quote")]


def _quote_forms(quotes: list[str]) -> list[str]:
    """Every shape a fetched quote takes once it is on a page.

    The same words appear three ways: raw in a JSON payload's decoded value,
    HTML-escaped inside a blockquote, and JSON-escaped inside the inline
    <script type="application/json">. All three are the statute's words, so all
    three are removed before we scan; nothing else is.
    """
    forms: list[str] = []
    for q in quotes:
        forms.append(q)
        forms.append(H.escape(q))
        forms.append(json.dumps(q, ensure_ascii=False)[1:-1])
    # longest first, so a short quote that is a prefix of a longer one cannot
    # leave the tail of the longer one behind to be scanned as if it were ours.
    return sorted({f for f in forms if f}, key=len, reverse=True)


def verdict_gate(pages: dict[str, str]) -> tuple[bool, dict]:
    quotes = _citation_quotes()
    forms = _quote_forms(quotes)
    known = set(quotes)
    hits: list[str] = []
    unbacked: list[str] = []
    blocks = 0
    for name, raw in pages.items():
        # (2) every block marked as a quote must BE a fetched quote. Script
        # bodies are cut out first: the inline tool holds the JavaScript that
        # BUILDS a quote block, and its template text is source, not a quote.
        # It is still scanned for banned phrases below, and browser_test.py
        # checks the block that template actually renders.
        for inner in QUOTE_BLOCK.findall(SCRIPT.sub(" ", raw)):
            blocks += 1
            got = H.unescape(re.sub(r"(?s)<[^>]+>", "", inner)).strip()
            if got not in known:
                unbacked.append(f"{name}: quote block not in citations.json: "
                                f"{got[:60]!r}")
        # (1) scan what is left once the statute's own words are taken out.
        residue = raw
        for f in forms:
            if f in residue:
                residue = residue.replace(f, " ")
        low = residue.lower()
        for phrase in BANNED:
            if phrase in low:
                hits.append(f"{name}: {phrase!r}")
    ok = not hits and not unbacked
    return ok, {"pages": len(pages), "citations": len(quotes),
                "quote_blocks": blocks, "verdict_hits": len(hits),
                "unbacked_quotes": len(unbacked),
                "problems": (hits + unbacked)[:8]}


def check_refresh() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    ok = (r.returncode == 0 and "REFRESH id=contractor-audit-file" in out
          and "cites_ok=" in out)
    line = next((ln for ln in out.splitlines() if ln.startswith("REFRESH")),
                "no summary line")
    return ok, line


def paid_page() -> tuple[str, str]:
    """(the wrapped private page, the buyer email that must not be in it)."""
    import fulfil as F
    import ppp
    session = json.loads(_text(FIXTURE))
    email = (session.get("customer_details") or {}).get("email", "")
    out = F.fulfil(session)
    wrapped = ppp.wrap_private_page(
        "contractor-audit-file", F.PRODUCT_NAME, out["html"],
        session.get("created"))
    return wrapped, email


def check_fulfil() -> tuple[bool, str]:
    import fulfil as F
    session = json.loads(_text(FIXTURE))
    out = F.fulfil(session)
    wrapped, email = paid_page()
    noindex = 'content="noindex' in wrapped
    has_title = bool(re.search(r"(?is)<title>.+?</title>", wrapped))
    email_leak = bool(email) and email in wrapped
    state_ok = out.get("state_update") is None
    consts = (F.ETA_MINUTES == 15 and bool(F.PRODUCT_NAME)
              and bool(F.LINK_ID_ENV_OR_CATALOG))
    ok = (bool(out.get("html")) and noindex and has_title and not email_leak
          and state_ok and consts)
    return ok, (f"{len(wrapped)} bytes wrapped, noindex={noindex}, "
                f"title={has_title}, email_leak={email_leak}, "
                f"state_update_none={state_ok}, constants={consts}")


def check_citations() -> tuple[bool, str]:
    path = DATA / "citations.json"
    if not path.is_file():
        return False, "data/citations.json has not been written yet"
    rows = json.loads(_text(path)).get("citations", [])
    bad = [r for r in rows
           if not r.get("url") or not r.get("quote") or not r.get("fetched")]
    drifted = [r for r in rows if r.get("status") == "drifted"]
    return not bad and bool(rows), (f"{len(rows)} rows, {len(bad)} incomplete, "
                                    f"{len(drifted)} drifted")


def free_pages() -> dict[str, str]:
    pages: dict[str, str] = {}
    idx = FAM_DIR / "index.html"
    if idx.is_file():
        pages["index"] = _text(idx)
    for p in sorted(FAM_DIR.glob("*/index.html")):
        pages[p.parent.name] = _text(p)
    return pages


def check_pages(pages: dict[str, str]) -> tuple[bool, dict]:
    import privacy
    stats = {"pages": len(pages), "subpages": max(len(pages) - 1, 0),
             "indexable": 0, "personal_subjects": 0, "missing_element": 0}
    if "index" not in pages:
        return False, {**stats, "why": "family page not built yet"}
    if len(pages) < 2:
        return False, {**stats, "why": "no free sub-pages built yet"}
    problems: list[str] = []
    for name, raw in pages.items():
        is_sub = name != "index"
        if 'content="noindex' not in raw:
            stats["indexable"] += 1
        needs = [("<title", "<title" in raw.lower()),
                 ("<h1", "<h1" in raw.lower()),
                 ("data-source-url", "data-source-url" in raw)]
        if is_sub:
            needs.append(("freshness stamp",
                          'name="data-newest"' in raw
                          and 'name="data-cadence-days"' in raw))
            needs.append(("visible price", PRICE in raw))
        for label, present in needs:
            if not present:
                stats["missing_element"] += 1
                problems.append(f"{name}: missing {label}")
        if privacy.looks_personal(_h1_text(raw)):
            stats["personal_subjects"] += 1
            problems.append(f"{name}: h1 reads as a natural person")
    stats["indexable_ok"] = stats["indexable"] <= INDEX_BUDGET
    ok = (stats["missing_element"] == 0 and stats["personal_subjects"] == 0
          and stats["indexable_ok"])
    if problems:
        stats["problems"] = problems[:8]
    return ok, stats


def check_browser() -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(HERE / "browser_test.py")],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    line = next((ln for ln in out.splitlines() if ln.startswith("BROWSER")),
                out.strip().splitlines()[-1] if out.strip() else "no output")
    return r.returncode == 0 and "good=ok" in out and "bad=ok" in out, line


def main() -> int:
    all_ok = True

    ok, line = check_refresh()
    all_ok &= ok
    print(f"refresh    {'ok ' if ok else 'FAIL'} {line}")

    ok, note = check_fulfil()
    all_ok &= ok
    print(f"fulfil     {'ok ' if ok else 'FAIL'} {note}")

    ok, note = check_citations()
    all_ok &= ok
    print(f"citations  {'ok ' if ok else 'FAIL'} {note}")

    pages = free_pages()
    ok, stats = check_pages(pages)
    all_ok &= ok
    print(f"pages      {'ok ' if ok else 'FAIL'} {stats['subpages']} sub-pages, "
          f"{stats.get('indexable')} indexable (<= {INDEX_BUDGET}: "
          f"{stats.get('indexable_ok')}), {stats['missing_element']} missing "
          f"elements, {stats['personal_subjects']} personal subjects")
    for p in stats.get("problems", []):
        print(f"           - {p}")

    scanned = dict(pages)
    try:
        wrapped, _ = paid_page()
        scanned["paid page"] = wrapped
    except Exception as exc:
        all_ok = False
        print(f"verdict    FAIL could not render the paid page: {exc!r}")
        wrapped = ""
    ok, vstats = verdict_gate(scanned)
    all_ok &= ok
    print(f"verdict    {'ok ' if ok else 'FAIL'} {vstats['pages']} pages scanned "
          f"against {vstats['citations']} citation rows, {vstats['quote_blocks']} "
          f"quote blocks, {vstats['verdict_hits']} banned phrases, "
          f"{vstats['unbacked_quotes']} unbacked quote blocks")
    for p in vstats.get("problems", []):
        print(f"           - {p}")

    ok, line = check_browser()
    all_ok &= ok
    print(f"browser    {'ok ' if ok else 'FAIL'} {line}")

    print("SELFTEST", "ok" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
