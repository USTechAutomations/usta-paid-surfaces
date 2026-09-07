#!/usr/bin/env python3
"""Self-check for the Patent Practitioner Directory family. Prints counts,
never dumps. Exits 0 only when every check below passes.

  1. refresh.py --dry-run --limit 5 works against the bundled fixture.
     Run with --no-build added on top of what the fixture normally uses: a
     dry run against a 5-row fixture would qualify 0 cities (25-practitioner
     floor), and letting that hand off to build_slices.py --only would wipe
     every one of the 200 real city pages this family's last real refresh
     built, since build_slices.py deletes any of a family's slice pages that
     the new run does not re-emit. --no-build checks the same aggregation
     code path without touching a single file under families/.
  2. fulfil.py renders non-empty HTML from fixtures/session_paid.json.
  3. Every already-built sub-page on disk has a <title>, an <h1>, a
     data-source-url, and an "as of YYYY-MM-DD" freshness stamp.
  4. The indexable page count is <= 200.
  5. Zero natural-person subjects: every firm name printed in a page's table
     is re-checked against privacy.looks_personal() at self-test time, not
     just trusted from the aggregation step that produced it.

CLI: python3 selftest.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
FAM_DIR = REPO_ROOT / "families" / "patent-practitioner-directory"
FIXTURE_SESSION = HERE / "fixtures" / "session_paid.json"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import privacy  # noqa: E402

MAX_PAGES = 200
TITLE_RE = re.compile(r"<title>[^<]+</title>")
H1_RE = re.compile(r"<h1[^>]*>")
SOURCE_RE = re.compile(r'data-source-url="[^"]+"')
STAMP_RE = re.compile(r"as of \d{4}-\d{2}-\d{2}")
FIRM_ROW_RE = re.compile(r"<tr><td>([^<]+)</td><td>\d+</td></tr>")


def fail(msg: str) -> None:
    print(f"SELFTEST FAIL: {msg}")


def check_refresh_dry_run() -> bool:
    proc = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5", "--no-build"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    ok = proc.returncode == 0 and proc.stdout.strip().startswith("REFRESH ")
    print(f"refresh --dry-run --limit 5 --no-build: rc={proc.returncode} ok={ok}")
    if not ok:
        print(proc.stdout[-500:], file=sys.stderr)
        print(proc.stderr[-500:], file=sys.stderr)
    return ok


def check_fulfil() -> bool:
    proc = subprocess.run(
        [sys.executable, str(HERE / "fulfil.py"), "--fixture", str(FIXTURE_SESSION)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    html = proc.stdout
    ok = proc.returncode == 0 and len(html) > 100 and "<html" in html
    print(f"fulfil --fixture: rc={proc.returncode} bytes={len(html)} ok={ok}")
    if not ok:
        print(proc.stderr[-500:], file=sys.stderr)
    return ok


def city_dirs() -> list[Path]:
    if not FAM_DIR.is_dir():
        return []
    out = []
    for child in sorted(FAM_DIR.iterdir()):
        if not child.is_dir():
            continue
        page = child / "index.html"
        if page.is_file():
            out.append(page)
    return out


def check_pages() -> bool:
    pages = city_dirs()
    n = len(pages)
    missing_title = missing_h1 = missing_source = missing_stamp = 0
    personal_hits = 0
    checked_firms = 0

    for page in pages:
        text = page.read_text(encoding="utf-8")
        if not TITLE_RE.search(text):
            missing_title += 1
        if not H1_RE.search(text):
            missing_h1 += 1
        if not SOURCE_RE.search(text):
            missing_source += 1
        if not STAMP_RE.search(text):
            missing_stamp += 1
        for name in FIRM_ROW_RE.findall(text):
            display = name.replace("&amp;", "&")
            if display.strip().lower().startswith("individual practitioners"):
                continue
            checked_firms += 1
            if privacy.looks_personal(display):
                personal_hits += 1

    print(f"sub-pages on disk: {n} (cap {MAX_PAGES})")
    print(f"missing title={missing_title} h1={missing_h1} "
          f"data-source-url={missing_source} freshness-stamp={missing_stamp}")
    print(f"firm names re-checked: {checked_firms}, flagged as personal: {personal_hits}")

    ok = True
    if n == 0:
        fail("0 sub-pages on disk -- run refresh.py (no flags) before selftest.py")
        ok = False
    if n > MAX_PAGES:
        fail(f"{n} sub-pages exceeds the {MAX_PAGES} index cap")
        ok = False
    if missing_title or missing_h1 or missing_source or missing_stamp:
        fail("one or more sub-pages is missing a required element")
        ok = False
    if personal_hits:
        fail(f"{personal_hits} printed firm name(s) read as a person's own name")
        ok = False
    return ok


def main() -> int:
    results = [
        check_refresh_dry_run(),
        check_fulfil(),
        check_pages(),
    ]
    if all(results):
        print("SELFTEST PASS")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
