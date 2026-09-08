#!/usr/bin/env python3
"""Turn one paid checkout into a private watch page and a watch record.

Input is a Stripe Checkout Session object: pass a file with --fixture, or pipe
the JSON on stdin (which is how the real webhook would hand it over). We never
read payment credentials here -- the session is handed to us already settled.

On a paid session we:

  1. read the serial and (optional) mark text out of the checkout custom fields,
  2. find that serial in the dated store refresh.py keeps,
  3. render a private watch page (never indexed) under
     families/trademark-watch/p/<private_slug>/,
  4. append the watch to ~/.hermes/state/fv5/trademark-watch/watches.jsonl so
     refresh.py keeps the page current for 12 months,
  5. print a JSON report (and the state_update the fulfilment system stores).

The buyer's email is never written onto the page. It stays in the watch record,
which is operational state, not a published page.

Run:  python3 fv5/families/trademark-watch/fulfil.py --fixture \
        fv5/families/trademark-watch/fixtures/session_paid.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import marks  # noqa: E402

FAMILY = marks.FAMILY
DATA = HERE / "data" / "marks.json"
FAM_DIR = ROOT / "families" / FAMILY
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
WATCHES = STATE / "watches.jsonl"
WATCH_MONTHS_DAYS = 365


def _custom_field(session: dict, key: str) -> str:
    for f in session.get("custom_fields") or []:
        if f.get("key") == key:
            return (f.get("text") or {}).get("value") or ""
    return ""


def load_store() -> list[dict]:
    if DATA.is_file():
        try:
            return json.loads(DATA.read_text(encoding="utf-8")).get("marks", [])
        except (OSError, ValueError):
            return []
    return []


def fulfil(session: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if session.get("payment_status") != "paid":
        return {"family": FAMILY, "ok": False,
                "reason": f"session is not paid (payment_status="
                          f"{session.get('payment_status')!r}); nothing fulfilled"}

    serial = _custom_field(session, "serial").strip()
    mark_text = _custom_field(session, "mark_text").strip()
    session_id = session.get("id") or "unknown"
    email = (session.get("customer_details") or {}).get("email") or ""

    recs = load_store()
    rec = next((r for r in recs if r.get("serial") == serial), None)
    if rec and not mark_text:
        mark_text = rec.get("mark_text") or ""

    token = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    base = marks.slug_for({"mark_text": mark_text, "serial": serial})
    private_slug = f"{base}-{token}"
    until = (today + dt.timedelta(days=WATCH_MONTHS_DAYS)).isoformat()

    stamp = _stamp(recs) if recs else today.isoformat()
    fixture = True                       # store came from the fixture in this build

    watch = {
        "serial": serial,
        "mark_text": mark_text,
        "private_slug": private_slug,
        "until": until,
    }

    sim = marks.similar_marks(rec, recs, _as_of(stamp, today)) if rec else []
    dest = FAM_DIR / "p" / private_slug / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(marks.render_private(watch, rec, sim, stamp, fixture, today),
                    encoding="utf-8")

    # Append the watch to operational state (not a page), so refresh.py keeps it
    # fresh. Email is kept here for the operator; it never reaches a page.
    STATE.mkdir(parents=True, exist_ok=True)
    with WATCHES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**watch, "session": session_id, "email": email,
                             "started": today.isoformat()}) + "\n")

    return {
        "family": FAMILY,
        "ok": True,
        "session": session_id,
        "serial": serial,
        "mark_text": mark_text,
        "found_in_store": rec is not None,
        "status": marks.status_text(rec) if rec else "not yet in the daily copy we hold",
        "similar_count": len(sim),
        "private_page": str(dest.relative_to(ROOT)),
        "private_url": f"https://ustechautomations.com/feeds/{FAMILY}/p/{private_slug}",
        "until": until,
        "weekly_update_promise": (
            "We re-read the USPTO record about once a week for 12 months and email "
            "you on any status change, similar filing, or upcoming deadline."
        ),
        "state_update": {"watch": watch},
    }


def _stamp(recs: list[dict]) -> str:
    dates = [r.get("transaction_date") for r in recs if r.get("transaction_date")]
    return max(dates) if dates else dt.date.today().isoformat()


def _as_of(stamp: str, today: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(stamp[:10])
    except ValueError:
        return today


def _load_session(args) -> dict:
    if args.fixture:
        return json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("no session on stdin and no --fixture given")
    return json.loads(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="path to a checkout session JSON file")
    args = ap.parse_args(argv)
    report = fulfil(_load_session(args))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
