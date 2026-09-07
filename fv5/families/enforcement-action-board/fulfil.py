#!/usr/bin/env python3
"""Turn one paid checkout into the buyer's private confirmation page.

WHAT THIS RETURNS
    fulfil(session) -> {"title": str, "html": str, "state_update": dict | None}

    On a clean sale it returns a private page confirming the firm's name, the
    state whose Get help slot they bought, a link to that public board, the exact
    line that will show in the Get help box, and the date the twelve months end;
    and a state_update that tells the framework to feature this firm.

    If that state's slot is already held by someone else (first paid, first
    shown), it returns instead a "slot already taken" page that tells the buyer to
    reply to their Stripe receipt for a refund, and NO state_update -- we never
    feature a second firm on a taken state, and this file never moves money.

RULES HONOURED HERE
    * The buyer's email never appears on the page.
    * The private page carries <meta name="robots" content="noindex,nofollow">.
    * The delivery promise (15 minutes) and its fallback line, the 14-day refund
      line, and the "not EPA / not legal advice" disclaimer are on every page.
    * Deterministic for the same input and the same featured store.

RUN
    python3 fulfil.py --fixture fixtures/session_paid.json    # prints the HTML
    python3 fulfil.py --fixture fixtures/session_taken.json   # the taken page
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

FAMILY = "enforcement-action-board"
AGENCY = "EPA"
HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
RUNTIME_FEATURED = Path.home() / ".hermes" / "state" / "fv5" / FAMILY / "featured.json"
FIXTURE_FEATURED = FIXTURES / "featured.json"
PUBLIC_BASE = "https://ustechautomations.com/feeds/" + FAMILY

DISCLAIMER = (
    f"Records are reproduced from {AGENCY} as published, may lag the source, and "
    f"say nothing about guilt or current compliance. US Tech Automations is not {AGENCY}."
)
NOT_ADVICE = (
    f"Not affiliated with {AGENCY}. This is a paid listing on our page, not legal, tax "
    "or professional advice, and not any endorsement by any agency."
)
REFUND = (
    "Refund on request within 14 days, and any time the state you asked for was "
    "already taken: reply to your Stripe receipt and we refund it."
)
DELIVERY = (
    "Your listing goes live within 15 minutes of payment. Still not showing after "
    "15 minutes? Reply to your Stripe receipt and a person will finish it by hand."
)

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

esc = html.escape


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _custom(session: dict) -> dict:
    """Flatten Stripe's custom_fields[] into {key: value}."""
    out: dict[str, str] = {}
    for cf in session.get("custom_fields") or []:
        key = cf.get("key")
        if not key:
            continue
        kind = cf.get("type")
        val = ""
        if kind == "dropdown":
            val = (cf.get("dropdown") or {}).get("value") or ""
        elif kind == "numeric":
            val = (cf.get("numeric") or {}).get("value") or ""
        else:
            val = (cf.get("text") or {}).get("value") or ""
        out[key] = str(val).strip()
    return out


def _until(created: int | None) -> str:
    """Twelve months from the payment date, as YYYY-MM-DD. Feb 29 -> Feb 28."""
    base = (dt.datetime.fromtimestamp(created, dt.timezone.utc).date() if created
            else dt.date.today())
    try:
        return base.replace(year=base.year + 1).isoformat()
    except ValueError:  # 29 Feb in a non-leap next year
        return base.replace(year=base.year + 1, day=28).isoformat()


def _normalise(store) -> list[dict]:
    """Accept any of the shapes a featured store might carry, return a flat list."""
    if isinstance(store, dict):
        feats = store.get("featured", store)
    else:
        feats = store
    out: list[dict] = []
    if isinstance(feats, list):
        out = [e for e in feats if isinstance(e, dict)]
    elif isinstance(feats, dict):
        # nested {"epa": {"CA": {...}}}
        for ag, by_state in feats.items():
            if isinstance(by_state, dict) and any(isinstance(v, dict) for v in by_state.values()):
                for code, e in by_state.items():
                    if isinstance(e, dict):
                        out.append({"agency": ag, "state": code, **e})
            elif isinstance(by_state, dict):
                out.append(by_state)  # single raw state_update under "featured"
        if not out and {"agency", "state"} <= set(feats):
            out = [feats]
    return out


def _store() -> list[dict]:
    """The featured list from the runtime store if present, else the fixture."""
    for path in (RUNTIME_FEATURED, FIXTURE_FEATURED):
        if path.is_file():
            try:
                return _normalise(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                return []
    return []


def _holder(state_code: str, today: str) -> dict | None:
    """Who, if anyone, already holds this state's active slot."""
    for e in _store():
        if str(e.get("agency", "epa")).lower() != "epa":
            continue
        if str(e.get("state", "")).upper() != state_code.upper():
            continue
        until = str(e.get("until") or "")
        if not until or until >= today:  # no end date, or not yet ended
            return e
    return None


# --------------------------------------------------------------------- pages

_STYLE = (
    "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:44rem;margin:2rem auto;"
    "padding:0 1rem;color:#1a1a1a}.box{border:1px solid #ccc;border-radius:8px;"
    "padding:1rem 1.25rem;margin:1rem 0}.fine{color:#555;font-size:.9rem}"
    "a{color:#0b5}</style>"
)


def _shell(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex,nofollow\">\n"
        f"<title>{esc(title)}</title>\n{_STYLE}\n</head>\n<body>\n"
        f"{body}\n"
        f"<p class=\"fine\">{esc(DELIVERY)}</p>\n"
        f"<p class=\"fine\">{esc(REFUND)}</p>\n"
        f"<p class=\"fine\">{esc(NOT_ADVICE)}</p>\n"
        f"<p class=\"fine\">{esc(DISCLAIMER)}</p>\n"
        "</body>\n</html>\n"
    )


def _success_page(state_name: str, board_url: str, firm: str, site: str,
                  until: str, get_help: str) -> tuple[str, str]:
    title = f"Your Get help slot on the {state_name} EPA enforcement board"
    body = (
        f"<h1>{esc(title)}</h1>\n"
        f"<p>Thank you. Your firm now holds the Featured &ldquo;Get help&rdquo; slot on "
        f"the <strong>{esc(state_name)}</strong> EPA enforcement board for twelve "
        f"months, ending <strong>{esc(until)}</strong>.</p>\n"
        '<div class="box">\n'
        "  <p>This is the line that will show in the Get help box on that board, "
        "exactly as written:</p>\n"
        f"  <p>{get_help}</p>\n"
        "</div>\n"
        f'<p>The public board is here: <a href="{esc(board_url)}">{esc(board_url)}</a></p>\n'
        f"<p>Firm on record: <strong>{esc(firm)}</strong>"
        + (f' &middot; <a href="{esc(site)}">{esc(site)}</a>' if site else "")
        + "</p>\n"
    )
    return title, _shell(title, body)


def _taken_page(state_name: str) -> tuple[str, str]:
    title = f"The {state_name} Get help slot is already taken"
    body = (
        f"<h1>{esc(title)}</h1>\n"
        f"<p>We&rsquo;re sorry &mdash; the Featured &ldquo;Get help&rdquo; slot for "
        f"<strong>{esc(state_name)}</strong> was already bought by another firm before "
        "your payment, and we only ever show one firm per state (first paid, first "
        "shown).</p>\n"
        '<div class="box">\n'
        "  <p><strong>Please reply to your Stripe receipt and we will refund you in "
        "full.</strong> Your card was charged; nothing is published for you; the refund "
        "is the whole of what happens next.</p>\n"
        "</div>\n"
        "<p>If you would like a different state, reply to that same receipt and tell us "
        "which one, and we will check whether it is open before charging anything.</p>\n"
    )
    return title, _shell(title, body)


def fulfil(session: dict) -> dict:
    cf = _custom(session)
    code = (cf.get("state") or "").upper()
    firm = cf.get("business_name") or ""
    site = cf.get("website") or ""
    state_name = STATES.get(code, code or "your state")
    today = dt.date.today().isoformat()
    until = _until(session.get("created"))
    board_url = f"{PUBLIC_BASE}/{_slug(state_name)}/" if code in STATES else PUBLIC_BASE

    holder = _holder(code, today) if code in STATES else None
    if holder and (holder.get("business_name") or "") != firm:
        title, page = _taken_page(state_name)
        return {"title": title, "html": page, "state_update": None}

    get_help = (
        f"Get help in {esc(state_name)}: the Featured slot is held by "
        f"<strong>{esc(firm)}</strong>"
        + (f" &mdash; {esc(site)}" if site else "") + "."
    )
    title, page = _success_page(state_name, board_url, firm, site, until, get_help)
    state_update = {"featured": {
        "agency": "epa",
        "state": code,
        "business_name": firm,
        "website": site,
        "until": until,
    }}
    return {"title": title, "html": page, "state_update": state_update}


def _main(argv: list[str]) -> int:
    if "--fixture" not in argv:
        print("usage: python3 fulfil.py --fixture fixtures/session_paid.json",
              file=sys.stderr)
        return 2
    path = Path(argv[argv.index("--fixture") + 1])
    if not path.is_absolute():
        path = Path.cwd() / path
    session = json.loads(path.read_text(encoding="utf-8"))
    out = fulfil(session)
    sys.stdout.write(out["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
