#!/usr/bin/env python3
"""Turn fetched official pages into the rule rows the pages are built from.

Nothing here writes a legal conclusion. For each jurisdiction it does three
things and stops:

  1. fetch the official address in data/sources_seed.json;
  2. check the bytes really carry the section we asked for;
  3. lift out, word for word, the passages that talk about control, about the
     hiring firm's usual business, and about the worker's own trade -- plus any
     passage that names a penalty.

A jurisdiction whose page did not answer, or answered without any of those
words, is recorded with a status saying exactly that. It gets no page. We would
rather publish twenty states we can quote than fifty we cannot.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import fetchlib as F

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SEEDS = DATA / "sources_seed.json"

# Three families of words, because the three questions every one of these tests
# asks are the same three: who controls the work, whose business is it part of,
# and does the worker have a business of their own. The words differ by state;
# the question does not.
PRONG_SETS = {}

# Three families of words, because the three questions these state tests ask are
# the same three: who controls the work, whose business is it part of, and does
# the worker have a business of their own. The words differ by state; the
# question does not. The anchors are deliberately narrow -- a loose one lifted a
# sentence about leased-employee brokers out of the Kansas code and would have
# published it as a prong of the worker test.
PRONG_SETS["state"] = [
    {
        "id": "control",
        "label": "Control over how the work is done",
        "asks": ("whether the worker is free from the hiring firm's control and "
                 "direction over how the work is performed"),
        "anchors": ["free from the control and direction", "free from control",
                    "free from the control", "free from any control",
                    "free from direction", "free from the essential direction",
                    "not subject to control", "not subject to that person's control"],
        "must_also": ["control", "direction"],
        "documents": [
            "The written agreement, and any schedule or statement of work attached to it",
            "Messages that set hours, order of work or method (email, chat, job app)",
            "Any training material, handbook or induction the worker was given",
            "Timesheets, rotas or shift rosters the hiring firm produced",
        ],
    },
    {
        "id": "business",
        "label": "Whether the work sits outside the hiring firm's usual business",
        "asks": ("whether the work performed is outside the usual course of the "
                 "hiring firm's business, or outside all its places of business"),
        "anchors": ["outside the usual course", "outside of the usual course",
                    "outside all the places", "outside of all the places",
                    "outside all of the places", "usual course of the business",
                    "usual course of business"],
        "must_also": ["usual course", "places of business", "all the places"],
        "documents": [
            "The hiring firm's own description of what it sells (website, catalogue, filings)",
            "The job or brief the worker was engaged for, in writing",
            "Any list of the firm's own staff doing the same kind of work",
            "The address where the work was carried out",
        ],
    },
    {
        "id": "independent",
        "label": "Whether the worker has an independent business of their own",
        "asks": ("whether the worker is customarily engaged in an independently "
                 "established trade, occupation or business of the same kind"),
        "anchors": ["customarily engaged in an independently established",
                    "independently established trade",
                    "engaged in an independently established",
                    "customarily engaged in an independent"],
        "must_also": ["independently established", "independently"],
        "documents": [
            "The worker's own business registration, licence or trading name",
            "Invoices the worker raised, and invoices they raised to other firms",
            "The worker's own advertising: website, listing, van livery, cards",
            "Proof of the worker's own tools, equipment, premises or insurance",
        ],
    },
]

# The federal wage-law factors, in the words of 29 CFR part 795 itself.
PRONG_SETS["dol"] = [
    {"id": "profit-loss", "label": "Opportunity for profit or loss depending on managerial skill",
     "asks": "whether the worker can make more or less money by the way they run the work",
     "anchors": ["opportunity for profit or loss depending on managerial skill"],
     "must_also": None, "min_len": 40,
     "documents": ["Quotes and bids the worker gave", "Any job the worker turned down",
                   "Evidence the worker set or negotiated their own rate",
                   "Records of the worker's own costs on the job"]},
    {"id": "investment", "label": "Investments by the worker and the potential employer",
     "asks": "whether the worker put their own money into equipment or capacity",
     "anchors": ["investments by the worker and the potential employer"],
     "must_also": None, "min_len": 40,
     "documents": ["Receipts for the worker's own tools, vehicle or software",
                   "The hiring firm's own equipment list for the same work",
                   "Lease or finance agreements in the worker's own name",
                   "Insurance the worker bought for the work"]},
    {"id": "permanence", "label": "Degree of permanence of the work relationship",
     "asks": "whether the arrangement is open-ended or for a definite piece of work",
     "anchors": ["degree of permanence of the work relationship"],
     "must_also": None, "min_len": 40,
     "documents": ["Start and end dates in the written agreement",
                   "Every renewal or extension, in writing",
                   "The full payment history and its dates",
                   "Records of the worker's engagements with other firms in the same period"]},
    {"id": "control-fed", "label": "Nature and degree of control",
     "asks": "who sets the schedule, supervises the work and sets the terms",
     "anchors": ["nature and degree of control"],
     "must_also": None, "min_len": 20,
     "documents": ["Rotas, schedules or shift assignments",
                   "Supervision notes, reviews or quality checks",
                   "Rules the worker had to follow beyond the law",
                   "Any exclusivity or non-compete clause"]},
    {"id": "integral", "label": "Extent to which the work is an integral part of the business",
     "asks": "whether the work is part of what the hiring firm exists to do",
     "anchors": ["integral part of the potential employer's business",
                 "is an integral part of"],
     "must_also": None, "min_len": 40,
     "documents": ["The hiring firm's own description of its business",
                   "Revenue split by the service the worker performed",
                   "Whether the firm's own staff do the same work",
                   "What the firm sells to its own customers"]},
    {"id": "skill", "label": "Skill and initiative",
     "asks": "whether the worker brings specialised skill they use in their own business",
     "anchors": ["skill and initiative"],
     "must_also": None, "min_len": 20,
     "documents": ["The worker's qualifications, tickets or certificates",
                   "Training the worker paid for themselves",
                   "The worker's own marketing of that skill",
                   "Evidence the firm trained the worker instead"]},
]

# The three headings the IRS itself puts on its common-law factors.
PRONG_SETS["irs"] = [
    {"id": "behavioral", "label": "Behavioral control",
     "asks": "whether the firm has the right to direct and control how the work is done",
     "anchors": ["behavioral : does the company control", "behavioral"],
     "must_also": None, "min_len": 40,
     "documents": ["Instructions given about when, where and how to work",
                   "Training the firm provided", "Evaluation systems the firm applied",
                   "Any required tools, systems or procedures"]},
    {"id": "financial", "label": "Financial control",
     "asks": "whether the firm controls the money side of the job",
     "anchors": ["financial : are the business aspects", "financial"],
     "must_also": None, "min_len": 40,
     "documents": ["How and when the worker was paid, and on what document",
                   "Unreimbursed expenses the worker carried",
                   "The worker's own investment in equipment",
                   "Whether the worker offers the service to the wider market"]},
    {"id": "relationship", "label": "Type of relationship",
     "asks": "what the two sides agreed and how permanent it looks",
     "anchors": ["type of relationship : are there written contracts",
                 "type of relationship"], "must_also": None, "min_len": 40,
     "documents": ["The written contract itself",
                   "Any benefits given (insurance, pension, paid leave)",
                   "How long the arrangement has run",
                   "Whether the work is a key part of the firm's regular business"]},
]

# Ordered: the sentence that names an amount beats the sentence that only says
# the word "penalty". passage() takes the first anchor that hits, so the order
# here is what decides which sentence a buyer reads.
PENALTY_ANCHORS = ["not less than five thousand", "fine of not less than",
                   "penalty of not less than", "treble damages", "shall be fined",
                   "civil penalty", "liable for a penalty", "penalties"]

CAP = 300


def _shape(found: list[str]) -> str:
    """What the fetched text looks like -- read off the text, never assumed."""
    n = len(found)
    if n >= 3:
        return ("The section we fetched carries wording for all three questions: "
                "control, the firm's usual business, and the worker's own trade.")
    if n == 2:
        return ("The section we fetched carries wording for two of the three "
                "questions. The third is not in the passage we quote.")
    if n == 1:
        return ("The section we fetched carries wording for one of the three "
                "questions. The rest is not in the passage we quote.")
    return "No passage in the page we fetched carried any of the words we look for."


def build_one(row: dict, *, today: str, offline: bool) -> dict:
    url = row["url"].replace("{date}", "2026-01-01")
    if offline:
        st, body, note = F.fetch(url, use_cache=True)
        if note != "cache":
            return {**_blank(row, url), "status": "not-cached",
                    "why": "run refresh.py without --dry-run once to fetch it"}
    else:
        st, body, note = F.fetch(url, use_cache=True)
    if st != 200 or not body:
        return {**_blank(row, url), "status": "unreachable",
                "why": f"the address answered {st} from this host"}
    text = F.to_text(body)
    if row.get("must") and not F.carries(text, row["must"]):
        return {**_blank(row, url), "status": "wrong-page",
                "why": ("the page came back without the section number we asked "
                        "for, so we do not treat it as that section")}
    prongs = []
    for p in PRONG_SETS[row.get("prong_set", "state")]:
        q = F.passage(text, p["anchors"], cap=CAP, must_also=p.get("must_also"),
                      min_len=p.get("min_len", 60))
        if not q or len(q) < p.get("min_len", 60):
            continue
        prongs.append({
            "id": p["id"], "label": p["label"], "asks": p["asks"],
            "quote": q, "cite_url": url, "cite": row["cite"],
            "documents": p["documents"],
        })
    penalties = []
    pen = F.passage(text, PENALTY_ANCHORS, cap=CAP)
    if pen and len(pen) >= 60:
        penalties.append({"quote": pen, "cite_url": url, "cite": row["cite"],
                          "name": row.get("name", "")})
    out = _blank(row, url)
    out.update({
        "prongs": prongs, "penalties": penalties,
        "fetched": today,
        "status": "quoted" if prongs else "no-passage",
        "why": "" if prongs else ("the page answered, but none of the words these "
                                  "tests are written with are in it"),
        "shape": _shape([p["id"] for p in prongs]),
        "chars": len(text),
    })
    return out


def _blank(row: dict, url: str) -> dict:
    return {
        "code": row["code"], "name": row["name"],
        "slug": re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-"),
        "source_url": url, "cite": row["cite"],
        "prongs": [], "penalties": [], "fetched": "", "shape": "", "chars": 0,
    }


def build(*, limit: int = 0, offline: bool = False) -> dict:
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    states, federal = [], []
    rows = seeds["states"]
    if limit:
        rows = rows[:limit]
    for r in rows:
        states.append(build_one(r, today=today, offline=offline))
    fed_rows = seeds["federal"]
    if limit:
        fed_rows = fed_rows[:max(1, limit // 4)]
    for r in fed_rows:
        federal.append(build_one(r, today=today, offline=offline))

    # Penalty pages are fetched on their own and hung on the state they belong
    # to. A penalty is a separate section of law from the test, and quoting one
    # off the other page would put words in the wrong statute's mouth.
    by_code = {j["code"]: j for j in states}
    pen_rows = seeds.get("penalties", [])
    if limit:
        pen_rows = [r for r in pen_rows if r["for"] in by_code]
    for r in pen_rows:
        got = build_one({**r, "prong_set": "state"}, today=today, offline=offline)
        host = by_code.get(r["for"])
        if host is None:
            continue
        for q in got["penalties"]:
            host["penalties"].append(q)

    # A penalty sentence is only worth quoting if it names what it costs. South
    # Carolina's page answered with a sentence about settling a penalty and
    # never said an amount; New Jersey's answered with a sentence about back
    # pay. Both read like facts and neither is one. A chapter number is not an
    # amount either, so the test looks for money words, not for any digit.
    money = ("$", "dollar", "treble", "fined", "percent", "per cent")
    for j in states + federal:
        keep, seen = [], set()
        for p in j["penalties"]:
            low = p["quote"].lower()
            if not any(w in low for w in money) or p["quote"] in seen:
                continue
            seen.add(p["quote"])
            keep.append(p)
        j["penalties"] = keep

    return {
        "generated": today,
        "jurisdictions": sorted(states, key=lambda x: x["name"]),
        "federal": federal,
    }


def citations_of(rules: dict) -> list[dict]:
    """One row per quoted passage: url, exact quote, when we read it, status."""
    out = []
    for j in rules["jurisdictions"] + rules["federal"]:
        for p in j["prongs"]:
            out.append({"key": f"{j['code']}:{p['id']}", "jurisdiction": j["name"],
                        "cite": p["cite"], "url": p["cite_url"], "quote": p["quote"],
                        "fetched": j["fetched"], "status": "fetched"})
        for i, p in enumerate(j["penalties"]):
            out.append({"key": f"{j['code']}:penalty{i}", "jurisdiction": j["name"],
                        "cite": p["cite"], "url": p["cite_url"], "quote": p["quote"],
                        "fetched": j["fetched"], "status": "fetched"})
    return out
