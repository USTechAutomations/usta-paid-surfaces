#!/usr/bin/env python3
"""Slices for /feeds/agentic-commerce — machine-buyable storefront files.

What this is, in plain words. A shopping robot that wants to buy something on
your behalf does not read the shop's web page. It looks for a small set of
machine-readable files at fixed addresses on the shop's own domain: an
agent-instructions file at /llms.txt, a checkout manifest at /.well-known/ucp,
and a few draft-standard files that tell a robot where the shop's tool server
lives. When one of those files turns up on a site that did not have it, that
company has just opened a door to an automated buyer. Nobody announces it. The
file is simply there one morning and was not there the night before.

We ask a fixed list of company websites for the same seven files every day and
keep every answer. That is the whole product: the day a door opened, named.

THE ONE RULE THAT MAKES THE NUMBERS REAL. A server answering "200 OK" is not
proof a file exists. Plenty of shops answer 200 for a file they do not have and
hand back their home page or a "page not found" page instead. On the newest read
behind these pages that happened 155 times across 39 companies -- puma.com
answers 200 for all seven files and returns its home page every time. So a file
counts as there only when the body we saved really is that kind of file:

  robots.txt              text with a User-agent line in it
  agent-instructions      text that does not begin with a tag
  checkout manifest       JSON whose top level has a ucp key
  the four agent/tool     JSON with an object at the top level
  files

Anything whose first character is "<" is markup, not a document. That single
check is what separates a real file from a 200 that is not one, and it is why
these pages disagree with a naive count.

404 and 410 mean the file is not there. Everything else -- 403, 429, a timeout,
a 5xx, a site whose robots.txt told us not to fetch -- means we could not tell,
and we say we could not tell rather than calling it gone.

Everything on these pages is read out of the clock database when this module is
called. The only constant is the cadence. The database is opened read-only and
is never written to.
"""
from __future__ import annotations

import collections
import html
import json
import re
import sqlite3
import sys
import zlib

FAMILY = "agentic-commerce"
CADENCE_DAYS = 1

DB_PATH = "/home/gmullins/Claude CLI/clocks/agentic_commerce/data/agentic_commerce.db"

# Twelve rows keeps a page readable. Every caption says how many rows the real
# file carries, so nobody mistakes the sample for the whole thing.
ROW_CAP = 12

# A slice with fewer than five real named rows does not ship. It is dropped and
# the reason is printed, never padded.
MIN_ROWS = 5

MAIL = "operations@ustechautomations.com"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The seven addresses we ask every company for, every day. The short label is
# what a buyer should be able to say out loud; the path is what we actually
# fetch. Nothing outside this list is ever asked for or named.
RESOURCES = {
    "robots": ("robots.txt", "/robots.txt",
               "The access policy every crawler reads first. It is a door sign, not a door."),
    "llms": ("Agent-instructions file", "/llms.txt",
             "A plain text file telling an AI assistant what the shop sells and where to look."),
    "ucp": ("Checkout manifest", "/.well-known/ucp",
            "The one that matters for buying: it names the shop's checkout, its cart and "
            "which payment methods a robot may use."),
    "agent_card": ("Agent card", "/.well-known/agent-card.json",
                   "The current address for an agent-to-agent card."),
    "agent_json": ("Older agent card", "/.well-known/agent.json",
                   "The older address for the same card, kept for anything that has not moved."),
    "mcp": ("Tool-server pointer", "/.well-known/mcp",
            "A draft standard. Points a robot at the shop's tool server."),
    "mcp_server_card": ("Tool-server card", "/.well-known/mcp/server-card.json",
                        "A draft standard. Describes what that tool server can do."),
}

# The six that are about buying or being talked to by a robot. robots.txt is
# excluded on purpose: nearly every site has one, and having one has never meant
# a shop will sell to a machine.
BUY_SIDE = ("ucp", "llms", "agent_card", "agent_json", "mcp", "mcp_server_card")

# Anything opening with a tag is markup. robots.txt and an agent-instructions
# file never begin with "<"; a checkout manifest begins with "{". This one test
# is what catches a 200 that is not a file, including ulta.com, whose
# /llms.txt on the newest read opens with an <esi:debug/> edge-server tag and
# then a whole HTML page.
BOM = b"\xef\xbb\xbf"
UA_LINE = re.compile(rb"(?im)^\s*user-agent\s*:")
TITLE = re.compile(rb"(?is)<title[^>]*>(.*?)</title>")

# How many days of clean, uninterrupted "not there" we require before we will
# print that a file was taken down. Two consecutive reads can both fail on our
# side; three weeks of clean 404s cannot.
DURABLE_DAYS = 14

BANNED = ["get started", "soc 2", "fortune 500", "hipaa", "leverage", "robust",
          "seamless", "comprehensive", "unlock", "empower", "powerful"]


# --------------------------------------------------------------------------
# reading the sealed copies
# --------------------------------------------------------------------------

_CACHE: dict | None = None


def _connect():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _kind(raw: bytes) -> tuple[str, object]:
    """What the saved body actually is. Never what the status code claimed."""
    b = raw.lstrip(BOM).lstrip()
    if not b:
        return "empty", None
    if b[:1] == b"<":
        return "markup", None
    if b[:1] in (b"{", b"["):
        try:
            obj = json.loads(b.decode("utf-8", "replace"))
        except ValueError:
            return "badjson", None
        return "json", obj if isinstance(obj, dict) else None
    return "text", None


def _is_file(resource: str, kind: str, obj, raw: bytes) -> bool:
    """Is this body really the file we asked for?"""
    if kind in ("markup", "empty", "badjson"):
        return False
    if resource == "robots":
        return kind == "text" and bool(UA_LINE.search(raw))
    if resource == "llms":
        return kind == "text"
    if resource == "ucp":
        return kind == "json" and isinstance(obj, dict) and "ucp" in obj
    return kind == "json" and isinstance(obj, dict)


def _state(resource: str, status, sha, bodies) -> str:
    """there / not there / cannot tell, for one company on one day."""
    if status is None:
        return "unknown"                       # transport failure or robots gate
    if 200 <= status < 300:
        if sha is None:
            return "unknown"                   # answered, kept us no body to judge
        kind, obj, raw = bodies[sha]
        return "there" if _is_file(resource, kind, obj, raw) else "gone"
    if status in (404, 410):
        return "gone"
    return "unknown"                           # 403, 429, 5xx, a redirect we could not follow


def _load() -> dict:
    """Read every sealed answer once and work out what moved between them."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    con = _connect()

    bodies: dict[str, tuple[str, object, bytes]] = {}
    for sha, gz in con.execute("select content_sha256, content_gz from blobs"):
        raw = zlib.decompressobj().decompress(gz, 262144)
        kind, obj = _kind(raw)
        bodies[sha] = (kind, obj, raw)

    series: dict[tuple[str, str], list] = collections.defaultdict(list)
    dates: set[str] = set()
    domains: set[str] = set()
    outcome = collections.Counter()
    reads = 0
    for dom, day, res, status, sha, err in con.execute(
        "select domain, snapshot_date, resource, status_code, content_sha256, fetch_error "
        "from page_snapshots order by domain, resource, snapshot_date"
    ):
        st = _state(res, status, sha, bodies)
        series[(dom, res)].append((day, st, status, sha, err))
        dates.add(day)
        domains.add(dom)
        reads += 1
        outcome[_outcome_label(st, status, sha, err, res, bodies)] += 1

    days = sorted(dates)

    # A file appeared when a day we know it was not there is followed by a day
    # we know it was, with nothing in between that we could read. Days we could
    # not read are dropped from the sequence entirely rather than guessed at:
    # peakdesign.com answered 429 on 16 July, and treating that as "not there"
    # would have invented a change on the wrong date.
    appeared: list[dict] = []
    vanished: list[dict] = []
    changed: list[dict] = []
    first_there: dict[tuple[str, str], str] = {}
    known_days: dict[tuple[str, str], int] = {}
    for key, rows in series.items():
        dom, res = key
        known = [r for r in rows if r[1] != "unknown"]
        known_days[key] = len(known)
        for i, (day, st, status, sha, _err) in enumerate(known):
            if st == "there" and key not in first_there:
                first_there[key] = day
            if i == 0:
                continue
            pday, pst, pstatus, psha, _ = known[i - 1]
            if pst == "gone" and st == "there":
                appeared.append({
                    "domain": dom, "resource": res, "from_date": pday,
                    "from_status": pstatus, "was_markup": _was_markup(psha, bodies),
                    "to_date": day, "to_status": status,
                    "heading": _heading(res, sha, bodies),
                })
            elif pst == "there" and st == "gone":
                run = 0
                for r in known[i:]:
                    if r[1] != "gone":
                        break
                    run += 1
                vanished.append({
                    "domain": dom, "resource": res, "last_seen": pday,
                    "first_gone": day, "clean_gone_days": run,
                    "still_gone": run == len(known) - i,
                    "durable": run >= DURABLE_DAYS and run == len(known) - i,
                })
            elif pst == "there" and st == "there" and sha != psha:
                changed.append({"domain": dom, "resource": res,
                                "from_date": pday, "to_date": day})

    _CACHE = {
        "con": con,
        "bodies": bodies,
        "series": series,
        "days": days,
        "domains": sorted(domains),
        "reads": reads,
        "outcome": outcome,
        "appeared": appeared,
        "vanished": vanished,
        "changed": changed,
        "first_there": first_there,
        "known_days": known_days,
        "newest": days[-1],
        "oldest": days[0],
    }
    return _CACHE


def _outcome_label(st, status, sha, err, res, bodies) -> str:
    """One plain phrase per sealed answer, for the coverage tally."""
    if st == "there":
        return "the file was there"
    if err == "robots_disallowed":
        return "their robots.txt told us not to fetch it"
    if err == "robots_unavailable":
        return "we could not read their robots.txt, so we did not fetch"
    if err:
        return "we could not reach the server"
    if status is None:
        return "we could not reach the server"
    if 200 <= status < 300:
        if sha is None:
            return "answered 200 and kept us no body"
        return "answered 200 with something that was not the file"
    if status in (404, 410):
        return "the file was not there"
    return f"the server answered {status}"


def _was_markup(sha, bodies) -> bool:
    return bool(sha) and bodies.get(sha, ("", None, b""))[0] == "markup"


def _heading(res: str, sha, bodies) -> str:
    """The first real line of the file, so a row can be checked by hand."""
    if not sha or sha not in bodies:
        return ""
    kind, obj, raw = bodies[sha]
    if res == "ucp" and kind == "json" and isinstance(obj, dict):
        u = obj.get("ucp")
        if isinstance(u, dict) and u.get("version"):
            return f"version {u['version']}"
        return ""
    if kind != "text":
        return ""
    txt = raw.lstrip(BOM).decode("utf-8", "replace")
    lines = [l.strip() for l in txt.splitlines()[:25]]
    for l in lines:
        if l.startswith("#"):
            return l[:64]
    for l in lines:
        if l and not l.startswith("---"):
            return l[:64]
    return ""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _esc(s) -> str:
    return html.escape(str(s))


_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten", "eleven", "twelve")


def _num(n: int) -> str:
    """Small numbers read better as words in the middle of a sentence."""
    return _WORDS[n] if 0 <= n < len(_WORDS) else f"{n:,}"


def _and_list(names) -> str:
    """a, b and c — so a derived list of companies still reads like a sentence."""
    names = [_esc(n) for n in names]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _label(res: str) -> str:
    return RESOURCES[res][0]


def _path(res: str) -> str:
    return RESOURCES[res][1]


def _today_state(res: str) -> dict[str, str]:
    d = _load()
    newest = d["newest"]
    out = {}
    for (dom, r), rows in d["series"].items():
        if r != res:
            continue
        for day, st, _status, _sha, _err in rows:
            if day == newest:
                out[dom] = st
    return out


def _today_row(res: str) -> dict[str, tuple]:
    d = _load()
    newest = d["newest"]
    out = {}
    for (dom, r), rows in d["series"].items():
        if r != res:
            continue
        for row in rows:
            if row[0] == newest:
                out[dom] = row
    return out


def _serving(res: str) -> list[str]:
    return sorted(dom for dom, st in _today_state(res).items() if st == "there")


def _ever_served(res: str) -> list[str]:
    d = _load()
    return sorted({dom for (dom, r) in d["first_there"] if r == res})


def _reads_for(resources) -> int:
    d = _load()
    return sum(len(rows) for (dom, r), rows in d["series"].items() if r in resources)


def _standing_appearances() -> list[dict]:
    """Appearances whose file is still there on our newest read."""
    d = _load()
    out = []
    for a in d["appeared"]:
        st = _today_state(a["resource"]).get(a["domain"])
        b = dict(a)
        b["still_there"] = st == "there"
        b["today"] = st
        out.append(b)
    return sorted(out, key=lambda a: (a["to_date"], a["domain"], a["resource"]))


# --------------------------------------------------------------------------
# the shared small print
# --------------------------------------------------------------------------

def _panel_limit() -> str:
    d = _load()
    return (
        f"The panel is a fixed list of {len(d['domains'])} company websites, frozen before "
        f"collection started. A company that is not on that list is not missing from this "
        f"feed — we have never asked it anything. Email {MAIL} with the companies you "
        "follow and we will tell you which of them we already hold."
    )


def _not_launch_limit() -> str:
    return (
        "The thing we observed is that a file appeared at a fixed address. That is not the "
        "same as a company launching automated selling, and we never write it as if it "
        "were. We cannot tell you whether anything behind the file works, whether a robot "
        "can really complete a purchase, or whether the company meant to publish it."
    )


def _absent_cell(row) -> str:
    """One cell for a file we hold as absent. Never a bare status code.

    A 404 or a 410 is the server saying the file is not there. A 200 whose body
    is not the file is a different thing: the server answered, and what it sent
    was not the file we asked for. Printing "answered 200" under a caption that
    says the file is absent invites the reader to check the code and call us
    wrong, so the cell says which of the two it was.
    """
    status = row[2]
    if status in (404, 410):
        return f"answered {status}"
    if status is not None and 200 <= status < 300:
        return f"answered {status}, not the file"
    if status is None:
        return "no answer we could use"
    return f"answered {status}"


def _two_hundred_limit() -> str:
    d = _load()
    lies = _lies_today()
    return (
        f"A server answering 200 is not proof of a file. We count a file as there only when "
        f"the body we saved really is that kind of file. On {_day(d['newest'])} that test threw "
        f"out {sum(len(v) for v in lies.values())} answers of 200 across {len(lies)} companies "
        "whose servers handed back a web page instead."
    )


def _unknown_limit() -> str:
    d = _load()
    blocked = _blocked_today()
    return (
        f"On {_day(d['newest'])} we could not read one or more files at {len(blocked)} of the "
        f"{len(d['domains'])} companies, because the server refused us, rate-limited us, timed "
        "out, or its robots.txt told us not to fetch. Those are shown as cannot tell. We never "
        "count a refusal as the file being gone."
    )


def _start_limit() -> str:
    d = _load()
    return (
        f"Our first read is {_day(d['oldest'])}. A file already up that morning shows a first "
        f"seen date of {_day(d['oldest'])}, and we cannot tell you how long it had been there "
        "before we started looking."
    )


def _gap_limit() -> str:
    d = _load()
    gaps = _missing_days()
    if not gaps:
        return ("We hold a sealed read for every day in the window, with no gaps.")
    return (
        f"There are {len(gaps)} days in the window with no read at all: "
        + ", ".join(_day(g) for g in gaps)
        + ". Where a file appeared across one of those gaps we give the two dates we actually "
        "hold, never a guessed one in between."
    )


def _missing_days() -> list[str]:
    import datetime as _dt
    d = _load()
    have = set(d["days"])
    a = _dt.date.fromisoformat(d["oldest"])
    b = _dt.date.fromisoformat(d["newest"])
    out = []
    n = (b - a).days
    for i in range(n + 1):
        day = (a + _dt.timedelta(days=i)).isoformat()
        if day not in have:
            out.append(day)
    return out


def _lies_today() -> dict[str, list[tuple[str, str, int]]]:
    """Company -> the files whose 200 was not a file, on the newest read."""
    d = _load()
    newest = d["newest"]
    out = collections.defaultdict(list)
    for (dom, res), rows in d["series"].items():
        for day, st, status, sha, _err in rows:
            if day != newest or status is None or not (200 <= status < 300) or not sha:
                continue
            kind, obj, raw = d["bodies"][sha]
            if _is_file(res, kind, obj, raw):
                continue
            m = TITLE.search(raw[:262144])
            title = m.group(1).decode("utf-8", "replace").strip() if m else ""
            title = re.sub(r"\s+", " ", html.unescape(title))[:58]
            out[dom].append((res, title, len(raw)))
    return out


def _blocked_today() -> dict[str, collections.Counter]:
    """Company -> why we could not read it, counted over the seven files today."""
    d = _load()
    newest = d["newest"]
    out = collections.defaultdict(collections.Counter)
    for (dom, res), rows in d["series"].items():
        for day, st, status, sha, err in rows:
            if day != newest or st != "unknown":
                continue
            if err == "robots_disallowed":
                out[dom]["their robots.txt told us not to fetch"] += 1
            elif err == "robots_unavailable":
                out[dom]["we could not read their robots.txt"] += 1
            elif err:
                out[dom][err.replace("_", " ")] += 1
            elif status is None:
                out[dom]["no answer"] += 1
            else:
                out[dom][f"answered {status}"] += 1
    return out


# --------------------------------------------------------------------------
# tables that more than one page uses
# --------------------------------------------------------------------------

def _file_roster_table() -> dict:
    d = _load()
    rows = []
    for res in RESOURCES:
        label, path, _ = RESOURCES[res]
        today = len(_serving(res))
        ever = _ever_served(res)
        firsts = [a for a in d["appeared"] if a["resource"] == res]
        when = min((a["to_date"] for a in firsts), default=None)
        rows.append([
            _esc(label),
            f"<code>{_esc(path)}</code>",
            f"{today:,}" if today else "none",
            f"{len(ever):,}" if ever else "none",
            _day(when) if when else "no company added it while we watched",
        ])
    return {
        "caption": (f"Every file we ask for, and how many of the {len(d['domains'])} companies "
                    f"served it on {_day(d['newest'])}"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["File", "Where we ask for it", "Companies serving it on our newest read",
                    "Companies that served it on any day we could read them",
                    "First day one appeared"],
        "rows": rows,
        "moved_col": 4,
    }


def _appeared_table(resource: str | None = None) -> dict | None:
    d = _load()
    rows = []
    for a in _standing_appearances():
        if resource and a["resource"] != resource:
            continue
        before = ("answered 200 with a web page" if a["was_markup"]
                  else f"answered {a['from_status']}")
        rows.append([
            _esc(a["domain"]),
            _esc(_label(a["resource"])),
            _day(a["from_date"]),
            _day(a["to_date"]),
            _esc(before),
            _esc(a["heading"]) or "—",
            "still there" if a["still_there"] else "taken down again",
        ])
    if not rows:
        return None
    what = ("an " + _label(resource).lower() if resource
            else "one of the seven files")
    return {
        "caption": (f"Every time {what} appeared on a company that did not have it, "
                    f"{_day(d['oldest'])} to {_day(d['newest'])}"),
        "stamp": f"{_day(d['oldest'])} to {_day(d['newest'])}",
        "headers": ["Company", "File", "Last day we saw it absent", "First day we saw it there",
                    "What the server said the day before", "First line of the file",
                    f"On {_day(d['newest'])}"],
        "rows": rows,
        "moved_col": 3,
    }


# --------------------------------------------------------------------------
# the pages
# --------------------------------------------------------------------------

def _doors_slice() -> dict | None:
    d = _load()
    tab = _appeared_table()
    if tab is None:
        return None
    standing = [a for a in _standing_appearances() if a["still_there"]]
    firms = sorted({a["domain"] for a in standing})
    all_firms = sorted({a["domain"] for a in _standing_appearances()})
    dead = [a for a in _standing_appearances() if not a["still_there"]]

    facts = [
        f"{len(_standing_appearances())} files appeared on {len(all_firms)} companies between "
        f"{_day(d['oldest'])} and {_day(d['newest'])}. {len(standing)} of them, on "
        f"{len(firms)} companies, were still there on our newest read.",
        f"Every one of those {len(_standing_appearances())} rows is a file that was provably "
        f"not there on a named day and provably there on a named day, out of "
        f"{d['reads']:,} sealed reads of {len(d['domains'])} company websites.",
    ]
    liars = [a for a in _standing_appearances() if a["was_markup"]]
    if liars:
        facts.append(
            f"{len(liars)} of them were never a 404. "
            + _and_list([a["domain"] for a in liars])
            + f" answered 200 for <code>{_path(liars[0]['resource'])}</code> the day before as "
            "well, with a web page. Only the body tells you which day the real file went up."
        )
    if dead:
        a = dead[0]
        v = [x for x in d["vanished"] if x["domain"] == a["domain"]
             and x["resource"] == a["resource"]]
        if v:
            v = v[0]
            facts.append(
                f"One went the other way. {a['domain']} put a {_label(a['resource']).lower()} up "
                f"on {_day(a['to_date'])}, and it was gone again on {_day(v['first_gone'])}. It "
                f"has answered 404 on every one of the {v['clean_gone_days']} days we have read "
                "it since, so this is a file that was taken down, not a read that failed."
            )
    facts.append(
        f"Nobody on the panel served an agent card or either tool-server file on any day. "
        f"That absence is itself a reading: {len(d['domains'])} company websites asked "
        f"{len(d['days'])} times each, and the count is still zero."
    )

    limits = [
        _not_launch_limit(),
        _two_hundred_limit(),
        _unknown_limit(),
        _panel_limit(),
        _start_limit(),
        _gap_limit(),
        "We do not report a file as taken down until it has been cleanly absent on every "
        f"read since, for at least {DURABLE_DAYS} days. A file missing for one read and back "
        "the next is our reader having a bad day, not the company changing its mind.",
    ]

    return {
        "slug": "doors-opened",
        "name": "Files that appeared",
        "h1": "The day each company opened a door to an automated buyer",
        "lede": (f"A shopping robot cannot read your web page. It looks for a small set of "
                 f"files at fixed addresses, and one morning they are simply there. "
                 f"<strong>{len(_standing_appearances())} of those files appeared on "
                 f"{len(all_firms)} companies</strong> between {_day(d['oldest'])} and "
                 f"{_day(d['newest'])}, and this page names every one of them with both dates."),
        "desc": (f"{len(all_firms)} named companies, {len(_standing_appearances())} "
                 f"machine-buyable files that appeared between {_day(d['oldest'])} and "
                 f"{_day(d['newest'])}, both dates given."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": d["reads"],
        "tables": [tab, _file_roster_table()],
        "facts": facts,
        "limits": limits,
    }


def _llms_slice() -> dict | None:
    d = _load()
    res = "llms"
    serving = _serving(res)
    if len(serving) < MIN_ROWS:
        return None
    today = _today_row(res)

    newest_first = sorted(serving, key=lambda x: (d["first_there"][(x, res)], x), reverse=True)
    rows = []
    for dom in newest_first[:ROW_CAP]:
        _day_, _st, _status, sha, _err = today[dom]
        kind, obj, raw = d["bodies"][sha]
        rows.append([
            _esc(dom),
            _day(d["first_there"][(dom, res)]),
            _esc(_heading(res, sha, d["bodies"])) or "—",
            f"{len(raw):,}",
        ])
    who = {
        "caption": (f"{len(serving)} of the {len(d['domains'])} companies served a real "
                    f"agent-instructions file on {_day(d['newest'])}. These are the "
                    f"{len(rows)} we saw most recently for the first time"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Company", "First day we saw the file", "First line of the file",
                    "Bytes"],
        "rows": rows,
        "moved_col": 1,
    }

    appeared = _appeared_table(res)

    rewrites = collections.Counter()
    lastchg: dict[str, str] = {}
    for ch in d["changed"]:
        if ch["resource"] != res:
            continue
        rewrites[ch["domain"]] += 1
        lastchg[ch["domain"]] = ch["to_date"]
    rw_rows = []
    for dom, n in rewrites.most_common(ROW_CAP):
        held = sum(1 for _day_, st, *_ in d["series"][(dom, res)] if st == "there")
        rw_rows.append([_esc(dom), f"{n:,}", f"{held:,}", _day(lastchg[dom])])
    rewrite = {
        "caption": (f"{len(rewrites)} companies rewrote their agent-instructions file while we "
                    f"watched, {sum(rewrites.values()):,} times between them. A file that "
                    "changes every single day is usually a date stamp inside it, not a rewrite"),
        "stamp": f"{_day(d['oldest'])} to {_day(d['newest'])}",
        "headers": ["Company", "Times the file came back different", "Days we held the file",
                    "Most recent change"],
        "rows": rw_rows,
        "moved_col": 1,
    }

    tables = [t for t in (appeared, who, rewrite) if t and t["rows"]]

    facts = [
        f"{len(serving)} of the {len(d['domains'])} companies on the panel served a real "
        f"agent-instructions file at <code>/llms.txt</code> on {_day(d['newest'])}.",
        f"{len(appeared['rows']) if appeared else 0} of them put it up while we were watching, "
        f"each on a day we can name.",
        f"{len(rewrites)} companies rewrote the file after publishing it, "
        f"{sum(rewrites.values()):,} times in total. We compare the bytes, so a date stamped "
        "inside the file counts as a change.",
        "The file is the shop talking to a machine in its own words, so the first line is worth "
        "reading: some write a plain company summary, others open with "
        "<code># Agent Instructions</code> and address the robot directly.",
    ]

    limits = [
        "An agent-instructions file tells an assistant what to say about a shop. It is not a "
        "checkout. A company can serve one and still have no way for a robot to buy anything.",
        _two_hundred_limit(),
        _unknown_limit(),
        _panel_limit(),
        _start_limit(),
        "We compare the bytes of the file, not its meaning. A company that stamps today's date "
        "inside its file shows up as changing it every day, and the table says so rather than "
        "selling you the churn as news.",
        _gap_limit(),
    ]

    return {
        "slug": "agent-instructions",
        "name": "Agent-instructions files",
        "h1": "Which companies tell an AI assistant what they sell",
        "lede": (f"<code>/llms.txt</code> is a plain text file where a shop tells an AI "
                 f"assistant what it sells and where to look. <strong>{len(serving)} of the "
                 f"{len(d['domains'])} companies we watch served a real one on "
                 f"{_day(d['newest'])}</strong>, and we can name the day each of them put it up."),
        "desc": (f"{len(serving)} named companies serving a real /llms.txt on "
                 f"{_day(d['newest'])}, plus the day each one appeared and every rewrite since."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": _reads_for(("llms",)),
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _ucp_slice() -> dict | None:
    d = _load()
    res = "ucp"
    serving = _serving(res)
    if len(serving) < MIN_ROWS:
        return None
    today = _today_row(res)

    def manifest(dom):
        sha = today[dom][3]
        return d["bodies"][sha][1]

    newest_first = sorted(serving, key=lambda x: (d["first_there"][(x, res)], x), reverse=True)
    rows = []
    for dom in newest_first[:ROW_CAP]:
        obj = manifest(dom) or {}
        u = obj.get("ucp", {}) if isinstance(obj, dict) else {}
        pay = u.get("payment_handlers")
        names = []
        if isinstance(pay, list):
            names = [p.get("id", "") for p in pay if isinstance(p, dict)]
        elif isinstance(pay, dict):
            names = list(pay)
        rows.append([
            _esc(dom),
            _day(d["first_there"][(dom, res)]),
            _esc(u.get("version") or "—"),
            _esc(", ".join(n for n in names if n)[:60]) or "—",
        ])
    who = {
        "caption": (f"{len(serving)} of the {len(d['domains'])} companies served a real checkout "
                    f"manifest on {_day(d['newest'])}. These are the {len(rows)} we saw most "
                    "recently for the first time"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Company", "First day we saw the manifest", "Version it declares",
                    "Payment methods it names"],
        "rows": rows,
        "moved_col": 1,
    }

    moved = []
    for a in _standing_appearances():
        if a["resource"] != res:
            continue
        moved.append([_esc(a["domain"]), "the manifest appeared", _day(a["from_date"]),
                      _day(a["to_date"]),
                      "still there" if a["still_there"] else "taken down again"])
    for v in d["vanished"]:
        if v["resource"] != res or not v["durable"]:
            continue
        moved.append([_esc(v["domain"]), "the manifest was taken down", _day(v["last_seen"]),
                      _day(v["first_gone"]),
                      f"absent on all {v['clean_gone_days']} reads since"])
    for ch in d["changed"]:
        if ch["resource"] != res:
            continue
        moved.append([_esc(ch["domain"]), "the manifest was rewritten", _day(ch["from_date"]),
                      _day(ch["to_date"]), "still there"])
    moved.sort(key=lambda r: r[3])
    changes = {
        "caption": ("Everything that moved on a checkout manifest while we watched — put up, "
                    "taken down, or rewritten"),
        "stamp": f"{_day(d['oldest'])} to {_day(d['newest'])}",
        "headers": ["Company", "What happened", "Last read before", "Read it happened on",
                    f"On {_day(d['newest'])}"],
        "rows": moved,
        "moved_col": 1,
    }

    caps = collections.Counter()
    for dom in serving:
        obj = manifest(dom) or {}
        u = obj.get("ucp", {}) if isinstance(obj, dict) else {}
        cp = u.get("capabilities")
        if isinstance(cp, dict):
            for k in cp:
                caps[k] += 1
        elif isinstance(cp, list):
            for k in cp:
                caps[str(k)] += 1
    cap_rows = [[f"<code>{_esc(k)}</code>", f"{n:,}", f"{round(100 * n / len(serving))}%"]
                for k, n in caps.most_common(ROW_CAP)]
    checkout_n = max((n for k, n in caps.items() if k.endswith("checkout")), default=0)
    pays = collections.Counter()
    for dom in serving:
        obj = manifest(dom) or {}
        u = obj.get("ucp", {}) if isinstance(obj, dict) else {}
        ph = u.get("payment_handlers")
        seen = set()
        if isinstance(ph, list):
            seen = {p.get("id") for p in ph if isinstance(p, dict) and p.get("id")}
        elif isinstance(ph, dict):
            seen = set(ph)
        for k in seen:
            pays[k] += 1
    pay_top, pay_top_n = (pays.most_common(1) or [("no payment method", 0)])[0]
    capability = {
        "caption": (f"What the {len(serving)} manifests say a robot may do, read out of the "
                    "manifests themselves"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Named in the manifest", "Companies naming it",
                    "Share of the manifests we hold"],
        "rows": cap_rows,
        "moved_col": None,
    }

    tables = [t for t in (who, changes, capability) if t["rows"]]

    facts = [
        f"{len(serving)} of the {len(d['domains'])} companies served a real checkout manifest at "
        f"<code>/.well-known/ucp</code> on {_day(d['newest'])}. This is the file that names a "
        "shop's cart, its checkout and the payment methods a robot may use.",
        (f"Every one of those {len(serving)} manifests names a checkout a robot may drive"
         if checkout_n == len(serving) else
         f"{checkout_n} of those {len(serving)} manifests name a checkout a robot may drive")
        + (f", and every one names <code>{html.escape(pay_top)}</code>."
           if pay_top_n == len(serving)
           else f", and {pay_top_n} name <code>{html.escape(pay_top)}</code>."),
        f"{len([a for a in d['appeared'] if a['resource'] == res])} manifests appeared while we "
        f"were watching and {len([ch for ch in d['changed'] if ch['resource'] == res])} were "
        "rewritten after publishing.",
        f"{len([v for v in d['vanished'] if v['resource'] == res and v['durable']])} was taken "
        "down again and has not come back — the whole reason to hold dated copies rather than "
        "trust today's read.",
    ]

    limits = [
        "A manifest is a shop saying what a robot may do. We read the file. We do not place an "
        "order, do not test the checkout, and cannot tell you whether any of it works.",
        _two_hundred_limit(),
        _unknown_limit(),
        _panel_limit(),
        _start_limit(),
        "Most of these manifests are served by the same shop platform, so they look alike. "
        "That is what the file says, not a judgement about the company behind it.",
        _gap_limit(),
    ]

    return {
        "slug": "checkout-manifest",
        "name": "Checkout manifests",
        "h1": "Which companies let a robot reach their checkout",
        "lede": (f"The checkout manifest at <code>/.well-known/ucp</code> is the one that "
                 f"matters for buying: it names the cart, the checkout and the payment methods "
                 f"a robot may use. <strong>{len(serving)} of the {len(d['domains'])} companies "
                 f"we watch served a real one on {_day(d['newest'])}.</strong>"),
        "desc": (f"{len(serving)} named companies serving a real checkout manifest on "
                 f"{_day(d['newest'])}, with the day each appeared and what each one allows."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": _reads_for(("ucp",)),
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _lies_slice() -> dict | None:
    d = _load()
    lies = _lies_today()
    if len(lies) < MIN_ROWS:
        return None
    rows = []
    for dom in sorted(lies, key=lambda x: (-len(lies[x]), x))[:ROW_CAP]:
        got = lies[dom]
        title = next((t for _r, t, _n in got if t), "")
        biggest = max(n for _r, _t, n in got)
        rows.append([
            _esc(dom),
            f"{len(got)} of 7",
            _esc(title) or "a web page with no title",
            f"{biggest:,}",
        ])
    who = {
        "caption": (f"Companies whose server answered 200 for a file it does not have, on "
                    f"{_day(d['newest'])}. {len(lies)} companies did this, "
                    f"{sum(len(v) for v in lies.values())} times between them"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Company", "Files answered 200 that were not files",
                    "What the page we got back was called", "Bytes of the biggest one"],
        "rows": rows,
        "moved_col": 1,
    }

    per = collections.Counter()
    for dom, got in lies.items():
        for res, _t, _n in got:
            per[res] += 1
    per_rows = [[_esc(_label(r)), f"<code>{_esc(_path(r))}</code>", f"{per.get(r, 0):,}",
                 f"{len(_serving(r)):,}" if _serving(r) else "none"]
                for r in RESOURCES]
    per_tab = {
        "caption": "The same day, broken down by which file was being asked for",
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["File", "Where we ask for it", "Answers of 200 that were not the file",
                    "Companies that really served it"],
        "rows": per_rows,
        "moved_col": 2,
    }

    total_200 = d["outcome"]["answered 200 with something that was not the file"]
    allseven = sorted(dom for dom, got in lies.items() if len(got) == len(RESOURCES))
    same_body = 0
    for dom in allseven:
        shas = {d["series"][(dom, res)][-1][3] for res in RESOURCES}
        if len(shas) == 1:
            same_body += 1
    # The body that does not even open with a doctype is the one a status-code
    # check and a naive "starts with <!DOCTYPE" check would both wave through.
    odd = None
    order = {r: i for i, r in enumerate(("llms", "ucp", "robots"))}
    for dom in sorted(lies):
        for res, _t, _n in sorted(lies[dom], key=lambda x: order.get(x[0], 9)):
            raw = d["bodies"][_today_row(res)[dom][3]][2].lstrip(BOM).lstrip()
            low = raw[:16].lower()
            if low.startswith(b"<!") or low.startswith(b"<html"):
                continue
            odd = (dom, res, raw[:14].decode("utf-8", "replace"))
            break
        if odd:
            break
    facts = [
        f"On {_day(d['newest'])}, {len(lies)} of the {len(d['domains'])} companies answered 200 "
        f"for at least one file they do not have, {sum(len(v) for v in lies.values())} answers "
        "in total.",
        f"{_and_list(allseven)} answered 200 for all seven addresses on that read"
        + (f", and {_num(same_body)} of them handed back byte-for-byte the same page for all "
           "seven." if same_body else "."),
        f"Across the whole window that has happened {total_200:,} times in {d['reads']:,} sealed "
        "reads. A count built on status codes alone would carry every one of them.",
        "We tell them apart by the body, not the status. Anything whose first character is a "
        "tag is markup, not a document"
        + (f" — which is also how {odd[0]} is caught, since its <code>{_path(odd[1])}</code> "
           f"opens with <code>{_esc(odd[2])}</code> and then a whole web page rather than the "
           "usual doctype." if odd else "."),
    ]

    limits = [
        "This page is about what a server did on one day, not about the company. A shop that "
        "answers 200 for a file it does not have is running an ordinary catch-all page, which "
        "is a normal way to build a website.",
        "We keep the first 256 kilobytes of a body. A page longer than that is cut off and "
        "flagged, and the cut copy is still enough to tell a web page from a text file.",
        _unknown_limit(),
        _panel_limit(),
        "This is the newest read only. A server that answered 200 with a page today may answer "
        "404 tomorrow; we hold both answers, dated.",
        _gap_limit(),
    ]

    return {
        "slug": "two-hundred-not-a-file",
        "name": "Servers that say 200 and mean nothing",
        "h1": "The 200 that is not a file, and why every count depends on it",
        "lede": (f"Ask a shop for a file it does not have and a great many of them answer "
                 f"<strong>200 OK</strong> and hand back their home page. On "
                 f"{_day(d['newest'])} that happened "
                 f"{sum(len(v) for v in _lies_today().values())} times across {len(lies)} "
                 "companies. Count status codes and every number you publish is wrong."),
        "desc": (f"{len(lies)} named companies whose servers answered 200 for files they do not "
                 f"have on {_day(d['newest'])}, and how we tell a real file apart."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": d["reads"],
        "tables": [who, per_tab],
        "facts": facts,
        "limits": limits,
    }


def _blocked_slice() -> dict | None:
    d = _load()
    blocked = _blocked_today()
    full = {dom: c for dom, c in blocked.items() if sum(c.values()) == len(RESOURCES)}
    if len(full) < MIN_ROWS:
        return None

    def shut_days(dom):
        n = 0
        for day in d["days"]:
            bad = 0
            for res in RESOURCES:
                for row in d["series"][(dom, res)]:
                    if row[0] == day and row[1] == "unknown":
                        bad += 1
            if bad == len(RESOURCES):
                n += 1
        return n

    ranked = sorted(full, key=lambda x: (-shut_days(x), x))
    steady = [dom for dom in full if shut_days(dom) >= 0.9 * len(d["days"])]
    # How many have never once let us read anything. Where that is most of them,
    # saying "nine days in ten" would understate what the data actually shows.
    every_day = [dom for dom in full if shut_days(dom) == len(d["days"])]
    rows = []
    for dom in ranked[:ROW_CAP]:
        c = full[dom]
        why = ", ".join(
            f"{k} to all seven" if v == len(RESOURCES) else f"{k}, {_num(v)} of the seven"
            for k, v in c.most_common(2)
        )
        n = shut_days(dom)
        rows.append([_esc(dom), _esc(why), f"{n} of {len(d['days'])}"])
    who = {
        "caption": (f"{len(full)} of the {len(d['domains'])} companies gave us nothing readable "
                    f"on {_day(d['newest'])}. These are the {len(rows)} that have been shut to "
                    "us longest"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Company", "What their server did", "Days shut to us"],
        "rows": rows,
        "moved_col": 2,
    }

    per = collections.Counter()
    for dom, c in blocked.items():
        for k, v in c.items():
            per[k] += v
    reason_rows = [[_esc(k), f"{v:,}"] for k, v in per.most_common(ROW_CAP)]
    reasons = {
        "caption": f"Why we could not read a file on {_day(d['newest'])}, counted over all "
                   f"{len(d['domains']) * len(RESOURCES):,} reads that day",
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["What happened", "Reads"],
        "rows": reason_rows,
        "moved_col": None,
    }

    gate = per.get("their robots.txt told us not to fetch", 0)
    facts = [
        f"{len(blocked)} of the {len(d['domains'])} companies gave us at least one unreadable "
        f"answer on {_day(d['newest'])}, and {len(full)} of them gave us nothing readable at all.",
        f"{ranked[0]} has been shut to us on all seven files on {shut_days(ranked[0])} of the "
        f"{len(d['days'])} days we have read it, and "
        + (f"{len(every_day)} companies have never once let us read a single one of the seven, "
           f"on any of the {len(d['days'])} days."
           if len(every_day) >= len(steady) else
           f"{len(steady)} companies have been shut to us on more than nine days in ten.")
        + " That is a posture, held steadily, not an outage.",
        f"{gate} reads that day were not attempted because the company's own robots.txt told us "
        "not to fetch that address. We stop, seal the refusal, and never go around it.",
        "None of this is counted as a file being missing. A company that will not answer us is "
        "shown as cannot tell, on this page and on every other page in this feed.",
    ]

    limits = [
        "A refusal is what our reader saw, not a fault. Blocking an unfamiliar reader is an "
        "ordinary thing for a large shop to do, and we name our reader and give a contact "
        "address in every request.",
        "We cannot tell you whether these companies serve any of the seven files. They may "
        "serve all of them. We can only tell you we were not allowed to look.",
        f"We do not retry within a day and we do not change our reader to get around a block. "
        f"That keeps the record honest and it is why this list stays roughly the same size "
        f"from day to day.",
        _panel_limit(),
        _gap_limit(),
    ]

    return {
        "slug": "cannot-read",
        "name": "Companies we cannot read",
        "h1": "The companies that will not answer our reader, and what we do about it",
        "lede": (f"<strong>{len(full)} of the {len(d['domains'])} companies on the panel gave "
                 f"us nothing readable on {_day(d['newest'])}.</strong> Their servers refuse "
                 "us, rate-limit us, or their robots.txt tells us not to fetch. We show every "
                 "one of those as cannot tell, never as a missing file."),
        "desc": (f"{len(full)} named companies whose servers gave us nothing readable on "
                 f"{_day(d['newest'])}, why, and how long each has been shut to us."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": d["reads"],
        "tables": [who, reasons],
        "facts": facts,
        "limits": limits,
    }


def _no_door_slice() -> dict | None:
    d = _load()
    states = {res: _today_state(res) for res in RESOURCES}
    shut = [dom for dom in d["domains"]
            if all(states[r].get(dom) == "gone" for r in BUY_SIDE)]
    if len(shut) < MIN_ROWS:
        return None

    # "Absent" covers two different answers and we split them, because only one
    # of the two is a not-found. A 200 carrying a web page is the server
    # answering with something that is not the file: still no door, still not a
    # not-found. Anyone who spot-checks the status code on one of these must
    # find the page already said so.
    _rows_now = {r: _today_row(r) for r in BUY_SIDE}
    flat_no = [dom for dom in shut
               if all(_rows_now[r][dom][2] in (404, 410) for r in BUY_SIDE)]
    odd_two_hundred = [dom for dom in shut if dom not in set(flat_no)]

    def read_days(dom):
        return max(sum(1 for row in d["series"][(dom, r)] if row[1] != "unknown")
                   for r in BUY_SIDE)

    ranked = sorted(shut, key=lambda x: (-read_days(x), x))
    today = {r: _today_row(r) for r in ("robots", "llms", "ucp")}
    rows = []
    for dom in ranked[:ROW_CAP]:
        rows.append([
            _esc(dom),
            "yes" if states["robots"].get(dom) == "there" else "no",
            _absent_cell(today["llms"][dom]),
            _absent_cell(today["ucp"][dom]),
            f"{read_days(dom)} of {len(d['days'])}",
        ])
    who = {
        "caption": (f"{len(shut)} of the {len(d['domains'])} companies had every one of the six "
                    f"buying files provably absent on {_day(d['newest'])}. These are the "
                    f"{len(rows)} we have the cleanest run of reads for"),
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["Company", "Serves a robots.txt", "Agent-instructions file",
                    "Checkout manifest", "Days we got a clear answer"],
        "rows": rows,
        "moved_col": 3,
    }

    robots_n = sum(1 for dom in shut if states["robots"].get(dom) == "there")
    llms = set(_serving("llms"))
    ucp = set(_serving("ucp"))
    cannot = [dom for dom in d["domains"]
              if dom not in shut
              and not any(states[r].get(dom) == "there" for r in BUY_SIDE)]
    split = [
        ["Serves both an agent-instructions file and a checkout manifest",
         f"{len(llms & ucp):,}"],
        ["Serves an agent-instructions file only", f"{len(llms - ucp):,}"],
        ["Serves a checkout manifest only", f"{len(ucp - llms):,}"],
        ["Every buying file provably absent", f"{len(shut):,}"],
        ["We could not tell, on every buying file", f"{len(cannot):,}"],
    ]
    tally = {
        "caption": f"All {len(d['domains'])} companies on the panel, on {_day(d['newest'])}",
        "stamp": f"read {_day(d['newest'])}",
        "headers": ["On our newest read", "Companies"],
        "rows": split,
        "moved_col": None,
    }

    facts = [
        f"{len(shut)} of the {len(d['domains'])} companies had every one of the six buying files "
        f"absent on {_day(d['newest'])}. A robot sent to buy from them has nothing to read.",
        f"Those {len(shut)} split two ways. {len(flat_no)} answered a plain 404 or 410 on all six. "
        f"The other {len(odd_two_hundred)} answered 200 at least once with something that was not "
        "the file, which is still no door but is not a not-found, and the table says which.",
        f"{len(llms & ucp)} companies served both an agent-instructions file and a checkout "
        f"manifest that day, {len(llms - ucp)} served the instructions only, and "
        f"{len(ucp - llms)} the manifest only.",
        f"A further {len(cannot)} companies gave us no clear answer on any buying file, so they "
        "are on neither list. Guessing which side they belong on is exactly the thing this feed "
        "refuses to do.",
        f"{robots_n} of these {len(shut)} companies do serve a robots.txt. Having one has never "
        "meant a shop will sell to a machine, which is why it is not counted as a door here.",
    ]

    limits = [
        "Absent is not a judgement. Plenty of large shops sell perfectly well without any of "
        "these files, and several of the biggest names on the panel are on this list.",
        "This is our newest read. Any company here can publish one of these files tomorrow, and "
        "the day it does is the row this feed exists to sell you.",
        _two_hundred_limit(),
        _unknown_limit(),
        _panel_limit(),
        _gap_limit(),
    ]

    return {
        "slug": "no-machine-door",
        "name": "Companies a robot cannot buy from",
        "h1": "The companies with no machine-readable door at all",
        "lede": (f"<strong>{len(shut)} of the {len(d['domains'])} companies we watch had every one "
                 f"of the six buying files absent on {_day(d['newest'])}.</strong> "
                 f"{len(flat_no)} of them answered a plain not-found on all six; the other "
                 f"{len(odd_two_hundred)} answered 200 at least once with something that was not "
                 "the file. A shopping robot sent to any of them finds nothing to read. This page "
                 "names them, and separates them from the ones we simply could not check."),
        "desc": (f"{len(shut)} named companies with every machine-buyable file provably absent "
                 f"on {_day(d['newest'])}, kept separate from the ones we could not read."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": _reads_for(BUY_SIDE),
        "tables": [who, tally],
        "facts": facts,
        "limits": limits,
    }


def _coverage_slice() -> dict:
    d = _load()
    roster = _file_roster_table()

    out_rows = [[_esc(k), f"{v:,}", f"{round(100 * v / d['reads'], 1)}%"]
                for k, v in d["outcome"].most_common(ROW_CAP)]
    outcomes = {
        "caption": (f"What all {d['reads']:,} sealed reads actually produced, "
                    f"{_day(d['oldest'])} to {_day(d['newest'])}"),
        "stamp": f"{_day(d['oldest'])} to {_day(d['newest'])}",
        "headers": ["What happened", "Reads", "Share of every read we hold"],
        "rows": out_rows,
        "moved_col": None,
    }

    gaps = _missing_days()
    gap_rows = [[_day(g), "no read sealed that day",
                 "the pages either side give the two dates we do hold"] for g in gaps]
    gapt = {
        "caption": ("Every day in the window with no sealed read. We name the gap rather than "
                    "quietly skip it"),
        "stamp": f"{_day(d['oldest'])} to {_day(d['newest'])}",
        "headers": ["Day", "What we hold", "What we do about it"],
        "rows": gap_rows,
        "moved_col": None,
    }

    tables = [roster, outcomes] + ([gapt] if len(gap_rows) >= 1 else [])

    facts = [
        f"{len(d['domains'])} company websites, seven addresses each, read every day. That is "
        f"{d['reads']:,} sealed answers across {len(d['days'])} dated copies, from "
        f"{_day(d['oldest'])} to {_day(d['newest'])}.",
        f"{d['outcome']['the file was there']:,} of those reads found a real file. "
        f"{d['outcome']['answered 200 with something that was not the file']:,} answered 200 "
        "with something that was not the file, and are counted as not there.",
        f"The company list was frozen before the first read and has not changed since. Every "
        "sealed run is bound to the exact bytes of that list, so a row can never quietly be "
        "added or dropped underneath a count.",
        f"Four of the seven files — both agent cards and both tool-server files — have never "
        f"been served by anybody on this panel on any of the {len(d['days'])} days. We publish "
        "that zero because it is a reading, and the first company to break it is the row worth "
        "paying for.",
    ]

    limits = [
        _panel_limit(),
        _not_launch_limit(),
        _two_hundred_limit(),
        _unknown_limit(),
        _start_limit(),
        _gap_limit(),
        "We read seven fixed addresses and nothing else. We do not crawl the shop, do not read "
        "product pages, and do not touch anything behind a login. There is no personal data in "
        "this feed by construction.",
        "One read a day per address. If a company puts a file up and takes it down inside "
        "twenty-four hours, we will not have seen it.",
    ]

    return {
        "slug": "coverage",
        "name": "What this feed covers",
        "h1": "What the machine-buyable files feed covers, and what it does not",
        "lede": (f"Every file we ask for, every company we ask, what all {d['reads']:,} sealed "
                 "answers actually came back as, and the days we have no read for."),
        "desc": (f"The {len(d['domains'])}-company panel, the seven files we ask for, and what "
                 f"all {d['reads']:,} sealed reads produced. Newest read {_day(d['newest'])}."),
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": d["reads"],
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# --------------------------------------------------------------------------

def _real_rows(s: dict) -> int:
    return sum(len(t["rows"]) for t in s["tables"])


def slices() -> list[dict]:
    """Every agentic-commerce slice that has enough real rows to ship."""
    wanted = [
        ("coverage", _coverage_slice),
        ("doors-opened", _doors_slice),
        ("agent-instructions", _llms_slice),
        ("checkout-manifest", _ucp_slice),
        ("two-hundred-not-a-file", _lies_slice),
        ("cannot-read", _blocked_slice),
        ("no-machine-door", _no_door_slice),
    ]
    out = []
    for label, fn in wanted:
        s = fn()
        if s is None:
            print(f"slice_agentic_commerce: dropped {label} — the database does not carry "
                  "enough rows for it today", file=sys.stderr)
            continue
        n = _real_rows(s)
        if n < MIN_ROWS:
            print(f"slice_agentic_commerce: dropped {s['slug']} — only {n} real rows, floor "
                  f"is {MIN_ROWS}", file=sys.stderr)
            continue
        out.append(s)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """A real extract of the product: every file that appeared, with both dates."""
    d = _load()
    headers = ["company", "file", "path", "last_read_it_was_absent", "status_that_day",
               "first_read_it_was_there", "first_line_of_the_file", f"state_on_{d['newest']}"]
    rows = []
    for a in _standing_appearances():
        rows.append([
            a["domain"],
            _label(a["resource"]),
            _path(a["resource"]),
            a["from_date"],
            ("200 with a web page" if a["was_markup"] else str(a["from_status"])),
            a["to_date"],
            a["heading"],
            "there" if a["still_there"] else "taken down again",
        ])
    return headers, rows


# --------------------------------------------------------------------------

def _visitor_text(s: dict) -> str:
    bits = [s["name"], s["h1"], s["lede"], s["desc"]] + s["facts"] + s["limits"]
    for t in s["tables"]:
        bits += [t["caption"], t["stamp"]] + t["headers"]
        for row in t["rows"]:
            bits += [str(c) for c in row]
    return " ".join(bits).lower()


if __name__ == "__main__":
    got = slices()
    bad = 0
    for s in got:
        text = _visitor_text(s)
        for word in BANNED:
            if word in text:
                print(f"  BANNED WORD {word!r} in {s['slug']}", file=sys.stderr)
                bad += 1
        for key in ("slug", "name", "h1", "lede", "desc", "newest", "oldest",
                    "runs", "cadence_days", "row_count", "tables", "facts", "limits"):
            if key not in s:
                print(f"  MISSING KEY {key} in {s['slug']}", file=sys.stderr)
                bad += 1
        if len(s["newest"]) != 10 or len(s["oldest"]) != 10:
            print(f"  BAD DATE in {s['slug']}", file=sys.stderr)
            bad += 1
        if len(s["desc"]) > 155:
            print(f"  DESC {len(s['desc'])} chars in {s['slug']}", file=sys.stderr)
            bad += 1
        if not 3 <= len(s["facts"]) <= 6:
            print(f"  {len(s['facts'])} facts in {s['slug']}", file=sys.stderr)
            bad += 1
        if not 2 <= len(s["limits"]) <= 8:
            print(f"  {len(s['limits'])} limits in {s['slug']}", file=sys.stderr)
            bad += 1
        if not 1 <= len(s["tables"]) <= 3:
            print(f"  {len(s['tables'])} tables in {s['slug']}", file=sys.stderr)
            bad += 1
        n = _real_rows(s)
        head = s["tables"][0]
        print(f"{s['slug']:>24}  newest {s['newest']}  copies {s['runs']:>3}  "
              f"rows held {s['row_count']:>8,}  table rows {n:>3}  "
              f"desc {len(s['desc']):>3}  facts {len(s['facts'])}  limits {len(s['limits'])}")
    heads, rows = sample()
    print()
    print(f"slices returned: {len(got)}")
    print(f"sample: {len(heads)} columns, {len(rows)} rows, "
          f"first {rows[0][:3] if rows else 'none'}")
    if bad:
        print(f"PROBLEMS: {bad}", file=sys.stderr)
        raise SystemExit(1)
