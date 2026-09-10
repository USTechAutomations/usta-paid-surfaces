#!/usr/bin/env python3
"""Build the private page a buyer gets after paying $49.

fulfil(session) returns the whole explained bank as one long private web page:
every question from every sitting, grouped by topic, with CBP's official answer
and our explanation on each. It is deterministic -- the same bank on disk
produces the same page every time -- carries `noindex,nofollow`, and never prints
the buyer's email or any other personal detail from the Stripe session.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the HTML

The full bank is read from the state dir if it is there (that copy is always
complete), otherwise from data/bank.json. Nothing here calls a model or the
network; the explanations were drafted and checked when refresh.py ran.
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

FAMILY = "customs-broker-exam-bank"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BANK_JSON = DATA / "bank.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

STATE = family_state(FAMILY)
FULL_BANK = STATE / "raw" / "bank.full.json"

CBP_PAGE = ("https://www.cbp.gov/document/publications/"
            "past-customs-broker-license-examinations-answer-keys")
DISCLAIMER = (
    "Questions and answer keys are US Customs and Border Protection publications "
    "(public domain). Explanations are ours, machine-drafted and machine-checked, "
    "not CBP's. US Tech Automations is not CBP and does not guarantee exam results. "
    "Not legal, tax or professional advice.")


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def load_bank() -> dict:
    """The complete bank. The state-dir copy is always whole; fall back to data/."""
    for p in (FULL_BANK, BANK_JSON):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"sittings": [], "generated": ""}


def _answer(q: dict) -> str:
    ans = q.get("answer") or ""
    if q.get("answer_status") == "credit":
        return "All examinees granted credit (question withdrawn by CBP)"
    if q.get("answer_status") == "multi":
        return f"{_e(ans)} — two answers accepted"
    opt = q.get("options", {}).get(ans)
    return f"{_e(ans)}) {_e(opt)}" if opt else _e(ans)


def _explanation(q: dict) -> str:
    if q.get("explanation_status") == "ok" and q.get("explanation"):
        cited = q.get("cfr_used")
        src = q.get("cfr_source_url")
        tail = ""
        if cited and src:
            tail = (f'<div class="src">Quotes 19 CFR {_e(cited)} — '
                    f'<a href="{_e(src)}" data-source-url="{_e(src)}">'
                    f"eCFR text used</a></div>")
        return f'<div class="expl">{_e(q["explanation"])}</div>{tail}'
    reason = {
        "no-cfr": "the official key cites the tariff schedule (HTSUS), not the "
                  "CFR, so there is no CFR text for us to quote",
        "no-cfr-text": "the cited rule did not resolve to a passage we could quote "
                       "from the eCFR",
        "flagged": "our checker flagged the first draft against the rule text, so "
                   "it is withheld",
        "no-door": "the local drafting model was down when this bank was built",
        "pending": "not yet drafted",
        "special": "this question has no single correct answer to explain",
        "no-answer": "the key carries no single answer letter",
        "in-paid-bank": "held in the full bank",
    }.get(q.get("explanation_status"), "no explanation")
    return (f'<div class="expl withheld">Explanation withheld: {reason}. '
            f"The official answer above is CBP's own.</div>")


def _question_block(q: dict) -> str:
    opts = "".join(
        f'<li><strong>{_e(k)})</strong> {_e(v)}</li>'
        for k, v in sorted(q.get("options", {}).items()))
    src = q.get("cfr_source_url") or CBP_PAGE
    return (
        f'<article class="q" id="{_e(q["sitting"])}-{q["num"]}" '
        f'data-source-url="{_e(src)}">\n'
        f'  <div class="qhead"><span class="qno">{_e(q["sitting"])} · '
        f'Q{q["num"]}</span> <span class="topic">{_e(q.get("topic",""))}</span></div>\n'
        f'  <p class="stem">{_e(q["stem"])}</p>\n'
        f'  <ul class="opts">{opts}</ul>\n'
        f'  <p class="ans"><span class="lab">CBP official answer:</span> '
        f'{_answer(q)}</p>\n'
        f'  {_explanation(q)}\n'
        f"</article>")


def build_html(bank: dict) -> str:
    sittings = [s for s in bank.get("sittings", []) if s.get("questions")]
    gen = bank.get("generated") or ""
    total = sum(len(s["questions"]) for s in sittings)
    explained = sum(1 for s in sittings for q in s["questions"]
                    if q.get("explanation_status") == "ok")

    # Per-sitting stats.
    stat_rows = "".join(
        f"<tr><td>{_e(s['label'])}</td><td>{len(s['questions'])}</td>"
        f"<td>{sum(1 for q in s['questions'] if q.get('explanation_status')=='ok')}</td></tr>"
        for s in sittings)

    # All questions grouped by topic; within a topic, newest sitting first then
    # question number. Topic order is alphabetical for a stable, deterministic page.
    by_topic: dict[str, list[dict]] = {}
    for s in sittings:
        for q in s["questions"]:
            by_topic.setdefault(q.get("topic") or "Uncategorised", []).append(q)
    for qs in by_topic.values():
        qs.sort(key=lambda q: (q["sitting"], q["num"]), reverse=False)

    topics = sorted(by_topic)
    index = "".join(
        f'<li><a href="#topic-{i}">{_e(t)}</a> '
        f'<span class="c">{len(by_topic[t])}</span></li>'
        for i, t in enumerate(topics))
    body = ""
    for i, t in enumerate(topics):
        blocks = "\n".join(_question_block(q) for q in by_topic[t])
        body += (f'<section class="topic-sec" id="topic-{i}">\n'
                 f"  <h2>{_e(t)}</h2>\n{blocks}\n</section>\n")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Customs Broker Exam Bank — full explained bank</title>
<style>
 body{{font:16px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
   max-width:820px;margin:0 auto;padding:1.5rem;color:#1a1a1a}}
 h1{{font-size:1.6rem;margin:.2rem 0}}
 .honest{{background:#fff8e1;border:1px solid #e6d28a;padding:.7rem 1rem;
   border-radius:8px;font-size:.92rem;margin:1rem 0}}
 table{{border-collapse:collapse;margin:1rem 0;width:100%}}
 th,td{{border:1px solid #ddd;padding:.35rem .6rem;text-align:left}}
 th{{background:#f4f4f4}}
 .index{{columns:2;font-size:.92rem}}
 .index li{{list-style:none}} .index .c{{color:#888}}
 .topic-sec h2{{border-bottom:2px solid #333;padding-bottom:.25rem;margin-top:2rem}}
 .q{{border:1px solid #e4e4e4;border-radius:8px;padding:.8rem 1rem;margin:.9rem 0}}
 .qhead{{font-size:.8rem;color:#666;display:flex;justify-content:space-between}}
 .stem{{font-weight:600;margin:.4rem 0}}
 .opts{{margin:.3rem 0 .6rem 1rem;padding:0}} .opts li{{list-style:none;margin:.15rem 0}}
 .ans{{margin:.3rem 0}} .ans .lab{{color:#2b6a2b;font-weight:600}}
 .expl{{background:#f3f7ff;border-left:3px solid #4a7fd0;padding:.5rem .8rem;
   border-radius:4px;margin:.4rem 0}}
 .expl.withheld{{background:#f6f6f6;border-left-color:#bbb;color:#555;font-size:.92rem}}
 .src{{font-size:.8rem;color:#666;margin:.2rem 0 .5rem}}
 footer{{margin-top:2.5rem;font-size:.85rem;color:#555;border-top:1px solid #ddd;
   padding-top:1rem}}
</style>
</head>
<body>
<h1>Customs Broker Exam Bank — the full explained bank</h1>
<p>The last {len(sittings)} Customs Broker License Exam sittings, every question
with CBP's official answer and, where the key cites a Title 19 CFR rule, our
explanation that quotes it. <strong>{explained} of {total}</strong> questions
explained. Sealed copy stamped {_e(gen)}.</p>

<div class="honest"><strong>{_e(DISCLAIMER)}</strong></div>
<p class="honest" style="background:#eef7ee;border-color:#bcd8bc">This is your
private copy, delivered within 15 minutes of payment. <strong>Refund on request
within 14 days.</strong> Still not here 15 minutes after paying? Reply to your
Stripe receipt. Data from CBP as of {_e(gen)}
(<a href="{CBP_PAGE}" data-source-url="{CBP_PAGE}">source</a>).</p>

<h2>What is in the bank</h2>
<table>
<thead><tr><th>Sitting</th><th>Questions</th><th>We explain</th></tr></thead>
<tbody>{stat_rows}</tbody>
</table>

<h2>Topics</h2>
<ul class="index">{index}</ul>

{body}
<footer>{_e(DISCLAIMER)} Source: <a href="{CBP_PAGE}"
data-source-url="{CBP_PAGE}">CBP past exams &amp; answer keys</a>.</footer>
</body>
</html>
"""


def fulfil(session: dict) -> dict:
    """The contract entry point. session is a Stripe Checkout Session object.

    We read nothing personal out of it -- there are no custom fields on this
    product and the buyer's email never touches the page. state_update is None:
    delivering the bank changes no server state.
    """
    bank = load_bank()
    html_page = build_html(bank)
    return {
        "title": "Customs Broker Exam Bank — full explained bank",
        "html": html_page,
        "state_update": None,
    }


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "metadata": {}}
    out = fulfil(session)
    sys.stdout.write(out["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
