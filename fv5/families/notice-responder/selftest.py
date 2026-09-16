#!/usr/bin/env python3
"""Prove notice-responder's delivery is safe to ship, in counts not dumps.

Exit 0 only when:

  * fulfil() on the paid fixture (CP2000, disagree) renders a page carrying
    the notice code, the deadline rule, all 7 editable blanks and an
    enclosure-checklist item count that matches data/notices.json for that
    notice, with no "@" character anywhere on the page;
  * fulfil() on the bad fixture (an unknown code) never renders an empty
    page and never renders a letter or a checklist -- it lists all 20 codes
    instead -- and also carries no "@".

Model: fv5/families/notary-journal/selftest.py, cut down to what this family
actually needs to prove (no states, no citations, no browser test: this
family has no per-notice pages and no scraped source text to check).

Run:  python3 selftest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fulfil as F  # noqa: E402

GOOD = HERE / "fixtures" / "session_paid.json"
BAD = HERE / "fixtures" / "session_bad.json"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def check_good() -> tuple[bool, str]:
    session = _load(GOOD)
    out = F.fulfil(session)
    page = out.get("html", "")
    code_value = F._field(session, "notice_code")
    notice = F.notices_by_value().get(code_value)
    bad = []
    if notice is None:
        return False, f"fixture notice_code {code_value!r} not found in data/notices.json"
    if notice["code"] not in page:
        bad.append("no code")
    if notice["deadline_rule"] not in page:
        bad.append("no deadline rule")
    fields_present = sum(1 for k, _ in F.EDITABLE_FIELDS if f'data-field="{k}"' in page)
    if fields_present != len(F.EDITABLE_FIELDS):
        bad.append(f"only {fields_present}/{len(F.EDITABLE_FIELDS)} editable fields")
    want_items = len(notice.get("documents_usually_needed") or [])
    got_items = page.count("<li><label><input type=\"checkbox\">")
    if got_items != want_items:
        bad.append(f"checklist {got_items} of {want_items} from data")
    if "@" in page:
        bad.append('an "@" character is on the page')
    if out.get("state_update") is not None:
        bad.append("state_update is not None")
    return not bad, (
        f"{len(page):,} bytes; code={notice['code']}; "
        f"fields={fields_present}/{len(F.EDITABLE_FIELDS)}; "
        f"checklist={got_items}/{want_items}"
        + ("; " + "; ".join(bad) if bad else "; clean"))


def check_bad() -> tuple[bool, str]:
    session = _load(BAD)
    out = F.fulfil(session)
    page = out.get("html", "")
    notices = F.load_notices()
    bad = []
    if not page.strip():
        bad.append("empty page")
    if "@" in page:
        bad.append('an "@" character is on the page')
    if "nr-letter" in page or "nr-checklist" in page:
        bad.append("rendered a letter or checklist for an unknown code")
    codes_listed = sum(1 for n in notices if n["code"] in page)
    if codes_listed != len(notices):
        bad.append(f"only {codes_listed}/{len(notices)} codes listed")
    return not bad, (
        f"{len(page):,} bytes; {codes_listed}/{len(notices)} codes listed"
        + ("; " + "; ".join(bad) if bad else "; clean"))


def main() -> int:
    checks = [("good fixture", check_good), ("bad fixture", check_bad)]
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
