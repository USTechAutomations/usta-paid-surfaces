#!/usr/bin/env python3
"""Write fixtures/sample_daily.xml: a synthetic stand-in for the USPTO daily file.

The real product reads the USPTO "Trademark Applications Daily XML" (TRTDXFAP)
bulk file. That file needs no login, but the no-login bulk host was not
reachable from this build (bulkdata.uspto.gov did not resolve, and the ODP API
returned a single-page-app shell rather than a dataset). SOURCES.md records that
as a fact. So refresh.py falls back to this file, which is shaped like the real
one and is clearly, deliberately fake:

  * every serial number begins 99 and none is a real registration,
  * every owner is an invented company or an invented person,
  * every mark text is two made-up words.

Regenerate with:  python3 fv5/families/trademark-watch/tools/make_fixture.py

It is deterministic: same output every run, so the committed file and the code
that writes it never drift. No network, no randomness.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "fixtures" / "sample_daily.xml"

AS_OF = dt.date(2026, 9, 5)          # the "daily file" date
N = 250                              # total case-files to synthesise

ROOTS = [
    "NORTH", "BLUE", "APEX", "SUMMIT", "RIVER", "IRON", "CEDAR", "ORION",
    "VERTEX", "LUMEN", "HARBOR", "PRAIRIE", "FALCON", "QUARTZ", "NOVA",
    "EMBER", "ATLAS", "MERIDIAN", "COBALT", "GRANITE", "WILLOW", "PIONEER",
    "ZENITH", "CASCADE", "SABLE", "TERRA", "HELIOS", "VANTAGE", "BRAVO",
    "KESTREL",
]
SUFFIXES = [
    "WORKS", "LABS", "HARVEST", "FORGE", "MARKET", "GRID", "PULSE", "CRAFT",
    "FIELDS", "LOOM", "TRAIL", "BEACON", "CIRCUIT", "ORCHARD", "DEPOT",
    "FOUNDRY", "PANTRY", "SIGNAL", "HOLLOW", "BLOOM", "RIDGE", "ANCHOR",
    "MOTION", "SPARK", "CANOPY", "DELTA", "PRESS", "LEDGER",
]
COMPANY_TAILS = [
    ("HOLDINGS LLC", "16", "LIMITED LIABILITY COMPANY"),
    ("TECHNOLOGIES INC", "03", "CORPORATION"),
    ("BRANDS CORP", "03", "CORPORATION"),
    ("LABS LLC", "16", "LIMITED LIABILITY COMPANY"),
    ("GROUP LLC", "16", "LIMITED LIABILITY COMPANY"),
    ("INDUSTRIES INC", "03", "CORPORATION"),
    ("PARTNERS LP", "20", "LIMITED PARTNERSHIP"),
    ("SYSTEMS INC", "03", "CORPORATION"),
    ("VENTURES LLC", "16", "LIMITED LIABILITY COMPANY"),
    ("FOODS CO", "03", "CORPORATION"),
    ("OUTDOORS LLC", "16", "LIMITED LIABILITY COMPANY"),
    ("BEVERAGE CO", "03", "CORPORATION"),
]
FIRSTS = ["JAMES", "MARIA", "DAVID", "LINDA", "ROBERT", "PATRICIA", "JOHN",
          "JENNIFER", "MICHAEL", "ELIZABETH"]
LASTS = ["SMITH", "GARCIA", "JOHNSON", "MARTINEZ", "BROWN", "DAVIS", "MILLER",
         "WILSON", "MOORE", "TAYLOR"]

CLASSES = [
    ("009", "Downloadable and recorded computer software"),
    ("025", "Clothing, footwear and headwear"),
    ("035", "Advertising and business management services"),
    ("041", "Education and entertainment services"),
    ("030", "Coffee, tea, baked goods and confectionery"),
    ("032", "Beers and non-alcoholic beverages"),
    ("005", "Pharmaceutical and sanitary preparations"),
    ("042", "Scientific and technology services"),
    ("021", "Household and kitchen utensils"),
    ("028", "Games, toys and sporting goods"),
]

# (event code, event description, status code) -- the illustrative subset this
# product cares about. The first three are the ones a watch is bought for.
QUALIFYING = [
    ("PUBO", "PUBLISHED FOR OPPOSITION", "681"),
    ("CNSA", "NON-FINAL ACTION E-MAILED", "641"),
    ("GNRN", "FINAL REFUSAL E-MAILED", "654"),
]
NONQUAL = [
    ("NOAM", "NOTICE OF ALLOWANCE E-MAILED", "686"),
    ("R.PR", "REGISTERED-PRINCIPAL REGISTER", "700"),
]


def _fmt(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _case(i: int) -> str:
    serial = 99000001 + i
    cluster = i // 6
    root = ROOTS[(i * 7) % len(ROOTS)]
    suffix = SUFFIXES[(i * 5) % len(SUFFIXES)]
    mark = f"{root} {suffix}"
    intl, gs = CLASSES[cluster % len(CLASSES)]

    # Owner: every 6th application is an individual (withheld downstream); the
    # rest are invented companies.
    individual = (i % 6 == 5)
    if individual:
        owner = f"{FIRSTS[i % len(FIRSTS)]} {LASTS[(i * 3) % len(LASTS)]}"
        entity_code, entity_stmt = "01", "INDIVIDUAL"
    else:
        tail, entity_code, entity_stmt = COMPANY_TAILS[i % len(COMPANY_TAILS)]
        owner = f"{root} {tail}"

    # Event: most company applications carry a watch-worthy event; a slice do
    # not, so the "only pages we can sell a watch on" filter has something to
    # drop.
    non_qualifying = (not individual and i % 11 == 0)
    if individual:
        pool = QUALIFYING if i % 2 == 0 else NONQUAL
        ev_code, ev_desc, status = pool[i % len(pool)]
    elif non_qualifying:
        ev_code, ev_desc, status = NONQUAL[i % len(NONQUAL)]
    else:
        ev_code, ev_desc, status = QUALIFYING[i % len(QUALIFYING)]

    # Dates. Recent clusters were filed inside the last 90 days so the
    # "similar marks filed recently" table has rows; older clusters were not.
    if cluster % 2 == 0:
        filed = AS_OF - dt.timedelta(days=30 + (cluster * 4) % 55)
    else:
        filed = AS_OF - dt.timedelta(days=220 + (cluster * 13) % 520)
    event_date = AS_OF - dt.timedelta(days=(i % 12))
    if event_date < filed:
        event_date = filed

    return f"""      <case-file>
        <serial-number>{serial}</serial-number>
        <transaction-date>{_fmt(AS_OF)}</transaction-date>
        <case-file-header>
          <filing-date>{_fmt(filed)}</filing-date>
          <status-code>{status}</status-code>
          <status-date>{_fmt(event_date)}</status-date>
          <mark-identification>{escape(mark)}</mark-identification>
        </case-file-header>
        <classifications>
          <classification>
            <international-code>{intl}</international-code>
            <primary-code>{intl}</primary-code>
            <gs-text>{escape(gs)}</gs-text>
          </classification>
        </classifications>
        <case-file-owners>
          <case-file-owner>
            <entry-number>1</entry-number>
            <party-name>{escape(owner)}</party-name>
            <legal-entity-type-code>{entity_code}</legal-entity-type-code>
            <entity-statement>{escape(entity_stmt)}</entity-statement>
          </case-file-owner>
        </case-file-owners>
        <case-file-event-statements>
          <case-file-event-statement>
            <code>{ev_code}</code>
            <type>O</type>
            <description-text>{escape(ev_desc)}</description-text>
            <date>{_fmt(event_date)}</date>
          </case-file-event-statement>
        </case-file-event-statements>
      </case-file>"""


def build() -> str:
    cases = "\n".join(_case(i) for i in range(N))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- SYNTHETIC FIXTURE — NOT USPTO DATA. Generated by tools/make_fixture.py.
     Shaped like the public USPTO "Trademark Applications Daily XML" (TRTDXFAP).
     Every serial begins 99 and is fake; every owner and mark is invented.
     Used only when the no-login USPTO bulk file cannot be reached. -->
<trademark-applications-daily>
  <version>
    <version-no>1.0</version-no>
    <version-date>{_fmt(AS_OF)}</version-date>
  </version>
  <application-information>
    <file-segments>
      <action-keys>
{cases}
      </action-keys>
    </file-segments>
  </application-information>
</trademark-applications-daily>
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({N} case-files, {OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
