#!/usr/bin/env python3
"""Build the private page a buyer gets after paying $49 for one product.

It is the same calculator that sits on the free family page, with the DRAFT
stamp off, the three vector downloads on, and the product name from the Stripe
custom field printed on it. Nothing is pre-computed: the buyer's recipe never
reaches us, so the page carries the whole tool and picks the recipe up out of
the browser's own storage under the key the free page wrote.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the fragment

The returned html is a body fragment; fv5/lib/ppp.py wraps it with the
noindex header. It is deterministic, it never prints the buyer's email, and it
touches neither the network nor a model.
"""
from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

FAMILY = "nutrition-label-forge"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

LINK_ID_ENV_OR_CATALOG = FAMILY
PRODUCT_NAME = "Nutrition Facts panel builder"
ETA_MINUTES = 15

ECFR_9 = "https://www.ecfr.gov/current/title-21/section-101.9"
FDC = "https://fdc.nal.usda.gov/download-datasets"

DISCLAIMER = (
    "Not affiliated with the Food and Drug Administration or the US Department of "
    "Agriculture. Not legal, tax or professional advice. Regulation text from the "
    "eCFR, which is not the official legal edition of the CFR. Nutrient values from "
    "USDA FoodData Central, a public database of generic foods and not a laboratory "
    "analysis of your product.")

MAX_NAME = 60


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _panel():
    spec = importlib.util.spec_from_file_location("nlf_panel", HERE / "panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status() -> dict:
    p = DATA / "status.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def drifted() -> list[dict]:
    p = DATA / "citations.json"
    if not p.is_file():
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("citations", [])
    return [r for r in rows if r.get("status") == "drifted"]


def product_name(session: dict) -> str:
    """The one thing we take out of the Stripe session. Never the email."""
    for f in session.get("custom_fields") or []:
        if f.get("key") == "product_name":
            v = (f.get("text") or {}).get("value") or ""
            v = " ".join(str(v).split())[:MAX_NAME]
            if v:
                return v
    return "your product"


def drift_banner(st: dict, rows: list[dict]) -> str:
    if not st.get("drift") and not rows:
        return ""
    names = ", ".join(sorted({r.get("key", "a cited rule") for r in rows})) or "a cited rule"
    return (
        '      <div class="honest drift"><strong>A cited rule has moved since this '
        f'pack was built.</strong> On {_e(st.get("date", "the build date"))} we '
        f're-read the regulation and {len(rows)} quoted passage(s) no longer match '
        f'word for word: {_e(names)}. Everything on this page reflects the eCFR '
        f'edition of {_e(st.get("ecfr_edition", "the stamp below"))}. Read the '
        f'current text at <a href="{ECFR_9}" data-source-url="{ECFR_9}">the eCFR'
        "</a> before you print.</div>\n")


def build_html(session: dict) -> tuple[str, str]:
    name = product_name(session)
    st = status()
    stamp = st.get("date", "")
    edition = st.get("ecfr_edition", "")
    tool = _panel().tool_html(paid=True, product_name=name)

    frag = f"""<style>
 .nlf-paid-head{{margin:0 0 1rem}}
 .nlf-paid-head h1{{font-size:1.6rem;margin:.2rem 0}}
 .honest{{background:#fff8e1;border:1px solid #e6d28a;padding:.7rem 1rem;
   border-radius:8px;font-size:.92rem;margin:1rem 0}}
 .honest.drift{{background:#fdecea;border-color:#e0a09a}}
 .honest.ok{{background:#eef7ee;border-color:#bcd8bc}}
 .nlf-paid-foot{{margin-top:2.5rem;font-size:.85rem;color:#555;
   border-top:1px solid #ddd;padding-top:1rem}}
 @media print{{.honest,.nlf-paid-foot,.nlf-paid-head p{{display:none}}}}
</style>
<div class="nlf-paid-head">
  <h1>Nutrition Facts panel — {_e(name)}</h1>
  <p>Your private copy, for this one product. The DRAFT stamp is off and the
  three panel files are downloadable as true vector SVG. If you built the recipe
  on the free page in this browser, it has been picked up below and the free
  page's copy has been cleared.</p>
</div>
{drift_banner(st, drifted())}      <div class="honest ok">Delivered within
{ETA_MINUTES} minutes of payment. <strong>Refund on request within 14 days.</strong>
Still not here 15 minutes after paying? Reply to your Stripe receipt. Regulation
text is the eCFR edition of {_e(edition)}; food data is USDA FoodData Central as
read on {_e(stamp)} (<a href="{FDC}" data-source-url="{FDC}">source</a>).</div>
      <div class="honest"><strong>Before you send this to a printer.</strong> The
files carry point sizes taken from 21 CFR 101.9(d), but a printer can rescale
artwork without telling you. Measure the type on the printed proof. The percent
Daily Values are worked out from the rounded figures the panel prints, as
101.9(c) directs, and the added sugars figure is the one you typed. The
ingredient statement and the allergen line are your words, unedited by us.</div>
{tool}
      <div class="nlf-paid-foot">{_e(DISCLAIMER)} Rules quoted from
<a href="{ECFR_9}" data-source-url="{ECFR_9}">21 CFR 101.9</a>, edition of
{_e(edition)}. Nothing here states whether your label or your business meets any
requirement.</div>
"""
    return name, frag


def fulfil(session: dict) -> dict:
    """The contract entry point. `session` is a Stripe Checkout Session object.

    The only field read is the `product_name` custom field. The buyer's email is
    never touched. state_update is None: delivering the pack changes no server
    state.
    """
    name, frag = build_html(session)
    return {
        "title": f"Nutrition Facts panel — {name}",
        "html": frag,
        "state_update": None,
    }


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        if not fx.is_absolute() and not fx.exists():
            fx = HERE / fx
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "custom_fields": [], "metadata": {}}
    sys.stdout.write(fulfil(session)["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
