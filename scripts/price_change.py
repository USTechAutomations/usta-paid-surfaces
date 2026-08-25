"""Tell a real price change from a page that only looks different.

WHY THIS EXISTS

The B2B price-page feed was taken off sale on 2026-08-22 with this written
against it: "the change detector fingerprints the whole page, so an edit
anywhere reads as a price change". That is true of the raw body hash, and it
is still half-true of the price-fact signature in ``dom_diff.py``, which
improves on the body hash but keys on a bare SET of currency amounts with no
idea which plan any of them belongs to. Run over the sealed archive on
2026-08-24 that detector returned five CONFIRMED_ONE_WAY transitions on the
pricing lane. Read by hand, one of the five was a price:

  * secureframe.com  "Fundamentals -- Starting at $5,000/year" became
    "Starting at $7,000/year".  A price.
  * moderntreasury.com  "...powered $400 billion in payments" became
    "$600 billion in payments".  A marketing statistic in a sentence.
  * clickup.com and planetscale.com  amounts DISAPPEARED and none arrived.
    A page that stopped printing numbers is not a page that repriced.
  * runwayml.com  every amount and cadence on the page moved at once, which
    is a page rebuild, not a repricing anyone can name.

So a set of loose amounts is not enough. A price belongs to a PLAN, and the
only claim this feed can honestly sell is "this named plan cost X on this
date and Y on that date".

WHAT THIS KEYS ON

For every currency amount in the visible DOM text this module keeps three
things: the plan LABEL it sits under (the nearest preceding heading), the
canonical amount, and the cadence.  The fingerprint is a hash of that set.
Consequences, which are the four things the estate rule asks for:

  * an unrelated edit elsewhere on the page -- new hero copy, a rotated
    customer quote, a fresh nonce -- leaves every (label, amount, cadence)
    triple untouched, so the fingerprint does not move;
  * an amount changing under a label that is still there IS a price change;
  * a price card moved to a different position on the page keeps its label
    and its amount, so the fingerprint does not move;
  * a host with no usable snapshots is UNKNOWN.  Never "no change".

And two rejections that are the difference between the four bullets above:

  * an amount followed by a magnitude word -- billion, million, trillion --
    is a statistic, not a price, and is dropped.  This is what separates
    secureframe from moderntreasury;
  * an amount with no cadence marker sitting inside a long block of prose is
    dropped.  A price card line is short.  A sentence is not.

A label that appears on only one side of a transition is a plan ADDED or a
plan REMOVED, and neither is reported as a price change.  A transition where
no surviving label changed amount is ``NO_PRICE_CHANGE`` even though the
fingerprint moved, because the fingerprint moving is the page changing and
this feed does not sell that.

WHAT IT NEVER DOES

It never writes to the archive, never fetches anything, and never reads a
body that the seal did not cover.  Truncated bodies are UNKNOWN, not zero:
the 256 KiB cap can land mid-price-table and where it lands moves between
reads.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
import zlib
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence

# Two identical reads on each side of a move. One read either side of a change
# is one read either side of a bad afternoon at their end.
MIN_STABLE_OBSERVATIONS = 2

# Subtrees that are never visible price text.
_SKIP_TAGS = {"canvas", "head", "noscript", "script", "style", "svg", "template"}

# Block-level tags. Text is cut at these, so "Starting at $7,000/year" is one
# line and the paragraph after it is another.
_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

_PRICE_RE = re.compile(
    r"(?<![\w])(?:"
    r"(?P<symbol>[$€£¥])\s*"
    r"(?P<amount_a>\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)"
    r"(?P<scale>[kKmM])?"
    r"|"
    r"(?P<amount_b>\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)\s*"
    r"(?P<code>USD|EUR|GBP|CAD|AUD)"
    r")"
    r"(?:\s*(?P<cadence>/\s*(?:mo(?:nth)?|yr|year|user|seat)"
    r"|per\s+(?:month|year|user|seat)"
    r"|a\s+(?:month|year)))?",
    re.IGNORECASE,
)

# "$400 billion in payments" is a claim about somebody else's money.
_MAGNITUDE_RE = re.compile(
    r"^\s*(?:billion|billions|million|millions|trillion|trillions|bn)\b",
    re.IGNORECASE,
)

# How long a line may be before an amount inside it stops looking like a price
# card and starts looking like a sentence. Only applied when no cadence marker
# is attached; "$29/month" is a price wherever it sits.
PROSE_LINE_CHARS = 120

# A label longer than this is a paragraph that happened to be marked up as a
# heading, and pinning a price to it would make the pairing meaningless.
MAX_LABEL_CHARS = 60


class DetectorUnavailable(RuntimeError):
    """The archive cannot support a truthful answer."""


@dataclass(frozen=True, order=True)
class PlanPrice:
    """One named plan's price on one dated read."""

    plan_label: str
    currency: str
    amount: str
    cadence: str

    def as_row(self) -> dict[str, str]:
        return {
            "plan_label": self.plan_label,
            "currency": self.currency,
            "amount": self.amount,
            "cadence": self.cadence,
        }


@dataclass(frozen=True)
class Reading:
    """What one dated snapshot of one address said, or that it said nothing."""

    snapshot_date: str
    fingerprint: str | None          # None means UNKNOWN, never "no prices"
    prices: tuple[PlanPrice, ...] = ()
    reason: str = ""                 # why it is UNKNOWN, when it is
    # What the amount was charged FOR, as printed, with the number taken out:
    # "per 100k", "per cert / month". Deliberately NOT in the fingerprint --
    # the same price re-wrapped across two lines prints a different unit and
    # that is not a price change. It is a guard applied when a move is
    # reported, so a number that changed unit is never sold as old -> new.
    units: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Regime:
    first_date: str
    last_date: str
    fingerprint: str
    observations: int
    prices: tuple[PlanPrice, ...]
    units: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class PriceMove:
    """One plan's price moving between two dated reads. This is the product."""

    domain: str = ""
    resource: str = ""
    plan_label: str = ""
    currency: str = ""
    old_amount: str = ""
    new_amount: str = ""
    cadence: str = ""
    last_seen_old: str = ""
    first_seen_new: str = ""
    change_date: str | None = None
    reads_at_old_price: int = 0
    reads_at_new_price: int = 0
    old_unit: str = ""
    new_unit: str = ""
    verdict: str = ""


# ---------------------------------------------------------------- the parser

class _LabelledTextParser(HTMLParser):
    """Visible text cut into block lines, each carrying the heading above it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked: list[str] = []
        self._buffer: list[str] = []
        self._in_heading = 0
        self._heading_buffer: list[str] = []
        self._label = ""
        self.lines: list[tuple[str, str]] = []   # (label, line text)

    # -- block bookkeeping --------------------------------------------------
    def _flush(self) -> None:
        text = " ".join(" ".join(self._buffer).split())
        self._buffer.clear()
        if text:
            self.lines.append((self._label, text))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        hidden = any(
            key.lower() == "hidden"
            or (key.lower() == "aria-hidden" and str(value).lower() == "true")
            for key, value in attrs
        )
        if self._blocked or lowered in _SKIP_TAGS or hidden:
            self._blocked.append(lowered)
            return
        if lowered in _BLOCK_TAGS:
            self._flush()
        if lowered in _HEADING_TAGS:
            self._in_heading += 1
            self._heading_buffer.clear()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._blocked and tag.lower() in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._blocked:
            if lowered == self._blocked[-1]:
                self._blocked.pop()
            return
        if lowered in _BLOCK_TAGS:
            self._flush()
        if lowered in _HEADING_TAGS and self._in_heading:
            self._in_heading -= 1
            heading = " ".join(" ".join(self._heading_buffer).split())
            self._heading_buffer.clear()
            # A heading that is really a paragraph is not a plan name.
            if heading and len(heading) <= MAX_LABEL_CHARS:
                self._label = heading

    def handle_data(self, data: str) -> None:
        if self._blocked:
            return
        self._buffer.append(data)
        if self._in_heading:
            self._heading_buffer.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def labelled_lines(body: bytes) -> tuple[tuple[str, str], ...]:
    """(plan label, visible line) pairs, unicode- and whitespace-normalized."""

    parser = _LabelledTextParser()
    try:
        parser.feed(body.decode("utf-8", "replace"))
        parser.close()
    except (UnicodeError, ValueError):
        # A body the parser cannot consume is UNKNOWN, never a partial answer.
        return ()
    out = []
    for label, line in parser.lines:
        text = " ".join(unicodedata.normalize("NFKC", line).split())
        tag = " ".join(unicodedata.normalize("NFKC", label).split())
        if text:
            out.append((tag, text))
    return tuple(out)


# ------------------------------------------------------------ price picking

def _canonical_amount(raw: str, scale: str | None, cadence: str | None) -> str | None:
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    if scale:
        # "$5k/mo" is a price. "$5M raised" is not, and without a cadence
        # marker a letter suffix is far more often the second one.
        if not cadence:
            return None
        value *= Decimal(1_000 if scale.lower() == "k" else 1_000_000)
    rendered = format(value.normalize(), "f")
    return rendered or "0"


def _cadence(raw: str | None) -> str:
    compact = re.sub(r"\s+", "", (raw or "").lower())
    if "mo" in compact or "month" in compact:
        return "month"
    if "yr" in compact or "year" in compact:
        return "year"
    if "user" in compact or "seat" in compact:
        return "seat"
    return "unspecified"


MAX_UNIT_CHARS = 80


def _unit_text(line: str, start: int, end: int) -> str:
    """The price line with the number taken out: what the money buys.

    "$1 per 100k" and "$0.10 per 100k" share a unit, so one really did become
    the other. "$200 per cert / month" and "$0.27 per domain per active hour"
    do not, and calling that pair "$200 became $0.27" would be a lie told with
    two true numbers.
    """

    stripped = (line[:start] + " " + line[end:]).strip()
    return " ".join(stripped.lower().split())[:MAX_UNIT_CHARS]


def extract(body: bytes) -> tuple[tuple[PlanPrice, ...], dict[PlanPrice, frozenset]]:
    """Named plan prices, and the printed unit each one was charged in."""

    found: set[PlanPrice] = set()
    units: dict[PlanPrice, set[str]] = defaultdict(set)
    for label, line in labelled_lines(body):
        if not label:
            continue                      # an unlabelled amount names no plan
        for match in _PRICE_RE.finditer(line):
            tail = line[match.end():]
            if _MAGNITUDE_RE.match(tail):
                continue                  # "$400 billion in payments"
            cadence_raw = match.group("cadence")
            if not cadence_raw and len(line) > PROSE_LINE_CHARS:
                continue                  # an amount adrift in a sentence
            amount = _canonical_amount(
                match.group("amount_a") or match.group("amount_b"),
                match.group("scale"),
                cadence_raw,
            )
            if amount is None:
                continue
            symbol = match.group("symbol")
            currency = _CURRENCY.get(symbol, (match.group("code") or "").upper())
            price = PlanPrice(label, currency, amount, _cadence(cadence_raw))
            found.add(price)
            units[price].add(_unit_text(line, match.start(), match.end()))
    return tuple(sorted(found)), {k: frozenset(v) for k, v in units.items()}


def plan_prices(body: bytes) -> tuple[PlanPrice, ...]:
    """Every named plan price the visible text carries, canonicalized."""

    return extract(body)[0]


def fingerprint(prices: Sequence[PlanPrice]) -> str | None:
    """Hash the named prices. No named price is UNKNOWN, never zero."""

    if not prices:
        return None
    payload = json.dumps(
        [[p.plan_label, p.currency, p.amount, p.cadence] for p in sorted(prices)],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_body(body: bytes, snapshot_date: str = "") -> Reading:
    prices, units = extract(body)
    return Reading(snapshot_date, fingerprint(prices), prices,
                   "" if prices else "no named plan price in the visible text",
                   units)


# ------------------------------------------------------------- the sequence

def regimes(readings: Sequence[Reading],
            *, min_stable: int = MIN_STABLE_OBSERVATIONS) -> tuple[Regime, ...]:
    """Runs of identical fingerprints. UNKNOWN breaks the run, never joins it."""

    out: list[Regime] = []
    current: Regime | None = None
    for item in readings:
        if item.fingerprint is None:
            if current is not None:
                out.append(current)
                current = None
            continue
        if current is not None and current.fingerprint == item.fingerprint:
            current = Regime(current.first_date, item.snapshot_date,
                             current.fingerprint, current.observations + 1,
                             current.prices, current.units)
        else:
            if current is not None:
                out.append(current)
            current = Regime(item.snapshot_date, item.snapshot_date,
                             item.fingerprint, 1, item.prices, item.units)
    if current is not None:
        out.append(current)
    return tuple(r for r in out if r.observations >= min_stable)


def _next_day(before: str, after: str) -> str | None:
    try:
        return after if date.fromisoformat(after) == date.fromisoformat(before) + timedelta(days=1) else None
    except ValueError:
        return None


def _returns_later(readings: Sequence[Reading], price: PlanPrice, after: str) -> bool:
    return any(r.snapshot_date > after and price in r.prices for r in readings)


def _seen_earlier(readings: Sequence[Reading], price: PlanPrice, before: str) -> bool:
    return any(r.snapshot_date < before and price in r.prices for r in readings)


def price_moves(domain: str, resource: str, readings: Sequence[Reading],
                *, min_stable: int = MIN_STABLE_OBSERVATIONS,
                include_refused: bool = False) -> tuple[PriceMove, ...]:
    """Named plans whose price moved, and nothing else.

    Four things are NOT a price change and none of them comes back from here
    unless a caller asks to see what was refused and why:

      * a label on one side only -- a plan was added or withdrawn;
      * a transition where no surviving label changed amount -- the page moved
        and its prices did not, which is the whole reason this module exists;
      * the old price coming back later, or the new one having been seen
        before. Snyk's Team plan read $25 a month, then $750 for three days,
        then $25 again. Something happened; a repricing is not what we can
        prove happened, so we do not sell it as one;
      * the unit changing with the number. ngrok's certificate line went from
        $200 per cert per month to $0.27 per domain per active hour. Both
        numbers are real and "$200 became $0.27" is not true of anything.
    """

    stable = regimes(readings, min_stable=min_stable)
    out: list[PriceMove] = []
    for before, after in zip(stable, stable[1:]):
        if before.fingerprint == after.fingerprint:
            continue
        old_by_label: dict[str, set[PlanPrice]] = defaultdict(set)
        new_by_label: dict[str, set[PlanPrice]] = defaultdict(set)
        for price in before.prices:
            old_by_label[price.plan_label].add(price)
        for price in after.prices:
            new_by_label[price.plan_label].add(price)
        for label in sorted(set(old_by_label) & set(new_by_label)):
            old, new = old_by_label[label], new_by_label[label]
            if old == new:
                continue
            # Pair on (currency, cadence) so a monthly price moving is not
            # matched against the annual one printed beside it.
            old_keyed = {(p.currency, p.cadence): p for p in old}
            new_keyed = {(p.currency, p.cadence): p for p in new}
            if len(old) != len(old_keyed) or len(new) != len(new_keyed):
                continue   # two prices share a slot; we cannot say which moved
            for key in sorted(set(old_keyed) & set(new_keyed)):
                was, now = old_keyed[key], new_keyed[key]
                if was.amount == now.amount:
                    continue
                old_units = before.units.get(was, frozenset())
                new_units = after.units.get(now, frozenset())
                flapped = (_returns_later(readings, was, after.first_date)
                           or _seen_earlier(readings, now, before.last_date))
                if flapped:
                    verdict = "AMBIGUOUS_FLAP"
                elif old_units & new_units:
                    verdict = "PRICE_CHANGED"
                else:
                    verdict = "REFUSED_UNIT_ALSO_CHANGED"
                move = PriceMove(
                    domain=domain, resource=resource, plan_label=label,
                    currency=was.currency, old_amount=was.amount,
                    new_amount=now.amount, cadence=was.cadence,
                    last_seen_old=before.last_date,
                    first_seen_new=after.first_date,
                    change_date=_next_day(before.last_date, after.first_date),
                    reads_at_old_price=before.observations,
                    reads_at_new_price=after.observations,
                    old_unit=" | ".join(sorted(old_units)),
                    new_unit=" | ".join(sorted(new_units)),
                    verdict=verdict)
                if verdict == "PRICE_CHANGED" or include_refused:
                    out.append(move)
    return tuple(out)


def verdict_for(domain: str, resource: str, readings: Sequence[Reading],
                *, min_stable: int = MIN_STABLE_OBSERVATIONS) -> str:
    """UNKNOWN / NO_PRICE_CHANGE / PRICE_CHANGED for one address."""

    if not readings or all(r.fingerprint is None for r in readings):
        return "UNKNOWN"
    if price_moves(domain, resource, readings, min_stable=min_stable):
        return "PRICE_CHANGED"
    return "NO_PRICE_CHANGE"


# ----------------------------------------------------------- the sealed store

def connect_read_only(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file() or path.is_symlink():
        raise DetectorUnavailable(f"archive missing or non-regular: {path}")
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise DetectorUnavailable(str(exc)) from exc


def readings_from_store(conn: sqlite3.Connection,
                        resources: Iterable[str] = ("pricing", "plans"),
                        ) -> dict[tuple[str, str], list[Reading]]:
    """Every dated read of every price address, as Readings. Read-only."""

    marks = ",".join("?" * len(tuple(resources)))
    rows = conn.execute(
        f"SELECT p.domain,p.resource,p.snapshot_date,p.status_code,p.fetch_error,"
        f"p.content_sha256,b.content_gz,b.truncated "
        f"FROM page_snapshots p LEFT JOIN blobs b USING(content_sha256) "
        f"WHERE p.resource IN ({marks}) "
        f"ORDER BY p.domain,p.resource,p.snapshot_date", tuple(resources))
    out: dict[tuple[str, str], list[Reading]] = defaultdict(list)
    cache: dict[str, tuple[str | None, tuple[PlanPrice, ...], dict]] = {}
    for domain, resource, day, status, err, sha, gz, truncated in rows:
        usable = (
            isinstance(status, int) and 200 <= status < 300 and not err
            and isinstance(sha, str) and gz is not None and not bool(truncated)
        )
        if not usable:
            why = ("body cut at the size cap" if truncated else
                   (err or (f"HTTP {status}" if status else "no answer")))
            out[(domain, resource)].append(Reading(day, None, (), str(why)))
            continue
        hit = cache.get(sha)
        if hit is None:
            try:
                body = zlib.decompress(gz)
            except (TypeError, zlib.error) as exc:
                raise DetectorUnavailable(f"blob {sha} unreadable: {exc}") from exc
            prices, units = extract(body)
            hit = (fingerprint(prices), prices, units)
            cache[sha] = hit
        mark, prices, units = hit
        out[(domain, resource)].append(
            Reading(day, mark, prices,
                    "" if mark else "no named plan price in the visible text",
                    units))
    return dict(out)


def scan(db_path: Path | str,
         resources: Iterable[str] = ("pricing", "plans")) -> dict[str, object]:
    """Every real price move in the sealed archive, with the counts behind it."""

    conn = connect_read_only(db_path)
    try:
        readings = readings_from_store(conn, resources)
    finally:
        conn.close()

    moves: list[PriceMove] = []
    verdicts: dict[str, int] = defaultdict(int)
    for (domain, resource), items in sorted(readings.items()):
        moves.extend(price_moves(domain, resource, items))
        verdicts[verdict_for(domain, resource, items)] += 1
    usable_reads = sum(1 for items in readings.values()
                       for r in items if r.fingerprint is not None)
    return {
        "schema_version": 1,
        "source": str(Path(db_path)),
        "addresses": len(readings),
        "dated_reads": sum(len(v) for v in readings.values()),
        "reads_with_a_named_plan_price": usable_reads,
        "addresses_by_verdict": dict(verdicts),
        "price_moves": [asdict(m) for m in moves],
        "price_move_count": len(moves),
    }
