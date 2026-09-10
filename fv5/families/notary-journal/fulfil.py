#!/usr/bin/env python3
"""Build the private page a buyer gets after paying $49.

The page is the same journal tool the public page carries, with the entry limit
off and the state they chose already selected. That is deliberate: the buyer has
already put entries into this browser through the free tool, the store is the
same store, and their entries are simply there when the unlocked page opens.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the HTML

Deterministic, no network, no model. The buyer's email is never read and never
printed; the only thing taken out of the Stripe session is the state they picked
from the dropdown, and a commission number they chose to type.
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import app_html  # noqa: E402
import states_build as sb  # noqa: E402

FAMILY = "notary-journal"
DATA = HERE / "data"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

STATE = family_state(FAMILY)
PRODUCT_NAME = "Notary journal — unlocked copy"
LINK_ID_ENV_OR_CATALOG = "notary-journal"
ETA_MINUTES = 15


def _e(s) -> str:
    return html.escape(str(s or ""))


def chosen_state(session: dict) -> str:
    """The state code off the Stripe custom field, or empty if none was sent."""
    for f in session.get("custom_fields") or []:
        if f.get("key") == "state":
            d = f.get("dropdown") or {}
            t = f.get("text") or {}
            return str(d.get("value") or t.get("value") or "").strip()
    return ""


def commission(session: dict) -> str:
    for f in session.get("custom_fields") or []:
        if f.get("key") == "commission":
            return str((f.get("text") or {}).get("value") or "").strip()
    return ""


def status() -> dict:
    p = DATA / "status.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"stamp": "", "drift": False, "drifted": []}


def drift_banner(st: dict, states: list[dict]) -> str:
    """Say which cited rule moved, so the buyer knows what to re-read.

    A pack that quietly went stale is worse than one that says it did. If a
    state's own words changed since this copy was built, the copy still shows
    the words it was built from and names them as the ones that moved.
    """
    if not st.get("drift"):
        return ""
    names = {s["code"]: s["name"] for s in states}
    moved = ", ".join(_e(names.get(c, c)) for c in st.get("drifted", []))
    return (
        '<p class="nj-stop"><strong>A cited rule changed.</strong> '
        f"The words on the state's own page moved for: {moved}. "
        f"This copy shows the text as it stood on {_e(st.get('stamp', '')[:10])}. "
        "Read the state's page, linked next to the rule, before you rely on it.</p>")


def build_html(session: dict) -> str:
    blob = sb.load_states()
    states = blob.get("states", [])
    st = status()
    code = chosen_state(session)
    pick = next((s for s in states if s["code"] == code), None)
    comm = commission(session)

    head = [
        "<h2>Your notary journal</h2>",
        drift_banner(st, states),
        ('<p><strong>This page is your copy. It does not expire.</strong> '
         'Save the address, or save the page itself to your own machine. There '
         'is no renewal, no account and nothing to cancel.</p>'),
    ]
    if pick:
        head.append(
            f"<p>The form below follows the text we read on "
            f'<a href="{_e(pick["cite_url"])}" rel="nofollow">{_e(pick["cite_label"])}</a> '
            f'for {_e(pick["name"])}, read {_e(pick["checked"])}. '
            f"You can switch states at any time; every state we could read is "
            f"in the list.</p>")
        if pick.get("quote"):
            head.append(f'<blockquote>“{_e(pick["quote"])}”</blockquote>')
    if comm:
        head.append(f"<p>Commission number you gave us: {_e(comm)}.</p>")
    head.append(
        "<p>Entries you already made in the free tool are in this browser "
        "already, and they open here with the same passphrase. Nothing was "
        "copied or moved to do that, and nothing was sent to us.</p>")
    head.append(
        "<p>Not affiliated with any secretary of state or notary regulator. "
        "Not legal, tax or professional advice. Data from each state's own "
        f"legislature or notary office as of {_e(st.get('stamp', '')[:10] or blob.get('generated', ''))}.</p>")

    frag = app_html.app_fragment(states, blob.get("generated", ""),
                                 unlocked=True, preselect=code or "PA")
    return "\n".join(x for x in head if x) + "\n" + frag


def fulfil(session: dict) -> dict:
    """The contract entry point. session is a Stripe Checkout Session object."""
    return {
        "title": PRODUCT_NAME,
        "html": build_html(session),
        "state_update": None,
    }


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "custom_fields": []}
    sys.stdout.write(fulfil(session)["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
