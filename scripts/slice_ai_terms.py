#!/usr/bin/env python3
"""Slice pages for AI policy and terms changes (/feeds/ai-terms/...).

An AI vendor rewrites its terms, its privacy policy or its data-use page
whenever it likes. The page you read today is the only one the vendor keeps.
We save our own dated copy of every watched page every day, seal the day, and
store the difference between one day's copy and the next as plain text. So we
hold the sentence as it was written before, the sentence as it is written now,
and both dates.

Every row this module returns is read out of those stored differences at call
time. Nothing is typed in here. In particular there is no date literal in this
file: the newest day comes from the sealed day records themselves, because a
file's modification time and a run log both lied by eight days on this estate
in August 2026.

The store is read only. Nothing here opens a file for writing.

Two things are deliberately NOT rows:

  * A page whose fingerprint changed but whose readable wording did not. The
    archive holds hundreds of those. A fingerprint moving is not a promise
    moving, so a change only becomes a row when we can quote the sentence that
    moved out of the stored difference.
  * A sentence that changes and then changes back on the same page. That is one
    of the vendor's own servers disagreeing with another, not a decision. Both
    halves of every such pair are dropped, counted, and named on the coverage
    page.
"""
from __future__ import annotations

import difflib
import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

FAMILY = "ai-terms"
CADENCE_DAYS = 1

ARCHIVE = Path("/home/gmullins/Claude CLI/constraint-moat/archive")

# The five-real-rows floor. A page under this is dropped, never padded.
MIN_ROWS = 5
TABLE_CAP = 12

# How much of a quote a table cell carries before it is cut. The buyer's file
# carries the whole stored passage; the page shows an excerpt and says so.
QUOTE_CHARS = 210

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# What the vendor calls the page, in our words.
SURFACE_WORDS = {
    "terms": "terms of service",
    "privacy": "privacy policy",
    "acceptable_use": "acceptable-use policy",
    "data_use": "data-use page",
    "deprecation": "model retirement page",
    "enterprise": "enterprise terms",
    "model_card": "model card",
}

# The vendor's own spelling, where the folder name is not it.
COMPANY_WORDS = {
    "amazon_aws": "Amazon Web Services",
    "google_deepmind": "Google DeepMind",
    "huggingface": "Hugging Face",
    "openrouter": "OpenRouter",
    "deepl": "DeepL",
    "openai": "OpenAI",
    "nvidia": "NVIDIA",
    "gitlab": "GitLab",
    "heygen": "HeyGen",
    "elevenlabs": "ElevenLabs",
    "writer_com": "Writer",
    "you_com": "You.com",
    "stability_ai": "Stability AI",
    "ai21": "AI21 Labs",
    "x_ai": "xAI",
    "ibm": "IBM",
    "sap": "SAP",
    "aws": "Amazon Web Services",
}

# One vendor serves its terms as UTF-8 while telling the browser otherwise, so
# an apostrophe reaches us as two or three stray characters. This finds those
# runs so they can be put back. It changes no word.
MOJIBAKE = re.compile("\u00e2[\u0080-\u00bf]{2}|[\u00c2-\u00c3][\u0080-\u00bf]"
                      "|\u00c2(?=\\s|$)")

# Icon-font glyphs and invisible spacing characters. A legal page carries them
# where a menu icon sits; they are not words and never belong in a quote.
PUA = re.compile("[\ue000-\uf8ff\u200b-\u200f\ufeff\u00ad]")

# Put between two runs of touched lines that are not next to each other, so no
# sentence is ever built across the gap between two separate edits.
BREAK = "\x00"

W = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
DIGIT_TOKEN = re.compile(r"^[\d\W_]+$")
TRACE = "This is the Trace Id"
DATEONLY = re.compile(r"^\s*(last\s+(updated|modified|revised)|effective|updated|"
                      r"version)\b", re.I)
STOP = set(
    "a an the and or of to in for that this these those is are was were be been by "
    "with as it its any all we our us you your they their he she not no if then than "
    "such shall may will must can from on at into under over between about which who "
    "whom whose there here do does".split()
)
# The words a promise is made with, plus an address to write to. A short
# passage carrying one of these is doing something to somebody.
PROMISE = (r"[\w.+-]+@[\w-]+\.[\w.]{2,}"
           r"|\b(?:shall|must|may\s+not|will\s+not|prohibit|agree|consent|liab"
           r"|warrant|indemnif|arbitrat|claim|hearing|terminat|retain"
           r"|delete|disclos|govern|jurisdiction|opt[\s-]*out|retire|deprecat"
           r"|shut\s?down|sunset|licen[sc]|train|process|transfer|sell)\w*")
STRONG = re.compile(PROMISE, re.I)
# The same, plus a year or a money figure. Those mark a clause when there is
# enough of it to read; on their own, on a short passage, they are as likely to
# be the fundraising banner a vendor prints above its terms.
SIGNAL = re.compile(r"\b(?:19|20)\d\d\b|[$€£]\s?\d|" + PROMISE, re.I)

# What a site's own spam filter leaves behind where an address used to be. Our
# copy of it changing is our fetch changing, not the vendor's wording.
MASKED_ADDRESS = "[email protected]"
# Words that say who a passage is about. A clause in a contract nearly always
# names one of them. A product menu printed on the same page as the terms
# almost never does, which is how the two are told apart.
PARTY = re.compile(r"\b(?:you|your|yours|we|us|our|ours|customer|customers|user|"
                   r"users|subscriber|member|client|it's|its)\b", re.I)
# Machine widget markup on a legal page, e.g. an "ask this page" box.
UI_TOKEN = re.compile(r"[a-z]_[a-z]+[A-Z]")
# Where one sentence ends and the next begins.
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(]|[a-z]\)|[ivx]+[.)])")
# A clause number or letter at the front of a sentence.
ENUM = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[ivxlcIVXLC]+|[A-Za-z])\s*[.)]\s*")

# Tuning, all of it measured against the stored differences rather than guessed.
PAIR_RATIO = 0.50      # how alike two lines must be to be read as one rewrite
PAIR_BUDGET = 40000    # comparisons we will spend on one rewritten stretch
MIN_WORDS = 25         # words in a move before it needs no other reason to count
FLOOR_WORDS = 5        # words below which nothing is a clause, whatever it says
TITLE_FRAC = 0.70      # share of capitalised words that marks a link list
JAM_HITS = 3           # run-together words that mark a navigation menu
STOP_FRAC = 0.18       # share of ordinary joining words in real prose

_CACHE: dict = {}


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _company(slug: str) -> str:
    if slug in COMPANY_WORDS:
        return COMPANY_WORDS[slug]
    return " ".join(p.capitalize() for p in slug.replace("-", "_").split("_"))


def _surface(slug: str) -> str:
    return SURFACE_WORDS.get(slug, slug.replace("_", " "))


def _mend(s: str) -> str:
    """Make a stored line readable without changing a word of it.

    Two things get in the way. One vendor serves its terms as UTF-8 while
    declaring a different encoding, so an apostrophe arrives as three stray
    characters; those are put back. And several vendors print menu icons from a
    private font, which arrive as characters with no meaning at all; those are
    dropped. Neither step touches a word.
    """
    if PUA.search(s):
        s = PUA.sub(" ", s)
    if not MOJIBAKE.search(s):
        return s

    def put_back(hit: re.Match) -> str:
        run = hit.group(0)
        if len(run) == 1:
            return ""
        try:
            return run.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return run

    return MOJIBAKE.sub(put_back, s)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _bare(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _jam(s: str) -> int:
    return len(re.findall(r"[a-z][A-Z]", s))


def _titleish(s: str) -> float:
    w = W.findall(s)
    if len(w) < 6:
        return 0.0
    return sum(1 for x in w if x[0].isupper()) / len(w)


def _stopfrac(s: str) -> float:
    w = [x.lower() for x in W.findall(s)]
    if not w:
        return 1.0
    return sum(1 for x in w if x in STOP) / len(w)


def _hunks(diff_text: str):
    """Split a stored difference into the blocks the vendor actually edited.

    A stored page is hard-wrapped, so one edit shows up as a run of touched
    lines with untouched lines around it. Two runs that are not next to each
    other are two different edits, and gluing them into one sentence would
    invent a sentence the vendor never wrote. A break marker is put between
    runs so that cannot happen.
    """
    cur = None
    prev = ""
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if cur is not None:
                yield cur
            cur = {"minus": [], "plus": []}
            prev = ""
        elif cur is None:
            continue
        elif line.startswith("+"):
            if prev != "+" and cur["plus"]:
                cur["plus"].append(BREAK)
            cur["plus"].append(_mend(line[1:]))
            prev = "+"
        elif line.startswith("-"):
            if prev != "-" and cur["minus"]:
                cur["minus"].append(BREAK)
            cur["minus"].append(_mend(line[1:]))
            prev = "-"
        else:
            prev = " "
    if cur is not None:
        yield cur


def _sentences(lines: list[str]) -> list[str]:
    """One day's removed or added text, cut into sentences.

    Lines are the wrong unit. When a vendor changes the template its page is
    built from, the same paragraph comes back broken across different lines,
    and reading line against line then reports a page full of new promises
    where not one word moved. Sentences survive that, so sentences are what we
    compare.
    """
    out: list[str] = []
    chunk: list[str] = []
    for line in list(lines) + [BREAK]:
        if line == BREAK:
            text = _norm(" ".join(x.strip() for x in chunk if x.strip()))
            chunk = []
            if text:
                out += [x.strip() for x in SENT_SPLIT.split(text) if x.strip()]
        else:
            chunk.append(line)
    return out


def _align(minus: list[str], plus: list[str]) -> list[tuple[str, str]]:
    """Pair each removed sentence with the sentence that replaced it.

    The two sides are lined up in order first, so the sentences that did not
    move drop out. Only inside a stretch that really was rewritten do we ask
    which sentence replaced which, and only when the two resemble each other at
    all. Anything left over is an arrival or a departure, and is shown as one.
    """
    old, new = _sentences(minus), _sentences(plus)
    if not old and not new:
        return []
    pairs: list[tuple[str, str]] = []
    order = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in order.get_opcodes():
        if tag == "equal":
            continue
        pairs += _pair_block(old[i1:i2], new[j1:j2])
    return pairs


def _pair_block(left: list[str], right: list[str]) -> list[tuple[str, str]]:
    """Inside one rewritten stretch, match each old sentence to its replacement."""
    if not left:
        return [("", p) for p in right]
    if not right:
        return [(m, "") for m in left]
    cands = []
    if len(left) * len(right) <= PAIR_BUDGET:
        for i, m in enumerate(left):
            for j, p in enumerate(right):
                sm = difflib.SequenceMatcher(None, m, p)
                if sm.real_quick_ratio() < PAIR_RATIO:
                    continue
                if sm.quick_ratio() < PAIR_RATIO:
                    continue
                r = sm.ratio()
                if r >= PAIR_RATIO:
                    cands.append((r, i, j))
        cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_m: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[str, str]] = []
    for _r, i, j in cands:
        if i in used_m or j in used_p:
            continue
        used_m.add(i)
        used_p.add(j)
        pairs.append((left[i], right[j]))
    pairs += [(m, "") for i, m in enumerate(left) if i not in used_m]
    pairs += [("", p) for j, p in enumerate(right) if j not in used_p]
    return pairs


CLAUSE_TOKEN = re.compile(r"^\(?[0-9ivxlcIVXLCa-zA-Z]{1,4}[.)]$")
FURNITURE_WORDS = 6


def _moved_words(b: str, a: str) -> tuple[list[str], list[str], int, int]:
    """The words that actually differ between two versions of one sentence.

    A vendor can rewrite a clause, or it can leave the clause alone and change
    the menu printed above it. Both look like an edited line. Reading only the
    words that moved is what tells the two apart.
    """
    bw, aw = b.split(), a.split()
    rem: list[str] = []
    add: list[str] = []
    first_b = first_a = -1
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, bw, aw, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if first_b < 0:
            first_b, first_a = i1, j1
        rem += bw[i1:i2]
        add += aw[j1:j2]
    return rem, add, first_b, first_a


def _reject(before: str, after: str) -> str | None:
    """Why this pair is not a wording change. None means it is one."""
    b, a = _norm(before), _norm(after)
    both = f"{b} {a}".strip()
    if not both:
        return "empty"
    if MASKED_ADDRESS in both:
        return "address hidden by the site"
    lines = [x for x in (b, a) if x]
    if all(DIGIT_TOKEN.match(x) for x in lines):
        return "rotating token"
    if any(x.startswith(TRACE) for x in lines):
        return "session trace line"
    if b and a and _bare(b) == _bare(a):
        return "capitals or punctuation only"
    if b and a and _bare(ENUM.sub("", b)) == _bare(ENUM.sub("", a)):
        return "clause numbering only"
    if any(UI_TOKEN.search(x) for x in lines):
        return "page widget markup"
    if sum(_jam(x) for x in lines) >= JAM_HITS:
        return "run-together menu"
    longer = max(lines, key=len)
    if _titleish(longer) >= TITLE_FRAC:
        return "list of links"
    if _stopfrac(longer) < STOP_FRAC:
        return "list rather than prose"
    if all(DATEONLY.match(x) for x in lines):
        return "date line only"
    if len(W.findall(max(lines, key=len))) < FLOOR_WORDS:
        return "too short to be a clause"
    if len(W.findall(both)) < MIN_WORDS and not STRONG.search(both):
        return "too short, and promises nothing"
    if not PARTY.search(both) and not SIGNAL.search(both):
        return "names nobody it applies to"
    if b and a:
        rem, add, at_b, at_a = _moved_words(b, a)
        moved = " ".join(rem + add)
        if moved and all(CLAUSE_TOKEN.match(x) for x in rem + add):
            return "clause letter only"
        # Words that changed at the very front of a passage, carry no promise
        # word, name nobody, and hold no punctuation, are the menu strip a
        # vendor prints above its policy. The clause underneath did not move.
        if (moved and at_b <= 0 and at_a <= 0
                and len(W.findall(moved)) <= FURNITURE_WORDS
                and not re.search(r"[,;:]", moved)
                and not SIGNAL.search(moved) and not PARTY.search(moved)):
            return "menu text above the clause"
    return None


def _kind(before: str, after: str) -> str:
    if before and after:
        return "reworded"
    return "arrived" if after else "removed"


def _read() -> dict:
    if _CACHE:
        return _CACHE

    # The day list comes out of the sealed day records themselves. Every field
    # below is read from inside a file, never from a file name and never from a
    # modification time.
    seals = []
    for path in sorted((ARCHIVE / "seals").glob("*.txt")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if rec.get("snapshot_date"):
            seals.append(rec)
    seal_days = sorted({s["snapshot_date"] for s in seals})
    leaves = {s["snapshot_date"]: int(s.get("leaf_count") or 0) for s in seals}

    records = []
    for path in sorted((ARCHIVE / "diffs").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue

    kinds = Counter(r.get("change_type") for r in records)
    diff_days = sorted({r["snapshot_date"] for r in records if r.get("snapshot_date")})
    newest = max(seal_days + diff_days)
    oldest = min(seal_days + diff_days)

    # Pass one: every candidate pair, before anything is judged.
    cands = []
    hunk_total = 0
    rejected_moves = 0
    for r in records:
        if r.get("change_type") != "changed" or not r.get("unified_diff"):
            continue
        key = f"{r.get('company')}__{r.get('surface_type')}"
        blocks = list(_hunks(r["unified_diff"]))
        hunk_total += len(blocks)
        minus = [x for h in blocks for x in h["minus"] + [BREAK]]
        plus = [x for h in blocks for x in h["plus"] + [BREAK]]
        # A passage that leaves one part of the page and turns up unchanged
        # somewhere else on it has not been reworded; the page was reordered.
        # Hold the whole day's edit so we can see that before calling anything
        # new.
        gone = {_bare(x) for x in _sentences(minus)}
        came = {_bare(x) for x in _sentences(plus)}
        for before, after in _align(minus, plus):
            if not before and _bare(after) in gone:
                rejected_moves += 1
                continue
            if not after and _bare(before) in came:
                rejected_moves += 1
                continue
            cands.append({
                "key": key,
                "company": r.get("company") or "",
                "surface": r.get("surface_type") or "",
                "url": r.get("url") or "",
                "prev_date": r.get("prev_date") or "",
                "date": r.get("snapshot_date") or "",
                "before": _norm(before),
                "after": _norm(after),
            })

    # Pass two: a sentence that moved one way on a page and moved back on the
    # same page is that vendor's two servers disagreeing, not a decision. That
    # covers both a rewrite that reverses itself and a passage that leaves the
    # page and then comes back.
    seen = {(c["key"], c["before"], c["after"]) for c in cands}
    flip = {(k, b, a) for (k, b, a) in seen if (k, a, b) in seen and b and a}
    arrived: dict[str, set] = defaultdict(set)
    departed: dict[str, set] = defaultdict(set)
    for c in cands:
        if c["after"] and not c["before"]:
            arrived[c["key"]].add(c["after"])
        elif c["before"] and not c["after"]:
            departed[c["key"]].add(c["before"])
    both_ways = {k: arrived[k] & departed[k] for k in set(arrived) | set(departed)}

    moves = []
    rejected = Counter()
    pingpong_hits = 0
    pingpong_pages = set()
    for c in cands:
        text = c["after"] or c["before"]
        if ((c["key"], c["before"], c["after"]) in flip
                or text in both_ways.get(c["key"], ())):
            pingpong_hits += 1
            pingpong_pages.add(c["key"])
            continue
        why = _reject(c["before"], c["after"])
        if why:
            rejected[why] += 1
            continue
        c["kind"] = _kind(c["before"], c["after"])
        moves.append(c)

    # One edit often lands the same sentence on two of a vendor's pages the same
    # day. Keep it once, on the page it reads best on.
    order = {"terms": 0, "privacy": 1, "acceptable_use": 2, "data_use": 3}
    moves.sort(key=lambda m: (m["date"], m["company"],
                              order.get(m["surface"], 9), m["before"]))
    dedup = []
    seen_pair = set()
    for m in moves:
        sig = (m["company"], m["date"], m["before"], m["after"])
        if sig in seen_pair:
            continue
        seen_pair.add(sig)
        dedup.append(m)
    moves = dedup
    moves.sort(key=lambda m: (m["date"], m["company"], m["surface"]), reverse=True)

    # What the newest day actually tried to read.
    man_path = ARCHIVE / "data" / newest / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    entries = man.get("entries") or man.get("surfaces") or []
    blocked = [e for e in entries if e.get("blocked")]
    block_reasons = Counter(e.get("block_reason") or "unknown" for e in blocked)
    statuses = Counter(e.get("status") for e in entries)
    errors = Counter(e.get("error") for e in entries if e.get("error"))
    surfaces_watched = Counter(e.get("surface_type") for e in entries)
    companies_watched = sorted({e.get("company") for e in entries if e.get("company")})
    fetched = sum(1 for e in entries if e.get("status") == 200 and not e.get("blocked"))

    _CACHE.update({
        "seal_days": seal_days,
        "leaves": leaves,
        "runs": len(seal_days),
        "newest": newest,
        "oldest": oldest,
        "records": len(records),
        "kinds": kinds,
        "hunks": hunk_total,
        "cands": len(cands),
        "moved_on_page": rejected_moves,
        "moves": moves,
        "rejected": rejected,
        "pingpong_hits": pingpong_hits,
        "pingpong_pages": sorted(pingpong_pages),
        "manifest": man,
        "entries": entries,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "statuses": statuses,
        "errors": errors,
        "surfaces_watched": surfaces_watched,
        "companies_watched": companies_watched,
        "fetched": fetched,
        "added": [r for r in records if r.get("change_type") == "added"],
        "removed": [r for r in records if r.get("change_type") == "removed"],
    })
    return _CACHE


# --------------------------------------------------------------- presentation

# How many sentences must move on one page in one read before we call it a
# whole-page replacement rather than an edit.
BIG_REWRITE = 20

# A retirement row has to carry a date, or it is not telling anyone when
# something gets switched off.
RETIRE = re.compile(r"\b(?:retir\w*|deprecat\w*|shut\s?down|shutting\s+down|"
                    r"sunset\w*|end[-\s]of[-\s]life|no longer (?:be )?(?:available"
                    r"|supported|offered)|will be removed|discontinu\w*)\b", re.I)
YEAR = re.compile(r"\b(?:19|20)\d\d\b")

GONE = "<em>gone from the page</em>"
NEW = "<em>not on the page before</em>"


def _clip(text: str, limit: int = QUOTE_CHARS) -> str:
    text = _norm(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def _window(words: list[str], start: int, end: int, pad: int = 9) -> str:
    a = max(0, start - pad)
    b = min(len(words), end + pad)
    out = " ".join(words[a:b])
    if a > 0:
        out = "… " + out
    if b < len(words):
        out = out + " …"
    return out


def _excerpt(before: str, after: str) -> tuple[str, str]:
    """Show the part of a long clause that actually moved.

    A vendor can change three words in the middle of a ninety-word sentence.
    Cutting the quote at the front would show a buyer two cells that look
    identical, so the cut is taken around the change instead, with enough either
    side of it to read.
    """
    if not before or not after:
        return _clip(before), _clip(after)
    bw, aw = before.split(), after.split()
    ops = [o for o in difflib.SequenceMatcher(None, bw, aw, autojunk=False).get_opcodes()
           if o[0] != "equal"]
    if not ops:
        return _clip(before), _clip(after)
    i1, i2 = ops[0][1], min(ops[-1][2], ops[0][1] + 30)
    j1, j2 = ops[0][3], min(ops[-1][4], ops[0][3] + 30)
    return _clip(_window(bw, i1, i2)), _clip(_window(aw, j1, j2))


def _row(m: dict, with_page: bool = True) -> list[str]:
    before, after = _excerpt(m["before"], m["after"])
    row = [html.escape(_company(m["company"]))]
    if with_page:
        row.append(html.escape(_surface(m["surface"])))
    row += [html.escape(before) if before else NEW,
            html.escape(after) if after else GONE,
            f'{_day(m["prev_date"])} &rarr; {_day(m["date"])}']
    return row


def _score(m: dict) -> tuple:
    """Which of a day's changes is the one worth putting on the page.

    A sentence that reads as a sentence beats one the vendor's page ran together
    into a single string. A change with both halves readable beats one where a
    passage only arrived or only left, and a passage carrying a promise word
    beats one that does not. Nothing here invents a row; it only decides which
    real row is shown first.
    """
    rank = {"reworded": 0, "arrived": 1, "removed": 2}
    text = f'{m["before"]} {m["after"]}'
    # A passage a vendor's page ran together into one string is real, but it is
    # unreadable, so a clean sentence is shown ahead of it.
    return (min(_jam(text), 2), rank.get(m["kind"], 3),
            0 if SIGNAL.search(text) else 1, -len(W.findall(text)))


def _best_of(group: list[dict]) -> dict:
    return min(group, key=_score)


def _pick(rows: list[dict], cap: int = TABLE_CAP, per_vendor: int = 3) -> list[dict]:
    """Spread the shown rows so one vendor's rewrite cannot fill the table."""
    groups: dict[tuple, list] = defaultdict(list)
    for m in rows:
        groups[(m["company"], m["date"])].append(m)
    best = sorted((_best_of(g) for g in groups.values()),
                  key=lambda m: (m["date"], m["company"]), reverse=True)
    while True:
        seen = Counter()
        out = []
        for m in best:
            if seen[m["company"]] >= per_vendor:
                continue
            seen[m["company"]] += 1
            out.append(m)
            if len(out) >= cap:
                break
        if len(out) >= min(cap, MIN_ROWS) or per_vendor >= len(best):
            return out
        per_vendor += 1


def _one_per_vendor(rows: list[dict], cap: int = TABLE_CAP) -> list[dict]:
    best: dict[str, dict] = {}
    for m in rows:
        if m["company"] not in best or _score(m) < _score(best[m["company"]]):
            best[m["company"]] = m
    return sorted(best.values(), key=lambda m: (m["date"], m["company"]),
                  reverse=True)[:cap]


def _window_words() -> str:
    d = _read()
    return f"{_day(d['oldest'])} to {_day(d['newest'])}"


def _base(slug: str, name: str, h1: str, lede: str, desc: str, row_count: int) -> dict:
    d = _read()
    return {
        "slug": slug,
        "name": name,
        "h1": h1,
        "lede": lede,
        "desc": desc,
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": d["runs"],
        "cadence_days": CADENCE_DAYS,
        "row_count": row_count,
        "tables": [],
        "facts": [],
        "limits": [],
    }


def _limits(extra: str | None = None) -> list[str]:
    d = _read()
    refused = d["block_reasons"].get("http_403", 0)
    told_off = d["block_reasons"].get("robots_disallow", 0)
    out = [
        "We can only show a change between two of our own reads. A vendor who "
        "changed a sentence and changed it back between one read and the next did "
        "something we never saw, and it is not on this page.",
        f"A page's fingerprint moving is not its wording moving. "
        f"{d['kinds'].get('changed', 0):,} pages came back different from the day "
        f"before in this window; most of that was a session number, a menu, or the "
        f"capitals in a heading, and produced no sentence anyone could quote. Those "
        f"are not rows.",
        f"{d['pingpong_hits']:,} passages on {len(d['pingpong_pages'])} pages moved "
        f"one way and then moved back. That is one of the vendor's own servers "
        f"disagreeing with another, not a decision, so both halves are left out.",
        "We read the page the vendor publishes on the open web. The contract you "
        "actually signed can say something different, and we never see that.",
        f"The quote in the table is an excerpt, cut at about {QUOTE_CHARS} characters "
        "around the part that moved. The file you buy carries the whole stored "
        "passage and the date on either side of it.",
        f"We only hold pages we can fetch. On {_day(d['newest'])}, {refused} of the "
        f"pages we ask for refused us outright and {told_off} tell any automated "
        f"reader not to fetch them, so we do not. Every one of them is named on the "
        f"coverage page.",
        "We say what moved and when. We do not grade any company, we do not score "
        "one, and we do not tell you whether a change is good or bad for you. That "
        "is your lawyer's job, not ours.",
    ]
    if extra:
        out.append(extra)
    return out


def _shared_facts(d: dict) -> str:
    return (f"We hold {d['runs']} sealed days, {_window_words()}, and read every "
            f"watched page once a day.")


def _held_sentence() -> str:
    """The "how much do you hold" line, COUNTED, never typed.

    This sentence was typed into catalog.json. It said 44 sealed days to
    22 August 2026 while the archive held 46 to 24 August, and it was going to
    be wrong by one more day every morning, because the reader seals a new day
    each night and nothing was going to retype the number.

    Both numbers now come out of _read(), which is the same set of sealed day
    records the page stamp already uses: the day list is read from INSIDE each
    seal file, never from a file name and never from a modification time. If the
    reader stops, the end date stops with it and the page says so on its own.
    """
    d = _read()
    return (
        f"We hold {d['runs']:,} dated seal days, from {_day(d['oldest'])} to "
        f"{_day(d['newest'])}. We will tell you which of your vendors are inside "
        f"them. There is nothing to buy yet."
    )


# -------------------------------------------------------------------- slices

SURFACE_PAGES = (
    (("privacy",), "privacy-policies", "Privacy policy changes",
     "When an AI vendor changed its privacy policy, and what the sentence said",
     "How they say they handle your data is the part that moves most.",
     "Wording that moved on {vendors} AI vendors' privacy policies, {window}. "
     "The old sentence, the new one, and both dates.",
     "A privacy policy is one document per vendor. A change to a sub-processor "
     "list, a regional annex or a cookie table sits on a different page, and "
     "unless we watch that page too it is not here."),
    (("terms",), "terms-of-service", "Terms of service changes",
     "When an AI vendor changed its terms of service, and what the sentence said",
     "The terms are what you agreed to. They get rewritten without telling you.",
     "Wording that moved in {vendors} AI vendors' terms of service, {window}. "
     "The old sentence, the new one, and both dates.",
     "Some vendors publish one set of terms for everybody and negotiate a "
     "different one with enterprise buyers. We read the published set."),
    (("data_use", "acceptable_use"), "data-use-and-limits",
     "Data-use and acceptable-use changes",
     "When an AI vendor changed what it may do with your data, or what you may "
     "do with its model",
     "Two pages decide the same argument: what they may train on, and what you "
     "are not allowed to build.",
     "Wording that moved on {vendors} AI vendors' data-use and acceptable-use "
     "pages, {window}. Old sentence, new sentence, both dates.",
     "Only some vendors publish a separate data-use page at all. A vendor "
     "missing from this table may have said the same thing inside its privacy "
     "policy, which is on the privacy page instead."),
)


def _surface_slice(surfaces, slug, name, h1, blurb, desc, extra) -> dict | None:
    d = _read()
    rows = [m for m in d["moves"] if m["surface"] in surfaces]
    if len(rows) < MIN_ROWS:
        print(f"[{FAMILY}] dropped {slug}: {len(rows)} quotable changes, floor is "
              f"{MIN_ROWS}", file=sys.stderr)
        return None
    vendors = sorted({m["company"] for m in rows})
    days = sorted({m["date"] for m in rows})
    kinds = Counter(m["kind"] for m in rows)
    shown = _pick(rows)
    if len(shown) < MIN_ROWS:
        print(f"[{FAMILY}] dropped {slug}: only {len(shown)} rows to show",
              file=sys.stderr)
        return None
    heaviest, heavy_n = Counter(
        (m["company"], m["date"]) for m in rows).most_common(1)[0]

    sl = _base(
        slug=slug, name=name, h1=h1,
        lede=(f"{blurb} {len(vendors)} of the vendors we watch moved "
              f"{len(rows):,} sentences here on {len(days)} separate days, "
              f"{_window_words()}. <strong>We hold the copy from the day "
              f"before every one of them.</strong>"),
        desc=desc.format(vendors=len(vendors), window=_window_words()),
        row_count=len(rows),
    )
    sl["tables"].append({
        "caption": (f"{len(shown)} real changes, newest first, spread across vendors "
                    f"so one rewrite cannot fill the table. The file you buy carries "
                    f"all {len(rows):,}."),
        "stamp": _window_words(),
        "headers": ["Vendor", "Page", "What it said before", "What it says now",
                    "Between"],
        "rows": [_row(m) for m in shown],
        "moved_col": 3,
    })
    sl["facts"] = [
        f"{len(rows):,} sentences moved on these pages, across {len(vendors)} named "
        f"vendors and {len(days)} separate days, {_window_words()}.",
        f"{kinds.get('arrived', 0):,} passages arrived that were not on the page the "
        f"day before, {kinds.get('removed', 0):,} left it entirely, and "
        f"{kinds.get('reworded', 0):,} were rewritten in place.",
        f"The heaviest single day was {_company(heaviest[0])} on {_day(heaviest[1])}: "
        f"{heavy_n:,} sentences moved on one page between two of our reads.",
        _shared_facts(d),
    ]
    sl["limits"] = _limits(extra)
    return sl


def _retirements() -> dict | None:
    """Models and features being switched off, with the date they go."""
    d = _read()
    rows = [m for m in d["moves"]
            if RETIRE.search(m["after"] or m["before"])
            and YEAR.search(m["after"] or m["before"])
            and len(W.findall(m["after"] or m["before"])) >= 8]
    if len(rows) < MIN_ROWS:
        print(f"[{FAMILY}] dropped model-retirements: {len(rows)} dated notices, "
              f"floor is {MIN_ROWS}", file=sys.stderr)
        return None
    vendors = sorted({m["company"] for m in rows})
    pages = len({(m["company"], m["surface"]) for m in rows})
    watched = d["surfaces_watched"].get("deprecation", 0)

    sl = _base(
        slug="model-retirements",
        name="Models and features being switched off",
        h1="AI models and features being switched off, and the date they go",
        lede=(f"A model you built on gets a retirement date, and the notice goes up "
              f"on a page you were never told to read. We read it every day. "
              f"{len(rows)} dated switch-off notices moved on {pages} pages, "
              f"{_window_words()}."),
        desc=(f"{len(rows)} dated notices of AI models and features being switched "
              f"off, caught {_window_words()}, with the date on either side."),
        row_count=len(rows),
    )
    sl["tables"].append({
        "caption": (f"Every dated switch-off notice we caught moving, newest first. "
                    f"A row with nothing in the left column is a notice that was not "
                    f"on the page the day before."),
        "stamp": _window_words(),
        "headers": ["Vendor", "Page", "What it said before", "What it says now",
                    "Between"],
        "rows": [_row(m) for m in rows[:TABLE_CAP]],
        "moved_col": 3,
    })
    sl["facts"] = [
        f"{len(rows)} dated switch-off notices moved, across {len(vendors)} named "
        f"vendors, {_window_words()}.",
        f"Only {watched} of the {len(d['companies_watched'])} vendors we watch "
        f"publish a page listing what they are retiring. Everyone else announces it "
        f"somewhere else, or not at all.",
        "A retirement notice is the one change with a deadline attached. It tells "
        "you the date your code stops working, which is why we quote the sentence "
        "rather than say the page changed.",
        _shared_facts(d),
    ]
    sl["limits"] = _limits(
        "This page carries notices that name a year. A vendor who writes "
        "“this model will be retired in due course” has told you nothing "
        "datable, and we would rather leave the row out than print a deadline "
        "nobody gave.")
    return sl


def _rewrites() -> dict | None:
    """Whole pages a vendor replaced between one of our reads and the next."""
    d = _read()
    per = Counter((m["company"], m["surface"], m["date"]) for m in d["moves"])
    big = sorted(((k, n) for k, n in per.items() if n >= BIG_REWRITE),
                 key=lambda kn: (-kn[1], kn[0]))
    if len(big) < MIN_ROWS:
        print(f"[{FAMILY}] dropped whole-page-rewrites: {len(big)} days at or over "
              f"{BIG_REWRITE} sentences, floor is {MIN_ROWS}", file=sys.stderr)
        return None
    by_key = defaultdict(list)
    for m in d["moves"]:
        by_key[(m["company"], m["surface"], m["date"])].append(m)

    rows = []
    for (company, surface, date), n in big[:TABLE_CAP]:
        pick = _best_of(by_key[(company, surface, date)])
        before, after = _excerpt(pick["before"], pick["after"])
        rows.append([
            html.escape(_company(company)),
            html.escape(_surface(surface)),
            f"{n:,}",
            f'{_day(pick["prev_date"])} &rarr; {_day(date)}',
            html.escape(after or before) or NEW,
        ])

    total = sum(n for _k, n in big)
    vendors = sorted({k[0] for k, _n in big})
    top_key, top_n = big[0]

    sl = _base(
        slug="whole-page-rewrites",
        name="Whole pages replaced in a day",
        h1="AI vendors that replaced a whole legal page in one day",
        lede=(f"Most days a vendor changes a sentence. Some days the page you agreed "
              f"to is gone and a different one is in its place. On {len(big)} days, "
              f"{_window_words()}, {BIG_REWRITE} or more sentences moved on one page "
              f"between two of our reads. <strong>We hold the copy from the day "
              f"before each one.</strong>"),
        desc=(f"{len(big)} days when an AI vendor replaced most of a legal page at "
              f"once, {_window_words()}, with both dates and a sentence from each."),
        row_count=len(big),
    )
    sl["tables"].append({
        "caption": (f"Every day on which {BIG_REWRITE} or more sentences moved on one "
                    f"page. The quote is one sentence out of that day's change; the "
                    f"file you buy carries all {total:,} of them."),
        "stamp": _window_words(),
        "headers": ["Vendor", "Page", "Sentences that moved", "Between",
                    "One of them"],
        "rows": rows,
        "moved_col": 2,
    })
    sl["facts"] = [
        f"{len(big)} whole-page days across {len(vendors)} named vendors, holding "
        f"{total:,} of the {len(d['moves']):,} sentence changes we caught in all.",
        f"The largest was {_company(top_key[0])}'s {_surface(top_key[1])} on "
        f"{_day(top_key[2])}: {top_n:,} sentences moved between two of our reads.",
        "On a day like this the live page tells you nothing about what you agreed "
        "to last week, and the vendor keeps no copy of the old one.",
        _shared_facts(d),
    ]
    sl["limits"] = _limits(
        "A big number here is not proof of a big legal change. A vendor moving to "
        "a new page template can shift hundreds of sentences without altering a "
        "promise. We do not guess which it was; the row shows you a sentence so "
        "you can read it yourself.")
    return sl


def _by_vendor() -> dict | None:
    d = _read()
    per = Counter(m["company"] for m in d["moves"])
    ranked = per.most_common()
    if len(ranked) < MIN_ROWS:
        print(f"[{FAMILY}] dropped by-vendor: {len(ranked)} vendors, floor is "
              f"{MIN_ROWS}", file=sys.stderr)
        return None
    pages = defaultdict(set)
    days = defaultdict(set)
    for m in d["moves"]:
        pages[m["company"]].add(m["surface"])
        days[m["company"]].add(m["date"])

    count_rows = [[
        html.escape(_company(c)),
        html.escape(", ".join(sorted(_surface(s) for s in pages[c]))),
        f"{len(days[c])}",
        f"{n:,}",
    ] for c, n in ranked[:TABLE_CAP]]
    quote_rows = [_row(m) for m in _one_per_vendor(d["moves"])]
    quiet = len(d["companies_watched"]) - len(ranked)

    sl = _base(
        slug="by-vendor",
        name="Which vendors changed a legal page",
        h1="Which AI vendors changed a legal page, and how much moved",
        lede=(f"{len(ranked)} named vendors moved wording on a legal page in the "
              f"{d['runs']} days from {_day(d['oldest'])} to {_day(d['newest'])}. "
              f"This page ranks them by how much moved, then quotes one real change "
              f"from each."),
        desc=(f"{len(ranked)} named AI vendors that changed wording on a legal page, "
              f"{_window_words()}, ranked by how much moved."),
        row_count=len(d["moves"]),
    )
    sl["tables"].append({
        "caption": (f"The {len(count_rows)} vendors who moved the most wording, out of "
                    f"{len(ranked)} who moved any. A day counts once, however many "
                    f"sentences moved on it."),
        "stamp": _window_words(),
        "headers": ["Vendor", "Pages they changed", "Days something moved",
                    "Sentences that moved"],
        "rows": count_rows,
        "moved_col": 3,
    })
    sl["tables"].append({
        "caption": (f"One real change from each of {len(quote_rows)} vendors, newest "
                    f"first. The file you buy carries every vendor and every change."),
        "stamp": _window_words(),
        "headers": ["Vendor", "Page", "What it said before", "What it says now",
                    "Between"],
        "rows": quote_rows,
        "moved_col": 3,
    })
    sl["facts"] = [
        f"{len(ranked)} of the {len(d['companies_watched'])} vendors we watch moved "
        f"wording on a legal page in this window. The other {quiet} did not move a "
        f"sentence we could quote.",
        f"{len(d['moves']):,} sentence changes in all, on "
        f"{len({(m['company'], m['surface']) for m in d['moves']})} separate pages.",
        f"The busiest was {_company(ranked[0][0])}: {ranked[0][1]:,} sentences over "
        f"{len(days[ranked[0][0]])} "
        f"{'day' if len(days[ranked[0][0]]) == 1 else 'days'}.",
        _shared_facts(d),
    ]
    sl["limits"] = _limits(
        "A vendor near the bottom of this table is not tidier than one near the "
        "top. It may publish a shorter page, or one that refuses us.")
    return sl


def _coverage() -> dict:
    d = _read()
    entries = d["entries"]
    said = {200: "answered with a page", 401: "asked us to log in",
            403: "refused us", 404: "said there is no such page",
            429: "told us to slow down", 500: "their server errored",
            503: "their server was unavailable"}
    err_words = {
        "empty_after_extract": "answered, but with no readable text on the page",
        "non_text_content_type:application/pdf": "answered with a PDF, which we do "
                                                 "not read",
        "http_404": "said there is no such page",
        "http_401": "asked us to log in",
        "http_429": "told us to slow down",
    }
    status_rows = []
    for code, count in sorted(d["statuses"].items(),
                              key=lambda kv: (-kv[1], str(kv[0]))):
        word = ("we never asked, because the site tells automated readers not to"
                if code is None else said.get(code, f"answered with code {code}"))
        status_rows.append([html.escape(word), f"{count:,}"])
    # An error that is just the answer code again would say the same thing twice.
    for err, count in sorted(d["errors"].items(), key=lambda kv: (-kv[1], kv[0])):
        if err.startswith("http_"):
            continue
        status_rows.append([html.escape("of those, " + err_words.get(err, err)),
                            f"{count:,}"])

    blocked_rows = [[
        html.escape(_company(e.get("company") or "")),
        html.escape(_surface(e.get("surface_type") or "")),
        "they refuse us" if e.get("block_reason") == "http_403"
        else "they tell automated readers not to",
        html.escape(_clip(e.get("url") or "", 70)),
    ] for e in sorted(d["blocked"], key=lambda e: (e.get("company") or "",
                                                   e.get("surface_type") or ""))]
    watched_rows = [[html.escape(_surface(s)), f"{n:,}"]
                    for s, n in d["surfaces_watched"].most_common()]

    quotable_pages = len({(m["company"], m["surface"]) for m in d["moves"]})
    sl = _base(
        slug="coverage",
        name="What is and is not in this feed",
        h1="What is and is not in the AI terms feed",
        lede=(f"Every day we ask {len(entries):,} pages belonging to "
              f"{len(d['companies_watched'])} AI vendors for their current wording "
              f"and seal what comes back. This page says how many answered, names "
              f"every page we cannot read, and says what we throw out before "
              f"anything becomes a row."),
        desc=(f"How many of the {len(entries):,} AI vendor legal pages we ask for "
              f"each day answer, which refuse us, and what we leave out."),
        row_count=len(entries),
    )
    sl["tables"].append({
        "caption": (f"What the {len(entries):,} pages did when we asked for them on "
                    f"{_day(d['newest'])}. The lines beginning “of those” "
                    f"break down pages that answered with nothing we could read."),
        "stamp": _day(d["newest"]),
        "headers": ["What the page did", "How many pages"],
        "rows": status_rows[:TABLE_CAP],
        "moved_col": None,
    })
    sl["tables"].append({
        "caption": (f"Every page we could not collect on {_day(d['newest'])}, named. "
                    f"A blocked page is recorded as blocked; it is never treated as a "
                    f"page with nothing on it."),
        "stamp": _day(d["newest"]),
        "headers": ["Vendor", "Page", "Why we have no copy", "Address"],
        "rows": blocked_rows,
        "moved_col": 2,
    })
    sl["tables"].append({
        "caption": "The kinds of page we ask every vendor for.",
        "stamp": _day(d["newest"]),
        "headers": ["Kind of page", "How many we ask for"],
        "rows": watched_rows[:TABLE_CAP],
        "moved_col": None,
    })
    sl["facts"] = [
        f"{len(entries):,} pages asked for on {_day(d['newest'])}: {d['fetched']:,} "
        f"read and sealed, {len(d['blocked'])} not collected.",
        f"{len(d['companies_watched'])} named vendors. We hold {d['runs']} sealed "
        f"days, {_window_words()}, one seal a day with a fingerprint over every page "
        f"in it.",
        f"Across those days {d['kinds'].get('changed', 0):,} pages came back different "
        f"from the day before, {d['kinds'].get('added', 0):,} pages appeared that we "
        f"had never held, and {d['kinds'].get('removed', 0):,} stopped being there.",
        f"Of those changes, {len(d['moves']):,} were sentences we could quote, on "
        f"{quotable_pages} pages. The rest moved something that is not wording.",
        f"{d['pingpong_hits']:,} passages on {len(d['pingpong_pages'])} pages moved "
        f"one way and back again. We drop both halves rather than sell you a change "
        f"that undid itself.",
    ]
    sl["limits"] = _limits(
        f"{d['moved_on_page']:,} passages moved from one part of a page to another "
        f"without a word changing. We do not count those as changes, and we do not "
        f"tell you where on a page a passage sits.")
    return sl


def slices() -> list[dict]:
    out: list[dict] = []
    for surfaces, slug, name, h1, blurb, desc, extra in SURFACE_PAGES:
        sl = _surface_slice(surfaces, slug, name, h1, blurb, desc, extra)
        if sl:
            out.append(sl)
    for build in (_retirements, _rewrites, _by_vendor):
        sl = build()
        if sl:
            out.append(sl)
    out.append(_coverage())
    # Stamped here and nowhere else. The slice dicts above are assembled in
    # three separate places, and stamping each of them separately is how a key
    # ends up wired into one caller out of three.
    note = _held_sentence()
    for sl in out:
        sl["contact_note_counted"] = note
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for /feeds/ai-terms/sample.json and sample.csv."""
    d = _read()
    headers = ["vendor", "page", "said_before", "says_now", "what_moved",
               "first_read", "second_read", "url"]
    words = {"reworded": "rewritten in place",
             "arrived": "arrived on the page",
             "removed": "left the page"}
    rows = []
    for m in _pick(d["moves"], cap=25, per_vendor=2):
        rows.append([_company(m["company"]), _surface(m["surface"]),
                     m["before"], m["after"], words[m["kind"]],
                     m["prev_date"], m["date"], m["url"]])
    return headers, rows


if __name__ == "__main__":
    t0 = time.time()
    d = _read()
    print(f"family {FAMILY}")
    print(f"  sealed days   {d['runs']}   {d['oldest']} to {d['newest']}")
    print(f"  diff records  {d['records']}  {dict(d['kinds'])}")
    print(f"  hunks {d['hunks']}  candidate pairs {d['cands']}  "
          f"moved on the page {d['moved_on_page']}")
    print(f"  ping-pong dropped {d['pingpong_hits']} on "
          f"{len(d['pingpong_pages'])} pages")
    print(f"  rejected {dict(d['rejected'].most_common())}")
    print(f"  quotable {len(d['moves'])} across "
          f"{len({m['company'] for m in d['moves']})} vendors  "
          f"{dict(Counter(m['surface'] for m in d['moves']))}")
    print(f"  newest day: {len(d['entries'])} asked, {d['fetched']} read, "
          f"{len(d['blocked'])} blocked {dict(d['block_reasons'])}")
    print()
    ok = True
    for sl in slices():
        shown = sum(len(t["rows"]) for t in sl["tables"])
        bad = []
        if sl["row_count"] < MIN_ROWS or shown < MIN_ROWS:
            bad.append("UNDER THE FIVE-ROW FLOOR")
        if len(sl["desc"]) > 155:
            bad.append(f"DESC {len(sl['desc'])} > 155")
        if not 1 <= len(sl["tables"]) <= 3:
            bad.append("TABLE COUNT")
        if not 3 <= len(sl["facts"]) <= 6:
            bad.append("FACT COUNT")
        if not 2 <= len(sl["limits"]) <= 8:
            bad.append(f"LIMIT COUNT {len(sl['limits'])}")
        for t in sl["tables"]:
            if any(len(r) != len(t["headers"]) for r in t["rows"]):
                bad.append("ROW WIDTH")
            if len(t["rows"]) > 30:
                bad.append(f"TABLE OF {len(t['rows'])} ROWS")
        ok = ok and not bad
        print(f"  {sl['slug']:<20} held={sl['row_count']:<6} shown={shown:<3} "
              f"tables={len(sl['tables'])} facts={len(sl['facts'])} "
              f"limits={len(sl['limits'])} desc={len(sl['desc'])}"
              + ("   " + "; ".join(bad) if bad else ""))
    hdr, srows = sample()
    print(f"\n  sample {len(srows)} rows, {len(hdr)} columns")
    for r in srows[:2]:
        print("    ", [str(x)[:52] for x in r])
    print(f"\n{'OK' if ok else 'PROBLEM'} in {time.time() - t0:.1f}s")
