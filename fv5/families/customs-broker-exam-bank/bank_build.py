#!/usr/bin/env python3
"""Turn the sealed CBLE PDFs into an explained question bank.

This is the library behind refresh.py. It never prints a page and never edits
the estate; it parses the ten PDFs in fv5_data_cble/, fetches the rule text the
official key cites from the eCFR API, drafts one explanation per question on the
LOCAL model door :30003, checks that explanation on :30004, and hands back a
dict. refresh.py writes it to disk.

Walls this file lives inside (see COMMON-FAMILY.md):
  * no paid model, ever. Drafting goes to http://127.0.0.1:30003 and the check
    to :30004, both OpenAI-style, no auth. If a door is down the explanation is
    withheld and counted -- never recalled from a bigger model.
  * the model quotes the rule it was given; it is never asked for a fact it was
    not handed. A question whose key cites only the tariff schedule (no CFR text
    to fetch) gets no explanation, and that is counted honestly.
  * every model step logs its tokens to the state dir; past 2,000,000 tokens in
    one run the step stops.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------
FAMILY = "customs-broker-exam-bank"
HERE = Path(__file__).resolve().parent
# The repo root is .../<repo>/fv5/families/<id>/ -> parents[2]
REPO = HERE.parents[2]
PDF_DIR = REPO / "fv5_data_cble"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

STATE = family_state(FAMILY)
ECFR_CACHE = STATE / "ecfr"
TOKENS_LOG = STATE / "tokens.jsonl"
RAW_DIR = STATE / "raw"
FULL_BANK = RAW_DIR / "bank.full.json"          # the untrimmed copy refresh writes
DATA_DIR = HERE / "data"
BANK_JSON = DATA_DIR / "bank.json"              # the committed copy

# A question whose status is one of these was already settled by the model on an
# earlier run (drafting + checking both cost tokens). On a chunked resume we carry
# these across unchanged and never re-draft them, so each `--limit N` run spends
# its budget on N *new* questions instead of redoing the same first ones.
DONE_STATUSES = {"ok", "flagged"}

# The two local doors. Model ids are read off /v1/models at call time so a
# restart that renames the shard (qwen38-s3 -> qwen38-s4) does not break us.
DRAFT_DOOR = "http://127.0.0.1:30003"
CHECK_DOOR = "http://127.0.0.1:30004"
TOKEN_CAP = 2_000_000
CFR_CHARS = 4200  # how much rule text we hand the model; keeps us under 8k ctx

# When the model tells us it could not find the cited provision in the excerpt we
# handed it, that is an honest non-answer, not an explanation. We withhold it and
# count it rather than publish "I cannot explain this" on a page a buyer paid for.
CANNOT = re.compile(
    r"do(?:es)? not contain|cannot quote|can not quote|not (?:present|provided|"
    r"included|found|in the (?:excerpt|text|source))|missing from|"
    r"no (?:text|provision|mention)|unable to", re.I)

# The five sittings, newest first. Dates are the exam date printed on the paper.
# source_url is the CBP page every one of these came off (see SOURCES.md); the
# individual PDF URLs are recorded there, not re-typed here.
CBP_PAGE = ("https://www.cbp.gov/document/publications/"
            "past-customs-broker-license-examinations-answer-keys")
SITTINGS = [
    {"id": "2026-04", "label": "April 2026", "date": "2026-04-23"},
    {"id": "2025-10", "label": "October 2025", "date": "2025-10-22"},
    {"id": "2025-04", "label": "April 2025", "date": "2025-04-23"},
    {"id": "2024-10", "label": "October 2024", "date": "2024-10-23"},
    {"id": "2024-05", "label": "May 2024", "date": "2024-05-01"},
]

# The six exam categories are printed at the top of every sitting. A question's
# number tells you its topic; we read the ranges off the paper rather than guess.
NOISE = re.compile(
    r"CBP Publication|Customs Broker License Exam|Section \d+:|"
    r"^\s*Page\s+\d+|DIRECTIONS|Category [IVX]+\s*[-–]|^\s*Questions?\s+\d+\s*[-–]",
    re.I)


# ---------------------------------------------------------------------------
# PDF -> text
# ---------------------------------------------------------------------------
def _pdftext(path: Path) -> str:
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                         capture_output=True, text=True)
    return out.stdout


def _pdf_present(sitting_id: str, which: str) -> Path | None:
    p = PDF_DIR / f"{sitting_id}_{which}.pdf"
    return p if p.is_file() else None


# ---------------------------------------------------------------------------
# The category map, read off the exam's own contents block
# ---------------------------------------------------------------------------
CAT_LINE = re.compile(
    r"Category\s+([IVX]+)\s*[-–]\s*(.+?)\s+Questions?\s+(\d+)\s*[-–]\s*(\d+)")


def parse_categories(exam_text: str) -> list[tuple[int, int, str]]:
    """[(first, last, topic)] from the exam's printed contents. May be empty."""
    out = []
    for m in CAT_LINE.finditer(exam_text):
        topic = re.sub(r"\s+", " ", m.group(2)).strip()
        out.append((int(m.group(3)), int(m.group(4)), topic))
    # De-dup: the block is sometimes printed twice.
    seen, uniq = set(), []
    for lo, hi, topic in out:
        if (lo, hi) not in seen:
            seen.add((lo, hi))
            uniq.append((lo, hi, topic))
    return uniq


def topic_for(num: int, cats: list[tuple[int, int, str]]) -> str:
    for lo, hi, topic in cats:
        if lo <= num <= hi:
            return topic
    return "Uncategorised"


# ---------------------------------------------------------------------------
# The exam paper: numbered questions with A-E options
# ---------------------------------------------------------------------------
Q_START = re.compile(r"^\s*(\d{1,3})\.\s+(\S.*)$")
OPT = re.compile(r"^\s*([A-E])\)\s+(\S.*)$")


def parse_exam(exam_text: str) -> dict[int, dict]:
    """{num: {stem, options}} for questions 1..80.

    Robust against stray numbered lines (a year, a directive number) by only
    accepting a line as question N when N is the next number we expect. Options
    and stems wrap across lines and page breaks; noise lines are dropped.
    """
    lines = exam_text.splitlines()
    qs: dict[int, dict] = {}
    expect = 1
    cur: int | None = None
    opt: str | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        m = Q_START.match(line)
        if m and int(m.group(1)) == expect:
            cur = expect
            expect += 1
            opt = None
            qs[cur] = {"stem": m.group(2).strip(), "options": {}}
            continue
        if cur is None:
            continue
        mo = OPT.match(line)
        if mo:
            opt = mo.group(1)
            qs[cur]["options"][opt] = mo.group(2).strip()
            continue
        if NOISE.search(line):
            continue
        # A continuation of whatever we are inside.
        piece = line.strip()
        if opt is not None:
            qs[cur]["options"][opt] += " " + piece
        else:
            qs[cur]["stem"] += " " + piece
    # Tidy whitespace.
    for q in qs.values():
        q["stem"] = re.sub(r"\s+", " ", q["stem"]).strip()
        q["options"] = {k: re.sub(r"\s+", " ", v).strip() for k, v in q["options"].items()}
    return qs


# ---------------------------------------------------------------------------
# The answer key: a three-column table, citations wrapping across lines
# ---------------------------------------------------------------------------
KEY_ROW = re.compile(r"^\s*(\d{1,3})\s+Answer\s+([A-E])\b\s*(.*)$")
KEY_CREDIT = re.compile(r"^\s*(\d{1,3})\s+All examinees granted credit", re.I)
KEY_AND = re.compile(r"^\s*(\d{1,3})\s+and\s*$")
BARE_ANSWER = re.compile(r"^\s*Answer\s+([A-E])\s*$")


def parse_key(key_text: str) -> dict[int, dict]:
    """{num: {answer, citations, status}} for questions 1..80.

    answer is a single letter for the normal case. Two honest exceptions the CBP
    keys carry, handled explicitly rather than dropped:
      * "All examinees granted credit" -- the question was thrown out. answer is
        "credit"; there is no single right answer to explain.
      * two accepted answers, printed as "Answer B / <n> and / Answer D" around
        the number. answer is the two letters joined; status is "multi".
    Anything we still cannot read is left out, and refresh.py reports the count
    of missing rows against the 80 expected -- see the README.
    """
    lines = key_text.splitlines()
    keys: dict[int, dict] = {}
    cur: int | None = None
    # First pass: the multi-answer wrap. A bare "Answer X" line, then "<n> and",
    # then another bare "Answer Y" -> question n accepts X and Y.
    pending_letter: str | None = None
    for i, raw in enumerate(lines):
        ba = BARE_ANSWER.match(raw)
        if ba:
            pending_letter = ba.group(1)
            continue
        ma = KEY_AND.match(raw)
        if ma and pending_letter:
            n = int(ma.group(1))
            second = None
            for j in range(i + 1, min(i + 4, len(lines))):
                b2 = BARE_ANSWER.match(lines[j])
                if b2:
                    second = b2.group(1)
                    break
            letters = pending_letter + ((", " + second) if second else "")
            cite = ""
            for j in range(i + 1, min(i + 8, len(lines))):
                cm = re.search(r"(19\s+C\.?F\.?R\.?.*|HTSUS.*|GRI.*|ACE.*|General.*)",
                               lines[j])
                if cm and not BARE_ANSWER.match(lines[j]):
                    cite = cm.group(1).strip()
                    break
            keys[n] = {"answer": letters, "citations": cite, "status": "multi"}
            pending_letter = None
            continue
        pending_letter = None

    # Second pass: the normal rows and the credited ones.
    cur = None
    for raw in lines:
        mc = KEY_CREDIT.match(raw)
        if mc:
            n = int(mc.group(1))
            keys.setdefault(n, {"answer": "credit", "citations": "", "status": "credit"})
            cur = None
            continue
        m = KEY_ROW.match(raw)
        if m:
            n = int(m.group(1))
            cur = n
            if n not in keys:  # do not clobber a multi/credit row
                keys[n] = {"answer": m.group(2), "citations": m.group(3).strip(),
                           "status": "single"}
            continue
        # Citation continuation for the row we are on.
        if cur is not None and keys.get(cur, {}).get("status") == "single":
            s = raw.strip()
            if not s or NOISE.search(s) or BARE_ANSWER.match(raw) or KEY_AND.match(raw):
                continue
            if re.match(r"^\d{1,3}\s+Answer", raw):
                continue
            keys[cur]["citations"] = (keys[cur]["citations"] + " " + s).strip()
    for k in keys.values():
        k["citations"] = re.sub(r"\s+", " ", k["citations"]).strip()
    return keys


# ---------------------------------------------------------------------------
# Citations -> eCFR section text
# ---------------------------------------------------------------------------
# "19 CFR 111.2(b)", "19 C.F.R. 141.0a", "19 CFR 111.30 (d)". We want part 111
# and section 111.2 -- the subsection in parentheses is not part of the lookup.
CFR_CITE = re.compile(r"19\s+C\.?F\.?R\.?\s+(?:§\s*)?(\d+)\.(\d+[a-z]?)")


def cfr_cites(citation: str) -> list[tuple[str, str]]:
    """Distinct (part, section) pairs a citation string points at, in order."""
    out, seen = [], set()
    for m in CFR_CITE.finditer(citation or ""):
        part = m.group(1)
        section = f"{part}.{m.group(2)}"
        if section not in seen:
            seen.add(section)
            out.append((part, section))
    return out


def _cfr_url(date: str, part: str, section: str) -> str:
    q = urllib.parse.urlencode({"part": part, "section": section})
    return f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-19.xml?{q}"


def fetch_cfr(part: str, section: str, date: str) -> tuple[str, str] | None:
    """(plain rule text, source url) for one section, cached on disk. None on miss.

    The eCFR endpoint insists on a compression header; without it it answers an
    error, not the section. Cached under the state dir keyed by date+section so a
    refresh re-run does not re-hit the API for text that does not move.
    """
    ECFR_CACHE.mkdir(parents=True, exist_ok=True)
    url = _cfr_url(date, part, section)
    cache = ECFR_CACHE / f"{date}_title-19_{section}.txt"
    if cache.is_file():
        body = cache.read_text(encoding="utf-8")
        return (body, url) if body.strip() else None
    try:
        req = urllib.request.Request(url, headers={
            "Accept-Encoding": "gzip",
            "User-Agent": "usta-fv5-customs-broker-exam-bank/1.0",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
    except (urllib.error.URLError, OSError, gzip.BadGzipFile):
        return None
    xml = data.decode("utf-8", "replace")
    if "<error" in xml[:200].lower() or "<DIV8" not in xml:
        cache.write_text("", encoding="utf-8")  # remember the miss
        return None
    text = _xml_to_text(xml)
    cache.write_text(text, encoding="utf-8")
    return (text, url) if text.strip() else None


def _xml_to_text(xml: str) -> str:
    xml = re.sub(r"(?is)<HEAD>(.*?)</HEAD>", r"\1\n", xml)
    xml = re.sub(r"(?is)<[^>]+>", " ", xml)
    xml = (xml.replace("&quot;", '"').replace("&amp;", "&")
           .replace("&lt;", "<").replace("&gt;", ">").replace("“", '"')
           .replace("”", '"').replace("§", "§"))
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", xml)).strip()


def cfr_date_for(sitting: dict, exam_text: str) -> str:
    """Which eCFR snapshot to quote for a sitting.

    The exam paper states the CFR edition its questions were written against
    ("Title 19 ... Revised as of April 1, YYYY"). We quote that snapshot when we
    can read it, so the rule text matches the exam; otherwise April 1 of the year
    before the sitting. Never a date in the future -- clamped to today.
    """
    m = re.search(r"Revised as of April 1,\s*(\d{4})", exam_text)
    year = int(m.group(1)) if m else int(sitting["id"][:4]) - 1
    date = dt.date(year, 4, 1)
    today = dt.date.today()
    if date > today:
        date = today
    return date.isoformat()


# ---------------------------------------------------------------------------
# The two local doors
# ---------------------------------------------------------------------------
_MODEL_CACHE: dict[str, str] = {}


def _model_id(door: str) -> str:
    if door in _MODEL_CACHE:
        return _MODEL_CACHE[door]
    try:
        with urllib.request.urlopen(f"{door}/v1/models", timeout=8) as r:
            mid = json.load(r)["data"][0]["id"]
    except Exception:
        mid = "qwen38"
    _MODEL_CACHE[door] = mid
    return mid


def door_up(door: str) -> bool:
    try:
        urllib.request.urlopen(f"{door}/v1/models", timeout=8).read()
        return True
    except Exception:
        return False


class TokenBudget:
    """Runs the tokens.jsonl log and stops a run past the 2M cap (guardrail 10)."""

    def __init__(self) -> None:
        self.total = 0
        STATE.mkdir(parents=True, exist_ok=True)

    def spend(self, door: str, kind: str, usage: dict) -> None:
        n = int((usage or {}).get("total_tokens") or 0)
        self.total += n
        with TOKENS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "stamp": dt.datetime.now().isoformat(timespec="seconds"),
                "door": door, "kind": kind, "tokens": n, "run_total": self.total,
            }) + "\n")

    def exhausted(self) -> bool:
        return self.total >= TOKEN_CAP


def _chat(door: str, system: str, user: str, budget: TokenBudget,
          kind: str, max_tokens: int = 320) -> str:
    body = json.dumps({
        "model": _model_id(door),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "/no_think\n" + user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(door + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        o = json.load(r)
    budget.spend(door, kind, o.get("usage") or {})
    text = o["choices"][0]["message"]["content"]
    return re.sub(r"(?is)<think>.*?</think>", "", text).strip()


DRAFT_SYSTEM = (
    "You explain one US Customs Broker License Exam question for a candidate. "
    "You are given the question, its options, the official correct answer, and "
    "the exact text of the regulation the official key cites. Write 2 to 4 "
    "sentences. Quote the regulation you were given -- do not rely on memory. "
    "Say why the official answer is correct under that text. Do not invent facts, "
    "do not cite any section that is not in the text you were given, and never "
    "contradict the official answer. Plain English."
)
CHECK_SYSTEM = (
    "You are a checker. You are given a regulation excerpt, an official answer "
    "letter, and a candidate explanation. Answer with a single word on the first "
    "line: PASS or FLAG. FLAG if the explanation contradicts the official answer, "
    "OR cites any section number that does not appear in the excerpt, OR states a "
    "fact not supported by the excerpt. Otherwise PASS. After the word, one short "
    "reason."
)


def draft_explanation(q: dict, rule_text: str, budget: TokenBudget) -> str:
    opts = "\n".join(f"{k}) {v}" for k, v in sorted(q["options"].items()))
    user = (
        f"QUESTION:\n{q['stem']}\n\nOPTIONS:\n{opts}\n\n"
        f"OFFICIAL CORRECT ANSWER: {q['answer']}\n\n"
        f"THE OFFICIAL KEY CITES: {q['citations']}\n\n"
        f"REGULATION TEXT (quote from this only):\n{rule_text[:CFR_CHARS]}\n\n"
        "Write the explanation now."
    )
    return _chat(DRAFT_DOOR, DRAFT_SYSTEM, user, budget, "draft")


def check_explanation(q: dict, rule_text: str, explanation: str,
                      budget: TokenBudget) -> tuple[bool, str]:
    user = (
        f"REGULATION EXCERPT:\n{rule_text[:CFR_CHARS]}\n\n"
        f"OFFICIAL ANSWER: {q['answer']}\n\n"
        f"CANDIDATE EXPLANATION:\n{explanation}\n\n"
        "PASS or FLAG?"
    )
    verdict = _chat(CHECK_DOOR, CHECK_SYSTEM, user, budget, "check", max_tokens=80)
    first = (verdict.splitlines() or [""])[0].upper()
    passed = "PASS" in first and "FLAG" not in first
    return passed, verdict.strip()[:200]


# ---------------------------------------------------------------------------
# Assemble one sitting, then the whole bank
# ---------------------------------------------------------------------------
def load_sitting(sitting: dict) -> dict:
    """Parse one sitting's exam+key. No network, no model. source_ok reflects PDFs."""
    exam_pdf = _pdf_present(sitting["id"], "exam")
    key_pdf = _pdf_present(sitting["id"], "key")
    rec = dict(sitting)
    rec.update({"source_url": CBP_PAGE, "exam_present": bool(exam_pdf),
                "key_present": bool(key_pdf), "questions": []})
    if not exam_pdf or not key_pdf:
        rec["cfr_date"] = ""
        return rec
    exam_text = _pdftext(exam_pdf)
    key_text = _pdftext(key_pdf)
    cats = parse_categories(exam_text)
    qmap = parse_exam(exam_text)
    kmap = parse_key(key_text)
    rec["cfr_date"] = cfr_date_for(sitting, exam_text)
    rec["key_rows_parsed"] = len(kmap)
    rec["key_rows_missing"] = sorted(n for n in range(1, 81) if n not in kmap)
    for num in sorted(qmap):
        q = qmap[num]
        k = kmap.get(num, {})
        rec["questions"].append({
            "sitting": sitting["id"], "num": num,
            "topic": topic_for(num, cats),
            "stem": q["stem"], "options": q["options"],
            "answer": k.get("answer", ""),
            "answer_status": k.get("status", "missing"),
            "citations": k.get("citations", ""),
            "cfr": cfr_cites(k.get("citations", "")),
            "explanation": "", "explanation_status": "pending",
            "cfr_used": "", "cfr_source_url": "", "checker": "",
        })
    return rec


def _load_prior_bank() -> dict | None:
    """The last bank refresh.py wrote, if any -- for resuming a chunked build.

    Prefers the untrimmed state-dir copy; falls back to the committed data copy.
    A missing or unreadable file just means "nothing to resume from" (first run).
    """
    for p in (FULL_BANK, BANK_JSON):
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def overlay_prior(bank: dict) -> int:
    """Carry already-settled explanations from a prior run onto this fresh parse.

    Keyed by (sitting, num). Only model-settled questions (see DONE_STATUSES) are
    copied over: those are the ones whose draft+check already spent tokens, so a
    resume must not redo them. Everything else is left `pending` and recomputed --
    those paths (no-answer / no-cfr / no-door) spend no model tokens. Returns the
    number of questions carried over.
    """
    prior = _load_prior_bank()
    if not prior:
        return 0
    prior_q: dict[tuple, dict] = {}
    for s in prior.get("sittings", []):
        for q in s.get("questions", []):
            prior_q[(q.get("sitting"), q.get("num"))] = q
    carried = 0
    for rec in bank["sittings"]:
        for q in rec["questions"]:
            pq = prior_q.get((q["sitting"], q["num"]))
            if pq and pq.get("explanation_status") in DONE_STATUSES:
                for f in ("explanation", "explanation_status", "cfr_used",
                          "cfr_source_url", "checker"):
                    q[f] = pq.get(f, q[f])
                carried += 1
    return carried


def explain_bank(bank: dict, limit: int, budget: TokenBudget) -> None:
    """Draft+check explanations in place, up to `limit` questions this run.

    Priority order fills the free per-sitting sample pages first: each sitting's
    lowest-numbered CFR-citing questions come first, then the rest. A question
    whose key cites no fetchable 19 CFR section is marked no-cfr and never sent to
    the model. If either door is down, nothing is drafted and every eligible
    question is left no-door -- the honest zero the spec calls for.

    Questions already settled by an earlier run (carried over by overlay_prior)
    keep their status and are skipped, so a chunked resume drafts N *new*
    questions per `--limit N` rather than repeating the first N every time.
    """
    draft_ok = door_up(DRAFT_DOOR)
    check_ok = door_up(CHECK_DOOR)
    doors_ok = draft_ok and check_ok
    # Build the eligible worklist: single-answer questions with a CFR citation.
    work: list[dict] = []
    for rec in bank["sittings"]:
        for q in rec["questions"]:
            if q["explanation_status"] in DONE_STATUSES:
                continue  # settled on a prior run -- do not re-draft
            if q["answer_status"] != "single" or not q["cfr"]:
                if q["answer_status"] != "single":
                    q["explanation_status"] = "no-answer" if not q["answer"] else "special"
                else:
                    q["explanation_status"] = "no-cfr"
                continue
            work.append(q)
    # Order: round-robin the sittings so all five free pages fill together, each
    # sitting in ascending question number.
    by_sitting: dict[str, list[dict]] = {}
    for q in work:
        by_sitting.setdefault(q["sitting"], []).append(q)
    for lst in by_sitting.values():
        lst.sort(key=lambda x: x["num"])
    ordered: list[dict] = []
    idx = 0
    order_ids = [s["id"] for s in SITTINGS if s["id"] in by_sitting]
    while any(by_sitting.values()):
        sid = order_ids[idx % len(order_ids)]
        idx += 1
        if by_sitting.get(sid):
            ordered.append(by_sitting[sid].pop(0))
    done = 0
    for q in ordered:
        if done >= limit or budget.exhausted():
            q["explanation_status"] = "pending"
            continue
        if not doors_ok:
            q["explanation_status"] = "no-door"
            continue
        # Fetch the first citation that resolves to real text.
        rule_text = source_url = used = ""
        for part, section in q["cfr"]:
            got = fetch_cfr(part, section, bank["sittings_by_id"][q["sitting"]]["cfr_date"])
            if got:
                rule_text, source_url = got
                used = section
                break
        if not rule_text:
            q["explanation_status"] = "no-cfr-text"
            continue
        try:
            expl = draft_explanation(q, rule_text, budget)
            passed, verdict = check_explanation(q, rule_text, expl, budget)
        except Exception as exc:  # a door that dropped mid-run
            q["explanation_status"] = "no-door"
            q["checker"] = f"door error: {exc}"[:120]
            continue
        q["cfr_used"] = used
        q["cfr_source_url"] = source_url
        q["checker"] = verdict
        if expl and CANNOT.search(expl):
            # The model said the excerpt does not cover the cited provision. That
            # is honest, and it is not an explanation -- withhold and count it.
            q["explanation_status"] = "no-cfr-text"
        elif passed and expl:
            q["explanation"] = expl
            q["explanation_status"] = "ok"
        else:
            q["explanation_status"] = "flagged"
        done += 1


def build_bank(limit: int = 0, dry_run: bool = False) -> dict:
    """Parse every sitting, then (unless dry-run) draft up to `limit` explanations."""
    budget = TokenBudget()
    sittings = [load_sitting(s) for s in SITTINGS]
    bank = {
        "family": FAMILY,
        "generated": dt.date.today().isoformat(),
        "source_page": CBP_PAGE,
        "sittings": sittings,
        "sittings_by_id": {s["id"]: s for s in sittings},
    }
    carried = 0
    if not dry_run:
        carried = overlay_prior(bank)  # resume: keep settled explanations
    if not dry_run and limit > 0:
        explain_bank(bank, limit, budget)
    bank["carried_over"] = carried
    # Roll up per-sitting stats.
    for rec in bank["sittings"]:
        qs = rec["questions"]
        rec["questions_total"] = len(qs)
        rec["questions_explained"] = sum(1 for q in qs if q["explanation_status"] == "ok")
        rec["questions_flagged"] = sum(1 for q in qs if q["explanation_status"] == "flagged")
    bank["tokens_this_run"] = budget.total
    # sittings_by_id is a convenience view; drop it before it is serialised so
    # the file has one copy of each sitting, not two.
    bank.pop("sittings_by_id", None)
    return bank


if __name__ == "__main__":
    import sys
    b = build_bank(limit=0, dry_run=True)
    for rec in b["sittings"]:
        miss = rec.get("key_rows_missing", [])
        print(f"{rec['id']}: {rec.get('questions_total', 0)} questions, "
              f"key parsed {rec.get('key_rows_parsed', 0)}/80, missing {miss}, "
              f"cfr_date {rec.get('cfr_date')}")
    sys.exit(0)
