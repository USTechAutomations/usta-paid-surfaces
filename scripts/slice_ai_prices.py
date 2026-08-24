#!/usr/bin/env python3
"""Slices for /feeds/ai-prices — what the published price of a named AI model did.

What this feed is, in plain words: every model on the OpenRouter marketplace
carries a published price per token. That page shows today's number and nothing
else. When a vendor changes it, the old number is simply gone. We read the
marketplace's own model list once a day, keep every dated copy, and so the
question "what did it cost last Tuesday, and when did it change" still has an
answer.

THE TRAP THIS MODULE EXISTS TO AVOID, and it has burned this project before.

The same clock also saves a fingerprint of each vendor's own pricing web page
(``raw_fetches.content_sha256``). Those fingerprints move when anything on the
page moves -- a banner, a footer, a tracking script, a build id. One vendor's
page produced a different fingerprint on 63 of the 63 gaps between our 64 reads,
while an actual published model price moved on far fewer. A "price change" feed
built out of page fingerprints would be wrong nearly every row. So:

    PRICES COME FROM   model_prices.pricing_json -> "prompt"  (what you send)
                       model_prices.pricing_json -> "completion" (what comes back)
    NOTHING COMES FROM raw_fetches.content_sha256
    NOTHING COMES FROM model_prices.row_sha256

That second one is the quieter trap. ``row_sha256`` covers the whole stored row
including the moment we collected it, so it is different for every model on
every single read -- 418 of 418 models "changed" between 21 and 22 August by
that measure, while 12 models really moved a price. It is a stamp of when we
looked, not of what the list said.

Dollars per million tokens is display arithmetic: the sealed reading is the raw
per-token decimal string, and that string is what goes in the file a buyer pays
for. We multiply by a million so a person can read it. We never treat the
multiplied number as the source.

Everything on these pages is read out of the clock database when this module is
called. The database is opened read-only and is never written to. The only
constants here are the cadence and the floors; every date, name and number is a
live read.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import NamedTuple

FAMILY = "ai-prices"

# We read the marketplace list once a day. freshness.py turns that into "more
# than two days behind and the page must admit it".
CADENCE_DAYS = 1

DB_PATH = "/home/gmullins/Claude CLI/clocks/ai_econ/data/ai_econ.db"

ROOT = Path(__file__).resolve().parents[1]
FAMILY_PAGE = ROOT / "families" / FAMILY / "index.html"

# The two markers in the family page between which the movers block is written.
# The family pages are hand-written, which is how a fact typed into one on the
# day it was written outlives being true. This one is rewritten from the
# database on every build instead, so it cannot go stale on its own.
BLOCK_START = "<!-- ai-prices:evidence:start -->"
BLOCK_END = "<!-- ai-prices:evidence:end -->"
# Fallback only. The real value is read off the family page's canonical link at
# write time; see write_family_block.
HERE = "/feeds/ai-prices/"
# How many rows the family page's own table can hold before it has to say it is
# showing a shortened set. Anything at or under this and the caption can honestly
# say "every move".
FAMILY_ROWS = 24

# A slice with fewer than five real named rows does not ship. It is dropped and
# the reason is printed, never padded.
MIN_ROWS = 5

# Twelve to fourteen rows keeps a page readable. Every caption says how many
# rows the real file carries, so nobody mistakes the sample for the whole thing.
ROW_CAP = 14

# The headline table on the movers page shows the WHOLE of the newest gap, not a
# top slice of it, because "everything that moved last night" is the claim.
PAIR_CAP = 26

# A vendor only gets its own page when we hold at least this many of its models
# on the newest read. Below that the page would be a headline and three rows.
MIN_VENDOR_MODELS = 8

MILLION = Decimal(1000000)

# Six decimal places on a per-million figure is a hundredth of a cent. Four
# strings in the whole window carry float noise past that (one reads
# 0.0000006000000000000001 per token). Those are shown as "about", never
# silently rounded into looking exact.
CENT = Decimal("0.000001")

SLUG_OK = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

MAIL = "operations@ustechautomations.com"

# What each lane in the clock is for, in plain words, and whether a published
# price is ever allowed to come out of it. The second half of each pair is the
# whole point of this table: it is the answer to the fingerprint trap, and it is
# also the honest answer about permission. We fetch these vendor pages; we
# publish nothing out of them.
LANES = {
    "openrouter_models": (
        "The marketplace's own machine-readable model list",
        True,
        'Yes<span class="sub">every price on this feed comes from here</span>',
    ),
    "hf_trending": (
        "A model-hosting site's list of what is being downloaded",
        False,
        'No<span class="sub">it carries no prices at all</span>',
    ),
    "anthropic_pricing": ("A vendor's own price page", False, ""),
    "openai_pricing": ("A vendor's own price page", False, ""),
    "together_pricing": ("A vendor's own price page", False, ""),
    "groq_pricing": ("A vendor's own price page", False, ""),
    "mistral_pricing": ("A vendor's own price page", False, ""),
    "cohere_pricing": ("A vendor's own price page", False, ""),
    "fireworks_pricing": ("A vendor's own price page", False, ""),
    "google_vertex_pricing": ("A vendor's own price page", False, ""),
}

NO_PUBLISH = (
    'No — on hold<span class="sub">we have no permission to relay this vendor\'s '
    "own page</span>"
)

FIELDS = (("prompt", "input"), ("completion", "output"))

FIELD_WORDS = {
    "input": "Input — what you send it",
    "output": "Output — what it sends back",
}

# The same two words for use inside a sentence, where the long form reads as a
# stutter.
FIELD_SHORT = {"input": "input", "output": "output"}


class Price(NamedTuple):
    """One model as one dated copy of the marketplace list recorded it."""
    name: str
    inp: Decimal | None
    out: Decimal | None
    context: int | None


class Move(NamedTuple):
    """One real difference in a published price between two dated copies."""
    was_date: str
    now_date: str
    model_id: str
    name: str
    vendor: str
    field: str          # "input" or "output"
    was: Decimal
    now: Decimal


# --------------------------------------------------------------------------
# reading the sealed copies
# --------------------------------------------------------------------------

_CACHE: dict | None = None


def _connect():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _load() -> dict:
    """Read every dated copy of the model list once, and work out what moved.

    The comparison is done on the decimal VALUE, not on the stored string. Two
    strings can spell the same number, and a feed that called that a price cut
    would be lying with a straight face.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    con = _connect()

    # --- the prices themselves -------------------------------------------
    by_date: dict[str, dict[str, Price]] = defaultdict(dict)
    q = ("select snapshot_date, model_id, name, pricing_json, context_length "
         "from model_prices")
    for day, mid, name, pricing_json, ctx in con.execute(q):
        try:
            p = json.loads(pricing_json)
        except Exception:
            continue
        by_date[day][mid] = Price(
            name or mid,
            _dec(p.get("prompt")),
            _dec(p.get("completion")),
            ctx,
        )
    dates = sorted(by_date)
    if not dates:
        con.close()
        raise SystemExit("slice_ai_prices: no dated price copies in the database")

    # --- the vendor page fingerprints, counted but never published --------
    fetch_days: dict[str, list[str]] = defaultdict(list)
    fetch_hash: dict[str, dict[str, str]] = defaultdict(dict)
    for src, day, sha in con.execute(
        "select source_id, snapshot_date, content_sha256 from raw_fetches order by snapshot_date"
    ):
        fetch_days[src].append(day)
        if sha:
            fetch_hash[src][day] = sha

    hashes: dict[str, dict] = {}
    for src, days in fetch_days.items():
        got = [(d, fetch_hash[src][d]) for d in sorted(set(days)) if d in fetch_hash[src]]
        flips = sum(1 for i in range(1, len(got)) if got[i][1] != got[i - 1][1])
        hashes[src] = {
            "reads": len(got),
            "gaps": max(len(got) - 1, 0),
            "flips": flips,
            "unique": len({s for _d, s in got}),
            "newest": got[-1][0] if got else None,
        }

    runs_total = con.execute("select count(*) from collection_runs").fetchone()[0]
    con.close()

    # --- vendor labels, taken from the newest copy ------------------------
    # A vendor's display name is read out of the list, never typed in here. The
    # list has renamed one of them mid-window, which is exactly why this is not
    # a hard-coded table.
    last = dates[-1]
    labels: dict[str, str] = {}
    seen_label: dict[str, Counter] = defaultdict(Counter)
    for day in dates:
        for mid, row in by_date[day].items():
            v = mid.split("/")[0]
            if ": " in row.name:
                seen_label[v][row.name.split(": ", 1)[0].strip()] += 1
    newest_label: dict[str, Counter] = defaultdict(Counter)
    for mid, row in by_date[last].items():
        v = mid.split("/")[0]
        if ": " in row.name:
            newest_label[v][row.name.split(": ", 1)[0].strip()] += 1
    for v in seen_label:
        pick = newest_label.get(v) or seen_label[v]
        labels[v] = pick.most_common(1)[0][0] if pick else v
    for day in dates:
        for mid in by_date[day]:
            labels.setdefault(mid.split("/")[0], mid.split("/")[0])

    # --- what moved -------------------------------------------------------
    # A model id starting with a tilde is a pointer, not a product: it follows
    # whichever model the marketplace currently calls "latest". Its price moves
    # because the model behind it moved, so counting it would report the same
    # cut twice under two names. Left out here, named in the limits.
    moves: list[Move] = []
    alias_moves = 0
    for i in range(1, len(dates)):
        a, b = dates[i - 1], dates[i]
        A, B = by_date[a], by_date[b]
        for mid in A.keys() & B.keys():
            for idx, word in ((1, "input"), (2, "output")):
                was, now = A[mid][idx], B[mid][idx]
                if was is None or now is None or was == now:
                    continue
                if mid.startswith("~"):
                    alias_moves += 1
                    continue
                moves.append(Move(a, b, mid, B[mid].name,
                                  mid.split("/")[0], word, was, now))

    _CACHE = {
        "by_date": by_date,
        "dates": dates,
        "moves": moves,
        "alias_moves": alias_moves,
        "labels": labels,
        "hashes": hashes,
        "runs_total": runs_total,
        "rows_total": sum(len(by_date[d]) for d in dates),
    }
    return _CACHE


# --------------------------------------------------------------------------
# words and numbers
# --------------------------------------------------------------------------

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _usd(per_token: Decimal | None) -> str:
    """A per-token decimal shown as dollars per million tokens.

    Display arithmetic, and it is labelled as such on every page. The sealed
    reading is the per-token string; this only multiplies it so a person can
    read it. Where the stored string carries float noise past a hundredth of a
    cent we say "about" rather than print sixteen digits or quietly round.
    """
    if per_token is None:
        return "not listed"
    v = per_token * MILLION
    if v == 0:
        return "nothing"
    approx = False
    s = format(v, "f")
    if "." in s and len(s.split(".")[1].rstrip("0")) > 6:
        v = v.quantize(CENT, rounding=ROUND_HALF_UP)
        approx = True
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0")
        frac = s.split(".")[1]
        if len(frac) == 0:
            s += "00"
        elif len(frac) == 1:
            s += "0"
    else:
        s += ".00"
    return ("about $" if approx else "$") + s


def _pct(was: Decimal, now: Decimal) -> str:
    if was == 0:
        return "was listed at nothing"
    change = (now - was) / was * 100
    word = "down" if now < was else "up"
    n = abs(change).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{word} {format(n, 'f')}%"


def _ratio(m: Move) -> Decimal:
    if m.was == 0:
        return Decimal(0)
    return (m.now - m.was) / m.was


def _e(v) -> str:
    return html.escape(str(v))


def _model_cell(m_name: str, model_id: str) -> str:
    return f'{_e(m_name)}<span class="sub">{_e(model_id)}</span>'


def _price_cell(v: Decimal | None, note: str = "") -> str:
    body = _e(_usd(v))
    if note:
        body += f'<span class="sub">{_e(note)}</span>'
    return body


def _num(n: int) -> str:
    words = ("no", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve")
    return words[n] if n < len(words) else f"{n:,}"


def _label(vendor: str) -> str:
    return _load()["labels"].get(vendor, vendor)


def _gaps() -> list[str]:
    """Calendar days inside the window for which we hold no dated copy."""
    data = _load()
    first = date.fromisoformat(data["dates"][0])
    last = date.fromisoformat(data["dates"][-1])
    held = set(data["dates"])
    out = []
    d = first
    while d <= last:
        if d.isoformat() not in held:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _nearest(day: str, before: bool) -> str:
    data = _load()
    if before:
        got = [d for d in data["dates"] if d < day]
        return got[-1] if got else "none"
    got = [d for d in data["dates"] if d > day]
    return got[0] if got else "none"


# --------------------------------------------------------------------------
# the shared honest paragraphs
# --------------------------------------------------------------------------

def _noisiest() -> tuple[str, dict]:
    """The vendor page whose fingerprint moved on the most gaps between reads."""
    data = _load()
    cand = {k: v for k, v in data["hashes"].items()
            if k.endswith("_pricing") and v["gaps"]}
    if not cand:
        return "", {}
    src = max(cand, key=lambda k: (cand[k]["flips"], cand[k]["reads"]))
    return src, cand[src]


def _hash_limit() -> str:
    src, h = _noisiest()
    data = _load()
    pair_moves = [m for m in data["moves"] if m.now_date == data["dates"][-1]]
    if not h:
        return ("A fingerprint of a web page is not a price, and no number on this page "
                "comes from one.")
    return (
        "A fingerprint of a web page is not a price. We also save a fingerprint of some "
        f"vendors' own price pages, and the noisiest of them came back different across "
        f"{h['flips']} of the {h['gaps']} gaps between our {h['reads']} reads. A published "
        f"model price moved across the newest of those gaps for {_num(len({m.model_id for m in pair_moves}))} "
        "models. A feed built out of page fingerprints would report a price change almost "
        "every day for almost every vendor, and almost every row would be wrong. Nothing "
        "on this page is built that way."
    )


def _source_limit() -> str:
    return (
        "These are the prices one marketplace publishes for each model, read from its own "
        "public model list. They are the sticker, not your bill. What you actually pay "
        "depends on how many tokens you send, which provider serves the request and any "
        "contract you already have, and we cannot see any of that."
    )


def _permission_limit() -> str:
    return (
        "We do not read the vendors' own price pages for these numbers. We do fetch some of "
        "those pages and we publish nothing out of them, because we have no permission to "
        "relay them. They are named on the coverage page and they are on hold."
    )


def _gap_limit() -> str:
    data = _load()
    gaps = _gaps()
    first, last = data["dates"][0], data["dates"][-1]
    span = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1
    return (
        f"We hold {len(data['dates'])} dated copies across the {span} days from {_day(first)} to "
        f"{_day(last)}, so there are {len(gaps)} days in that window we hold nothing for. A price "
        "that moved and moved back inside one of those days is invisible to us, and so it is "
        "invisible to you. The days are listed on the coverage page."
    )


def _alias_limit() -> str:
    data = _load()
    return (
        "The list carries a handful of pointer entries whose id starts with a tilde. They follow "
        "whichever model the marketplace currently calls the latest one, so their price moves when "
        f"the model behind them moves. We left {data['alias_moves']:,} of those moves out of every "
        "table here rather than count the same change twice under two names."
    )


def _why_limit() -> str:
    return (
        "We report that a published number changed between two copies we sealed. We do not know "
        "why, we do not claim a vendor announced anything, and we never ring anybody up to ask. "
        "A marketplace sticker can also tick more than once in a week, and when it does we show "
        "every tick rather than the tidy version."
    )


def _noise_limit() -> str:
    return (
        "Four price strings in the whole window carry float noise — one of them reads "
        "0.0000006000000000000001 per token. We show those as an \"about\" figure per million "
        "tokens and keep the exact string in the file you buy. We do not round a number and then "
        "present it as exact."
    )


# --------------------------------------------------------------------------
# table builders
# --------------------------------------------------------------------------

def _moves_table(moves: list[Move], caption: str, cap: int,
                 with_date: bool = True, stamp: str | None = None) -> dict | None:
    """One row per published price that moved. Never one row per fingerprint."""
    if not moves:
        return None
    shown = moves[:cap]
    headers = ["Model", "Listed under", "Which price",
               "Was, $ per million tokens", "Now, $ per million tokens"]
    headers.append("Read where it changed" if with_date else "Change")
    rows = []
    for m in shown:
        last_cell = (f"{_e(_day(m.now_date))}<span class=\"sub\">against {_e(_day(m.was_date))}</span>"
                     if with_date else _e(_pct(m.was, m.now)))
        rows.append([
            _model_cell(m.name, m.model_id),
            _e(_label(m.vendor)),
            _e(FIELD_WORDS[m.field]),
            _price_cell(m.was),
            _price_cell(m.now, _pct(m.was, m.now) if with_date else ""),
            last_cell,
        ])
    data = _load()
    if stamp is None:
        stamp = f"{_day(data['dates'][0])} to {_day(data['dates'][-1])}"
    if len(shown) < len(moves):
        caption += f" — {len(shown)} of {len(moves):,} shown here, all of them in the file"
    return {"caption": caption, "stamp": stamp, "headers": headers,
            "rows": rows, "moved_col": 4}


def _held_table(model_ids: list[str], caption: str, cap: int) -> dict | None:
    """What the newest dated copy lists for these models."""
    data = _load()
    last = data["dates"][-1]
    held = data["by_date"][last]
    got = [mid for mid in model_ids if mid in held]
    if not got:
        return None
    got = sorted(got, key=lambda mid: (held[mid].inp is None,
                                       held[mid].inp if held[mid].inp is not None else Decimal(0),
                                       mid))
    shown = got[:cap]
    rows = []
    for mid in shown:
        p = held[mid]
        rows.append([
            _model_cell(p.name, mid),
            _e(_label(mid.split("/")[0])),
            _price_cell(p.inp),
            _price_cell(p.out),
            _e(f"{p.context:,} tokens") if p.context else "not listed",
        ])
    if len(shown) < len(got):
        caption += f" — {len(shown)} of {len(got):,} shown here, all of them in the file"
    return {
        "caption": caption,
        "stamp": f"dated copy sealed {_day(last)}",
        "headers": ["Model", "Listed under", "Input, $ per million tokens",
                    "Output, $ per million tokens", "Context window it lists"],
        "rows": rows,
        "moved_col": None,
    }


def _pair_counts_table(cap: int) -> dict | None:
    """Every gap between two dated copies, and how much really moved across it."""
    data = _load()
    dates = data["dates"]
    per: dict[tuple[str, str], list[Move]] = defaultdict(list)
    for m in data["moves"]:
        per[(m.was_date, m.now_date)].append(m)
    pairs = [(dates[i - 1], dates[i]) for i in range(1, len(dates))]
    pairs = pairs[-cap:][::-1]
    rows = []
    for a, b in pairs:
        got = per.get((a, b), [])
        if got:
            big = min(got, key=_ratio) if any(_ratio(x) < 0 for x in got) else max(got, key=_ratio)
            big_cell = (f"{_e(big.name)}<span class=\"sub\">{_e(FIELD_WORDS[big.field])}, "
                        f"{_e(_usd(big.was))} to {_e(_usd(big.now))}</span>")
        else:
            big_cell = "nothing moved"
        rows.append([
            f"{_e(_day(a))} → {_e(_day(b))}",
            _e(f"{len({m.model_id for m in got}):,}"),
            _e(f"{len(got):,}"),
            big_cell,
        ])
    if not rows:
        return None
    return {
        "caption": ("Every gap between two dated copies we hold, newest first, and what "
                    "really moved across it"),
        "stamp": f"{len(dates) - 1} gaps in the window, {len(rows)} shown",
        "headers": ["Between these two dated copies", "Models whose price moved",
                    "Published prices that moved", "The biggest move in that gap"],
        "rows": rows,
        "moved_col": 1,
    }


def _stuck_table(moves: list[Move], caption: str, cap: int, cut: bool) -> dict | None:
    """Did the change stick, or did the number come back? Read from the newest copy."""
    data = _load()
    last = data["dates"][-1]
    held = data["by_date"][last]
    rows = []
    for m in moves[:cap]:
        p = held.get(m.model_id)
        idx = 1 if m.field == "input" else 2
        now = p[idx] if p else None
        if now is None:
            verdict = "not on the list any more"
        elif cut:
            verdict = "Yes, still at or below it" if now <= m.now else "No, it went back up"
        else:
            verdict = "Yes, still at or above it" if now >= m.now else "No, it came back down"
        rows.append([
            _model_cell(m.name, m.model_id),
            _e(FIELD_WORDS[m.field]),
            _e(_day(m.now_date)),
            _price_cell(m.now),
            _price_cell(now),
            _e(verdict),
        ])
    if not rows:
        return None
    return {
        "caption": caption,
        "stamp": f"checked against the dated copy sealed {_day(last)}",
        "headers": ["Model", "Which price", "Changed on this read",
                    "Changed to, $ per million", "On our newest copy, $ per million",
                    "Did it stay there?"],
        "rows": rows,
        "moved_col": 5,
    }


# --------------------------------------------------------------------------
# the slices
# --------------------------------------------------------------------------

def _base(slug: str, model_ids: set[str] | None = None) -> dict:
    """The freshness facts every slice carries, read out of the data table."""
    data = _load()
    if model_ids is None:
        dates = data["dates"]
        rows = data["rows_total"]
    else:
        dates = [d for d in data["dates"] if data["by_date"][d].keys() & model_ids]
        rows = sum(len(data["by_date"][d].keys() & model_ids) for d in dates)
    return {
        "slug": slug,
        "newest": dates[-1],
        "oldest": dates[0],
        "runs": len(dates),
        "cadence_days": CADENCE_DAYS,
        "row_count": rows,
    }


def _movers_slice() -> dict | None:
    data = _load()
    dates = data["dates"]
    if len(dates) < 2:
        return None
    a, b = dates[-2], dates[-1]
    pair = sorted([m for m in data["moves"] if (m.was_date, m.now_date) == (a, b)],
                  key=_ratio)
    if not pair:
        return None
    models = {m.model_id for m in pair}
    vendors = {m.vendor for m in pair}
    down = [m for m in pair if m.now < m.was]
    up = [m for m in pair if m.now > m.was]
    biggest = pair[0]

    t1 = _moves_table(
        pair,
        f"Every published price that moved between the copy we sealed on {_day(a)} and the "
        f"copy we sealed on {_day(b)}",
        PAIR_CAP,
        with_date=False,
        stamp=f"{_day(a)} → {_day(b)}",
    )
    t2 = _pair_counts_table(ROW_CAP)
    tables = [t for t in (t1, t2) if t]

    spec = _base("movers")
    spec.update({
        "name": "Last two reads",
        "h1": "Which model prices moved between our last two reads",
        "lede": (
            f"Between the copy we sealed on {_day(a)} and the copy we sealed on {_day(b)}, "
            f"{len(models)} named models changed a published price. Here is every one of them, "
            "with the number before and the number after. The marketplace page shows only the "
            "number after."
        ),
        "desc": (
            f"{len(models)} named AI models changed a published price between {b} and the copy "
            f"before it. Both numbers, read from dated copies."
        )[:155],
        "row_count": len(data["moves"]),
        "tables": tables,
        "facts": [
            f"{len(models)} models across {len(vendors)} vendors changed a published price "
            f"between {_day(a)} and {_day(b)}. That is {len(pair)} separate prices, because a "
            "model can change what it charges for input and for output on the same night.",
            f"{len(down)} of those {len(pair)} prices went down and {len(up)} went up. The "
            f"biggest single move was {_e(biggest.name)}, {FIELD_SHORT[biggest.field]}, "
            f"from {_usd(biggest.was)} to {_usd(biggest.now)} per million tokens, "
            f"{_pct(biggest.was, biggest.now)}.",
            f"Across the whole window we hold {len(data['moves']):,} price moves on "
            f"{len({m.model_id for m in data['moves']}):,} named models, from {_day(dates[0])} "
            f"to {_day(dates[-1])}.",
            f"The newest copy lists {len(data['by_date'][dates[-1]]):,} models. Every price here "
            "is read out of the marketplace's own model list, not out of a vendor's web page.",
            "The live list shows today's number only. Once a price moves, what it said the day "
            "before is gone from the place you would go and look.",
        ],
        "limits": [
            _source_limit(),
            _hash_limit(),
            _why_limit(),
            _gap_limit(),
            _alias_limit(),
            _permission_limit(),
        ],
    })
    return spec


def _direction_slice(down: bool) -> dict | None:
    data = _load()
    dates = data["dates"]
    got = [m for m in data["moves"]
           if m.was != 0 and ((m.now < m.was) if down else (m.now > m.was))]
    if not got:
        return None
    got.sort(key=_ratio, reverse=not down)
    word = "down" if down else "up"
    other = len(data["moves"]) - len(got)
    models = {m.model_id for m in got}
    biggest = got[0]

    t1 = _moves_table(
        got,
        f"The published prices that went {word} the furthest, out of every dated copy we hold",
        ROW_CAP,
    )
    t2 = _stuck_table(
        got,
        f"The same {word}ward moves, checked against our newest copy: did the number stay there?",
        ROW_CAP,
        cut=down,
    )
    tables = [t for t in (t1, t2) if t]
    if not tables:
        return None

    stuck = 0
    held = data["by_date"][dates[-1]]
    for m in got[:ROW_CAP]:
        p = held.get(m.model_id)
        if not p:
            continue
        now = p[1] if m.field == "input" else p[2]
        if now is None:
            continue
        if (now <= m.now) if down else (now >= m.now):
            stuck += 1

    spec = _base("cuts" if down else "rises")
    spec.update({
        "name": "Prices that went down" if down else "Prices that went up",
        "h1": f"Model prices that went {word}",
        "lede": (
            f"We hold {len(got):,} published prices that went {word} between two dated copies, "
            f"across {len(models):,} named models. The biggest was {biggest.name} "
            f"{FIELD_SHORT[biggest.field]}, {_usd(biggest.was)} to {_usd(biggest.now)} per "
            f"million tokens on {_day(biggest.now_date)}. The second table asks the harder "
            "question: did it stay there?"
        ),
        "desc": (
            f"Named AI models whose published price went {word} between two dated copies, biggest "
            f"first, and whether the number stayed there."
        )[:155],
        "row_count": len(got),
        "tables": tables,
        "facts": [
            f"{len(got):,} published prices went {word} across the {len(dates)} dated copies we "
            f"hold, on {len(models):,} named models. {other:,} moves in the same window went the "
            "other way.",
            f"The largest was {biggest.name}, {FIELD_SHORT[biggest.field]}, from "
            f"{_usd(biggest.was)} to {_usd(biggest.now)} per million tokens between "
            f"{_day(biggest.was_date)} and {_day(biggest.now_date)} — {_pct(biggest.was, biggest.now)}.",
            f"Of the {min(ROW_CAP, len(got))} largest shown here, {stuck} are still at or "
            f"{'below' if down else 'above'} the number they moved to on our newest copy, sealed "
            f"{_day(dates[-1])}. The rest came back.",
            f"We hold {len(dates)} dated copies from {_day(dates[0])} to {_day(dates[-1])} and "
            f"{data['rows_total']:,} dated price readings inside them.",
        ],
        "limits": [
            _source_limit(),
            "A big percentage move on a cheap model is a small number of dollars. We show the two "
            "prices as well as the percentage so you can see which one you are looking at.",
            _why_limit(),
            _hash_limit(),
            _gap_limit(),
            _alias_limit(),
        ],
    })
    return spec


def _restless_slice() -> dict | None:
    data = _load()
    dates = data["dates"]
    per = Counter(m.model_id for m in data["moves"])
    if not per:
        return None
    top = [mid for mid, _n in per.most_common(ROW_CAP)]
    rows = []
    for mid in top:
        firsts = next((data["by_date"][d][mid] for d in dates if mid in data["by_date"][d]), None)
        lasts = next((data["by_date"][d][mid] for d in reversed(dates) if mid in data["by_date"][d]), None)
        if not firsts or not lasts:
            continue
        note = ""
        if firsts.inp is not None and lasts.inp is not None and firsts.inp != 0:
            note = _pct(firsts.inp, lasts.inp)
        elif firsts.inp == lasts.inp:
            note = "same as it started"
        rows.append([
            _model_cell(lasts.name, mid),
            _e(_label(mid.split("/")[0])),
            _e(f"{per[mid]:,}"),
            _price_cell(firsts.inp),
            _price_cell(lasts.inp, note),
        ])
    if len(rows) < MIN_ROWS:
        return None
    t1 = {
        "caption": ("The models whose published price will not sit still, counted across every "
                    "dated copy we hold"),
        "stamp": f"{_day(dates[0])} to {_day(dates[-1])}",
        "headers": ["Model", "Listed under", "Times a published price moved",
                    "Input on our first copy, $ per million",
                    "Input on our newest copy, $ per million"],
        "rows": rows,
        "moved_col": 2,
    }

    # The single most restless model, read after read. This is the table that
    # shows what a live price card cannot: the shape of the movement.
    worst = per.most_common(1)[0][0]
    hist_rows = []
    prev = None
    for d in dates:
        p = data["by_date"][d].get(worst)
        if p is None:
            continue
        if prev is None:
            what = "first dated copy we hold of it"
        elif (p.inp, p.out) == (prev.inp, prev.out):
            prev = p
            continue
        else:
            bits = []
            if p.inp != prev.inp:
                bits.append(f"input {_pct(prev.inp, p.inp)}" if prev.inp else "input changed")
            if p.out != prev.out:
                bits.append(f"output {_pct(prev.out, p.out)}" if prev.out else "output changed")
            what = ", ".join(bits)
        hist_rows.append([_e(_day(d)), _price_cell(p.inp), _price_cell(p.out), _e(what)])
        prev = p
    tables = [t1]
    if len(hist_rows) >= MIN_ROWS:
        shown = hist_rows[-ROW_CAP:]
        wname = next((data["by_date"][d][worst].name for d in reversed(dates)
                      if worst in data["by_date"][d]), worst)
        cap = (f"Every dated copy in which {wname} listed a different price from the copy "
               "before it")
        if len(shown) < len(hist_rows):
            cap += f" — the {len(shown)} newest of {len(hist_rows)}, all of them in the file"
        tables.append({
            "caption": cap,
            "stamp": f"{_day(dates[0])} to {_day(dates[-1])}",
            "headers": ["Dated copy", "Input, $ per million tokens",
                        "Output, $ per million tokens", "What changed since the copy before"],
            "rows": shown,
            "moved_col": 3,
        })

    spec = _base("restless")
    spec.update({
        "name": "Models that will not sit still",
        "h1": "The model prices that keep moving",
        "lede": (
            f"Some published prices change once in a quarter. Others change again and again. "
            f"Across {len(dates)} dated copies we hold {per[top[0]]:,} separate price moves on one "
            "model alone. A live price card cannot show you that, because it only ever shows the "
            "latest one."
        ),
        "desc": ("Named AI models whose published price moved most often across our dated copies, "
                 "with the full run for the most restless one.")[:155],
        "row_count": len(data["moves"]),
        "tables": tables,
        "facts": [
            f"{len(per):,} named models changed a published price at least once. "
            f"{sum(1 for n in per.values() if n >= 10):,} of them did it ten times or more.",
            f"The most restless is {next((data['by_date'][d][worst].name for d in reversed(dates) if worst in data['by_date'][d]), worst)}, "
            f"with {per[worst]:,} price moves across the {len(dates)} copies we hold.",
            f"Between them, the models in the first table account for "
            f"{sum(per[m] for m in top):,} of the {len(data['moves']):,} price moves in the window.",
            "Nothing here is a fingerprint of a web page. Every row is a different number in the "
            "marketplace's own model list between two copies we sealed and dated ourselves.",
        ],
        "limits": [
            _source_limit(),
            "A price that moves often is not a price that is going anywhere. Several of these end "
            "the window close to where they started, having been up and down in between, and the "
            "table shows both ends so you can see it.",
            _why_limit(),
            _hash_limit(),
            _gap_limit(),
            _alias_limit(),
        ],
    })
    return spec


def _cheapest_slice() -> dict | None:
    data = _load()
    dates = data["dates"]
    last = dates[-1]
    held = data["by_date"][last]
    paid = [(mid, p) for mid, p in held.items()
            if not mid.startswith("~") and p.inp is not None and p.inp > 0]
    if len(paid) < MIN_ROWS:
        return None
    paid.sort(key=lambda kv: (kv[1].inp, kv[0]))
    free = [(mid, p) for mid, p in held.items()
            if not mid.startswith("~") and p.inp is not None and p.inp == 0
            and p.out is not None and p.out == 0]

    def rows_for(items):
        out = []
        for mid, p in items:
            out.append([
                _model_cell(p.name, mid),
                _e(_label(mid.split("/")[0])),
                _price_cell(p.inp),
                _price_cell(p.out),
                _e(f"{p.context:,} tokens") if p.context else "not listed",
            ])
        return out

    headers = ["Model", "Listed under", "Input, $ per million tokens",
               "Output, $ per million tokens", "Context window it lists"]
    stamp = f"dated copy sealed {_day(last)}"
    t1 = {
        "caption": (f"The lowest published input prices in our newest dated copy — "
                    f"{ROW_CAP} of the {len(paid):,} models that list a price above nothing"),
        "stamp": stamp, "headers": headers, "rows": rows_for(paid[:ROW_CAP]),
        "moved_col": 2,
    }
    t2 = {
        "caption": (f"The highest published input prices in the same dated copy — the top "
                    f"{min(10, len(paid))}"),
        "stamp": stamp, "headers": headers, "rows": rows_for(paid[-10:][::-1]),
        "moved_col": 2,
    }
    tables = [t1, t2]
    if len(free) >= MIN_ROWS:
        cap = f"Models the same copy lists at nothing for both input and output — {len(free)} of them"
        shown = free[:ROW_CAP]
        if len(shown) < len(free):
            cap += f", the first {len(shown)} shown"
        tables.append({
            "caption": cap, "stamp": stamp, "headers": headers,
            "rows": rows_for(shown), "moved_col": None,
        })

    cheapest, dearest = paid[0], paid[-1]
    spread = (dearest[1].inp / cheapest[1].inp) if cheapest[1].inp else None
    # Every entry on the copy has to land in one of these buckets, or the fact
    # below quietly loses models a reader can count for themselves.
    pointers = [mid for mid in held if mid.startswith("~")]
    no_price = [mid for mid in held
                if not mid.startswith("~")
                and mid not in {m for m, _ in paid}
                and mid not in {m for m, _ in free}]
    assert len(pointers) + len(paid) + len(free) + len(no_price) == len(held)
    spec = _base("cheapest")
    spec.update({
        "name": "Cheapest and dearest",
        "h1": "What the cheapest and the dearest models list today",
        "lede": (
            f"On the copy we sealed on {_day(last)} the marketplace listed {len(paid):,} models at "
            f"a price above nothing. The lowest asks {_usd(cheapest[1].inp)} per million input "
            f"tokens and the highest asks {_usd(dearest[1].inp)}. This is what each one publishes, "
            "in one place, on one day."
        ),
        "desc": ("The lowest and highest published input prices in our newest dated copy of the "
                 "model list, with the models named.")[:155],
        "row_count": len(held),
        "tables": tables,
        "facts": [
            f"The newest copy, sealed {_day(last)}, carries {len(held):,} entries and every one "
            f"of them is in this count. {len(paid):,} carry an input price above nothing, "
            f"{len(free):,} are listed at nothing for both input and output, {len(pointers):,} are "
            f"pointer entries that follow whatever the marketplace currently calls the latest "
            f"model, and {len(no_price):,} publish no usable price at all.",
            (f"The dearest input price on that one copy is "
             f"{int(spread.quantize(Decimal('1'))):,} times the cheapest one. Both are on the "
             "same list, on the same day, for the same unit: a million tokens sent in.")
            if spread else "The cheapest model on that copy lists an input price of nothing.",
            f"{cheapest[1].name} lists {_usd(cheapest[1].inp)} per million input tokens. "
            f"{dearest[1].name} lists {_usd(dearest[1].inp)}. Both numbers are read out of the "
            "same dated copy.",
            "This is a list of published prices, not a ranking of vendors and not a judgement "
            "about any of them. We sort by the number the marketplace prints and nothing else.",
        ],
        "limits": [
            _source_limit(),
            "This page cannot tell you which model is good enough for your job. We hold prices. We "
            "hold no benchmark, no quality score and no opinion, and a cheap model that needs three "
            "tries costs more than a dear one that needs one.",
            "A model listed at nothing is not free of limits. The list does not tell us the rate "
            "limits, the queue, or how long that price lasts, so we do not guess at any of them.",
            "Input and output are priced separately and the ratio between them is not the same for "
            "every model. Sorting by input alone will not tell you what a job costs.",
            _alias_limit(),
            _permission_limit(),
            _gap_limit(),
        ],
    })
    return spec


def _vendor_slice(vendor: str) -> dict | None:
    data = _load()
    dates = data["dates"]
    last = dates[-1]
    mine = {mid for mid in data["by_date"][last] if mid.split("/")[0] == vendor}
    if len(mine) < MIN_VENDOR_MODELS:
        return None
    if not SLUG_OK.match(vendor):
        return None
    label = _label(vendor)
    ever = {mid for d in dates for mid in data["by_date"][d] if mid.split("/")[0] == vendor}
    moves = sorted([m for m in data["moves"] if m.vendor == vendor],
                   key=lambda m: (m.now_date, m.model_id), reverse=True)
    movers = {m.model_id for m in moves}

    tables = []
    t1 = _moves_table(
        moves,
        f"Every published {label} price that moved between two dated copies, newest first",
        ROW_CAP,
    )
    if t1:
        tables.append(t1)
    t2 = _held_table(
        sorted(mine),
        f"What our newest dated copy lists for {label}, cheapest input first",
        ROW_CAP,
    )
    if t2:
        tables.append(t2)
    if not tables:
        return None

    quiet = not moves
    if quiet:
        lede = (
            f"Across {len(dates)} dated copies from {_day(dates[0])} to {_day(dates[-1])}, not one "
            f"{label} published price has moved. That is a real answer and we would rather print it "
            f"than dress an unchanged list up as a feed. The table shows what the newest copy lists."
        )
        desc = (f"{label} published model prices have not moved across the {len(dates)} dated "
                f"copies we hold. What the newest copy lists.")
        h1 = f"{label} list prices, and the fact that they have not moved"
    else:
        down = sum(1 for m in moves if m.now < m.was)
        lede = (
            f"{label} has {len(mine)} models on the copy we sealed on {_day(last)}. Across the "
            f"{len(dates)} copies we hold, {len(movers)} of its models changed a published price "
            f"{len(moves)} times — {down} of those went down. Here they are, named, with both "
            "numbers."
        )
        desc = (f"Named {label} models whose published price moved between two dated copies, with "
                f"the number before and after. Newest copy {last}.")
        h1 = f"What moved in {label} list prices"

    facts = [
        f"Our newest dated copy, sealed {_day(last)}, lists {len(mine)} {label} models. Across the "
        f"whole window we have seen {len(ever)} of them.",
        f"{len(movers)} of those models changed a published price at least once, across "
        f"{len(moves)} separate moves." if moves else
        f"None of those models has changed a published price in the {len(dates)} copies we hold.",
        f"We hold {len(dates)} dated copies from {_day(dates[0])} to {_day(dates[-1])}, and "
        f"{sum(1 for d in dates for mid in data['by_date'][d] if mid.split('/')[0] == vendor):,} "
        f"dated price readings for {label} inside them.",
    ]
    if moves:
        big = min(moves, key=_ratio)
        facts.append(
            f"The largest {label} move we hold is {big.name}, {FIELD_SHORT[big.field]}, "
            f"from {_usd(big.was)} to {_usd(big.now)} per million tokens on {_day(big.now_date)} — "
            f"{_pct(big.was, big.now)}."
        )
        newest_move = max(m.now_date for m in moves)
        facts.append(
            f"The most recent {label} price move we hold is dated {_day(newest_move)}."
        )

    spec = _base(vendor, mine | ever)
    spec.update({
        "name": label,
        "h1": h1,
        "lede": lede,
        "desc": desc[:155],
        "tables": tables,
        "facts": facts[:6],
        "limits": [
            _source_limit(),
            f"This is what one marketplace publishes for {label}. It is not a quote from "
            f"{label} and it is not a contract price. If you buy direct, your number may be a "
            "different number and we cannot see it.",
            _permission_limit(),
            _hash_limit(),
            _why_limit(),
            _gap_limit(),
        ],
    })
    return spec


def _coverage_slice() -> dict | None:
    data = _load()
    dates = data["dates"]
    last = dates[-1]
    held = data["by_date"][last]

    lane_rows = []
    for src in sorted(data["hashes"]):
        what, publishes, note = LANES.get(src, ("A source in this clock", False, ""))
        h = data["hashes"][src]
        answer = note or (NO_PUBLISH if not publishes else "Yes")
        lane_rows.append([
            _e(src.replace("_", " ")),
            _e(what),
            _e(f"{h['reads']} dated copies"),
            _e(_day(h["newest"])) if h["newest"] else "none",
            answer,
            _e(f"{h['flips']} of {h['gaps']}"),
        ])
    t1 = {
        "caption": ("Every lane in this clock, what it is, and whether a published price is ever "
                    "allowed to come out of it"),
        "stamp": f"{_day(dates[0])} to {_day(last)}",
        "headers": ["Lane", "What it is", "Dated copies we hold", "Newest dated copy",
                    "Do we publish prices from it?",
                    "Gaps where the page itself came back different"],
        "rows": lane_rows,
        "moved_col": 5,
    }

    by_vendor: dict[str, set[str]] = defaultdict(set)
    for mid in held:
        if not mid.startswith("~"):
            by_vendor[mid.split("/")[0]].add(mid)
    moved: dict[str, set[str]] = defaultdict(set)
    newest_move: dict[str, str] = {}
    for m in data["moves"]:
        moved[m.vendor].add(m.model_id)
        if m.now_date > newest_move.get(m.vendor, ""):
            newest_move[m.vendor] = m.now_date
    order = sorted(by_vendor, key=lambda v: (-len(by_vendor[v]), v))
    shown = order[:24]
    vendor_rows = []
    for v in shown:
        vendor_rows.append([
            _e(_label(v)),
            f'{_e(f"{len(by_vendor[v]):,}")}<span class="sub">{_e(v)}</span>',
            _e(f"{len(moved.get(v, ())):,}"),
            _e(_day(newest_move[v])) if v in newest_move else "no move on record",
            "Yes" if len(by_vendor[v]) >= MIN_VENDOR_MODELS else
            f"No — we hold fewer than {MIN_VENDOR_MODELS} of its models",
        ])
    cap2 = ("Who is on the newest dated copy, how many of their models we hold, and how many of "
            "those have ever changed a published price")
    if len(shown) < len(order):
        cap2 += f" — the {len(shown)} largest of {len(order)}, all of them in the file"
    t2 = {
        "caption": cap2,
        "stamp": f"dated copy sealed {_day(last)}",
        "headers": ["Listed under", "Models on our newest copy",
                    "Models whose price has ever moved", "Newest price move we hold",
                    "Has its own page here?"],
        "rows": vendor_rows,
        "moved_col": 2,
    }

    gaps = _gaps()
    tables = [t1, t2]
    if len(gaps) >= MIN_ROWS:
        gap_rows = [[
            _e(_day(g)),
            "nothing sealed that day",
            _e(_day(_nearest(g, True))) if _nearest(g, True) != "none" else "none",
            _e(_day(_nearest(g, False))) if _nearest(g, False) != "none" else "none",
        ] for g in gaps]
        tables.append({
            "caption": ("Days inside the window we hold no dated copy for, named rather than "
                        "quietly skipped"),
            "stamp": f"{len(gaps)} days out of {(date.fromisoformat(last) - date.fromisoformat(dates[0])).days + 1}",
            "headers": ["Day in the window", "What we hold for it",
                        "Nearest dated copy before it", "Nearest dated copy after it"],
            "rows": gap_rows,
            "moved_col": None,
        })

    src, h = _noisiest()
    pair_moves = len({m.model_id for m in data["moves"] if m.now_date == last})
    spec = _base("coverage")
    spec.update({
        "name": "What this feed covers",
        "h1": "What the AI price feed covers, and what it does not",
        "lede": (
            "Every lane this clock reads, which one the prices actually come from, which vendors "
            "are on the newest copy, and every day in the window we hold nothing for. If the model "
            "you follow is not here, this page is where you find that out before you pay."
        ),
        "desc": ("Which lanes the AI price feed reads, which vendors are on the newest dated copy, "
                 "and the days we hold nothing for.")[:155],
        "row_count": data["rows_total"],
        "tables": tables,
        "facts": [
            f"This feed holds {data['rows_total']:,} dated price readings on "
            f"{len({mid for d in dates for mid in data['by_date'][d]}):,} models, across "
            f"{len(dates)} dated copies from {_day(dates[0])} to {_day(last)}. "
            f"{data['runs_total']} collection runs produced those copies — some days ran more than "
            "once, which is why the two numbers differ.",
            f"Prices come from one lane only: the marketplace's own machine-readable model list. "
            f"The other {len(data['hashes']) - 1} lanes in the first table produce no price on this "
            "site at all.",
            (f"Why that matters: the noisiest vendor price page in this clock came back with a "
             f"different fingerprint across {h['flips']} of the {h['gaps']} gaps between our reads. "
             f"A published model price moved across the newest gap for {pair_moves} models. "
             "Fingerprints are not prices.") if h else
            "Prices come from the model list and never from a page fingerprint.",
            f"{len({m.model_id for m in data['moves']}):,} named models have changed a published "
            f"price at least once, across {len(data['moves']):,} moves. The rest have not moved, "
            "and we say so on their vendor's page rather than leaving it blank.",
            f"A vendor gets its own page here once we hold {MIN_VENDOR_MODELS} or more of its "
            "models on the newest copy. Below that a page would be a headline and three rows, so "
            "we do not make one.",
        ],
        "limits": [
            "This feed covers the models on one marketplace's public list and nothing else. A model "
            f"served only direct by its vendor is not here. If the one you follow is missing, email "
            f"{MAIL} and we will tell you straight whether we can collect it.",
            _permission_limit(),
            _source_limit(),
            _gap_limit(),
            _alias_limit(),
            _noise_limit(),
            "The display name a vendor is listed under can change without the vendor changing. One "
            "of them is listed under a different name in our newer copies than in our older ones. "
            "We take the name from the copy, so the older rows keep the older name.",
        ],
    })
    return spec


# --------------------------------------------------------------------------
# the family page's own evidence block
# --------------------------------------------------------------------------

def family_block(shipped: list[dict] | None = None, here: str = HERE) -> str:
    """The movers table that sits on /feeds/ai-prices itself.

    A family page is written by hand, so anything typed into one stays there
    after it stops being true. This block is rewritten out of the database on
    every build instead. It uses the same evidence markup as every other table
    on the site.
    """
    data = _load()
    dates = data["dates"]
    a, b = dates[-2], dates[-1]
    # Biggest move first, up or down. Sorting on the signed ratio puts every cut
    # at the top and pushes every rise off the bottom of a shortened table, which
    # is how a table captioned "every move" ends up showing one direction only.
    pair = sorted([m for m in data["moves"] if (m.was_date, m.now_date) == (a, b)],
                  key=lambda m: (-abs(_ratio(m)), m.name, m.field))
    models = {m.model_id for m in pair}
    ups = sum(1 for m in pair if m.now > m.was)
    downs = len(pair) - ups
    shown = pair[:FAMILY_ROWS]
    whole = len(shown) == len(pair)
    head_line = ("Every published price that moved between our last two dated copies"
                 if whole else
                 f"The {len(shown)} biggest of the {len(pair)} published price moves between "
                 "our last two dated copies")
    src, h = _noisiest()

    body = ""
    for m in shown:
        body += (
            "<tr>"
            f'<td>{_model_cell(m.name, m.model_id)}</td>'
            f"<td>{_e(FIELD_WORDS[m.field])}</td>"
            f"<td>{_e(_usd(m.was))}</td>"
            f'<td class="moved">{_e(_usd(m.now))}</td>'
            f"<td>{_e(_pct(m.was, m.now))}</td>"
            "</tr>\n              "
        )
    more = (f" {downs} of the {len(pair)} went down and {ups} went up.")
    if not whole:
        more += (f" The {len(shown)} biggest moves of the {len(pair)} are above, largest first "
                 f"whichever way they went; the rest are in "
                 f'<a href="{here}movers">the full table</a>.')
    else:
        more += (f' All {len(pair)} are above, largest first whichever way they went. '
                 f'<a href="{here}movers">The full table</a> carries the same set.')

    kids = ""
    if shipped:
        # The way in to every child page, written from the pages that actually
        # shipped this run. A slice that dropped under the five-row floor loses
        # its page, and it has to lose its link on the same build or the parent
        # starts pointing at a 404.
        items = ""
        for k in shipped:
            if k["slug"] == "coverage":
                continue
            items += (f'\n        <li><a href="{here}{k["slug"]}">{_e(k["h1"])}</a>'
                      f'<span class="sub">{_e(k["desc"])}</span></li>')
        items += (f'\n        <li><a href="{here}coverage">What this feed covers, and what it '
                  'does not</a><span class="sub">Every lane we read, every vendor on the newest '
                  'copy, and every day we hold nothing for.</span></li>')
        kids = f"""

      <h3>Every page in this feed</h3>
      <ul class="spec">{items}
      </ul>"""

    return f"""      <div class="evidence">
        <div class="evidence-head">
          <span>{_e(head_line)}</span>
          <span class="stamp">{_e(_day(a))} → {_e(_day(b))}</span>
        </div>
        <div class="scroll">
          <table>
            <thead>
              <tr><th>Model</th><th>Which price</th><th>Was, $ per million tokens</th><th>Now, $ per million tokens</th><th>Change</th></tr>
            </thead>
            <tbody>
              {body.rstrip()}
            </tbody>
          </table>
        </div>
      </div>

      <p class="note">{len(models)} named models changed a published price between the copy we
        sealed on {_e(_day(a))} and the copy we sealed on {_e(_day(b))}. That is {len(pair)} separate
        prices, because a model can change what it charges for input and for output on the same
        night.{more} Dollars per million tokens is us multiplying out the per-token number the list
        publishes; the exact per-token string is what goes in the file.</p>

      <div class="honest">
        <p><strong>What this table is not.</strong> This clock also saves a fingerprint of some
        vendors&rsquo; own price pages. The noisiest of them came back different across
        {h['flips']} of the {h['gaps']} gaps between our {h['reads']} reads, because a banner or a
        footer changing moves a fingerprint. Not one number above comes from a fingerprint. Every
        one is a different figure in the marketplace&rsquo;s own machine-readable model list
        between two copies we sealed and dated ourselves.</p>
      </div>{kids}"""


def write_family_block(shipped: list[dict] | None = None) -> bool:
    """Put today's movers table on the family page. Never fails a build."""
    try:
        raw = FAMILY_PAGE.read_text(encoding="utf-8")
    except OSError as e:
        print(f"slice_ai_prices: could not read the family page: {e!r}", file=sys.stderr)
        return False
    if BLOCK_START not in raw or BLOCK_END not in raw:
        print("slice_ai_prices: the family page has no evidence markers; left it alone",
              file=sys.stderr)
        return False
    # Where this page is actually published, read off its own canonical link.
    # Sibling links have to be written from the site root, not as "movers/": the
    # server hands out this page at /feeds/ai-prices with no trailing slash and
    # no redirect, so a browser reads "movers/" as /feeds/movers/ and lands on a
    # 404. Reading the prefix off the page means it cannot drift from where the
    # page is really served.
    here = HERE
    can = re.search(r'<link rel="canonical" href="https?://[^/"]+([^"]*)"', raw)
    if can:
        here = can.group(1).rstrip("/") + "/"
    head, rest = raw.split(BLOCK_START, 1)
    _old, tail = rest.split(BLOCK_END, 1)
    out = f"{head}{BLOCK_START}\n{family_block(shipped, here)}\n      {BLOCK_END}{tail}"
    if out != raw:
        FAMILY_PAGE.write_text(out, encoding="utf-8")
    return True


# --------------------------------------------------------------------------

def _real_rows(s: dict) -> int:
    return sum(len(t["rows"]) for t in s["tables"])


def _vendors() -> list[str]:
    data = _load()
    last = data["dates"][-1]
    counts = Counter(mid.split("/")[0] for mid in data["by_date"][last]
                     if not mid.startswith("~"))
    return [v for v, n in counts.most_common()
            if n >= MIN_VENDOR_MODELS and SLUG_OK.match(v)]


def slices() -> list[dict]:
    """Every ai-prices slice that has enough real named rows to ship."""
    wanted = [
        ("coverage", _coverage_slice, ()),
        ("movers", _movers_slice, ()),
        ("cuts", _direction_slice, (True,)),
        ("rises", _direction_slice, (False,)),
        ("restless", _restless_slice, ()),
        ("cheapest", _cheapest_slice, ()),
    ] + [(v, _vendor_slice, (v,)) for v in _vendors()]

    out = []
    for label, fn, args in wanted:
        s = fn(*args)
        if s is None:
            print(f"slice_ai_prices: dropped {label} — the database does not carry enough "
                  "for an honest page", file=sys.stderr)
            continue
        n = _real_rows(s)
        if n < MIN_ROWS:
            print(f"slice_ai_prices: dropped {s['slug']} — only {n} real rows, floor is "
                  f"{MIN_ROWS}", file=sys.stderr)
            continue
        out.append(s)

    # The family page's own table is rewritten from the same read, so the parent
    # and its children can never disagree about what moved last night.
    try:
        write_family_block(out)
    except Exception as e:  # never take a build down over the parent page
        print(f"slice_ai_prices: could not refresh the family page block: {e!r}",
              file=sys.stderr)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """A real extract of the product: the newest published price moves.

    The raw per-token string is the sealed reading and it is the first thing in
    the row. The dollars-per-million columns are the same number multiplied out.
    """
    data = _load()
    headers = ["model_id", "model_name", "listed_under", "which_price",
               "sealed_copy_before", "sealed_copy_after",
               "raw_per_token_before", "raw_per_token_after",
               "usd_per_million_before", "usd_per_million_after", "change"]
    rows = []
    for m in sorted(data["moves"], key=lambda m: (m.now_date, m.model_id), reverse=True)[:25]:
        rows.append([
            m.model_id, m.name, _label(m.vendor), m.field,
            m.was_date, m.now_date,
            format(m.was, "f"), format(m.now, "f"),
            _usd(m.was).replace("$", "").replace("about ", ""),
            _usd(m.now).replace("$", "").replace("about ", ""),
            _pct(m.was, m.now),
        ])
    return headers, rows


# --------------------------------------------------------------------------

BANNED = ["get started", "soc 2", "fortune 500", "hipaa", "leverage", "robust",
          "seamless", "comprehensive", "unlock", "empower", "powerful",
          "best-in-class", "world-class", "grade a", "score of"]


def _visitor_text(s: dict) -> str:
    bits = [s["name"], s["h1"], s["lede"], s["desc"]] + s["facts"] + s["limits"]
    for t in s["tables"]:
        bits += [t["caption"], t["stamp"]] + t["headers"]
        for row in t["rows"]:
            bits += [str(c) for c in row]
    return " ".join(str(b) for b in bits).lower()


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
        print(f"{s['slug']:16} {_real_rows(s):>3} rows shown · {s['row_count']:>7,} held · "
              f"newest {s['newest']} · {len(s['tables'])} tables")
    print(f"\n{len(got)} slices, {bad} problems")
    raise SystemExit(1 if bad else 0)
