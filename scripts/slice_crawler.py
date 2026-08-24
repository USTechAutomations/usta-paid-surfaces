#!/usr/bin/env python3
"""Slice pages for AI-crawler policy changes (/feeds/crawler/...).

A site rewrites robots.txt whenever it likes and keeps no history of it. The
file you fetch today is the only one there is. We save a dated copy of that file
from a fixed panel of sites every day, so we hold what it said before and what it
says now. The size of the panel is read from the data, never typed in here.

Every row this module returns is read out of the saved copies themselves at call
time. The rules are parsed out of the stored file bodies, not out of any verdict
column, because a verdict column cannot be checked by a reader and has been
wrong here before. The database is opened read-only and never written to.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sqlite3
import sys
import time
import zlib
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE, late_after  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table  # noqa: E402
from render_family import write as write_family  # noqa: E402

# The one sentence-opening a stale page must carry. Imported, never retyped:
# the build gate and the live probe both search for this exact string, and a
# hand-typed variant would leave both of them looking at a page they think is
# fine.
PAUSED = PAUSED_PHRASE.capitalize()

FAMILY = "crawler"

DB = "/home/gmullins/Claude CLI/clocks/closing_web/data/closing_web.db"
CADENCE_DAYS = 1

# The five-real-rows floor. A slice under this is dropped, never padded.
MIN_ROWS = 5
TABLE_CAP = 12

# How many of our own reads a page compares. Eight reads is seven day-to-day
# comparisons, which is the last week of the archive.
WINDOW_READS = 8

# Crawler names we look for, lowercase, exactly as a site would write them in
# robots.txt. A name only reaches a page if it is actually in a saved file.
AI_BOTS = (
    "gptbot", "oai-searchbot", "chatgpt-user", "claudebot", "claude-web",
    "claude-user", "claude-searchbot", "anthropic-ai", "perplexitybot",
    "perplexity-user", "ccbot", "google-extended", "googleother",
    "applebot-extended", "bytespider", "amazonbot", "meta-externalagent",
    "meta-externalfetcher", "facebookbot", "cohere-ai", "diffbot",
    "imagesiftbot", "omgili", "omgilibot", "timpibot", "youbot", "ai2bot",
    "duckassistbot", "mistralai-user", "webzio-extended", "img2dataset",
    "bedrockbot", "petalbot", "firecrawlagent", "novaact", "pangubot",
    "iaskspider/2.0", "cotoyogi", "velenpublicwebcrawler", "turnitinbot",
    "aihitbot", "brightbot 1.0", "echoboxbot", "kangaroo bot",
    "sidetrade indexer bot", "factset_spyderbot",
)
_BOT_SET = set(AI_BOTS)
_BOT_RE = re.compile("|".join(re.escape(b) for b in AI_BOTS), re.IGNORECASE)

# Crawlers that get a page of their own. Each still has to clear the five-row
# floor on real data or it is dropped.
BOT_PAGES = [
    ("gptbot", "gptbot", "GPTBot", "OpenAI runs GPTBot to gather pages."),
    ("claudebot", "claudebot", "ClaudeBot", "Anthropic runs ClaudeBot."),
    ("google-extended", "google-extended", "Google-Extended",
     "Google-Extended is the name Google tells sites to use to control its AI products."),
    ("ccbot", "ccbot", "CCBot",
     "Common Crawl runs CCBot. Its copy of the web is a starting point for many "
     "other people's models."),
    ("perplexitybot", "perplexitybot", "PerplexityBot", "Perplexity runs PerplexityBot."),
]

# What the file says about one crawler on one day.
PHRASE = {
    "absent": "not named in the file",
    "blocked_all": "blocked from the whole site",
    "blocked_except": "blocked from the whole site, with {n} exception{s}",
    "blocked_paths": "blocked from {n} folder{s}",
    "allowed_all": "allowed everywhere",
    "allow_only": "named, with {n} allow line{s} and no block",
    "named_no_rule": "named with nothing written under it",
}

BLOCKED_WHOLE_SITE = ("blocked_all", "blocked_except")

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _parse_robots(body: str) -> dict[str, list] | None:
    """Pull the named crawler groups out of a robots.txt body.

    Returns None when the thing we saved is not a robots file at all, which
    happens when a site answers with a web page or a bot-block screen instead.
    Treating one of those as a policy would be a false alarm.
    """
    if body.lstrip()[:1] == "<":
        return None
    groups: dict[str, list] = {}
    written: dict[str, str] = {}
    current: list[str] = []
    collecting_names = True
    saw_name = False
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if not collecting_names:
                current = []
                collecting_names = True
            current.append(value.lower())
            written.setdefault(value.lower(), value)
            saw_name = True
            for name in current:
                groups.setdefault(name, [])
        elif field in ("allow", "disallow"):
            collecting_names = False
            for name in current:
                groups.setdefault(name, []).append((field, value))
    if not saw_name:
        return None
    groups["__written__"] = written
    return groups


def _state(rules: list | None) -> tuple[str, int] | None:
    """Turn one crawler's rules into what the file says about it."""
    if rules is None:
        return None
    blocks = [v for d, v in rules if d == "disallow" and v]
    allows = [v for d, v in rules if d == "allow" and v]
    open_line = any(d == "disallow" and not v for d, v in rules)
    if "/" in blocks:
        return ("blocked_except", len(allows)) if allows else ("blocked_all", 0)
    if blocks:
        return ("blocked_paths", len(blocks))
    if open_line:
        return ("allowed_all", 0)
    if allows:
        return ("allow_only", len(allows))
    return ("named_no_rule", 0)


def _phrase(state: tuple[str, int] | None) -> str:
    if state is None:
        return PHRASE["absent"]
    kind, n = state
    return PHRASE[kind].format(n=n, s="" if n == 1 else "s")


def _direction(before: tuple | None, after: tuple | None) -> str:
    b = before[0] if before else "absent"
    a = after[0] if after else "absent"
    if a == "absent":
        return "unnamed"
    if b == "absent":
        return "blocked" if a in BLOCKED_WHOLE_SITE else "named"
    if b not in BLOCKED_WHOLE_SITE and a in BLOCKED_WHOLE_SITE:
        return "blocked"
    if b in BLOCKED_WHOLE_SITE and a not in BLOCKED_WHOLE_SITE:
        return "opened"
    return "changed"


# How interesting a change is, strongest first, for row order.
DIR_RANK = {"opened": 0, "blocked": 1, "unnamed": 2, "named": 3, "changed": 4}

_CACHE: dict = {}


def _read() -> dict:
    """Read the archive once and work out every crawler-level change."""
    if _CACHE:
        return _CACHE

    conn = _connect()
    # The dates come out of the DATA table, not out of the run log. A run can
    # finish, be recorded, and leave no row behind; if this page took its
    # freshness from collection_runs it would say we read the panel on a day we
    # hold nothing for. They agree today -- 70 dates either way -- and the day
    # they stop agreeing, the data table is the one telling the truth.
    run_dates = [r[0] for r in conn.execute(
        "select distinct snapshot_date from policy_snapshots order by snapshot_date")]
    runs = conn.execute("select count(*) from collection_runs").fetchone()[0]
    total_rows = conn.execute("select count(*) from policy_snapshots").fetchone()[0]
    newest, oldest = run_dates[-1], run_dates[0]

    # What each site did on our newest read, counted in SQL.
    status = dict(conn.execute(
        "select coalesce(status_code, -1), count(*) from policy_snapshots "
        "where snapshot_date=? and resource='robots' group by 1", (newest,)))
    errors = dict(conn.execute(
        "select coalesce(fetch_error, 'none'), count(*) from policy_snapshots "
        "where snapshot_date=? and resource='robots' group by 1", (newest,)))
    per_resource = dict(conn.execute(
        "select resource, sum(status_code = 200) from policy_snapshots "
        "where snapshot_date=? group by resource", (newest,)))
    sites_read = conn.execute(
        "select count(*) from policy_snapshots where snapshot_date=? and resource='robots'",
        (newest,)).fetchone()[0]

    # How the saved copies are stored, counted rather than described. A file
    # over the cap is kept up to the cap and no further, and a change that
    # touches one of those is dropped rather than guessed at, so the page has to
    # be able to say how big the cap is and how much of the archive it bit.
    blobs_held = conn.execute("select count(*) from blobs").fetchone()[0]
    blobs_cut = conn.execute("select count(*) from blobs where truncated=1").fetchone()[0]
    cut_at = conn.execute("select min(byte_len) from blobs where truncated=1").fetchone()[0]

    window = run_dates[-WINDOW_READS:]

    def load(date: str) -> dict[str, str]:
        return dict(conn.execute(
            "select domain, content_sha256 from policy_snapshots "
            "where snapshot_date=? and resource='robots' and content_sha256 is not null",
            (date,)))

    days = {d: load(d) for d in window}

    # A file that swings between an old and a new version day after day is two
    # of the site's servers answering differently, not the site changing its
    # mind. Those sites come out before anything is counted.
    seen_shas: dict[str, set] = defaultdict(set)
    last_sha: dict[str, str] = {}
    flapping: set[str] = set()
    for date in window:
        for domain, sha in days[date].items():
            if sha != last_sha.get(domain) and sha in seen_shas[domain]:
                flapping.add(domain)
            seen_shas[domain].add(sha)
            last_sha[domain] = sha

    truncated = {}
    bodies: dict[str, str | None] = {}
    parsed: dict[str, dict | None] = {}

    def group_map(sha: str) -> dict | None:
        if sha not in parsed:
            row = conn.execute(
                "select content_gz, truncated from blobs where content_sha256=?",
                (sha,)).fetchone()
            if row is None:
                parsed[sha] = None
            else:
                truncated[sha] = bool(row[1])
                text = zlib.decompress(row[0]).decode("utf-8", "replace")
                bodies[sha] = text
                parsed[sha] = _parse_robots(text)
        return parsed[sha]

    def _is_page(sha: str) -> bool:
        """True when the copy we saved is a web page rather than a text file.

        Only asked about copies group_map() has already read, so the body is
        already in hand. A copy we hold no body for is not a web page; it is a
        copy we cannot judge, and it counts in the other bucket.
        """
        text = bodies.get(sha)
        return bool(text) and text.lstrip()[:1] == "<"

    changes = []
    cut_flapping = 0
    cut_truncated = 0
    cut_not_robots = 0
    # Same split as the newest-read counters above: most of what we refuse to
    # read as a policy is a web page, but not all of it, and the page has to
    # say which is which rather than call all of it a web page.
    cut_not_robots_page = 0
    files_changed = 0
    for i in range(1, len(window)):
        before_date, after_date = window[i - 1], window[i]
        before_day, after_day = days[before_date], days[after_date]
        for domain, sha_before in before_day.items():
            sha_after = after_day.get(domain)
            if sha_after is None or sha_after == sha_before:
                continue
            files_changed += 1
            if domain in flapping:
                cut_flapping += 1
                continue
            groups_before = group_map(sha_before)
            groups_after = group_map(sha_after)
            if groups_before is None or groups_after is None:
                cut_not_robots += 1
                if _is_page(sha_before) or _is_page(sha_after):
                    cut_not_robots_page += 1
                continue
            if truncated.get(sha_before) or truncated.get(sha_after):
                cut_truncated += 1
                continue
            written = dict(groups_before["__written__"])
            written.update(groups_after["__written__"])
            # Sorted, not set order. A set of strings walks in a different
            # order in every process, so the same code on the same archive put
            # a different crawler's name against the same site from one build
            # to the next. The counts never moved; the rows a reader sees did.
            for bot in sorted(_BOT_SET):
                if bot not in groups_before and bot not in groups_after:
                    continue
                state_before = _state(groups_before.get(bot))
                state_after = _state(groups_after.get(bot))
                if state_before == state_after:
                    continue
                changes.append({
                    "domain": domain,
                    "bot": bot,
                    # The spelling the site itself used, not one we chose.
                    "written": written.get(bot, bot),
                    "before_date": before_date,
                    "after_date": after_date,
                    "before": _phrase(state_before),
                    "after": _phrase(state_after),
                    "direction": _direction(state_before, state_after),
                })

    # What the newest read actually holds, read out of the saved files.
    #
    # Two of these counters used to carry a word that was wider than the count
    # underneath it, which is the same fault as printing a number nobody can
    # re-derive, only harder to see:
    #
    #   * everything we would not read as a policy was called "a web page sent
    #     in its place". Most of it is. The rest is a plain-text file with no
    #     User-agent line in it at all -- an empty file, or comments only. That
    #     is not a web page, so the two are counted apart and both are printed.
    #   * a file "names" a crawler here if the crawler's name appears anywhere
    #     in the text, which caught names sitting in a comment or inside a
    #     Disallow path. The rest of this page decides what a site said by
    #     reading its User-agent groups, so this counts the same way, and the
    #     wider mention count is kept beside it rather than printed as if it
    #     were the same thing.
    real_files = 0
    not_robots_page = 0
    not_robots_no_agent = 0
    naming_ai = 0
    mentioning_ai = 0
    for sha, count in conn.execute(
            "select content_sha256, count(*) from policy_snapshots "
            "where snapshot_date=? and resource='robots' and content_sha256 is not null "
            "group by 1", (newest,)):
        row = conn.execute("select content_gz from blobs where content_sha256=?",
                           (sha,)).fetchone()
        if row is None:
            continue
        text = zlib.decompress(row[0]).decode("utf-8", "replace")
        if text.lstrip()[:1] == "<":
            not_robots_page += count
            continue
        groups = _parse_robots(text)
        if groups is None:
            not_robots_no_agent += count
            continue
        real_files += count
        if _BOT_RE.search(text):
            mentioning_ai += count
        if any(bot in groups for bot in _BOT_SET):
            naming_ai += count
    not_robots = not_robots_page + not_robots_no_agent
    conn.close()

    changes.sort(key=lambda c: (DIR_RANK[c["direction"]], c["domain"]))
    changes.sort(key=lambda c: c["after_date"], reverse=True)
    changes.sort(key=lambda c: DIR_RANK[c["direction"]])

    _CACHE.update({
        "changes": changes,
        "window": window,
        "per_day_files": {date: len(day) for date, day in days.items()},
        "run_dates": run_dates,
        "runs": runs,
        "total_rows": total_rows,
        "newest": newest,
        "oldest": oldest,
        "sites_read": sites_read,
        "status": status,
        "errors": errors,
        "per_resource": per_resource,
        "real_files": real_files,
        "not_robots": not_robots,
        "not_robots_page": not_robots_page,
        "not_robots_no_agent": not_robots_no_agent,
        "naming_ai": naming_ai,
        "mentioning_ai": mentioning_ai,
        "files_changed": files_changed,
        "cut_flapping": cut_flapping,
        "cut_truncated": cut_truncated,
        "cut_not_robots": cut_not_robots,
        "cut_not_robots_page": cut_not_robots_page,
        "cut_not_robots_no_agent": cut_not_robots - cut_not_robots_page,
        "flapping": len(flapping),
        "blobs_held": blobs_held,
        "blobs_cut": blobs_cut,
        "cut_at": cut_at,
        # Two different questions that look like one. A site can answer us with
        # a 200 and still leave us nothing to keep, and the two breakdowns below
        # only add up against the copies we actually saved -- so the page counts
        # saved copies, and says how many 200s left nothing behind.
        "answered_ok": status.get(200, 0),
        "files_saved": real_files + not_robots,
    })
    return _CACHE


def _written_name(rows: list[dict], token: str) -> str:
    for c in rows:
        if c["bot"] == token and c.get("written"):
            return c["written"]
    return token


def _bot_label(change: dict) -> str:
    """The crawler name as the site wrote it, falling back to the page name."""
    for token, _slug, label, _blurb in BOT_PAGES:
        if token == change["bot"]:
            return label
    return change.get("written") or change["bot"]


def _base(name: str, slug: str, h1: str, lede: str, desc: str, row_count: int) -> dict:
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


def _window_words() -> str:
    d = _read()
    return f"{_day(d['window'][0])} to {_day(d['window'][-1])}"


def _limits(extra: list[str] | None = None) -> list[str]:
    d = _read()
    out = [
        "We can only show a change between two of our own reads. A site that "
        "changed its file and changed it back between two of our reads did "
        "something we never saw, and it is not on this page.",
        "A crawler that is not named in the file is not the same as one that is "
        "allowed. When a crawler is not named, whatever the file says under "
        "User-agent: * applies to it instead. Us saying a name was dropped means "
        "only that: the name is gone.",
        "A site with no robots.txt at all has not given permission and has not "
        "blocked anyone. It has said nothing. We count those separately and never "
        "read them as a yes or a no.",
        f"On our newest read, {d['status'].get(403, 0):,} sites refused us and "
        f"{d['status'].get(-1, 0):,} never answered. We do not know what their file "
        "said that day, and we do not guess.",
        f"We read the {d['sites_read']:,} sites on one public list of the most-visited "
        f"sites. A site that is not on that list cannot appear here.",
        f"Two kinds of change are left out rather than sold to you. "
        f"{d['cut_flapping']:,} came from sites whose file swings between an old and a "
        f"new version day to day, which is two of the site's servers disagreeing, not a "
        f"change of mind. {d['cut_truncated']:,} touched a file too big for us to save "
        f"whole, so we could not be sure we had read all of it.",
        "What robots.txt says and what a crawler does are two different things. We "
        "report the file. We do not watch anyone's traffic, and we do not judge whether "
        "a site is right to block anyone.",
    ]
    return out + (extra or [])


def _spread(rows: list[dict], cap: int) -> list[dict]:
    """Pick `cap` rows that show every kind of move, one site each.

    Two things go wrong if you just take the top of the list.

    One site, over and over. One rewrite often moves twenty crawlers at once on
    the same site, so an untouched list hands you twelve rows off one domain.

    One kind of move, over and over. The list is ordered strongest-first, and
    "strongest" here means a whole-site block coming off. Take the first
    twenty-five and every single one of them is a block coming off -- which is
    exactly what the free sample file did until today, so a buyer opened it and
    saw one fifth of what the feed holds. The other four kinds of move were in
    the file and not in the sample.

    So this deals the rows out round-robin across the kinds of move, strongest
    kind first, never taking a site twice. A reader sees a block going on, a
    block coming off, a name appearing, a name vanishing and a rule rewritten:
    the whole product rather than its loudest corner.
    """
    buckets: dict[str, list[dict]] = {}
    for c in rows:
        buckets.setdefault(c["direction"], []).append(c)
    order = sorted(buckets, key=lambda k: DIR_RANK[k])
    out: list[dict] = []
    used: set[str] = set()
    while len(out) < cap:
        took = False
        for kind in order:
            bucket = buckets[kind]
            while bucket:
                c = bucket.pop(0)
                if c["domain"] in used:
                    continue
                used.add(c["domain"])
                out.append(c)
                took = True
                break
            if len(out) == cap:
                break
        if not took:
            break
    return out


def _row(c: dict, with_bot: bool) -> list[str]:
    row = [c["domain"]]
    if with_bot:
        row.append(_bot_label(c))
    row += [c["before"], c["after"],
            f"{_day(c['before_date'])} → {_day(c['after_date'])}"]
    return row


def _change_rows(rows: list[dict], with_bot: bool) -> list[list[str]]:
    """Twelve rows, twelve different sites, and every kind of move we hold."""
    return [_row(c, with_bot) for c in _spread(rows, TABLE_CAP)]


def _biggest_rewrite(rows: list[dict]) -> tuple[str, str, int]:
    """The site that moved the most crawlers in one day-to-day change."""
    by_edit = Counter((c["domain"], c["after_date"]) for c in rows)
    (domain, date), count = by_edit.most_common(1)[0]
    return domain, date, count


def _counts(rows: list[dict]) -> Counter:
    """How many separate sites did each kind of thing."""
    seen = defaultdict(set)
    for c in rows:
        seen[c["direction"]].add(c["domain"])
    return Counter({k: len(v) for k, v in seen.items()})


def _bot_slice(token: str, slug: str, label: str, blurb: str) -> dict | None:
    d = _read()
    rows = [c for c in d["changes"] if c["bot"] == token]
    if len(rows) < MIN_ROWS:
        print(f"[crawler] dropped {slug}: {len(rows)} real changes, floor is {MIN_ROWS}",
              file=sys.stderr)
        return None

    sites = len({c["domain"] for c in rows})
    n = _counts(rows)
    sl = _base(
        name=f"Sites that changed their answer to {label}",
        slug=slug,
        h1=f"Sites that changed what robots.txt says about {label}",
        lede=(f"{blurb} In the {len(d['window']) - 1} days from {_window_words()}, "
              f"{sites:,} named sites rewrote what their robots.txt says about it. "
              f"Here is what the file said before and what it says now."),
        desc=(f"{sites:,} named sites that changed their robots.txt answer to {label} "
              f"between {_window_words()}. Both readings and both dates. $175/mo."),
        row_count=len(rows),
    )
    table_rows = _change_rows(rows, with_bot=False)
    sl["tables"].append({
        "caption": (f"What the file said about {label} before, and what it says now. "
                    f"One row per site, {len(table_rows)} sites shown of {sites:,}; the "
                    f"file you buy carries all {len(rows):,} changes."),
        "stamp": _window_words(),
        "headers": ["Site", "What the file said before", "What it says now", "Between"],
        "rows": table_rows,
        "moved_col": 2,
    })

    sl["facts"] = [
        f"{n['blocked']:,} sites shut {label} out of the whole site in this window. "
        f"{n['opened']:,} took that block off.",
        f"{n['unnamed']:,} stopped naming {label} in the file at all, and "
        f"{n['named']:,} started naming it. Neither of those is the same as a block "
        f"going on or coming off.",
        f"{len(rows):,} changes across {sites:,} sites, out of {len(d['changes']):,} "
        f"crawler-level changes we caught across every crawler we watch.",
        f"We read {d['sites_read']:,} sites a day. On {_day(d['newest'])}, "
        f"{d['real_files']:,} of them gave us a real robots.txt and {d['naming_ai']:,} of "
        f"those name at least one AI crawler.",
    ]
    sl["limits"] = _limits()
    return sl


def _direction_slice(direction: str, slug: str, name: str, h1: str, lede: str,
                     desc: str) -> dict | None:
    d = _read()
    rows = [c for c in d["changes"] if c["direction"] == direction]
    if len(rows) < MIN_ROWS:
        print(f"[crawler] dropped {slug}: {len(rows)} real changes, floor is {MIN_ROWS}",
              file=sys.stderr)
        return None

    sites = len({c["domain"] for c in rows})
    bots = Counter(c["bot"] for c in rows)
    sl = _base(name=name, slug=slug, h1=h1,
               lede=lede.format(sites=f"{sites:,}", rows=f"{len(rows):,}",
                                window=_window_words(),
                                days=len(d["window"]) - 1),
               desc=desc.format(sites=f"{sites:,}", window=_window_words()),
               row_count=len(rows))
    table_rows = _change_rows(rows, with_bot=True)
    sl["tables"].append({
        "caption": (f"One row per site, {len(table_rows)} sites shown of {sites:,}. The "
                    f"file you buy carries all {len(rows):,} changes, with the site, the "
                    f"crawler, both readings and both dates."),
        "stamp": _window_words(),
        "headers": ["Site", "Crawler", "What the file said before", "What it says now",
                    "Between"],
        "rows": table_rows,
        "moved_col": 3,
    })

    top = ", ".join(f"{_written_name(rows, b)} ({c:,})" for b, c in bots.most_common(5))
    big_domain, big_date, big_count = _biggest_rewrite(rows)
    sl["facts"] = [
        f"{len(rows):,} changes across {sites:,} named sites in the "
        f"{len(d['window']) - 1} days from {_window_words()}.",
        f"The crawlers this happened to most: {top}.",
        f"The biggest single rewrite was {big_domain} on {_day(big_date)}: "
        f"{big_count:,} AI crawlers moved the same way in one edit.",
        f"{len(bots)} different crawler names are involved, all of them read out of the "
        f"saved files rather than from a list we made up.",
    ]
    sl["limits"] = _limits()
    return sl


def _coverage() -> dict:
    d = _read()
    sl = _base(
        name="What is and is not in the crawler feed",
        slug="coverage",
        h1="What is and is not in the crawler feed",
        lede=(f"Every day we ask {d['sites_read']:,} sites for four files and save what "
              f"comes back. This page says how many answered, how many said there is no "
              f"file, how many refused us, and what we leave out before anything is "
              f"counted."),
        desc=(f"How many of the {d['sites_read']:,} sites we read every day answer, "
              f"refuse, or have no robots.txt at all, and what we leave out of the "
              f"change file."),
        row_count=d["sites_read"],
    )

    known = {200: "gave us the file",
             404: "said there is no such file",
             403: "refused us",
             500: "their server errored",
             503: "their server was unavailable",
             429: "told us to slow down",
             301: "redirected us",
             401: "asked us to log in",
             202: "accepted but sent no file",
             400: "called our request bad"}
    err_words = {"dns_error": "the address does not resolve",
                 "timeout": "it never replied in time",
                 "ssl_error": "its certificate would not open",
                 "connection_refused": "it refused the connection",
                 "connection_reset": "it cut the connection",
                 "oserror": "the connection failed",
                 "invalidurl": "the address is not usable",
                 "incompleteread": "it stopped mid-answer"}
    err_rows = [[err_words.get(k, k), f"{v:,}"]
                for k, v in sorted(d["errors"].items(), key=lambda kv: -kv[1])
                if k != "none"]

    # The reasons a site never answered used to be a table of their own. The
    # builder allows three tables to a page and this page has four things worth
    # showing, so the breakdown moved in under the line it breaks down instead
    # of being cut. Nothing was dropped: every reason and every count is still
    # here, indented under "never answered at all" so it reads as a subdivision
    # of that number rather than as more sites on top of it.
    rows = []
    for code, count in sorted(d["status"].items(), key=lambda kv: -kv[1]):
        if code == -1:
            rows.append(["never answered at all", f"{count:,}"])
            rows.extend([[f"\u2014 {w}", n] for w, n in err_rows[:TABLE_CAP]])
        else:
            rows.append([f"{known.get(code, 'answered with code ' + str(code))} "
                         f"({code})", f"{count:,}"])
    sl["tables"].append({
        "caption": (f"What the {d['sites_read']:,} sites did when we asked for "
                    f"robots.txt on our newest read. The indented lines break down "
                    f"the sites that never answered; none of those is a block and "
                    f"none is permission, it means we do not know."),
        "stamp": _day(d["newest"]),
        "headers": ["What the site did", "How many sites"],
        "rows": rows[:TABLE_CAP + len(err_rows[:TABLE_CAP])],
        "moved_col": None,
    })

    sl["tables"].append({
        "caption": (f"The last {len(d['window'])} days we ran, and how many sites gave "
                    f"us a robots.txt each day. We have sealed {d['runs']} runs across "
                    f"{len(d['run_dates'])} days since {_day(d['oldest'])}."),
        "stamp": _window_words(),
        "headers": ["Day", "Sites that gave us a file"],
        "rows": [[_day(x), f"{d['per_day_files'][x]:,}"] for x in d["window"]],
        "moved_col": None,
    })

    bots = Counter(c["bot"] for c in d["changes"])
    if len(bots) >= MIN_ROWS:
        sl["tables"].append({
            "caption": (f"Crawler names that changed status somewhere in the last "
                        f"{len(d['window']) - 1} days. Top {TABLE_CAP} of {len(bots)} "
                        f"names that moved."),
            "stamp": _window_words(),
            "headers": ["Crawler name, as sites write it", "Changes we caught"],
            "rows": [[b, f"{c:,}"] for b, c in bots.most_common(TABLE_CAP)],
            "moved_col": None,
        })

    res_words = {"robots": "robots.txt", "ai": "ai.txt", "llms": "llms.txt",
                 "tdmrep": "tdmrep.json"}
    sl["facts"] = [
        f"We hold {d['total_rows']:,} dated rows in all, from {d['runs']} sealed runs "
        f"between {_day(d['oldest'])} and {_day(d['newest'])}.",
        f"We ask every site for four files each day. On {_day(d['newest'])} the number "
        f"that had one: " + ", ".join(
            f"{res_words.get(k, k)} {v:,}" for k, v in sorted(
                d["per_resource"].items(), key=lambda kv: -(kv[1] or 0))) + ".",
        f"Of the files we got back on {_day(d['newest'])}, {d['real_files']:,} are a "
        f"real robots.txt. Of the rest, {d['not_robots_page']:,} are a web page or a "
        f"bot-block screen sent in its place and {d['not_robots_no_agent']:,} are plain "
        f"text with no User-agent line in them at all. We do not read either as a policy.",
        f"{d['naming_ai']:,} of the real files give at least one AI crawler a "
        f"User-agent line of its own. A further "
        f"{d['mentioning_ai'] - d['naming_ai']:,} mention one somewhere else in the "
        f"file, in a comment or inside a path, which is not the same as naming it and "
        f"is not counted here.",
        f"In the last {len(d['window']) - 1} days, {d['files_changed']:,} robots.txt "
        f"files changed at all. Most of those changes touch nothing an AI crawler "
        f"cares about; {len(d['changes']):,} of them moved a named AI crawler.",
    ]
    sl["limits"] = _limits([
        f"{d['cut_not_robots']:,} file changes in this window were left out because one "
        f"of the two days answered with something we cannot read as a policy: a web page "
        f"or a bot-block screen in {d['cut_not_robots_page']:,} of them, and plain text "
        f"with no User-agent line in the other {d['cut_not_robots_no_agent']:,}.",
    ])
    return sl



# ---------------------------------------------------------------------------
# The family page: /feeds/crawler
#
# This page used to be built by scripts/build_wave2.py out of a hand-written
# file of numbers, samples/crawler.json. That is how it came to say we read
# 39,857 sites a day and caught 519 changes on 83 sites, none of which
# reproduces from this store under any window: the panel has been 100,000 sites
# every day since the first read, and no eight-day window in the archive
# produces 83 or 519. A typed number cannot go stale politely -- it just keeps
# making the promise after the promise stops being true.
#
# So the parent page is built here, from the same single live read as every
# child page under it, and nothing on it is typed twice.
# ---------------------------------------------------------------------------

FALLBACK_WORDS = {
    "contact_h2": "Start the thread",
    "contact_p": "Send the list of sites you follow. We send a checkout link in that "
                 "thread. A person still emails the file.",
    "contact_cta": "Email us for the $175/mo checkout link",
    "contact_note": "We will tell you which of your sites we already hold, and since "
                    "when, before you pay.",
}

# What each kind of move is called in a sentence, so the page counts the rows it
# is showing instead of describing them.
MOVE_WORDS = {
    "opened": "let a crawler back in",
    "blocked": "shut one out of the whole site",
    "unnamed": "stopped naming one at all",
    "named": "named one for the first time",
    "changed": "rewrote the rules under one",
}


def _fam_row() -> dict:
    """This family's own catalog row -- the one place a price is decided."""
    return family_rows().get(FAMILY, {})


def _words(fam: dict, key: str) -> str:
    return fam.get(key) or FALLBACK_WORDS[key]


def _days_behind() -> int:
    """How far our newest read is behind today, counted off the newest row.

    MAX(snapshot_date) in the data table, never a file time and never the run
    log. Both of those lied by eight days on this estate on 21 August: a healthy
    run record over a store nothing had refreshed.
    """
    d = _read()
    today = dt.date.today()
    return (today - dt.date.fromisoformat(d["newest"])).days


def _late() -> bool:
    return _days_behind() > late_after(CADENCE_DAYS)


def _n(x: int) -> str:
    return f"{x:,}"


def family_spec() -> dict:
    """The spec render_family.write() turns into families/crawler/index.html.

    Every number below comes out of _read(), which is the same read the child
    pages are built from in the same run. There is no second source to disagree
    with.
    """
    d = _read()
    fam = _fam_row()
    price = fam.get("price") or "not for sale today"
    changes = d["changes"]
    sites = len({c["domain"] for c in changes})
    reads = len(d["window"])
    late = _late()

    # The rows the table shows, picked once. The sentence under the table counts
    # THESE rows, not the file behind them: a sentence under a table has to
    # describe that table, and the first draft of this page counted the file and
    # told a reader all twelve rows were one kind of move when four of them were
    # not.
    picked = _spread(changes, TABLE_CAP)
    table_rows = [_row(c, with_bot=True) for c in picked]
    shown = Counter(c["direction"] for c in picked)
    parts = [f"{n} {MOVE_WORDS[k]}" for k, n in shown.most_common() if n]
    if len(parts) > 1:
        moves = ", ".join(parts[:-1]) + " and " + parts[-1]
    else:
        moves = parts[0] if parts else "no move we can name"
    # The warning only earns its place when a row on the page is the thing it
    # warns about.
    unnamed_note = (
        " A name disappearing is not the same as a block coming off, and that is "
        "the one people most often get wrong: when a crawler is not named, "
        "whatever the file says under <code>User-agent: *</code> applies to it "
        "instead."
        if shown.get("unnamed") else ""
    )

    big_domain, big_date, big_count = _biggest_rewrite(changes)
    bots = Counter(c["bot"] for c in changes)
    top = ", ".join(f"{_written_name(changes, b)} ({c:,})" for b, c in bots.most_common(5))

    coverage_link = (
        '<a href="https://ustechautomations.com/feeds/crawler/coverage">what is and is '
        "not in this feed</a>"
    )

    stale_head = []
    if late:
        stale_head = [section(
            "We are behind on this list",
            f"Newest dated copy {_day(d['newest'])}",
            f"      <p><strong>{PAUSED}.</strong> Our newest copy of these files is "
            f"{_day(d['newest'])}, which is {_days_behind()} days ago, and this source is "
            f"meant to be read every day. No number on this page moves until the reading "
            f"starts again.</p>\n"
            "      <p>Everything below is real and it is dated. It is a record of what we "
            "saw, and while we are behind it is not a feed.</p>",
        )]

    secs = stale_head + [
        section(
            "Public sample",
            f"{len(table_rows)} named sites \u00b7 {sites:,} sites changed their answer "
            f"in these {reads} reads",
            "      <p>A site rewrites <code>robots.txt</code> whenever it likes and keeps "
            "no history of it. The file you fetch today is the only one there is, so the "
            "rule that applied to your crawler last week is not recoverable from the "
            "site. <strong>We save a copy of each file every day.</strong></p>\n"
            + table(
                ["Site", "Crawler", "What the file said before", "What it says now",
                 "Between"],
                table_rows,
                f"One row per site, and every kind of move we hold. "
                f"{len(table_rows)} sites shown of {sites:,}. The file behind this page "
                f"holds all {len(changes):,} changes; what you buy is the part of it for "
                f"the sites you name.",
                _window_words(),
                moved_col=3,
            )
            + f"\n      <p>Of the {len(table_rows)} sites shown, "
            f"{moves}.{unnamed_note}</p>",
        ),
        section(
            "The biggest single rewrite in this window",
            f"{big_count:,} crawlers moved in one edit",
            f"      <p><strong>{html.escape(big_domain)}</strong> is the largest move we "
            f"caught between two reads: on {_day(big_date)} its file moved "
            f"{big_count:,} named AI crawlers at once. One edit, one day, and nothing on "
            f"the site to say it happened.</p>\n"
            f"      <p>Across the whole window the crawlers this happened to most were "
            f"{top}. Those names are read out of the saved files, spelled the way the "
            f"sites themselves spell them, not matched against a list we wrote.</p>",
        ),
        section(
            "The size of the panel, and the honest count",
            None,
            f"      <p>We ask <strong>{_n(d['sites_read'])} sites</strong> for their "
            f"<code>robots.txt</code> every day and have kept every copy since "
            f"{_day(d['oldest'])}. On our newest read, {_day(d['newest'])}, "
            f"<strong>{_n(d['files_saved'])}</strong> of them gave us a file we could "
            f"save, <strong>{_n(d['real_files'])}</strong> of those were a real "
            f"<code>robots.txt</code> and not one of the {_n(d['not_robots_page'])} web "
            f"pages or {_n(d['not_robots_no_agent'])} plain files with no "
            f"<code>User-agent</code> line sent in their place, and "
            f"<strong>{_n(d['naming_ai'])}</strong> of the real ones give at least one AI "
            f"crawler a <code>User-agent</code> line of its own. Across the {reads} reads "
            f"this page counts, {_window_words()}, "
            f"<strong>{sites:,} sites</strong> changed what their file says about a named "
            f"AI crawler, across <strong>{len(changes):,} crawler-level "
            f"changes</strong>.</p>\n"
            f"      <p>Every number in that paragraph was counted out of the stored files "
            f"themselves when this page was built, and each one is shown again, broken "
            f"down, on {coverage_link}. Ask us and we will show the working.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_n(d['cut_flapping'])} file changes on "
            f"{_n(d['flapping'])} sites were thrown out of this count on "
            f"purpose.</strong> Those files swing "
            f"between an old and a new version day to day, which is two of the site&rsquo;s "
            f"servers answering differently, not the site changing its mind. Counting them "
            f"would inflate the number and every one of them would be a false alarm in "
            f"your inbox.</p>\n"
            f"        <p><strong>{_n(d['cut_not_robots'])} more file changes were left "
            f"out</strong> because one of the two days answered with something we cannot "
            f"read as a policy: a web page or a bot-block screen in "
            f"{_n(d['cut_not_robots_page'])} of them, and plain text with no "
            f"<code>User-agent</code> line in the other "
            f"{_n(d['cut_not_robots_no_agent'])}. Neither is a policy and we do not read "
            f"either as one.</p>\n"
            f"        <p><strong>A very big file is saved up to a limit and no "
            f"further.</strong> The limit is {d['cut_at'] // 1024:,} KB. "
            f"{_n(d['blobs_cut'])} of the {_n(d['blobs_held'])} copies we hold are cut "
            f"that way, and {_n(d['cut_truncated'])} changes in this window touched one, "
            f"so we left those out rather than guess at the part we never read.</p>\n"
            f"        <p><strong>{_n(d['answered_ok'] - d['files_saved'])} sites answered "
            f"us on {_day(d['newest'])} and left us nothing to keep</strong>, and "
            f"{_n(d['status'].get(403, 0))} refused us outright. We do not know what any "
            f"of their files said that day, and we do not guess.</p>\n"
            "      </div>",
        ),
        section(
            "Doing this yourself",
            None,
            "      <p>You can fetch any site&rsquo;s <code>robots.txt</code> yourself in a "
            "second. What you cannot do is fetch yesterday&rsquo;s. Nothing about that "
            "file is versioned, announced or archived.</p>\n"
            f"      <p>To watch a panel this size you would have to fetch "
            f"{_n(d['sites_read'])} files every day, store every copy, and then work out "
            f"which differences are a real policy change and which are two of the "
            f"site&rsquo;s servers disagreeing. That last part is most of the work: it is "
            f"the {_n(d['cut_flapping'])} file changes above that we throw away.</p>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Every site in your list that changed its answer</strong>"
            '<span class="sub">Site, crawler, what it said before, what it says now, and '
            "both dates.</span></li>\n"
            "        <li><strong>Sites that flap between two versions are held back, not "
            'sent</strong><span class="sub">You get changes, not noise.</span></li>\n'
            "        <li><strong>The saved copy behind any row, on request</strong>"
            '<span class="sub">So you can read the whole rule, not just the part quoted '
            "on the page.</span></li>\n"
            "        <li><strong>Cancel any month by email</strong>"
            '<span class="sub">No account to close, no notice period.</span></li>\n'
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us the sites you care about, or ask for the whole "
            "panel.</li>\n"
            "        <li>We tell you which of them we already hold and since when, then "
            "send a checkout link in that thread.</li>\n"
            "        <li>A person emails you the changes file, and names anything we could "
            "not collect.</li>\n"
            "      </ol>",
        ),
    ]

    desc = (
        f"{sites:,} named sites changed their robots.txt answer to an AI crawler in our "
        f"last {reads} reads, to {_day(d['newest'])}. Both readings, both dates. {price}."
    )

    return {
        "sections": secs,
        "id": FAMILY,
        # Every one of these follows the newest row, not a stored decision.
        "ready": not late,
        "pill_text": None if not late else PAUSED,
        "pill_label": "Named sites on this page" if not late else _day(d["newest"]),
        "sample_dt": "Public sample" if not late else "Last sealed copy",
        "group": fam.get("group") or "Software and AI pages",
        "cadence": "Daily seals" if not late else "Reading behind",
        "cadence_long": ("Daily copies, changes file when something moves"
                         if not late else "Daily copies, reading behind"),
        "crumb": "AI-crawler policy changes",
        "h1": "AI-crawler policy changes",
        # One row, one price, every page in the family. Withdrawing the price in
        # catalog.json withdraws it here and on every child page in the same run.
        "price": price,
        "buyer": fam.get("buyer")
        or "Publishers and the SEO and AI teams who need to know who got blocked",
        "desc": desc,
        "lede": (
            "Sites rewrite <code>robots.txt</code> with no notice and keep no history. "
            "<strong>We save a copy of every file every day, so you get the day a site "
            "let a crawler in or shut one out.</strong>"
        ),
        "subj": "AI-crawler%20policy%20changes%20%24175/mo",
        "contact_h2": _words(fam, "contact_h2"),
        "contact_p": _words(fam, "contact_p"),
        "contact_cta": _words(fam, "contact_cta"),
        "contact_note": _words(fam, "contact_note"),
        "foot": (
            "Every row and every number on this page was read out of the saved "
            "robots.txt copies themselves when the page was built. Sites whose file "
            "swings between two versions were taken out and counted separately rather "
            "than sold as changes."
        ),
    }


def slices() -> list[dict]:
    out: list[dict] = []
    for token, slug, label, blurb in BOT_PAGES:
        sl = _bot_slice(token, slug, label, blurb)
        if sl:
            out.append(sl)

    for direction, slug, name, h1, lede, desc in [
        ("blocked", "started-blocking",
         "Sites that newly shut an AI crawler out",
         "Sites that newly shut an AI crawler out of the whole site",
         "On these {sites} sites the file went from not blocking a named AI crawler "
         "to blocking it from the whole site. That happened {rows} times, counting each "
         "crawler separately, in the {days} days from {window}. Every row shows what "
         "the file said on each of the two days.",
         "{sites} named sites that added a whole-site block for an AI crawler between "
         "{window}. Both readings and both dates. $175/mo."),
        ("opened", "stopped-blocking",
         "Sites that let an AI crawler back in",
         "Sites that took a whole-site block off an AI crawler",
         "These {sites} sites had a named AI crawler blocked from the whole site, and "
         "then took that block off. That happened {rows} times, counting each crawler "
         "separately, in the {days} days from {window}. These are the clearest rows we "
         "hold: the crawler is named on both days and the rule under it changes, so "
         "there is nothing to interpret.",
         "{sites} named sites that removed a whole-site block on an AI crawler between "
         "{window}. Both readings and both dates. $175/mo."),
        ("unnamed", "stopped-naming",
         "Sites that stopped naming an AI crawler",
         "Sites that stopped naming an AI crawler in robots.txt",
         "These {sites} sites named an AI crawler in robots.txt one day and did not "
         "name it the next. That happened {rows} times, counting each crawler separately, "
         "in the {days} days from {window}. This is the one people read wrong: a name "
         "disappearing is not the same as a block coming off, because whatever the "
         "file says for every crawler at once then applies instead.",
         "{sites} named sites that dropped an AI crawler's name out of robots.txt "
         "between {window}. Both readings and both dates. $175/mo."),
    ]:
        sl = _direction_slice(direction, slug, name, h1, lede, desc)
        if sl:
            out.append(sl)

    out.append(_coverage())
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for /feeds/crawler/sample.json and sample.csv."""
    d = _read()
    headers = ["domain", "crawler", "said_before", "says_now", "what_moved",
               "first_read", "second_read"]
    words = {"opened": "whole-site block taken off",
             "blocked": "whole-site block added",
             "unnamed": "crawler name dropped from the file",
             "named": "crawler named for the first time",
             "changed": "rules under the crawler rewritten"}
    rows = []
    for c in _spread(d["changes"], 25):
        rows.append([c["domain"], _bot_label(c), c["before"], c["after"],
                     words[c["direction"]], c["before_date"], c["after_date"]])
    return headers, rows


if __name__ == "__main__":
    t0 = time.time()
    d = _read()
    print(f"family: {FAMILY}")
    print(f"held: {d['total_rows']:,} dated rows, {d['runs']} runs on "
          f"{len(d['run_dates'])} days, {d['oldest']} to {d['newest']}")
    print(f"window: {d['window'][0]} to {d['window'][-1]} "
          f"({len(d['window']) - 1} day-to-day comparisons)")
    print(f"files changed: {d['files_changed']:,}  "
          f"crawler-level changes: {len(d['changes']):,}  "
          f"sites: {len({c['domain'] for c in d['changes']}):,}")
    print(f"left out: {d['cut_flapping']:,} flapping, {d['cut_truncated']:,} truncated, "
          f"{d['cut_not_robots']:,} not a robots file")
    print(f"newest read: {d['real_files']:,} real robots files, "
          f"{d['naming_ai']:,} name an AI crawler, {d['not_robots']:,} not a robots file")
    print()
    print(f"family page: {write_family(family_spec())}")
    print()
    ok = True
    for sl in slices():
        n = sum(len(t["rows"]) for t in sl["tables"])
        flag = "" if sl["row_count"] >= MIN_ROWS else "  <-- UNDER FLOOR"
        print(f"  {sl['slug']:<22} row_count={sl['row_count']:<7} "
              f"tables={len(sl['tables'])} table_rows={n} "
              f"newest={sl['newest']} runs={sl['runs']}{flag}")
        if sl["row_count"] < MIN_ROWS:
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
