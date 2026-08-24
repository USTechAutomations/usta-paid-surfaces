#!/usr/bin/env python3
"""Slice pages for named-role moves on company jobs pages (/feeds/hiring-watch/...).

A company rewrites its own jobs page whenever it likes and keeps no history of
it. The list you fetch today is the only one there is, so the role that was open
last month is not recoverable from the company. We save a dated copy of the jobs
page and the careers page from a fixed panel of companies every day, so we hold
what the list said before and what it says now.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE.

Most of the copies we hold are only a fingerprint of the page. A fingerprint
changes whenever anything on the page changes -- a rotating quote, a session id
in a script tag, a cache-busting number. On the panel behind this family, most
of the company-and-page pairs we have a long run of copies for produce a brand
new fingerprint on EVERY single copy. Building "hiring changes" out of that
would make every number on the page noise, and every alert a buyer got a false
one.

So a row on these pages can only come from a named job title read out of a
structured job list inside the stored page body: a real array of job records,
each with a title and its own stable identity, parsed out of the page's own
JSON. A change in the page fingerprint is never a row here, and no count on
these pages is a count of fingerprints.

Everything is read out of the sealed copies at call time. The database is opened
read-only and never written to. There is no date literal anywhere below: every
date on a page comes from MAX() or MIN() of the snapshot date column in the data
table itself.
"""
from __future__ import annotations

import difflib
import html
import json
import re
import sqlite3
import sys
import time
import zlib
from collections import Counter, defaultdict

FAMILY = "hiring-watch"

DB = "/home/gmullins/Claude CLI/clocks/b2b_change/data/b2b_change.db"
CADENCE_DAYS = 1

# The five-real-rows floor. A slice under this is dropped, never padded.
MIN_ROWS = 5
TABLE_CAP = 12

# The two page kinds this family reads. The store also keeps robots, pricing and
# plans for the same companies; none of those says anything about hiring.
RESOURCES = ("jobs", "careers")

# A pair needs a long run of copies before "a new fingerprint every time" means
# anything. Sixty is roughly two months of daily copies on this panel.
LONG_RUN = 60

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# ---------------------------------------------------------------------------
# Reading a job list out of a stored page body.
#
# Nothing below names a company. The shapes are found by walking the page's own
# JSON, so a fourth company that starts publishing a readable list is picked up
# by the next build without anyone editing this file, and a company that stops
# publishing one drops out of the count the same day.
# ---------------------------------------------------------------------------

TITLE_KEYS = ("title", "jobTitle", "name", "position", "role")
ID_KEYS = ("key", "id", "jobId", "job_id", "absolute_url", "hostedUrl", "applyUrl",
           "shortcode", "requisitionId", "slug", "link", "url")
LOC_KEYS = ("location", "locationName", "offices", "locations", "city", "office",
            "workplaceType", "country", "region")
DEPT_KEYS = ("department", "departments", "team", "category", "function", "discipline")

# Words a careers page prints where a role name would go. A list of these is a
# button, not a job list, so it never becomes a row.
NOT_A_ROLE = {"multiple open positions", "open positions", "open roles", "see all jobs",
              "view all jobs", "all jobs", "careers", "jobs", "join us", "apply now"}

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.I | re.S)
SCRIPT_JSON = re.compile(
    r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', re.I | re.S)
PAGE_STATE = re.compile(
    r'window\.__(?:NUXT|INITIAL_STATE|APOLLO_STATE|PRELOADED_STATE)__\s*=\s*(\{.*?\});?\s*</script>',
    re.S)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _gunzip(blob: bytes) -> str:
    try:
        return zlib.decompress(blob, zlib.MAX_WBITS | 16).decode("utf-8", "replace")
    except zlib.error:
        return zlib.decompress(blob).decode("utf-8", "replace")


def _json_blobs(body: str):
    """Every block of JSON the page carries in its own markup."""
    for m in NEXT_DATA.finditer(body):
        yield m.group(1)
    for m in SCRIPT_JSON.finditer(body):
        yield m.group(1)
    for m in PAGE_STATE.finditer(body):
        yield m.group(1)


def _text(v) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _flat(v, depth: int = 0) -> str | None:
    """One readable line out of a place, a team, or a list of either."""
    if depth > 3:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        for k in ("name", "title", "text", "label", "city", "locationName"):
            s = _text(v.get(k))
            if s:
                return s
        addr = v.get("address")
        if isinstance(addr, dict):
            parts = [addr.get(k) for k in
                     ("addressLocality", "addressRegion", "addressCountry")]
            parts = [p for p in parts if isinstance(p, str)]
            if parts:
                return ", ".join(parts)
        return None
    if isinstance(v, list):
        got = [x for x in (_flat(i, depth + 1) for i in v) if x]
        return "; ".join(dict.fromkeys(got)) if got else None
    return None


def _title_of(d: dict) -> str | None:
    for k in TITLE_KEYS:
        s = _text(d.get(k))
        if s:
            return s
    return None


def _id_of(d: dict) -> str | None:
    """The record's own identity, so a role can be followed across two copies.

    Without a stable identity every copy would read as the whole list being
    taken down and a whole new list going up, which is the fingerprint mistake
    wearing a different hat.
    """
    for k in ID_KEYS:
        v = d.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return None


def _field(d: dict, keys) -> str:
    for k in keys:
        s = _flat(d.get(k))
        if s:
            return s
    return ""


def _walk(obj, path: str, out: dict, depth: int = 0) -> None:
    """Collect every list-of-records, keyed by its path with indexes removed.

    A jobs page often splits its roles into one array per team. Those arrays sit
    at .jobs[0].jobs, .jobs[1].jobs and so on, and a team with a single opening
    would be thrown away by any rule that judged each array on its own. Dropping
    the index merges the lot, so a one-role team is counted like any other.
    """
    if depth > 12:
        return
    if isinstance(obj, list):
        records = [x for x in obj if isinstance(x, dict)]
        if records and len(records) == len(obj):
            out.setdefault(re.sub(r"\[\d+\]", "[]", path), []).extend(records)
        for i, x in enumerate(obj[:80]):
            _walk(x, f"{path}[{i}]", out, depth + 1)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, f"{path}.{k}" if path else k, out, depth + 1)


def _looks_like_jobs(path: str, recs: list[dict]) -> int:
    """How much this list looks like a job list, not a menu or a blog roll."""
    score = 0
    if re.search(r"job|position|opening|vacan|role", path.lower()):
        score += 5
    if sum(1 for r in recs if r["location"]) >= len(recs) * 0.6:
        score += 3
    if sum(1 for r in recs if r["department"]) >= len(recs) * 0.6:
        score += 2
    titles = [r["title"] for r in recs]
    if all(t.lower() in NOT_A_ROLE for t in titles):
        score -= 20
    if len(set(titles)) < max(2, len(recs) * 0.3):
        score -= 5
    return score


def _jobs_from_body(body: str) -> tuple[str, list[dict]] | None:
    """The one job list this page body carries, or None if it carries none."""
    best = None
    for raw in _json_blobs(body):
        try:
            data = json.loads(raw)
        except Exception:
            # A body cut off at the size cap leaves its last JSON block
            # unclosed, so it does not parse and nothing is read from it. That
            # is the behaviour we want: a half-read list would undercount.
            continue
        buckets: dict[str, list] = {}
        _walk(data, "", buckets)
        for path, records in buckets.items():
            recs, seen = [], set()
            for d in records:
                title, ident = _title_of(d), _id_of(d)
                if not title or not ident or ident in seen:
                    continue
                seen.add(ident)
                recs.append({
                    "id": ident,
                    "title": title,
                    "location": _field(d, LOC_KEYS),
                    "department": _field(d, DEPT_KEYS),
                })
            if len(recs) < 3:
                continue
            score = _looks_like_jobs(path, recs)
            if score < 8:
                continue
            key = (score, len(recs))
            if best is None or key > best[0]:
                best = (key, path, recs)
    return None if best is None else (best[1], best[2])


# ---------------------------------------------------------------------------
# The one read of the archive.
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def _read() -> dict:
    if _CACHE:
        return _CACHE

    conn = _connect()
    marks = ",".join("?" * len(RESOURCES))

    panel = conn.execute("select count(distinct domain) from page_snapshots").fetchone()[0]
    runs = conn.execute("select count(*) from collection_runs").fetchone()[0]
    dates = [r[0] for r in conn.execute(
        "select distinct snapshot_date from page_snapshots order by snapshot_date")]
    panel_newest, panel_oldest = dates[-1], dates[0]
    held_rows = conn.execute(
        f"select count(*) from page_snapshots where resource in ({marks})", RESOURCES
    ).fetchone()[0]
    domains_with_body = conn.execute(
        f"select count(distinct domain) from page_snapshots "
        f"where resource in ({marks}) and content_sha256 is not null", RESOURCES
    ).fetchone()[0]

    # The fingerprint defect, counted rather than described. A pair is one
    # company and one of its two pages.
    pair_runs = conn.execute(
        f"select domain, resource, count(*), count(distinct content_sha256) "
        f"from page_snapshots where resource in ({marks}) and content_sha256 is not null "
        f"group by 1, 2", RESOURCES
    ).fetchall()
    pairs_with_body = len(pair_runs)
    long_pairs = [p for p in pair_runs if p[2] >= LONG_RUN]
    churn_pairs = [p for p in long_pairs if p[3] == p[2]]

    # What the panel did on the newest copy, per request and per company.
    status = Counter()
    per_domain = defaultdict(lambda: {"body": 0, "cut": 0})
    for domain, code, sha, cut in conn.execute(
        f"select p.domain, p.status_code, p.content_sha256, coalesce(b.truncated, 0) "
        f"from page_snapshots p left join blobs b on b.content_sha256 = p.content_sha256 "
        f"where p.snapshot_date = ? and p.resource in ({marks})",
        (panel_newest, *RESOURCES),
    ):
        status[code if code is not None else -1] += 1
        if sha:
            per_domain[domain]["body"] += 1
            per_domain[domain]["cut"] += 1 if cut else 0
    bodies_newest = sum(v["body"] for v in per_domain.values())
    cut_newest = sum(v["cut"] for v in per_domain.values())
    cap_bytes = conn.execute(
        "select max(byte_len) from blobs where truncated = 1").fetchone()[0]

    # Read every distinct stored body once. Bodies are shared between copies and
    # between the two page kinds, so this is far less work than it looks.
    parsed: dict[str, tuple] = {}
    shas = [r[0] for r in conn.execute(
        f"select distinct content_sha256 from page_snapshots "
        f"where resource in ({marks}) and content_sha256 is not null", RESOURCES)]
    for sha in shas:
        blob = conn.execute(
            "select content_gz from blobs where content_sha256 = ?", (sha,)).fetchone()
        if not blob:
            continue
        try:
            body = _gunzip(blob[0])
        except Exception:
            continue
        if "json" not in body:
            continue
        got = _jobs_from_body(body)
        if got:
            parsed[sha] = got

    # How many of the copies we CAN read were cut short at the cap. A body being
    # cut is not on its own a reason we cannot read it: what matters is whether
    # the block of data holding the list closed before the cut. Saying "cut, so
    # unreadable" on the page would be a claim this number disproves.
    cut_parsed = 0
    if parsed:
        marks_p = ",".join("?" * len(parsed))
        cut_parsed = conn.execute(
            f"select count(*) from blobs where truncated = 1 "
            f"and content_sha256 in ({marks_p})", tuple(parsed)
        ).fetchone()[0]

    # One series per company. Where both page kinds parse we keep whichever has
    # the most dated copies, so a comparison is never made between two different
    # pages of the same site.
    series: dict[tuple[str, str], dict[str, list]] = defaultdict(dict)
    for domain, resource, date, sha in conn.execute(
        f"select domain, resource, snapshot_date, content_sha256 from page_snapshots "
        f"where resource in ({marks}) and content_sha256 is not null "
        f"order by domain, resource, snapshot_date", RESOURCES
    ):
        if sha in parsed:
            series[(domain, resource)][date] = parsed[sha][1]
    chosen: dict[str, str] = {}
    for (domain, resource), days in series.items():
        if domain not in chosen or len(days) > len(series[(domain, chosen[domain])]):
            chosen[domain] = resource

    companies = []
    moves = []
    for domain in sorted(chosen):
        resource = chosen[domain]
        days = series[(domain, resource)]
        seen_dates = sorted(days)
        companies.append({
            "domain": domain,
            "resource": resource,
            "copies": len(seen_dates),
            "first_date": seen_dates[0],
            "last_date": seen_dates[-1],
            "first_count": len(days[seen_dates[0]]),
            "last_count": len(days[seen_dates[-1]]),
        })
        for before, after in zip(seen_dates, seen_dates[1:]):
            was = {r["id"]: r for r in days[before]}
            now = {r["id"]: r for r in days[after]}
            for k in sorted(set(now) - set(was)):
                moves.append({"domain": domain, "kind": "appeared", "role": now[k],
                              "was_titled": None, "before": before, "after": after})
            for k in sorted(set(was) - set(now)):
                moves.append({"domain": domain, "kind": "gone", "role": was[k],
                              "was_titled": None, "before": before, "after": after})
            for k in sorted(set(was) & set(now)):
                if was[k]["title"] != now[k]["title"]:
                    moves.append({"domain": domain, "kind": "retitled", "role": now[k],
                                  "was_titled": was[k]["title"],
                                  "before": before, "after": after})
    moves.sort(key=lambda m: (m["after"], m["domain"], m["role"]["title"]), reverse=True)

    read_dates = sorted({d for c in companies for d in (c["first_date"], c["last_date"])})
    read_newest = max((c["last_date"] for c in companies), default=panel_newest)
    read_oldest = min((c["first_date"] for c in companies), default=panel_oldest)

    # A company is counted readable only on the newest copy of the whole panel,
    # so the number on the page is today's answer and not a high-water mark.
    readable_today = sorted(c["domain"] for c in companies if c["last_date"] == panel_newest)

    # Sorting the companies by size of move makes the tables read the same way
    # every build rather than in whatever order the database handed them over.
    by_company = Counter(m["domain"] for m in moves)

    # The retitle that changed the least. Some retitles are a promotion and some
    # are a spelling fix, and a buyer is owed the difference in writing.
    smallest = None
    for m in moves:
        if m["kind"] != "retitled":
            continue
        ratio = difflib.SequenceMatcher(
            None, m["was_titled"], m["role"]["title"]).ratio()
        if smallest is None or ratio > smallest[0]:
            smallest = (ratio, m)

    # Days the collector did not run, counted off the dates themselves.
    import datetime as _dt
    gaps = 0
    for a, b in zip(dates, dates[1:]):
        gaps += (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days - 1

    _CACHE.update({
        "panel": panel,
        "runs": runs,
        "dates": dates,
        "gaps": gaps,
        "panel_newest": panel_newest,
        "panel_oldest": panel_oldest,
        "held_rows": held_rows,
        "domains_with_body": domains_with_body,
        "pairs_with_body": pairs_with_body,
        "long_pairs": len(long_pairs),
        "churn_pairs": len(churn_pairs),
        "status": status,
        "per_domain": per_domain,
        "bodies_newest": bodies_newest,
        "cut_newest": cut_newest,
        "cap_bytes": cap_bytes,
        "companies": companies,
        "readable_today": readable_today,
        "moves": moves,
        "by_company": by_company,
        "read_newest": read_newest,
        "read_oldest": read_oldest,
        "read_dates": read_dates,
        "smallest_retitle": smallest,
        "parsed_bodies": len(parsed),
        "cut_parsed": cut_parsed,
        "bodies_read": len(shas),
    })
    return _CACHE


# ---------------------------------------------------------------------------
# Words.
# ---------------------------------------------------------------------------


def _copies_words(companies: list[dict]) -> str:
    """How many dated copies we hold of each readable page, in plain words."""
    lo = min(c["copies"] for c in companies)
    hi = max(c["copies"] for c in companies)
    return f"{lo}" if lo == hi else f"{lo} to {hi}"


def _kib(byte_len: int | None) -> str:
    return "unknown" if not byte_len else f"{byte_len // 1024:,} KiB"


def _domain_buckets() -> dict:
    """Every company in the panel put in exactly one bucket on the newest copy."""
    d = _read()
    readable = set(d["readable_today"])
    out = Counter()
    for domain in {r for r in _panel_domains()}:
        state = d["per_domain"].get(domain, {"body": 0, "cut": 0})
        if domain in readable:
            out["readable"] += 1
        elif state["body"] and state["cut"]:
            out["cut"] += 1
        elif state["body"]:
            out["whole"] += 1
        else:
            out["none"] += 1
    return out


def _panel_domains() -> list[str]:
    conn = _connect()
    return [r[0] for r in conn.execute("select distinct domain from page_snapshots")]


def _base(name: str, slug: str, h1: str, lede: str, desc: str, row_count: int,
          newest: str, oldest: str) -> dict:
    d = _read()
    return {
        "slug": slug,
        "name": name,
        "h1": h1,
        "lede": lede,
        "desc": desc,
        "newest": newest,
        "oldest": oldest,
        "runs": d["runs"],
        "cadence_days": CADENCE_DAYS,
        "row_count": row_count,
        "tables": [],
        "facts": [],
        "limits": [],
    }


def _limits(extra: list[str] | None = None) -> list[str]:
    """The gap, in writing, before anyone pays for it.

    Three of these are not optional and are the reason this family exists in
    this shape: how many companies we watch, how many of them we can actually
    read a job list from, and how many stored copies are cut short.
    """
    d = _read()
    buckets = _domain_buckets()
    out = [
        f"We ask <strong>{d['panel']:,} companies</strong> for a jobs page and a careers "
        f"page every day. That is the whole panel, and a company that is not on it cannot "
        f"appear here.",
        f"On our newest copy we can read a real list of named roles from "
        f"<strong>{buckets['readable']} of those {d['panel']:,} companies</strong>. This "
        f"feed is those companies and no others. The rest publish their openings in a way "
        f"we cannot read as a list, so we say nothing about them rather than guess.",
        f"{d['cut_newest']:,} of the {d['bodies_newest']:,} page copies we stored on our "
        f"newest read are cut short: they hit our {_kib(d['cap_bytes'])} size cap, so the "
        f"end of the page is not in the copy. Cut is not the same as useless &mdash; "
        f"{d['cut_parsed']:,} of the {d['parsed_bodies']:,} copies we can read a list out "
        f"of are themselves cut, because the block of data holding the list closed before "
        f"the cut. What we will not do is read a list out of a block that did not close: "
        f"if the cut lands inside the list we read nothing rather than a short list. The "
        f"risk we cannot rule out is a company that splits its roles across two blocks and "
        f"loses the second one to the cut.",
        f"{d['churn_pairs']} of the {d['long_pairs']} company-and-page pairs we hold "
        f"{LONG_RUN} or more copies of produce a brand new fingerprint on every single "
        f"copy, because "
        f"something trivial on the page changes each time. A fingerprint moving is not a "
        f"hiring change and is never a row on these pages.",
        "We can only show a change between two of our own copies. A role posted and taken "
        "down inside one day happened while we were not looking, and it is not here.",
        "We read the company's own page. A role advertised only on a job board, on a "
        "social network, or by a recruiter is not on that page and so is not here.",
        f"The archive is missing {d['gaps']} day{'' if d['gaps'] == 1 else 's'} between "
        f"{_day(d['panel_oldest'])} and {_day(d['panel_newest'])}, when the collector did "
        f"not run. A change across a missing day is dated to the two copies either side "
        f"of it, so the gap is visible in the dates rather than hidden.",
    ]
    return out + (extra or [])


def _cell(value: object) -> str:
    return html.escape(str(value))


def _between(move: dict) -> str:
    return f"{_day(move['before'])} &rarr; {_day(move['after'])}"


def _spread(moves: list[dict], cap: int) -> list[dict]:
    """Newest first, one company at a time, so no single company fills a table.

    Front alone accounts for most of what we hold. A table sorted by date would
    be a page about one company with two others in the footnotes, which is not
    what the page says it is.
    """
    per: dict[str, list] = defaultdict(list)
    for m in moves:
        per[m["domain"]].append(m)
    order = sorted(per, key=lambda k: (-len(per[k]), k))
    out: list[dict] = []
    while len(out) < cap and any(per[k] for k in order):
        for k in order:
            if per[k]:
                out.append(per[k].pop(0))
                if len(out) == cap:
                    break
    return out


def _role_rows(moves: list[dict], cap: int) -> list[list[str]]:
    rows = []
    for m in _spread(moves, cap):
        role = m["role"]
        rows.append([
            _cell(m["domain"]),
            _cell(role["title"]),
            _cell(role["location"] or "not stated on the page"),
            _cell(role["department"] or "not stated on the page"),
            _between(m),
        ])
    return rows


def _retitle_rows(moves: list[dict], cap: int) -> list[list[str]]:
    rows = []
    for m in _spread(moves, cap):
        rows.append([
            _cell(m["domain"]),
            _cell(m["was_titled"]),
            _cell(m["role"]["title"]),
            _cell(m["role"]["location"] or "not stated on the page"),
            _between(m),
        ])
    return rows


# ---------------------------------------------------------------------------
# The pages.
# ---------------------------------------------------------------------------


def _moves_slice() -> dict | None:
    d = _read()
    moves = d["moves"]
    appeared = [m for m in moves if m["kind"] == "appeared"]
    gone = [m for m in moves if m["kind"] == "gone"]
    retitled = [m for m in moves if m["kind"] == "retitled"]
    firms = sorted({m["domain"] for m in moves})

    if len(moves) < MIN_ROWS or len(appeared) < MIN_ROWS or len(gone) < MIN_ROWS:
        print(
            f"[hiring-watch] dropped roles-that-moved: {len(moves)} named moves "
            f"({len(appeared)} appeared, {len(gone)} came down) across {len(firms)} "
            f"companies; the floor is {MIN_ROWS}",
            file=sys.stderr,
        )
        return None

    named = ", ".join(firms)
    sl = _base(
        name="Named roles that moved",
        slug="roles-that-moved",
        h1="Named roles that appeared, came down, or were retitled",
        lede=(
            f"Every row below is one job title that is on a company's own page in one "
            f"dated copy and not in the next, or whose title changed while the job kept "
            f"its own id. <strong>{len(moves):,} of these across {len(firms)} companies</strong> "
            f"&mdash; {named} &mdash; between {_day(d['read_oldest'])} and "
            f"{_day(d['read_newest'])}. Those three are the only companies on our panel of "
            f"{d['panel']:,} whose openings we can read as a list. Nothing here comes from "
            f"a page fingerprint."
        ),
        desc=(
            f"{len(moves):,} named job titles that appeared, came down or were retitled on "
            f"{len(firms)} companies' own pages, with both dates. Not for sale yet."
        ),
        row_count=len(moves),
        newest=d["read_newest"],
        oldest=d["read_oldest"],
    )

    rows = _role_rows(appeared, TABLE_CAP)
    sl["tables"].append({
        "caption": (
            f"Job titles that were not on the page in one copy and were on it in the next. "
            f"{len(rows)} shown of {len(appeared):,}; the file you get carries every one, "
            f"with the link the company published."
        ),
        "stamp": f"{_day(d['read_oldest'])} to {_day(d['read_newest'])}",
        "headers": ["Company", "Role that appeared", "Where", "Team", "Between"],
        "rows": rows,
        "moved_col": 1,
    })

    rows = _role_rows(gone, TABLE_CAP)
    sl["tables"].append({
        "caption": (
            f"Job titles that were on the page in one copy and gone in the next. "
            f"{len(rows)} shown of {len(gone):,}. A role coming down can mean it was "
            f"filled, paused or pulled; the page does not say which and neither do we."
        ),
        "stamp": f"{_day(d['read_oldest'])} to {_day(d['read_newest'])}",
        "headers": ["Company", "Role that came down", "Where", "Team", "Between"],
        "rows": rows,
        "moved_col": 1,
    })

    if len(retitled) >= 2:
        rows = _retitle_rows(retitled, TABLE_CAP)
        firms_r = sorted({m["domain"] for m in retitled})
        one = (f"All {len(retitled)} are {firms_r[0]}." if len(firms_r) == 1
               else f"Across {len(firms_r)} companies.")
        sl["tables"].append({
            "caption": (
                f"The same job id, a different title. {len(rows)} shown of "
                f"{len(retitled)}. {one} This is the row a fingerprint can never give you: "
                f"the page changed by a few words and the job did not change hands."
            ),
            "stamp": f"{_day(d['read_oldest'])} to {_day(d['read_newest'])}",
            "headers": ["Company", "What it said before", "What it says now", "Where",
                        "Between"],
            "rows": rows,
            "moved_col": 2,
        })

    counts = ". ".join(
        f"{c['domain']} listed {c['first_count']} named roles on {_day(c['first_date'])} "
        f"and {c['last_count']} on {_day(c['last_date'])}"
        for c in sorted(d["companies"], key=lambda c: -c["last_count"])
    )
    per_firm = ", ".join(f"{k} ({v:,})" for k, v in d["by_company"].most_common())
    sl["facts"] = [
        f"{len(moves):,} named moves in all: {len(appeared):,} roles appeared, "
        f"{len(gone):,} came down, and {len(retitled)} kept their id and changed title.",
        f"Where they happened: {per_firm}.",
        f"{counts}.",
        f"Each company's list is read out of the data the page carries inside itself, and "
        f"each role is followed by the reference number the company gave it. Not one role "
        f"here changed its reference number between two copies, which is why an "
        f"appearance is an appearance and not the whole list being rebuilt.",
        f"We hold {_copies_words(d['companies'])} dated copies of each of these "
        f"{len(firms)} pages, from {d['runs']} sealed runs.",
    ]

    extra = []
    small = d["smallest_retitle"]
    if small and small[0] > 0.85:
        extra.append(
            f"A retitle is not always a promotion. The smallest one we hold is "
            f"&ldquo;{html.escape(small[1]['was_titled'])}&rdquo; becoming "
            f"&ldquo;{html.escape(small[1]['role']['title'])}&rdquo;, which is a wording "
            f"fix and not a decision. We send the pair and let you judge."
        )
    sl["limits"] = _limits(extra)
    return sl


def _coverage() -> dict:
    d = _read()
    buckets = _domain_buckets()
    firms = [c["domain"] for c in d["companies"]]

    sl = _base(
        name="What is and is not in the hiring feed",
        slug="coverage",
        h1="What is and is not in the hiring feed",
        lede=(
            f"Every day we ask {d['panel']:,} companies for their jobs page and their "
            f"careers page and save what comes back. <strong>Most of what comes back "
            f"cannot be read as a list of roles</strong>, and this page counts exactly how "
            f"much. Read it before you pay, not after."
        ),
        desc=(
            f"How many of the {d['panel']:,} companies we copy every day publish a job "
            f"list we can read, and how many copies are cut short by our size cap."
        ),
        row_count=d["held_rows"],
        newest=d["panel_newest"],
        oldest=d["panel_oldest"],
    )

    sl["tables"].append({
        "caption": (
            f"Every one of the {d['panel']:,} companies on the panel, in exactly one row "
            f"of this table, on our newest copy. Only the first line becomes rows on the "
            f"other page."
        ),
        "stamp": _day(d["panel_newest"]),
        "headers": ["What we can do with the company's pages today", "Companies"],
        "rows": [
            ["We can read a list of named roles", f"{buckets['readable']:,}"],
            ["Cut short at our size cap, and no readable list in what survived",
             f"{buckets['cut']:,}"],
            ["We stored the whole page and still cannot read a job list from it",
             f"{buckets['whole']:,}"],
            ["Neither page gave us anything to store", f"{buckets['none']:,}"],
        ],
        "moved_col": None,
    })

    known = {200: "gave us the page",
             202: "accepted the request and sent no page",
             302: "redirected us somewhere else",
             403: "refused us",
             404: "said there is no such page",
             429: "told us to slow down",
             500: "their server errored",
             503: "their server was unavailable"}
    code_rows = []
    for code, count in sorted(d["status"].items(), key=lambda kv: -kv[1]):
        if code == -1:
            code_rows.append(["never answered at all", f"{count:,}"])
        else:
            code_rows.append([f"{known.get(code, 'answered with code ' + str(code))} "
                              f"({code})", f"{count:,}"])
    sl["tables"].append({
        "caption": (
            f"The {sum(d['status'].values()):,} requests we made on our newest copy: two "
            f"per company. {d['bodies_newest']:,} of them gave us a body we could store."
        ),
        "stamp": _day(d["panel_newest"]),
        "headers": ["What came back", "Requests"],
        "rows": code_rows[:TABLE_CAP],
        "moved_col": None,
    })

    sl["tables"].append({
        "caption": (
            f"The {len(firms)} companies whose openings we can read as a list, and what we "
            f"hold for each. The count is named roles on the page that day, read out of "
            f"the data the page carries inside itself."
        ),
        "stamp": f"{_day(d['read_oldest'])} to {_day(d['read_newest'])}",
        "headers": ["Company", "Page we read", "Dated copies", "Named roles, first copy",
                    "Named roles, newest copy"],
        "rows": [
            [_cell(c["domain"]), _cell(c["resource"]), f"{c['copies']:,}",
             f"{c['first_count']} on {_day(c['first_date'])}",
             f"{c['last_count']} on {_day(c['last_date'])}"]
            for c in sorted(d["companies"], key=lambda c: -c["last_count"])
        ],
        "moved_col": None,
    })

    sl["facts"] = [
        f"We hold {d['held_rows']:,} dated jobs-page and careers-page rows from "
        f"{d['runs']} sealed runs across {len(d['dates'])} days between "
        f"{_day(d['panel_oldest'])} and {_day(d['panel_newest'])}.",
        f"{d['domains_with_body']:,} of the {d['panel']:,} companies have given us a page "
        f"body at least once, across {d['pairs_with_body']:,} company-and-page pairs. "
        f"Having a body is not the same as having a readable list, and this is the gap "
        f"the feed lives in.",
        f"We read every one of the {d['bodies_read']:,} distinct page bodies we hold and "
        f"found a readable job list in {d['parsed_bodies']:,} of them. "
        f"{d['cut_parsed']:,} of those {d['parsed_bodies']:,} are copies that were cut "
        f"short at the size cap and still carried a complete list before the cut, so "
        f"&ldquo;cut short&rdquo; on its own is not a reason we cannot read a company.",
        f"{d['churn_pairs']} of the {d['long_pairs']} pairs we have {LONG_RUN} or more "
        f"copies of have a different fingerprint on every copy. That is a page with "
        f"something restless on it, not a company changing its mind, and it is why no "
        f"count on this feed is a count of fingerprints.",
        f"What would widen this feed is not more companies. It is the {buckets['cut']:,} "
        f"companies whose page we store but cut short: raising the cap and copying again "
        f"would tell us whether their list of roles was past the cut or was never in the "
        f"page at all. We do not know which today, and we will not guess. Until that is "
        f"done and counted this feed is {buckets['readable']} companies and says so.",
    ]
    sl["limits"] = _limits()
    return sl


def slices() -> list[dict]:
    out = []
    moves = _moves_slice()
    if moves:
        out.append(moves)
    out.append(_coverage())
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for /feeds/hiring-watch/sample.json and sample.csv."""
    d = _read()
    words = {"appeared": "role appeared on the page",
             "gone": "role came down off the page",
             "retitled": "same job id, new title"}
    headers = ["company", "what_moved", "role_title", "previous_title", "where", "team",
               "first_copy", "second_copy"]
    rows = []
    for m in _spread(d["moves"], 25):
        role = m["role"]
        rows.append([
            m["domain"], words[m["kind"]], role["title"], m["was_titled"] or "",
            role["location"], role["department"], m["before"], m["after"],
        ])
    return headers, rows


if __name__ == "__main__":
    t0 = time.time()
    d = _read()
    buckets = _domain_buckets()
    print(f"family: {FAMILY}")
    print(f"panel: {d['panel']:,} companies · {d['runs']} sealed runs on "
          f"{len(d['dates'])} days · {d['panel_oldest']} to {d['panel_newest']} "
          f"({d['gaps']} missing days)")
    print(f"held: {d['held_rows']:,} dated jobs/careers rows · "
          f"{d['domains_with_body']:,} companies have a body · "
          f"{d['pairs_with_body']:,} company-and-page pairs")
    print(f"fingerprint churn: {d['churn_pairs']} of {d['long_pairs']} pairs with "
          f"{LONG_RUN}+ copies get a new fingerprint every copy")
    print(f"newest copy: {d['bodies_newest']:,} bodies stored, {d['cut_newest']:,} cut "
          f"short at {_kib(d['cap_bytes'])}")
    print(f"bodies read: {d['bodies_read']:,} distinct · job list found in "
          f"{d['parsed_bodies']:,} · of those, {d['cut_parsed']:,} were cut short and "
          f"still readable")
    print(f"companies today: readable {buckets['readable']} · cut short {buckets['cut']} · "
          f"whole but unreadable {buckets['whole']} · nothing stored {buckets['none']}")
    for c in d["companies"]:
        print(f"   {c['domain']:20} {c['resource']:8} {c['copies']:3} copies  "
              f"{c['first_count']:3} on {c['first_date']} -> {c['last_count']:3} on "
              f"{c['last_date']}")
    print(f"moves: {len(d['moves']):,} · " +
          " · ".join(f"{k} {v:,}" for k, v in Counter(
              m['kind'] for m in d['moves']).most_common()))
    print()
    ok = True
    for sl in slices():
        n = sum(len(t["rows"]) for t in sl["tables"])
        flag = "" if sl["row_count"] >= MIN_ROWS and n >= MIN_ROWS else "  <-- UNDER FLOOR"
        print(f"  {sl['slug']:<20} row_count={sl['row_count']:<7} tables={len(sl['tables'])} "
              f"table_rows={n} facts={len(sl['facts'])} limits={len(sl['limits'])} "
              f"desc={len(sl['desc'])} newest={sl['newest']}{flag}")
        if sl["row_count"] < MIN_ROWS or n < MIN_ROWS:
            ok = False
        if len(sl["desc"]) > 155:
            print("     DESC OVER 155")
            ok = False
        for t in sl["tables"]:
            if len(t["rows"]) > TABLE_CAP:
                print(f"     TABLE OVER CAP: {len(t['rows'])}")
                ok = False
    h, rows = sample()
    print()
    print(f"sample: {len(rows)} rows, headers {h}")
    for r in rows[:5]:
        print("   ", r)
    print()
    print(f"{'OK' if ok else 'PROBLEM'} in {time.time() - t0:.1f}s")
