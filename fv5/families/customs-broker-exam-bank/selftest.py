#!/usr/bin/env python3
"""Prove this family is safe to ship, and say so in counts, not dumps.

Exit 0 only when every one of these holds:

  * refresh.py --dry-run --limit 5 runs and prints its summary line;
  * fulfil() renders a page from the paid fixture, that page is noindex, and the
    buyer's email from the fixture is NOT anywhere in it;
  * every free sub-page carries a <title>, an <h1>, a data-source-url, and a
    freshness stamp (the data-newest / data-cadence-days meta the estate reads);
  * the indexable page count is <= 200;
  * no page's subject reads as a natural person (privacy.looks_personal, the same
    test scripts/check_site.py uses).

Anything short of all five exits 1. Run:  python3 selftest.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
FAM_DIR = REPO / "families" / "customs-broker-exam-bank"
FIXTURE = HERE / "fixtures" / "session_paid.json"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

INDEX_BUDGET = 200


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _h1_text(raw: str) -> str:
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    return re.sub(r"(?s)<[^>]+>", "", m.group(1)).strip() if m else ""


def check_refresh() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    ok = (r.returncode == 0 and "REFRESH id=customs-broker-exam-bank" in out
          and "source_ok=" in out)
    line = next((ln for ln in out.splitlines() if ln.startswith("REFRESH")), "no summary line")
    return ok, line


def check_fulfil() -> tuple[bool, str]:
    import fulfil as F
    session = json.loads(_text(FIXTURE))
    email = (session.get("customer_details") or {}).get("email", "")
    out = F.fulfil(session)
    html_page = out.get("html") or ""
    noindex = 'content="noindex' in html_page
    has_title = bool(re.search(r"(?is)<title>.+?</title>", html_page))
    email_leak = bool(email) and email in html_page
    state_ok = out.get("state_update") is None
    ok = bool(html_page) and noindex and has_title and not email_leak and state_ok
    note = (f"{len(html_page)} bytes, noindex={noindex}, title={has_title}, "
            f"email_leak={email_leak}, state_update_none={state_ok}")
    return ok, note


def check_pages() -> tuple[bool, dict]:
    import privacy
    stats = {"subpages": 0, "indexable": 0, "personal_subjects": 0,
             "missing_element": 0}
    if not (FAM_DIR / "index.html").is_file():
        return False, {**stats, "why": "family page not built yet"}
    pages = [FAM_DIR / "index.html"]
    subpages = sorted(FAM_DIR.glob("*/index.html"))
    stats["subpages"] = len(subpages)
    pages += subpages
    if not subpages:
        return False, {**stats, "why": "no free sub-pages built yet"}

    problems: list[str] = []
    for p in pages:
        raw = _text(p)
        is_sub = p != FAM_DIR / "index.html"
        if 'content="noindex' not in raw:
            stats["indexable"] += 1
        # Required elements on every page.
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
        # Subject test: the page's own h1 must not read as a person's name.
        if privacy.looks_personal(_h1_text(raw)):
            stats["personal_subjects"] += 1
            problems.append(f"{p.parent.name}: h1 reads as a natural person")

    stats["indexable_ok"] = stats["indexable"] <= INDEX_BUDGET
    ok = (stats["missing_element"] == 0 and stats["personal_subjects"] == 0
          and stats["indexable_ok"])
    if problems:
        stats["problems"] = problems[:8]
    return ok, stats


def main() -> int:
    all_ok = True

    ok, line = check_refresh()
    all_ok &= ok
    print(f"[{'ok' if ok else 'FAIL'}] refresh --dry-run --limit 5: {line}")

    ok, note = check_fulfil()
    all_ok &= ok
    print(f"[{'ok' if ok else 'FAIL'}] fulfil from fixture: {note}")

    ok, stats = check_pages()
    all_ok &= ok
    print(f"[{'ok' if ok else 'FAIL'}] pages: {stats.get('subpages')} sub-pages, "
          f"{stats.get('indexable')} indexable (<= {INDEX_BUDGET}: "
          f"{stats.get('indexable_ok')}), "
          f"{stats.get('missing_element')} missing elements, "
          f"{stats.get('personal_subjects')} personal subjects")
    for prob in stats.get("problems", []):
        print(f"       - {prob}")
    if "why" in stats:
        print(f"       - {stats['why']}")

    print("SELFTEST", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
