#!/usr/bin/env python3
"""Rewrite one family's sample.json/csv the hour its collector finishes.

The daily 06:20 rebuild rewrites every family. This script rewrites ONE family
from that family's own slice.sample(), so a collect that stored rows (or a
checked empty) is visible the same hour.

Exit codes (without --post):
  0  wrote the two sample files
  1  rewrite failed (unknown clock, slice error, write error)
  2  clock database is missing

--post (systemd ExecStartPost): always exit 0. Failure is a receipt, not a
failed collect.

--selftest uses a tiny fake store. It does not write live family files.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FAMILIES = ROOT / "families"
CLOCKS_ROOT = Path.home() / "Claude CLI" / "clocks"
RECEIPT_DIR = Path.home() / ".hermes" / "state" / "clocks"
ALERT_DIR = Path.home() / ".hermes" / "state" / "alerts"

SAMPLE_ROWS = 25
SAMPLE_NOTE = (
    "Real rows out of dated copies we sealed ourselves. Nothing here is made up."
)
NO_MOVERS_NOTE = (
    "The newest sealed copy has the same ids as the copy before it. Nothing "
    "appeared or disappeared. This file is not a list of new records."
)
REVISIONS_NOTE = (
    "No new ids versus the previous seal; the sample still changed "
    "(revisions or field moves)."
)

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


# clock_id -> family dir on disk, slice module, db, and the table used to
# count net-new ids vs the previous seal. Family dirs were checked under
# families/ on 2026-08-25. dc_materialization feeds dc-siting (not
# dc-buildout). b2b_change feeds hiring-watch.
CLOCKS: dict[str, dict[str, Any]] = {
    "usgs_quakes": {
        "family": "quakes",
        "module": "slice_quakes",
        "db": CLOCKS_ROOT / "usgs_quakes" / "data" / "usgs_quakes.db",
        "seal": ("quake", "event_id", "snapshot_date"),
    },
    "grid_queue": {
        "family": "grid",
        "module": "slice_grid",
        "db": CLOCKS_ROOT / "grid_queue" / "data" / "grid_queue.db",
        "seal": ("project_snapshots", "project_id", "snapshot_date"),
    },
    "ttb_permits": {
        "family": "ttb",
        "module": "slice_ttb",
        "db": CLOCKS_ROOT / "ttb_permits" / "data" / "ttb_permits.db",
        "seal": ("permit", "permit_number", "snapshot_date"),
    },
    "mesa_code_compliance": {
        "family": "mesa-code",
        "module": "slice_mesa_code",
        "db": CLOCKS_ROOT / "mesa_code_compliance" / "data" / "mesa_code_compliance.db",
        "seal": ("case_snapshot", "case_number", "snapshot_date"),
    },
    "closing_web": {
        "family": "crawler",
        "module": "slice_crawler",
        "db": CLOCKS_ROOT / "closing_web" / "data" / "closing_web.db",
        "seal": ("policy_snapshots", "domain", "snapshot_date"),
    },
    "civic_agenda": {
        "family": "civic-agenda",
        "module": "slice_civic_agenda",
        "db": CLOCKS_ROOT / "civic_agenda" / "data" / "civic_agenda.db",
        "seal": ("events", "event_id", "snapshot_date"),
    },
    "dc_materialization": {
        "family": "dc-siting",
        "module": "slice_dc_siting",
        "db": CLOCKS_ROOT / "dc_materialization" / "data" / "dc_materialization.db",
        "seal": ("application", "app_id", "snapshot_date"),
    },
    "b2b_change": {
        "family": "hiring-watch",
        "module": "slice_hiring_watch",
        "db": CLOCKS_ROOT / "b2b_change" / "data" / "b2b_change.db",
        "seal": ("page_snapshots", "domain", "snapshot_date"),
    },
}


def plain(cell: object) -> str:
    s = re.sub(r"(?is)<[^>]+>", " ", str(cell))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write then replace, same directory, so a crash cannot leave a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o664)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def load_sample_fn(module_name: str) -> Callable[[], tuple[list[str], list[list[str]]]]:
    path = HERE / f"{module_name}.py"
    if not path.is_file():
        raise RuntimeError(f"slice module missing: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "sample", None)
    if not callable(fn):
        raise RuntimeError(f"{module_name} has no sample()")
    return fn


def seal_delta(db: Path, table: str, id_col: str, date_col: str) -> dict[str, Any]:
    """Count ids that appeared or disappeared between the last two seals.

    Returns net_new=None when the store cannot answer (missing table, one
    seal). That is unknown, not zero.
    """
    empty = {
        "newer_seal": None,
        "older_seal": None,
        "appeared": 0,
        "disappeared": 0,
        "net_new": None,
        "newer_n": 0,
        "older_n": 0,
    }
    if not db.is_file():
        return empty
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30.0)
    except sqlite3.Error:
        return empty
    try:
        con.execute("PRAGMA query_only = 1")
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in names:
            return empty
        cols = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
        if date_col not in cols or id_col not in cols:
            return empty
        dates = [r[0] for r in con.execute(
            f'SELECT DISTINCT "{date_col}" FROM "{table}" '
            f'WHERE "{date_col}" IS NOT NULL ORDER BY 1 DESC LIMIT 2'
        )]
        if len(dates) < 2:
            empty["newer_seal"] = dates[0] if dates else None
            return empty
        newer, older = dates[0], dates[1]
        new_ids = {r[0] for r in con.execute(
            f'SELECT "{id_col}" FROM "{table}" WHERE "{date_col}"=?', (newer,))}
        old_ids = {r[0] for r in con.execute(
            f'SELECT "{id_col}" FROM "{table}" WHERE "{date_col}"=?', (older,))}
        appeared = len(new_ids - old_ids)
        disappeared = len(old_ids - new_ids)
        return {
            "newer_seal": newer,
            "older_seal": older,
            "appeared": appeared,
            "disappeared": disappeared,
            "net_new": appeared + disappeared,
            "newer_n": len(new_ids),
            "older_n": len(old_ids),
        }
    except sqlite3.Error:
        return empty
    finally:
        con.close()


def previous_rows(sample_json: Path) -> list[list[str]] | None:
    if not sample_json.is_file():
        return None
    try:
        body = json.loads(sample_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = body.get("rows")
    if not isinstance(rows, list):
        return None
    return rows


def movers_flags(
    delta: dict[str, Any],
    rows: list[list[str]],
    prev: list[list[str]] | None,
) -> tuple[bool, bool, str | None]:
    """no_movers, slice_diff, extra note.

    0 net-new ids still rewrite when the slice itself moved (quake revisions).
    Identical full snapshots get a no-movers note so the file cannot be read
    as thousands of new records.
    """
    slice_diff = prev is not None and rows != prev
    net_new = delta.get("net_new")
    if net_new is None:
        return False, slice_diff, None
    if net_new == 0 and slice_diff:
        return False, True, REVISIONS_NOTE
    if net_new == 0:
        return True, False, NO_MOVERS_NOTE
    return False, slice_diff, None


def payload(
    family: str,
    clock: str,
    headers: list[str],
    rows: list[list[str]],
    delta: dict[str, Any],
    no_movers: bool,
    slice_diff: bool,
    extra_note: str | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "family": family,
        "clock": clock,
        "generated": dt.date.today().isoformat(),
        "rewritten_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "note": SAMPLE_NOTE,
        "where_these_rows_came_from": (
            "Where these rows came from, and anything their publisher "
            "requires to be printed alongside them, is set out on the page "
            "this file came from: "
            f"https://ustechautomations.com/feeds/{family}"
        ),
        "rows_published": len(rows),
        "columns": len(headers),
        "headers": headers,
        "rows": rows,
        "net_new_ids": delta.get("net_new"),
        "appeared_ids": delta.get("appeared"),
        "disappeared_ids": delta.get("disappeared"),
        "newer_seal": delta.get("newer_seal"),
        "older_seal": delta.get("older_seal"),
        "no_movers": no_movers,
        "slice_diff": slice_diff,
    }
    if extra_note:
        out["snapshot_note"] = extra_note
    return out


def write_sample_files(fam_dir: Path, body: dict[str, Any]) -> list[str]:
    json_path = fam_dir / "sample.json"
    csv_path = fam_dir / "sample.csv"
    atomic_write_text(json_path, json.dumps(body, indent=2) + "\n")
    buf = tempfile.SpooledTemporaryFile(max_size=1_000_000, mode="w+", encoding="utf-8", newline="")
    w = csv.writer(buf)
    w.writerow(body["headers"])
    w.writerows(body["rows"])
    buf.seek(0)
    atomic_write_text(csv_path, buf.read())
    buf.close()
    return [json_path.name, csv_path.name]


def write_receipt(
    body: dict[str, Any],
    *,
    fail: bool,
    receipt_dir: Path = RECEIPT_DIR,
    alert_dir: Path = ALERT_DIR,
) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    clock = str(body.get("clock") or "unknown")
    path = receipt_dir / f"sample-rewrite-{clock}.json"
    atomic_write_text(path, json.dumps(body, indent=2, default=str) + "\n")
    if fail:
        alert_dir.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        alert = alert_dir / f"SAMPLE_REWRITE_FAIL_{clock}_{ts}.md"
        lines = [
            f"# Sample rewrite failed — {clock}",
            "",
            f"- family: `{body.get('family')}`",
            f"- exit: {body.get('exit')}",
            f"- error: {body.get('error')}",
            f"- at: {body.get('at')}",
            "",
            "Collect itself is not failed. This file is the miss.",
            "",
        ]
        atomic_write_text(alert, "\n".join(lines))
        body["alert"] = str(alert)
        atomic_write_text(path, json.dumps(body, indent=2, default=str) + "\n")
    return path


def rewrite_clock(
    clock: str,
    *,
    clocks: dict[str, dict[str, Any]] | None = None,
    outdir: Path | None = None,
    sample_fn: Callable[[], tuple[list[str], list[list[str]]]] | None = None,
    receipt_dir: Path | None = None,
    alert_dir: Path | None = None,
    write_receipts: bool = False,
) -> int:
    """Rewrite families/<fam>/sample.json and sample.csv for one clock.

    Returns 0/1/2. Does not swallow errors unless the caller does.
    """
    table = clocks if clocks is not None else CLOCKS
    spec = table.get(clock)
    if spec is None:
        print(f"unknown clock {clock!r}; want {sorted(table)}", file=sys.stderr)
        return 1
    db = Path(spec["db"])
    family = spec["family"]
    if not db.is_file():
        print(f"clock db missing: {db}", file=sys.stderr)
        if write_receipts:
            write_receipt(
                {"clock": clock, "family": family, "exit": 2,
                 "error": f"missing db {db}", "ok": False,
                 "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                fail=True,
                receipt_dir=receipt_dir or RECEIPT_DIR,
                alert_dir=alert_dir or ALERT_DIR,
            )
        return 2

    fam_root = Path(outdir) if outdir is not None else FAMILIES
    fam_dir = fam_root / family
    fam_dir.mkdir(parents=True, exist_ok=True)

    table_name, id_col, date_col = spec["seal"]
    delta = seal_delta(db, table_name, id_col, date_col)

    fn = sample_fn if sample_fn is not None else load_sample_fn(spec["module"])
    headers, rows = fn()
    headers = [plain(h) for h in headers]
    rows = [[plain(c) for c in r] for r in rows][:SAMPLE_ROWS]

    prev = previous_rows(fam_dir / "sample.json")
    no_movers, slice_diff, extra = movers_flags(delta, rows, prev)
    body = payload(family, clock, headers, rows, delta, no_movers, slice_diff, extra)
    written = write_sample_files(fam_dir, body)

    result = {
        "clock": clock,
        "family": family,
        "ok": True,
        "exit": 0,
        "written": [str(fam_dir / n) for n in written],
        "rows_published": len(rows),
        "no_movers": no_movers,
        "slice_diff": slice_diff,
        "net_new_ids": delta.get("net_new"),
        "appeared_ids": delta.get("appeared"),
        "disappeared_ids": delta.get("disappeared"),
        "newer_seal": delta.get("newer_seal"),
        "older_seal": delta.get("older_seal"),
        "at": body["rewritten_at"],
    }
    if extra:
        result["snapshot_note"] = extra
    print(json.dumps({k: result[k] for k in (
        "clock", "family", "ok", "rows_published", "no_movers", "slice_diff",
        "net_new_ids", "written")}))
    if write_receipts:
        write_receipt(result, fail=False,
                      receipt_dir=receipt_dir or RECEIPT_DIR,
                      alert_dir=alert_dir or ALERT_DIR)
    return 0


def run_post(
    clock: str,
    *,
    clocks: dict[str, dict[str, Any]] | None = None,
    outdir: Path | None = None,
    sample_fn: Callable[[], tuple[list[str], list[list[str]]]] | None = None,
    receipt_dir: Path | None = None,
    alert_dir: Path | None = None,
) -> int:
    """Always return 0. Used as systemd ExecStartPost."""
    rdir = receipt_dir or RECEIPT_DIR
    adir = alert_dir or ALERT_DIR
    try:
        rc = rewrite_clock(
            clock,
            clocks=clocks,
            outdir=outdir,
            sample_fn=sample_fn,
            receipt_dir=rdir,
            alert_dir=adir,
            write_receipts=True,
        )
        if rc != 0:
            # rewrite_clock already wrote a receipt on missing db; others
            # print and return 1 without a receipt.
            if rc != 2:
                write_receipt(
                    {"clock": clock, "ok": False, "exit": rc,
                     "error": "rewrite_clock returned non-zero",
                     "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                    fail=True, receipt_dir=rdir, alert_dir=adir,
                )
        return 0
    except Exception as exc:
        write_receipt(
            {"clock": clock, "ok": False, "exit": 1,
             "error": f"{type(exc).__name__}: {exc}",
             "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            fail=True, receipt_dir=rdir, alert_dir=adir,
        )
        print(f"sample rewrite failed (collect still ok): {exc!r}", file=sys.stderr)
        return 0


def selftest() -> int:
    """Tiny fake store. No live family writes. No network."""
    bad: list[str] = []
    checked = 0

    def check(name: str, got, want) -> None:
        nonlocal checked
        checked += 1
        ok = got == want
        print(f"  {'ok ' if ok else 'BAD'} {name}: got {got!r} want {want!r}")
        if not ok:
            bad.append(name)

    tmp = Path(tempfile.mkdtemp(prefix="sample-rewrite-selftest-"))
    receipt_dir = tmp / "receipts"
    alert_dir = tmp / "alerts"
    out = tmp / "families"

    print("unknown clock:")
    check("unknown clock exits 1", rewrite_clock("not-a-clock", clocks={}), 1)

    print("missing db:")
    missing_spec = {
        "ghost": {
            "family": "ghost",
            "module": "nope",
            "db": tmp / "no-such.db",
            "seal": ("item", "id", "snapshot_date"),
        }
    }
    check("missing db exits 2",
          rewrite_clock("ghost", clocks=missing_spec, outdir=out), 2)

    print("post hook never fails the collect:")
    rc_post = run_post("ghost", clocks=missing_spec, outdir=out,
                       receipt_dir=receipt_dir, alert_dir=alert_dir)
    check("--post missing db exits 0", rc_post, 0)
    alerts = list(alert_dir.glob("SAMPLE_REWRITE_FAIL_ghost_*.md"))
    check("--post missing db left an alert", len(alerts) >= 1, True)

    print("identical snapshot + same sample => no_movers:")
    db = tmp / "fake.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE item (id TEXT, snapshot_date TEXT)")
    con.executemany(
        "INSERT INTO item VALUES (?, ?)",
        [("a", "2026-08-24"), ("b", "2026-08-24"),
         ("a", "2026-08-25"), ("b", "2026-08-25")],
    )
    con.commit()
    con.close()
    spec = {
        "fake": {
            "family": "fake-fam",
            "module": "unused",
            "db": db,
            "seal": ("item", "id", "snapshot_date"),
        }
    }

    def sample_same() -> tuple[list[str], list[list[str]]]:
        return ["id", "what"], [["a", "held"], ["b", "held"]]

    rc = rewrite_clock("fake", clocks=spec, outdir=out, sample_fn=sample_same)
    check("identical first write exits 0", rc, 0)
    js_path = out / "fake-fam" / "sample.json"
    csv_path = out / "fake-fam" / "sample.csv"
    check("sample.json exists", js_path.is_file(), True)
    check("sample.csv exists", csv_path.is_file(), True)
    body = json.loads(js_path.read_text(encoding="utf-8"))
    check("first write net_new is 0", body.get("net_new_ids"), 0)
    check("first write no_movers (no prev slice diff)", body.get("no_movers"), True)
    check("no-movers note present", "same ids" in (body.get("snapshot_note") or ""), True)
    leftover = list((out / "fake-fam").glob("*.tmp"))
    check("no tmp leftovers after first write", leftover, [])

    rc = rewrite_clock("fake", clocks=spec, outdir=out, sample_fn=sample_same)
    body2 = json.loads(js_path.read_text(encoding="utf-8"))
    check("second identical write still 0", rc, 0)
    check("second write no_movers", body2.get("no_movers"), True)
    check("second write not a slice diff", body2.get("slice_diff"), False)

    print("0 net-new but sample rows moved (quakes revisions):")

    def sample_rev() -> tuple[list[str], list[list[str]]]:
        return ["id", "what"], [["a", "magnitude 2.33→1.75"]]

    rc = rewrite_clock("fake", clocks=spec, outdir=out, sample_fn=sample_rev)
    body3 = json.loads(js_path.read_text(encoding="utf-8"))
    check("revisions write exits 0", rc, 0)
    check("revisions net_new still 0", body3.get("net_new_ids"), 0)
    check("revisions is a slice diff", body3.get("slice_diff"), True)
    check("revisions does not claim no_movers", body3.get("no_movers"), False)
    check("revisions note names revisions", "revisions" in (body3.get("snapshot_note") or ""), True)
    check("csv has a header plus one row",
          len(csv_path.read_text(encoding="utf-8").strip().splitlines()), 2)

    print("atomic replace:")
    atomic_write_text(js_path, "{}\n")
    check("atomic overwrite readable", js_path.read_text(encoding="utf-8"), "{}\n")
    check("still no tmp leftovers", list((out / "fake-fam").glob("*.tmp")), [])

    print("existing quakes db dry (optional):")
    qdb = CLOCKS["usgs_quakes"]["db"]
    if Path(qdb).is_file():
        qout = tmp / "quakes-dry"
        rc = rewrite_clock("usgs_quakes", outdir=qout)
        check("quakes dry-run on real db exits 0", rc, 0)
        qjs = qout / "quakes" / "sample.json"
        check("quakes dry-run wrote sample.json", qjs.is_file(), True)
        if qjs.is_file():
            qbody = json.loads(qjs.read_text(encoding="utf-8"))
            check("quakes dry-run family key", qbody.get("family"), "quakes")
            check("quakes dry-run has headers", isinstance(qbody.get("headers"), list), True)
    else:
        print("  skip quakes live db (missing)")

    print()
    print(f"{'OK' if not bad else 'PROBLEM'} {checked - len(bad)}/{checked}")
    if bad:
        print("failed:", "; ".join(bad), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clock", default="",
                   help="keep-list clock id, e.g. usgs_quakes")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--post", action="store_true",
                   help="systemd post-hook: always exit 0, write a receipt")
    p.add_argument("--dry-run", action="store_true",
                   help="write into a temp folder, not families/")
    p.add_argument("--outdir", default="",
                   help="families root to write into (tests / dry-run)")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.clock:
        print("need --clock NAME (or --selftest)", file=sys.stderr)
        return 1

    outdir: Path | None = Path(args.outdir) if args.outdir else None
    if args.dry_run and outdir is None:
        outdir = Path(tempfile.mkdtemp(prefix="sample-rewrite-dry-"))
        print(f"dry-run outdir {outdir}", file=sys.stderr)

    if args.post:
        return run_post(args.clock, outdir=outdir)
    return rewrite_clock(args.clock, outdir=outdir)


if __name__ == "__main__":
    sys.exit(main())
