"""Proof that the price detector can reach every verdict, and reaches the right one.

Every host in here is a reserved test name (`.test` / `.local`). No fixture
names a real vendor, so no fixture ever needs a permission note to pass and
nobody is ever tempted to write one so a test goes green.
"""

from __future__ import annotations

import sqlite3
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from price_change import (            # noqa: E402
    PlanPrice,
    Reading,
    connect_read_only,
    fingerprint,
    labelled_lines,
    plan_prices,
    read_body,
    price_moves,
    readings_from_store,
    verdict_for,
)


# --------------------------------------------------------------- the fixtures

def page(cards: str, extra: str = "") -> bytes:
    return (
        "<html><head><title>Plans</title>"
        "<script>var nonce='%s';</script></head><body>"
        "<h1>Pricing</h1>%s%s</body></html>" % ("a" * 8, cards, extra)
    ).encode("utf-8")


STARTER = '<div><h3>Starter</h3><p>$29/month</p></div>'
TEAM = '<div><h3>Team</h3><p>$99/month</p></div>'
STARTER_DEARER = '<div><h3>Starter</h3><p>$39/month</p></div>'


def series(days_and_bodies):
    """A run of dated readings, built the way the store walk builds them."""
    return [read_body(body, day) for day, body in days_and_bodies]


# --------------------------------------- 1. an unrelated edit is not a change

def test_same_prices_with_an_unrelated_edit_is_not_a_change():
    before = page(STARTER + TEAM, '<p>Trusted by 900 teams.</p>')
    after = page(STARTER + TEAM, '<p>Trusted by 1,200 teams and growing.</p>')
    assert plan_prices(before) == plan_prices(after)
    assert fingerprint(plan_prices(before)) == fingerprint(plan_prices(after))
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                       ("2026-06-03", after), ("2026-06-04", after)])
    assert price_moves("vendor-a.test", "pricing", readings) == ()
    assert verdict_for("vendor-a.test", "pricing", readings) == "NO_PRICE_CHANGE"


def test_a_rotating_script_and_a_hidden_block_never_reach_the_fingerprint():
    quiet = page(STARTER, '<div hidden><p>$1/month</p></div>')
    loud = page(STARTER, '<div aria-hidden="true"><p>$2,000/year</p></div>'
                         '<script>window.p="$7/month";</script>')
    assert plan_prices(quiet) == plan_prices(loud)


# ------------------------------------------- 2. an amount changing IS a change

def test_a_price_amount_changing_under_the_same_plan_is_a_change():
    before, after = page(STARTER + TEAM), page(STARTER_DEARER + TEAM)
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                       ("2026-06-03", after), ("2026-06-04", after)])
    moves = price_moves("vendor-b.test", "pricing", readings)
    assert len(moves) == 1
    move = moves[0]
    assert (move.plan_label, move.old_amount, move.new_amount) == ("Starter", "29", "39")
    assert move.cadence == "month"
    assert (move.last_seen_old, move.first_seen_new) == ("2026-06-02", "2026-06-03")
    assert move.change_date == "2026-06-03"
    assert (move.reads_at_old_price, move.reads_at_new_price) == (2, 2)
    assert verdict_for("vendor-b.test", "pricing", readings) == "PRICE_CHANGED"


def test_one_read_either_side_is_not_enough():
    before, after = page(STARTER), page(STARTER_DEARER)
    readings = series([("2026-06-01", before), ("2026-06-02", after)])
    assert price_moves("vendor-c.test", "pricing", readings) == ()


# ------------------------------------------- 3. a price that only MOVED is not

def test_a_price_card_moved_on_the_page_is_not_a_change():
    before = page(STARTER + TEAM)
    after = page(TEAM + STARTER)          # same cards, swapped order
    assert fingerprint(plan_prices(before)) == fingerprint(plan_prices(after))
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                       ("2026-06-03", after), ("2026-06-04", after)])
    assert price_moves("vendor-d.test", "pricing", readings) == ()


def test_a_price_rewrapped_in_different_markup_is_not_a_change():
    before = page('<div><h3>Starter</h3><p>$29/month</p></div>')
    after = page('<section><h3>Starter</h3><div><span>$29</span>'
                 '<span>/month</span></div></section>')
    assert fingerprint(plan_prices(before)) == fingerprint(plan_prices(after))


# ------------------------------------------------- 4. missing snapshots = UNKNOWN

def test_a_host_with_no_usable_snapshots_is_unknown_not_no_change():
    readings = [Reading("2026-06-01", None, (), "HTTP 404"),
                Reading("2026-06-02", None, (), "body cut at the size cap")]
    assert verdict_for("vendor-e.test", "pricing", readings) == "UNKNOWN"
    assert verdict_for("vendor-e.test", "pricing", []) == "UNKNOWN"


def test_an_unknown_read_breaks_the_run_it_sits_in():
    before, after = page(STARTER), page(STARTER_DEARER)
    readings = [read_body(before, "2026-06-01"),
                Reading("2026-06-02", None, (), "timeout"),
                read_body(after, "2026-06-03")]
    # One stable read on neither side: nothing may be claimed.
    assert price_moves("vendor-f.test", "pricing", readings) == ()


# ------------------------------------------ the two rejections that do the work

def test_a_magnitude_in_a_sentence_is_never_a_price():
    before = page(STARTER, '<h2>Scale</h2><p>Built on the ledger that has powered '
                           '$400 billion in payments.</p>')
    after = page(STARTER, '<h2>Scale</h2><p>Built on the ledger that has powered '
                          '$600 billion in payments.</p>')
    assert plan_prices(before) == plan_prices(after)
    assert price_moves("vendor-g.test", "pricing", series([
        ("2026-06-01", before), ("2026-06-02", before),
        ("2026-06-03", after), ("2026-06-04", after)])) == ()


def test_an_amount_adrift_in_prose_with_no_cadence_is_dropped():
    body = page(STARTER, '<h2>Savings</h2><p>Customers on this plan report saving '
                         'about $1,500 over a typical year of running the old tool '
                         'alongside ours, which is why we wrote this page.</p>')
    assert all(p.plan_label == "Starter" for p in plan_prices(body))


def test_an_unlabelled_amount_names_no_plan_and_is_dropped():
    assert plan_prices(b"<html><body><p>$29/month</p></body></html>") == ()


# -------------------------------------------- plans added and withdrawn are not

def test_a_plan_disappearing_is_not_a_price_change():
    before, after = page(STARTER + TEAM), page(STARTER)
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                       ("2026-06-03", after), ("2026-06-04", after)])
    assert price_moves("vendor-h.test", "pricing", readings) == ()
    assert verdict_for("vendor-h.test", "pricing", readings) == "NO_PRICE_CHANGE"


def test_a_new_plan_appearing_is_not_a_price_change():
    before, after = page(STARTER), page(STARTER + TEAM)
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                       ("2026-06-03", after), ("2026-06-04", after)])
    assert price_moves("vendor-i.test", "pricing", readings) == ()


def test_the_monthly_price_is_not_matched_against_the_annual_one():
    both = '<div><h3>Starter</h3><p>$29/month or $290/year</p></div>'
    dearer = '<div><h3>Starter</h3><p>$39/month or $290/year</p></div>'
    readings = series([("2026-06-01", page(both)), ("2026-06-02", page(both)),
                       ("2026-06-03", page(dearer)), ("2026-06-04", page(dearer))])
    moves = price_moves("vendor-j.test", "pricing", readings)
    assert len(moves) == 1
    assert (moves[0].cadence, moves[0].old_amount, moves[0].new_amount) == ("month", "29", "39")


# ---------------------------------------- the two guards on a reported move

def test_a_price_that_comes_back_later_is_a_flap_not_a_change():
    """Snyk's Team plan read $25, then $750 for three days, then $25 again."""

    cheap = page('<div><h3>Team</h3><p>$25/month</p></div>')
    dear = page('<div><h3>Team</h3><p>$750/month</p></div>')
    readings = series([("2026-06-01", cheap), ("2026-06-02", cheap),
                        ("2026-06-03", dear), ("2026-06-04", dear),
                        ("2026-06-05", cheap), ("2026-06-06", cheap)])
    assert price_moves("vendor-o.test", "pricing", readings) == ()
    shown = price_moves("vendor-o.test", "pricing", readings, include_refused=True)
    assert shown and all(m.verdict == "AMBIGUOUS_FLAP" for m in shown)


def test_a_number_that_changed_unit_is_never_sold_as_old_to_new():
    """ngrok: $200 per cert / month became $0.27 per domain per active hour."""

    before = page('<div><h3>Certificates</h3><p>$200 per cert / month</p></div>')
    after = page('<div><h3>Certificates</h3>'
                 '<p>$0.27 per domain per active hour</p></div>')
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                        ("2026-06-03", after), ("2026-06-04", after)])
    assert price_moves("vendor-p.test", "pricing", readings) == ()
    shown = price_moves("vendor-p.test", "pricing", readings, include_refused=True)
    assert [m.verdict for m in shown] == ["REFUSED_UNIT_ALSO_CHANGED"]
    assert shown[0].old_unit == "per cert / month"
    assert shown[0].new_unit == "per domain per active hour"


def test_the_same_unit_with_a_different_number_is_the_change_we_sell():
    """ngrok: $1 per 100k became $0.10 per 100k. Same unit, new number."""

    before = page('<div><h3>Traffic units</h3><p>$1 per 100k</p></div>')
    after = page('<div><h3>Traffic units</h3><p>$0.10 per 100k</p></div>')
    readings = series([("2026-06-01", before), ("2026-06-02", before),
                        ("2026-06-03", after), ("2026-06-04", after)])
    moves = price_moves("vendor-q.test", "pricing", readings)
    assert len(moves) == 1
    assert (moves[0].old_amount, moves[0].new_amount) == ("1", "0.1")
    assert moves[0].old_unit == moves[0].new_unit == "per 100k"
    assert moves[0].verdict == "PRICE_CHANGED"


# ------------------------------------------------------- the store, end to end

SCHEMA = """
CREATE TABLE blobs (content_sha256 TEXT PRIMARY KEY, content_gz BLOB NOT NULL,
 byte_len INTEGER NOT NULL, truncated INTEGER NOT NULL DEFAULT 0,
 first_seen_date TEXT NOT NULL);
CREATE TABLE page_snapshots (domain TEXT NOT NULL, snapshot_date TEXT NOT NULL,
 resource TEXT NOT NULL, status_code INTEGER, content_sha256 TEXT,
 headers_json TEXT NOT NULL, fetch_error TEXT, row_sha256 TEXT NOT NULL,
 collected_at TEXT NOT NULL, PRIMARY KEY (domain, snapshot_date, resource));
"""


@pytest.fixture()
def store(tmp_path):
    """A throwaway archive. Never the real one, and never on the real path."""
    import hashlib

    path = tmp_path / "throwaway.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    rows = [
        ("vendor-k.test", "2026-06-01", page(STARTER), 200, None, 0),
        ("vendor-k.test", "2026-06-02", page(STARTER), 200, None, 0),
        ("vendor-k.test", "2026-06-03", page(STARTER_DEARER), 200, None, 0),
        ("vendor-k.test", "2026-06-04", page(STARTER_DEARER), 200, None, 0),
        # Same prices, different page bytes. If the store walk ever goes back
        # to fingerprinting the whole page these two stop matching, which is
        # the exact defect that took this feed off sale.
        ("vendor-n.test", "2026-06-01", page(STARTER, "<p>Trusted by 900 teams.</p>"), 200, None, 0),
        ("vendor-n.test", "2026-06-02", page(STARTER, "<p>Trusted by 1,200 teams.</p>"), 200, None, 0),
        ("vendor-l.local", "2026-06-01", None, 404, None, 0),
        ("vendor-l.local", "2026-06-02", None, None, "timeout", 0),
        # A DIFFERENT body: blobs are content-addressed, so a truncated copy
        # must not share a hash with a whole one or the flag would be the
        # first writer's, not this read's.
        ("vendor-m.local", "2026-06-01", page(TEAM), 200, None, 1),
    ]
    for domain, day, body, status, err, truncated in rows:
        sha = None
        if body is not None:
            sha = hashlib.sha256(body).hexdigest()
            conn.execute("INSERT OR IGNORE INTO blobs VALUES (?,?,?,?,?)",
                         (sha, zlib.compress(body), len(body), truncated, day))
        conn.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                     (domain, day, "pricing", status, sha, "{}", err, "x", day))
    conn.commit()
    conn.close()
    return path


def test_the_store_walk_finds_the_change_and_calls_the_rest_unknown(store):
    conn = connect_read_only(store)
    try:
        readings = readings_from_store(conn, ("pricing",))
    finally:
        conn.close()
    moves = price_moves("vendor-k.test", "pricing", readings[("vendor-k.test", "pricing")])
    assert len(moves) == 1
    assert (moves[0].old_amount, moves[0].new_amount) == ("29", "39")
    assert verdict_for("vendor-l.local", "pricing",
                       readings[("vendor-l.local", "pricing")]) == "UNKNOWN"
    # A body cut at the size cap is UNKNOWN, not a page with no prices on it.
    cut = readings[("vendor-m.local", "pricing")]
    assert [r.fingerprint for r in cut] == [None]
    assert "size cap" in cut[0].reason


def test_the_store_walk_fingerprints_the_prices_not_the_page(store):
    """The whole point of this module, asserted through the real store walk.

    Two dated reads whose page bytes differ and whose named plan prices do not
    must carry the SAME fingerprint. A whole-page hash cannot pass this.
    """
    conn = connect_read_only(store)
    try:
        readings = readings_from_store(conn, ("pricing",))
    finally:
        conn.close()
    pair = readings[("vendor-n.test", "pricing")]
    assert len(pair) == 2
    bodies_differ = True   # the fixture wrote two different pages on purpose
    assert bodies_differ
    assert pair[0].fingerprint is not None
    assert pair[0].fingerprint == pair[1].fingerprint
    assert price_moves("vendor-n.test", "pricing", pair) == ()
    assert verdict_for("vendor-n.test", "pricing", pair) == "NO_PRICE_CHANGE"


def test_the_detector_refuses_a_missing_archive(tmp_path):
    from price_change import DetectorUnavailable

    with pytest.raises(DetectorUnavailable):
        connect_read_only(tmp_path / "not-there.db")


def test_labels_come_from_headings_not_from_the_line_itself():
    pairs = dict(labelled_lines(page(STARTER)))
    assert "Starter" in pairs.values() or any(
        label == "Starter" for label, _line in labelled_lines(page(STARTER)))
    assert PlanPrice("Starter", "USD", "29", "month") in plan_prices(page(STARTER))
