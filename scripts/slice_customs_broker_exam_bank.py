#!/usr/bin/env python3
"""Build the public pages for the Customs Broker Exam Bank family.

The family page plus one free page per exam sitting. Each sitting page shows a
handful of that sitting's questions with CBP's official answer and our
machine-drafted, machine-checked explanation, and states honestly how many of
the sitting's questions we explain. The whole explained bank is the paid page,
rendered by fv5/families/customs-broker-exam-bank/fulfil.py, not here.

Everything on these pages is read out of data/bank.json, which
fv5/families/customs-broker-exam-bank/refresh.py writes from the sealed CBP
PDFs. This module never parses a PDF and never calls a model; if the bank is not
on disk yet it builds nothing and says so.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

FAMILY = "customs-broker-exam-bank"
ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "fv5" / "families" / FAMILY / "data" / "bank.json"
CBP_PAGE = ("https://www.cbp.gov/document/publications/"
            "past-customs-broker-license-examinations-answer-keys")

MAX_DESC = 155
SHOW_PER_SITTING = 10       # sample questions on each free sitting page
SAMPLE_ROWS = 25            # the public sample file (build_slices caps at 25 too)

DISCLAIMER = (
    "Questions and answer keys are US Customs and Border Protection publications "
    "(public domain). Explanations are ours, machine-drafted and machine-checked, "
    "not CBP's. US Tech Automations is not CBP and does not guarantee exam results. "
    "Not legal, tax or professional advice."
)


def _e(s) -> str:
    return html.escape(str(s or ""))


_BANK: dict | None = None


def bank() -> dict:
    global _BANK
    if _BANK is None:
        if not BANK.is_file():
            _BANK = {"sittings": [], "generated": ""}
        else:
            _BANK = json.loads(BANK.read_text(encoding="utf-8"))
    return _BANK


def _slug(sitting_id: str) -> str:
    # 2025-10 -> october-2025
    months = {"01": "january", "02": "february", "03": "march", "04": "april",
              "05": "may", "06": "june", "07": "july", "08": "august",
              "09": "september", "10": "october", "11": "november", "12": "december"}
    y, m = sitting_id.split("-")
    return f"{months.get(m, m)}-{y}"


def _generated() -> str:
    return bank().get("generated") or "2026-09-07"


def _oldest() -> str:
    dates = [s["date"] for s in bank().get("sittings", []) if s.get("date")]
    return min(dates) if dates else _generated()


def _answer_cell(q: dict) -> str:
    """CBP's official answer, with the option text where we have one letter."""
    ans = q.get("answer") or ""
    if q.get("answer_status") == "credit":
        return "All examinees granted credit (question withdrawn)"
    if q.get("answer_status") == "multi":
        return f"{_e(ans)} (two answers accepted)"
    opt = q.get("options", {}).get(ans)
    return f"{_e(ans)}) {_e(opt)}" if opt else _e(ans)


def _explanation_cell(q: dict) -> str:
    st = q.get("explanation_status")
    if st == "ok" and q.get("explanation"):
        return (f'{_e(q["explanation"])}<br><span class="sub">Drafted by a local '
                f"model, checked by a second; quotes {_e(q.get('cfr_used') or 'the cited rule')}.</span>")
    reason = {
        "no-cfr": "cites the tariff schedule, not the CFR",
        "no-cfr-text": "the cited rule text did not resolve to a passage we could quote",
        "flagged": "our checker flagged the first draft, so it is withheld",
        "no-door": "the local drafting model was down at build time",
        "pending": "not yet drafted for this free sample",
        "special": "no single correct answer to explain",
        "no-answer": "no answer letter in the key",
    }.get(st, "in the full paid bank")
    return f'<span class="sub">Explanation withheld: {reason}. The full bank is the paid page.</span>'


def _question_cell(q: dict) -> str:
    opts = "; ".join(f"{k}) {_e(v)}" for k, v in sorted(q.get("options", {}).items()))
    return f'{_e(q["stem"])}<br><span class="sub">{opts}</span>'


def _rows_for(sitting: dict) -> list[dict]:
    """Up to SHOW_PER_SITTING questions to show free, explained ones first."""
    qs = sitting.get("questions", [])
    explained = [q for q in qs if q.get("explanation_status") == "ok"]
    if len(explained) >= 5:
        chosen = sorted(explained, key=lambda q: q["num"])[:SHOW_PER_SITTING]
    else:
        chosen = sorted(qs, key=lambda q: q["num"])[:SHOW_PER_SITTING]
    return chosen


def _source_link(q: dict) -> str:
    src = q.get("cfr_source_url") or CBP_PAGE
    return f'<a href="{_e(src)}" data-source-url="{_e(src)}">Q{q["num"]}</a>'


def slices() -> list[dict]:
    out = []
    gen = _generated()
    oldest = _oldest()
    runs = len([s for s in bank().get("sittings", []) if s.get("exam_present")])
    for s in bank().get("sittings", []):
        if not s.get("exam_present") or not s.get("key_present"):
            continue
        rows_src = _rows_for(s)
        if len(rows_src) < 5:
            continue
        total = s.get("questions_total", len(s.get("questions", [])))
        explained = s.get("questions_explained", 0)
        label = s["label"]
        slug = _slug(s["id"])
        headers = ["#", "Question and options", "CBP official answer",
                   "Our explanation"]
        rows = [[_source_link(q), _question_cell(q), _answer_cell(q),
                 _explanation_cell(q)] for q in rows_src]
        stamp = f"CBP {label} sitting · sealed copy {gen}"
        desc = (f"{label} Customs Broker Exam: official answers and explained "
                f"sample questions.")[:MAX_DESC]
        facts = [
            f"CBP's {label} exam had {total} questions. We explain {explained} of "
            f"them; the {SHOW_PER_SITTING if len(rows) >= SHOW_PER_SITTING else len(rows)} "
            "below are a free sample.",
            "The answer letter on every row is CBP's own official answer key. The "
            "explanation next to it is ours.",
            "Each explanation quotes the exact Title 19 CFR text the official key "
            "cites, fetched from the eCFR — the model quotes the rule, it does not "
            "recall it.",
            "Every explanation is drafted by a local model and then checked by a "
            "second local model; a flagged draft is withheld, not shown.",
        ]
        limits = [
            "Classification questions cite the tariff schedule (HTSUS), not the "
            "CFR, so we do not draft explanations for those; they are marked.",
            "A few questions were withdrawn by CBP (\"all examinees granted "
            "credit\") or had two accepted answers; those carry no single explanation.",
            "Machine-drafted explanations can be wrong. This is a study aid, not "
            "legal or tax advice, and not CBP's own explanation.",
            "New sittings appear here only after we manually add the CBP PDFs, "
            "which we do after each April and October exam.",
        ]
        out.append({
            "slug": slug,
            "name": f"{label} sitting",
            "h1": f"{label} Customs Broker Exam — official answers, explained",
            "lede": (f"CBP's {label} Customs Broker License Exam, with the official "
                     f"answer on every question and our explanation on the ones the "
                     f"key ties to a Title 19 CFR rule. {explained} of {total} explained."),
            "desc": desc,
            "newest": gen,
            "oldest": oldest,
            "runs": max(runs, 1),
            "cadence_days": 183,
            "row_count": total,
            "read_label": "Twice a year (April & October)",
            "read_phrase": "We add a new sitting after each April and October exam.",
            "rows_intro": ("These are real questions from the sealed CBP paper. The "
                           "answer is CBP's official one; the explanation is ours and "
                           "quotes the rule the key cites."),
            "tables": [{
                "caption": f"{label} sample: {len(rows)} of {total} questions",
                "stamp": stamp,
                "headers": headers,
                "rows": rows,
            }],
            "facts": facts,
            "limits": limits,
            "foot": DISCLAIMER,
        })
    if out:
        out.append(_coverage())
    return out


# ---------------------------------------------------------------- coverage

# Why every question we cannot explain is named. The free sitting pages show the
# explained questions first, which is the right order to read them in and the
# wrong impression to leave: a reader who only sees those would think the whole
# bank is explained. This page is the other half of that sentence -- it counts
# every question in every sealed paper by what we can and cannot say about it,
# out of the same file the sitting pages are cut from, and prints the reason
# beside each group. Nothing here is typed; the counts move when the bank does.
STATUS_WORDS = {
    "ok": "explained by us, quoting the Title 19 CFR passage CBP's key cites",
    "pending": "not drafted yet",
    "no-cfr": "cites the tariff schedule (HTSUS), not the CFR, so we draft nothing",
    "no-cfr-text": "the cited rule did not resolve to a passage we could quote",
    "flagged": "our second model flagged the first draft, so it is withheld",
    "special": "withdrawn or two accepted answers, so there is no single one to explain",
    "no-answer": "no answer letter in CBP's key",
}


def _coverage() -> dict:
    b = bank()
    gen = _generated()
    sittings = [s for s in b.get("sittings", []) if s.get("exam_present")]
    total_q = sum(s.get("questions_total", 0) for s in sittings)
    explained = sum(s.get("questions_explained", 0) for s in sittings)
    counts: dict[str, int] = {}
    for s in sittings:
        for q in s.get("questions", []):
            counts[q.get("explanation_status") or "no-answer"] = (
                counts.get(q.get("explanation_status") or "no-answer", 0) + 1)
    order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    sitting_rows = []
    for s in sittings:
        t = s.get("questions_total", len(s.get("questions", [])))
        e = s.get("questions_explained", 0)
        sitting_rows.append([
            _e(s["label"]),
            _e(s.get("date") or "not printed on the paper"),
            f"{t:,}",
            f"{e:,}",
            "yes" if s.get("key_present") else "no, so no page is built for it",
        ])

    status_rows = [[
        _e(STATUS_WORDS.get(k, k)),
        f"{n:,}",
        f"{n / total_q * 100:.0f}%" if total_q else "—",
    ] for k, n in order]

    return {
        "slug": "coverage",
        "name": "What is and is not in this feed",
        "h1": "What is and is not in the customs broker exam bank",
        "lede": (f"We hold {len(sittings)} sealed CBP exam papers and their official "
                 f"answer keys, {total_q:,} questions in all. {explained:,} of them "
                 f"carry an explanation of ours. This page counts the rest and says, "
                 f"group by group, why they do not."),
        "desc": (f"{len(sittings)} CBP exam papers, {total_q:,} questions, "
                 f"{explained:,} explained. What the rest are, and why each group "
                 f"carries no explanation.")[:MAX_DESC],
        "newest": gen,
        "oldest": _oldest(),
        "runs": max(len(sittings), 1),
        "cadence_days": 183,
        "row_count": total_q,
        "read_label": "Twice a year (April & October)",
        "read_phrase": "We add a new sitting after each April and October exam.",
        "rows_intro": ("Both tables below are counted off the same sealed copy of the "
                       "CBP papers that every sitting page is cut from."),
        "tables": [
            {
                "caption": (f"Every sitting we hold: the questions in the paper, and how "
                            f"many of them we explain"),
                "stamp": f"sealed copy {gen}",
                "headers": ["Sitting", "Exam date", "Questions in the paper",
                            "Explained by us", "CBP answer key held"],
                "rows": sitting_rows,
                "moved_col": 3,
            },
            {
                "caption": (f"All {total_q:,} questions, grouped by what we can say about "
                            f"them. Only the first group carries an explanation."),
                "stamp": f"sealed copy {gen}",
                "headers": ["What we can say about the question", "Questions",
                            "Share of the bank"],
                "rows": status_rows,
                "moved_col": 1,
            },
        ],
        "facts": [
            (f"We hold {len(sittings)} CBP exam papers, from {_oldest()} to the "
             f"{sittings[0]['label'] if sittings else 'latest'} sitting, and CBP's own "
             f"answer key for every one of them. "
             f'<a href="{_e(CBP_PAGE)}" data-source-url="{_e(CBP_PAGE)}">CBP publishes both</a>'),
            (f"{explained:,} of the {total_q:,} questions carry an explanation of ours. "
             f"The other {total_q - explained:,} are counted in the second table beside "
             f"the reason they do not."),
            ("The answer letter on every question is CBP's own official key. The "
             "explanation beside it is ours: drafted by a local model, checked by a "
             "second, and withheld whenever the checker flags it."),
            (f"Each free sitting page shows up to {SHOW_PER_SITTING} questions. The "
             f"paid page carries all {total_q:,}, grouped by topic."),
            ("Nothing on this page is fetched. Every number is counted out of the "
             "sealed copy of the papers we keep ourselves."),
        ],
        "limits": [
            "Classification questions cite the tariff schedule (HTSUS), not the CFR, "
            "so we do not draft explanations for those; they are counted above.",
            "A question CBP withdrew (\"all examinees granted credit\") or answered two "
            "ways has no single explanation, and we do not invent one.",
            "Machine-drafted explanations can be wrong. This is a study aid, not legal "
            "or tax advice, and not CBP's own explanation.",
            (f"We hold nothing from a sitting before {_oldest()}. Older papers exist on "
             f"CBP's page; we have not sealed a copy of them."),
            "New sittings appear here only after we add the CBP PDFs by hand, which we "
            "do after each April and October exam.",
        ],
        "foot": DISCLAIMER,
    }


def sample() -> tuple[list[str], list[list[str]]]:
    """The public sample file: real explained questions across all sittings.

    Explained rows first so the file a buyer downloads shows the product; if the
    model doors were down at build time it falls back to answer-only rows, which
    still shows the shape of the bank. Never empty while the PDFs parse.
    """
    headers = ["sitting", "question_no", "topic", "cbp_official_answer",
               "our_explanation"]
    ranked: list[tuple[int, list[str]]] = []
    for s in bank().get("sittings", []):
        for q in s.get("questions", []):
            explained = q.get("explanation_status") == "ok" and q.get("explanation")
            expl = q["explanation"] if explained else "(in the full paid bank)"
            ans = q.get("answer") or ""
            ranked.append((
                0 if explained else 1,
                [s["label"], str(q["num"]), q.get("topic", ""), ans, expl],
            ))
    ranked.sort(key=lambda t: (t[0], t[1][0], int(t[1][1])))
    rows = [r for _, r in ranked][:SAMPLE_ROWS]
    return headers, rows


def _totals() -> dict:
    b = bank()
    sittings = [s for s in b.get("sittings", []) if s.get("exam_present")]
    total_q = sum(s.get("questions_total", 0) for s in sittings)
    explained = sum(s.get("questions_explained", 0) for s in sittings)
    return {"n_sittings": len(sittings), "total_q": total_q, "explained": explained}


def family_spec() -> dict:
    from render_family import section, table  # noqa: E402 (same dir on sys.path)
    t = _totals()
    gen = _generated()
    n_sit, total_q, explained = t["n_sittings"], t["total_q"], t["explained"]
    desc = (f"{explained} of {total_q} questions from the last {n_sit} Customs "
            f"Broker Exam sittings, explained. $49.")
    if len(desc) > MAX_DESC:
        desc = f"The last {n_sit} Customs Broker Exam sittings, explained. $49 one-off."[:MAX_DESC]

    # A directory of the sittings, each a free page, with its explained count.
    sit_rows = []
    for s in bank().get("sittings", []):
        if not s.get("exam_present"):
            continue
        slug = _slug(s["id"])
        link = (f'<a href="{slug}/" data-source-url="{CBP_PAGE}">{_e(s["label"])}</a>')
        sit_rows.append([link, str(s.get("questions_total", 0)),
                         str(s.get("questions_explained", 0))])
    directory = table(
        ["Sitting", "Questions", "We explain"], sit_rows,
        f"The {n_sit} sittings in the bank", f"sealed copy {gen}",
    ) if sit_rows else "      <p>No sittings parsed yet.</p>"

    secs = [
        section(
            "What this is", None,
            "      <p>This is the explained question bank for the last "
            f"{n_sit} sittings of the US Customs and Border Protection Customs "
            "Broker License Exam. Every question carries CBP's own official answer. "
            "Where the official key ties an answer to a Title 19 CFR rule, we add a "
            "short explanation that <strong>quotes that rule</strong> — fetched from "
            "the eCFR, drafted by a local model, and checked by a second local "
            f"model. So far we explain <strong>{explained} of {total_q}</strong> "
            "questions.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_e(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
        section(
            "The sittings", "free to read", "      <p>Each sitting has its own free "
            "page with a sample of its questions, the official answer, and our "
            "explanation. The paid page is the whole bank, all sittings, grouped by "
            "topic.</p>\n" + directory,
        ),
        section(
            "How the explanations are made", None,
            '      <ul class="spec">\n'
            "        <li><strong>The answer is CBP's, not ours</strong>"
            '<span class="sub">Every answer letter comes straight from CBP\'s '
            "published answer key.</span></li>\n"
            "        <li><strong>The rule is quoted, not recalled</strong>"
            '<span class="sub">We fetch the exact Title 19 CFR text the key cites '
            "from the eCFR and hand it to the model; the model quotes it.</span></li>\n"
            "        <li><strong>Two models, not one</strong>"
            '<span class="sub">A first local model drafts the explanation; a second '
            "local model checks it against the same rule text. A flagged draft is "
            "withheld and counted, never shown.</span></li>\n"
            "        <li><strong>We withhold rather than guess</strong>"
            '<span class="sub">Classification questions cite the tariff schedule, '
            "not the CFR, so they get no explanation here — and we say so.</span></li>\n"
            "      </ul>",
        ),
        section(
            "Where the questions come from", None,
            "      <p>The questions and answer keys are CBP publications, in the "
            "public domain as US government works (17 U.S.C. 105). We downloaded "
            f"them from CBP's own page.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><a href="{CBP_PAGE}" data-source-url="{CBP_PAGE}">'
            "CBP: Past Customs Broker License Examinations &amp; Answer Keys</a>"
            '<span class="sub">The source page for every sitting in this bank.</span>'
            "</li>\n      </ul>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Trade records",
        "cadence": "twice a year",
        "cadence_long": ("a one-off purchase; we add each new sitting after the "
                         "April and October exams"),
        "crumb": "Customs Broker Exam Bank",
        "h1": "The Customs Broker Exam, explained — last five sittings",
        "buyer": ("candidates studying for the CBP Customs Broker License Exam who "
                  "want the recent papers with the official answer and a plain "
                  "explanation on each question"),
        "desc": desc,
        "lede": ("The last five Customs Broker License Exam sittings, every question "
                 "with CBP's official answer and — where the key cites a Title 19 CFR "
                 f"rule — our explanation that quotes it. {explained} of {total_q} "
                 "explained so far."),
        "pill_label": "Samples ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Customs%20Broker%20Exam%20Bank",
        "contact_h2": "Buy the full explained bank",
        "contact_p": ("Ask anything about what is and is not explained before you "
                      "buy. We reply with the current explained count per sitting."),
        "contact_cta": "Email us for the $49 checkout link",
        "contact_note": ("One payment, no subscription. You get the whole bank as a "
                         "single page, delivered within 15 minutes of payment."),
        "foot": DISCLAIMER,
        "delivery": ("<strong>What arrives after you pay:</strong> a single private "
                     "web page with the whole explained bank — all sittings, every "
                     "question, grouped by topic — within 15 minutes of payment."),
        "sample_note": ("cut out of the sealed CBP papers. The answers are CBP's own; "
                        "the explanations are ours and quote the cited rule."),
        "sample_rest": "the paid page carries every question, not just this sample",
    }


def _main() -> int:
    b = bank()
    sl = slices()
    hdr, rows = sample()
    t = _totals()
    print(f"family   {FAMILY}")
    print(f"bank     {BANK} (generated {b.get('generated')})")
    print(f"sittings {t['n_sittings']}, questions {t['total_q']}, explained {t['explained']}")
    print(f"slices   {len(sl)} sitting pages; sample {len(rows)} rows x {len(hdr)} cols")
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC, len(spec["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
