#!/usr/bin/env python3
"""The one place that turns data/rules.json into what the pages show.

Both the free pages (scripts/slice_contractor_audit_file.py) and the paid page
(fulfil.py) read from here, so a prong shown free and the same prong shown in
the paid file carry the same words and the same citation. There is one copy of
the data, not two.

Nothing in this file writes a legal conclusion, and nothing in it invents text.
Every quote it hands out came back in official bytes and is stored word for word
in data/citations.json.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

FAMILY = "contractor-audit-file"
PRICE = "$49"

DISCLAIMER = (
    "Not affiliated with any state labor agency, the US Department of Labor or the "
    "IRS. Not legal, tax or professional advice. This is an evidence file, not an "
    "opinion: it lays out the official test and your own answers side by side and "
    "never says what the worker is. Statute and agency text quoted from the "
    "official pages listed on each page."
)

NO_VERDICT = (
    "This file does not decide anything. Only a court or an agency can classify a "
    "worker, and only on the whole record. What you get here is the official test "
    "in the statute's own words, your answers written next to the prong each one "
    "touches, and the documents an auditor would ask to see."
)


def _read(name: str) -> dict:
    path = DATA / name
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_RULES: dict | None = None
_QUESTIONS: dict | None = None


def rules() -> dict:
    global _RULES
    if _RULES is None:
        _RULES = _read("rules.json") or {"generated": "", "jurisdictions": [],
                                         "federal": []}
    return _RULES


def questions() -> dict:
    global _QUESTIONS
    if _QUESTIONS is None:
        _QUESTIONS = _read("questions.json") or {"questions": [], "prong_families": {}}
    return _QUESTIONS


def status() -> dict:
    return _read("status.json") or {}


def generated() -> str:
    return rules().get("generated") or "2026-09-08"


def quoted_states() -> list[dict]:
    return [j for j in rules().get("jurisdictions", []) if j.get("status") == "quoted"]


def all_states() -> list[dict]:
    return list(rules().get("jurisdictions", []))


def federal() -> list[dict]:
    return [f for f in rules().get("federal", []) if f.get("status") == "quoted"]


def federal_all() -> list[dict]:
    return list(rules().get("federal", []))


def by_code(code: str) -> dict | None:
    for j in all_states() + federal_all():
        if j["code"] == code:
            return j
    return None


SLUGS = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "DC": "district-of-columbia", "FL": "florida", "GA": "georgia", "HI": "hawaii",
    "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
    "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island",
    "SC": "south-carolina", "SD": "south-dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming",
    "US-DOL": "federal-dol-economic-reality",
    "US-IRS": "federal-irs-common-law",
}

STATUS_WORDS = {
    "quoted": "quoted from the official page",
    "unreachable": "the state's site did not answer this host",
    "wrong-page": "the address answered, but the bytes did not carry that section",
    "no-passage": "the page answered but carried none of the test's words",
    "not-cached": "not fetched on this run",
}


def slug_of(code: str) -> str:
    """The seed file carries a slug; SLUGS is the fallback for a row without one."""
    j = by_code(code)
    if j and j.get("slug"):
        return j["slug"]
    return SLUGS.get(code, code.lower())


def tool_payload() -> dict:
    """Exactly what the in-page tool needs, and nothing about any person.

    The payload is inlined into the page as JSON. It carries the questions, the
    quoted prongs per jurisdiction with their citations, and the penalty
    passages. It carries no scoring table and no conclusion, because there is
    none to carry.
    """
    q = questions()
    places = []
    for j in quoted_states() + federal():
        places.append({
            "code": j["code"],
            "name": j["name"],
            "cite": j["cite"],
            "url": j["source_url"],
            "slug": slug_of(j["code"]),
            "prongs": [{"id": p["id"], "label": p["label"], "asks": p["asks"],
                        "cite": p["cite"], "url": p["cite_url"], "quote": p["quote"],
                        "documents": p.get("documents", [])}
                       for p in j["prongs"]],
            "penalties": [{"cite": p["cite"], "url": p["cite_url"],
                           "quote": p["quote"]} for p in j["penalties"]],
        })
    return {
        "family": FAMILY,
        "generated": generated(),
        "storage_key": "fv6.contractor-audit-file.answers",
        "no_verdict": NO_VERDICT,
        "families": q.get("prong_families", {}),
        "questions": q.get("questions", []),
        "places": places,
    }
