#!/usr/bin/env python3
"""Everything that has to be true before this family ships. Exit 0 or 1.

    python3 selftest.py

It checks, in order:

  * refresh.py --dry-run --limit 5 exits 0 and prints its one summary line,
    working off the bytes already on disk so the test does not depend on eight
    government websites being up;
  * every row in data/citations.json carries a url, a quote and a fetch date,
    and every quote is at most 300 characters;
  * fulfil() renders the pack from the paid fixture, the wrapped page is
    noindex, and the buyer's email is nowhere in it;
  * the free generator agrees with the Python filter on both fixtures, so the
    JavaScript on the page and the code that built the data cannot drift apart
    without this failing;
  * every sub-page has a title, an h1, a source link, a freshness stamp and the
    catalog price in visible text, and the indexable count stays under budget;
  * no page's subject reads as a natural person;
  * the VERDICT GATE: no page, free or paid, tells the reader what their own
    legal position is.

The verdict gate is the one worth explaining. This family sells rule text and
draft wording. The moment a page says "you are covered" or "you must disclose"
it has stopped selling a document and started giving legal advice about a
situation it knows nothing about. So the sentences that would do that are
banned outright, and the ban is tested rather than remembered.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "fv5" / "lib"))

FAMILY = "ai-disclosure-notice"
PAGES = ROOT / "families" / FAMILY
PRICE = "$49"
INDEX_BUDGET = 200
QUOTE_MAX = 300

# The estate-wide list from scripts/check_site.py, plus the ones this domain
# needs. A page here may say what a rule says. It may not say what the reader's
# position under that rule is, and it may not tell them a draft is enough.
VERDICT_BANNED = [
    # inherited
    "you are an employee", "you are an independent contractor", "this worker is",
    "is an employee", "is a contractor", "likely employee", "likely contractor",
    "you are compliant", "you are exempt", "you do not need", "you are covered",
    "this label is compliant", "this journal satisfies",
    # this domain
    "you are not covered", "you are required to", "you must disclose",
    "you must display", "you must label", "you need to disclose",
    "no disclosure is required", "you are in the clear", "this applies to you",
    "does not apply to you", "applies to your", "you are subject to",
    "you are not subject to", "this makes you compliant", "brings you into compliance",
    "this notice is compliant", "this notice satisfies", "this pack satisfies",
    "satisfies article 50", "satisfies the eu ai act", "you have no obligation",
    "you have an obligation", "your obligations are", "your duty is",
    "legally sufficient", "this is enough to comply", "guarantees compliance",
]

_STAMP = re.compile(r'name="data-newest" content="(\d{4}-\d{2}-\d{2})"')


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _h1_text(raw: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.S | re.I)
    return re.sub(r"<[^>]+>", " ", m.group(1)) if m else ""


def check_refresh() -> tuple[bool, str]:
    code, out = _run([sys.executable, str(HERE / "refresh.py"),
                      "--dry-run", "--limit", "5"])
    line = next((l for l in out.splitlines() if l.startswith("REFRESH id=")), "")
    ok = code == 0 and line.startswith(f"REFRESH id={FAMILY} ")
    return ok, (line or f"exit {code}, no summary line")


def check_citations() -> tuple[bool, str]:
    p = HERE / "data" / "citations.json"
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return False, f"unreadable: {e}"
    bad_field = [r.get("id") for r in rows
                 if not (r.get("url") and r.get("quote") and r.get("fetched"))]
    too_long = [r.get("id") for r in rows if len(r.get("quote") or "") > QUOTE_MAX]
    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_drift = sum(1 for r in rows if r.get("status") == "drifted")
    ok = not bad_field and not too_long and not n_drift
    note = (f"{len(rows)} rows, {n_ok} verified, {n_drift} drifted, "
            f"{len(bad_field)} missing a field, {len(too_long)} over {QUOTE_MAX} chars")
    return ok, note


def check_fulfil() -> tuple[bool, str]:
    import fulfil as F
    import ppp
    fx = json.loads((HERE / "fixtures" / "session_paid.json").read_text(encoding="utf-8"))
    out = F.fulfil(fx)
    frag = out["html"]
    page = ppp.wrap_private_page(FAMILY, F.PRODUCT_NAME, frag, fx.get("created"))
    email = (fx.get("customer_details") or {}).get("email") or ""
    leak = bool(email) and email in page
    at_leak = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", page.replace(
        "operations@ustechautomations.com", "")))
    noindex = 'content="noindex' in page
    has_title = "<title>" in page
    org_in = "Northgate Labs Ltd" in frag
    consts = (F.ETA_MINUTES == 15 and bool(F.LINK_ID_ENV_OR_CATALOG)
              and bool(F.PRODUCT_NAME))
    state_ok = out["state_update"] is None
    verdict = [b for b in VERDICT_BANNED if b in page.lower()]
    ok = (bool(frag) and noindex and has_title and not leak and not at_leak
          and org_in and consts and state_ok and not verdict)
    note = (f"{len(page)} bytes, noindex={noindex}, title={has_title}, "
            f"email_leak={leak or at_leak}, org_name_used={org_in}, "
            f"state_update_none={state_ok}, verdict_hits={verdict or 0}")
    return ok, note


def check_generator() -> tuple[bool, str]:
    """The in-page tool and the Python filter must agree on both fixtures."""
    import notice_build as nb
    bad = []
    counts = []
    for name in ("known_good", "known_bad"):
        fx = json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
        a, want = fx["input"], fx["expect"]
        res = {r["id"]: r["result"] for r in nb.matrix(a)}
        for did, expected in (want.get("duty_status") or {}).items():
            if res.get(did) != expected:
                bad.append(f"{name}:{did} wanted {expected} got {res.get(did)}")
        n = sum(1 for v in res.values() if v == "matches")
        if "min_matches" in want and n < want["min_matches"]:
            bad.append(f"{name}: {n} matches, wanted at least {want['min_matches']}")
        if "max_matches" in want and n > want["max_matches"]:
            bad.append(f"{name}: {n} matches, wanted at most {want['max_matches']}")
        if want.get("no_row_matches") and n:
            bad.append(f"{name}: {n} rows matched but none should")
        if want.get("every_row_has_reason"):
            missing = [r["id"] for r in nb.matrix(a) if not (r.get("why") or "").strip()]
            if missing:
                bad.append(f"{name}: {len(missing)} rows with no reason given")
        keys = [x["key"] for x in nb.notices_for(a, a.get("org") or "[your organisation]")]
        if "notice_keys" in want and keys != want["notice_keys"]:
            bad.append(f"{name}: notices {keys} != {want['notice_keys']}")
        counts.append(f"{name}={n} match/{len(keys)} notices")
    return not bad, "; ".join(counts) + (f"  PROBLEMS: {bad}" if bad else "")


def check_pages() -> tuple[bool, dict]:
    import privacy
    st = {"family": 0, "subpages": 0, "indexable": 0, "personal": 0,
          "no_title": 0, "no_h1": 0, "no_source": 0, "no_stamp": 0,
          "no_price": 0, "verdict": [], "biggest": 0}
    fam = PAGES / "index.html"
    if fam.is_file():
        raw = fam.read_text(encoding="utf-8", errors="replace")
        st["family"] = 1
        st["biggest"] = max(st["biggest"], len(raw))
        if 'content="noindex' not in raw:
            st["indexable"] += 1
        if "<title>" not in raw:
            st["no_title"] += 1
        if not _h1_text(raw):
            st["no_h1"] += 1
        if "data-source-url" not in raw:
            st["no_source"] += 1
        if PRICE not in raw:
            st["no_price"] += 1
        if privacy.looks_personal(_h1_text(raw)):
            st["personal"] += 1
        for b in VERDICT_BANNED:
            if b in raw.lower():
                st["verdict"].append(f"index.html: {b}")

    for sub in sorted(PAGES.glob("*/index.html")):
        raw = sub.read_text(encoding="utf-8", errors="replace")
        st["subpages"] += 1
        st["biggest"] = max(st["biggest"], len(raw))
        if 'content="noindex' not in raw:
            st["indexable"] += 1
        if "<title>" not in raw:
            st["no_title"] += 1
        if not _h1_text(raw):
            st["no_h1"] += 1
        if "data-source-url" not in raw:
            st["no_source"] += 1
        if not _STAMP.search(raw):
            st["no_stamp"] += 1
        if PRICE not in raw:
            st["no_price"] += 1
        if privacy.looks_personal(_h1_text(raw)):
            st["personal"] += 1
        for b in VERDICT_BANNED:
            if b in raw.lower():
                st["verdict"].append(f"{sub.parent.name}: {b}")

    st["indexable_ok"] = st["indexable"] <= INDEX_BUDGET
    st["size_ok"] = st["biggest"] <= 900_000
    st["ok"] = (st["family"] == 1 and st["subpages"] >= 6
                and not st["no_title"] and not st["no_h1"] and not st["no_source"]
                and not st["no_stamp"] and not st["no_price"]
                and not st["personal"] and not st["verdict"]
                and st["indexable_ok"] and st["size_ok"])
    return st["ok"], st


def check_browser() -> tuple[bool, str]:
    """Drive the real page in a real browser, if the harness is on this host."""
    py = Path("/home/gmullins/Claude CLI/harness/browser/venv/bin/python")
    if not py.is_file():
        return True, "SKIPPED — the browser harness is not on this host"
    code, out = _run([str(py), str(HERE / "browser_test.py")])
    line = next((l for l in out.splitlines() if l.startswith("BROWSER id=")), "")
    return code == 0, (line or f"exit {code}: {out.strip().splitlines()[-1:] or ''}")


def main() -> int:
    results = []
    ok, note = check_refresh(); results.append(("refresh --dry-run", ok, note))
    ok, note = check_citations(); results.append(("citations", ok, note))
    ok, note = check_fulfil(); results.append(("fulfil + verdict gate", ok, note))
    ok, note = check_generator(); results.append(("generator vs fixtures", ok, note))
    ok, st = check_pages()
    results.append(("pages", ok,
                    f"{st['family']} family + {st['subpages']} sub-pages, "
                    f"{st['indexable']} indexable (<= {INDEX_BUDGET}: "
                    f"{st['indexable_ok']}), biggest {st['biggest']} bytes "
                    f"(<= 900000: {st['size_ok']}), missing: title={st['no_title']} "
                    f"h1={st['no_h1']} source={st['no_source']} stamp={st['no_stamp']} "
                    f"price={st['no_price']}, personal subjects={st['personal']}, "
                    f"verdict hits={len(st['verdict'])}"))
    if st["verdict"]:
        results.append(("verdict gate detail", False, "; ".join(st["verdict"][:10])))
    ok, note = check_browser(); results.append(("browser", ok, note))

    width = max(len(r[0]) for r in results)
    for name, good, note in results:
        print(f"{'PASS' if good else 'FAIL'}  {name:<{width}}  {note}")
    passed = all(r[1] for r in results)
    print("SELFTEST PASS" if passed else "SELFTEST FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
