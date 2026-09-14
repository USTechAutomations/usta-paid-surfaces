#!/usr/bin/env python3
"""Fetch the pages a buyer actually sees and check they are not quietly stale.

Why this exists and why it is separate from the build gate:

A build-time check only tells the truth at the moment of the build. A page that
was honest on Tuesday is a lie on Friday if nothing republishes it. That is
exactly how a /permits page went nine days stale while its collector was healthy
and its build code was correct -- nothing was scheduled to put the two together.

So this probe reads the PUBLISHED page over the public internet, takes the date
the page itself claims, and compares it to the cadence the page itself promises.
It is the only check that tests what the buyer sees.

It never fetches a source. It never writes to a database. It only reads our own
published pages and writes one alert file.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from html.parser import HTMLParser
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE, _visible, late_after  # noqa: E402

SITEMAP = "https://ustechautomations.com/feeds/sitemap.xml"
ALERT = Path.home() / ".hermes" / "state" / "alerts" / "feeds-live-freshness.md"
UA = "USTechAutomations-self-check/1.0 (+https://ustechautomations.com/feeds)"
CHECK_URLS = Path(__file__).resolve().parent / "check_urls.py"
SERVICE_BUDGET_SEC = 900
DIRECTORY_PACE = "1"

NEWEST = re.compile(r'<meta name="data-newest" content="(\d{4}-\d{2}-\d{2})"')
CADENCE = re.compile(r'<meta name="data-cadence-days" content="(\d+)"')
HAS_FRESHNESS_META = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']data-(?:newest|cadence-days)["']""",
    re.I,
)
MAX_BODY_BYTES = 1_000_000

# The lateness rule lives in one place and this file borrows it. Writing the
# numbers out again here is how the live alarm and the build gate end up
# disagreeing about the same page: they agreed at 1 and 7 days and nowhere else.
def ceiling(cadence_days: int) -> int:
    return late_after(cadence_days)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                return 0, "response too large"
            return r.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # a network refusal is UNKNOWN, never "fresh"
        return 0, f"{type(e).__name__}: {e}"


def _directory_cmd(out_path: Path) -> list[str]:
    return [
        sys.executable,
        str(CHECK_URLS),
        "--directory",
        "--pace", DIRECTORY_PACE,
        "--quiet",
        "--out", str(out_path),
    ]


def _directory_runner(cmd: list[str], **kwargs):
    return subprocess.run(cmd, **kwargs)


def _unknown_result(problem: str, exit_code: int | None = None, report=None) -> dict:
    return {"status": "unknown", "exit_code": exit_code, "problem": problem, "report": report}


def _fail_result(problem: str, exit_code: int | None, report) -> dict:
    return {"status": "fail", "exit_code": exit_code, "problem": problem, "report": report}


def _load_directory_report(out_path: Path) -> tuple[object | None, str]:
    if not out_path.is_file():
        return None, "UNKNOWN: directory report missing"
    raw = out_path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, "UNKNOWN: directory report empty"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "UNKNOWN: directory report malformed"
    if not isinstance(data, dict):
        return None, "UNKNOWN: directory report malformed"
    return data, ""


def _verdict_from_report(exit_code: int | None, report: dict) -> dict:
    for key in ("checked", "ok", "not_200", "unknown"):
        if type(report.get(key)) is not int or report[key] < 0:
            return _unknown_result("UNKNOWN: invalid directory count", exit_code, report)
    if report.get("version_changed_during_run") or exit_code == 3:
        return _unknown_result(
            "UNKNOWN: directory changed during check", exit_code, report
        )
    if report.get("directory_stability_unknown"):
        return _unknown_result(
            "UNKNOWN: directory stability could not be established", exit_code, report
        )
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows or int(report.get("checked") or 0) < 1:
        return _unknown_result("UNKNOWN: directory report empty", exit_code, report)
    if report["checked"] != len(rows) or sum(report[k] for k in ("ok", "not_200", "unknown")) != len(rows):
        return _unknown_result("UNKNOWN: inconsistent directory counts", exit_code, report)
    if not re.fullmatch(r"[0-9a-f]{64}", str(report.get("directory_source_sha256", ""))):
        return _unknown_result(
            "UNKNOWN: directory stability could not be established", exit_code, report
        )

    fail_bits: list[str] = []
    unk_bits: list[str] = []
    ok_n = 0
    for row in rows:
        if not isinstance(row, dict):
            return _unknown_result("UNKNOWN: directory report malformed", exit_code, report)
        status = row.get("status")
        outcome = row.get("outcome")
        url = row.get("url") or row.get("path") or "?"
        if outcome == "unknown" or status in (None, 0):
            unk_bits.append(str(url))
            continue
        if outcome == "ok" and status == 200:
            ok_n += 1
            continue
        fail_bits.append(f"{url} — {status}")

    if int(report.get("unknown") or 0) > 0 and not unk_bits:
        unk_bits.append("counted unknown rows")
    if int(report.get("not_200") or 0) > 0 and not fail_bits:
        fail_bits.append("counted non-200 rows")

    if fail_bits:
        return _fail_result(
            "directory hrefs not answering: " + "; ".join(fail_bits[:8]),
            exit_code,
            report,
        )
    if unk_bits:
        return _unknown_result(
            "UNKNOWN: directory checker incomplete (" + ", ".join(unk_bits[:5]) + ")",
            exit_code,
            report,
        )
    if exit_code != 0:
        return _unknown_result(
            "UNKNOWN: directory checker returned no verdict" if exit_code == 2
            else f"UNKNOWN: directory checker exit {exit_code}",
            exit_code,
            report,
        )
    if ok_n < 1 or int(report.get("ok") or 0) < 1:
        return _unknown_result("UNKNOWN: directory report empty", exit_code, report)
    return {"status": "pass", "exit_code": exit_code, "problem": "", "report": report}


def check_directory(
    out_path: Path | None = None,
    timeout: float = SERVICE_BUDGET_SEC,
    runner=None,
) -> dict:
    """Run existing check_urls.py --directory --pace 1 --quiet --out PATH.

    Pass requires raw exit 0 and a stable nonempty report of HTTP 200 rows.
    Empty, missing, malformed, unavailable, changing, or failed checkers
    cannot report pass. Network holes are UNKNOWN, never HTTP 0 broken.
    """
    try:
        timeout = min(float(timeout), float(SERVICE_BUDGET_SEC))
    except (TypeError, ValueError):
        return _unknown_result("UNKNOWN: directory checker unavailable (invalid timeout)")
    if timeout <= 0:
        return _unknown_result("UNKNOWN: directory check timed out")
    if out_path is None:
        fd, name = tempfile.mkstemp(prefix="feeds-directory-", suffix=".json")
        import os
        os.close(fd)
        out_path = Path(name)
        owned = True
    else:
        out_path = Path(out_path)
        owned = False
    cmd = _directory_cmd(out_path)
    run = runner if runner is not None else _directory_runner
    proc = None
    try:
        out_path.unlink(missing_ok=True)
        try:
            proc = run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return _unknown_result("UNKNOWN: directory check timed out")
        except Exception as exc:  # checker not runnable: UNKNOWN, not a 404
            return _unknown_result(
                f"UNKNOWN: directory checker unavailable ({type(exc).__name__})"
            )
        exit_code = getattr(proc, "returncode", None)
        report, problem = _load_directory_report(out_path)
        if report is None:
            return _unknown_result(problem, exit_code)
        return _verdict_from_report(exit_code, report)
    except (OSError, ValueError, TypeError):
        return _unknown_result("UNKNOWN: directory report unreadable or invalid")
    finally:
        if owned:
            out_path.unlink(missing_ok=True)


def _sitemap_urls(body: str) -> list[str] | None:
    try:
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        root = ElementTree.fromstring(body)
        urls = [e.text for e in root.findall(".//s:loc", ns) if e.text]
    except Exception:
        return None
    return urls


def _write_alert(lines: list[str]) -> None:
    ALERT.parent.mkdir(parents=True, exist_ok=True)
    ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _retain_unknown(problem: str, checked: int, extras: list | None = None) -> None:
    """Keep prior evidence. Only write UNKNOWN when no alert exists yet."""
    if ALERT.exists():
        return
    lines = [
        "# feeds live freshness UNKNOWN",
        "",
        f"when: {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
        f"checked: {checked} published pages",
        "",
        f"- {problem}",
    ]
    for u, why in (extras or [])[:8]:
        lines.append(f"- UNKNOWN: {u} — {why}")
    _write_alert(lines)


def _classify_page(page: str, today: dt.date):
    """Freshness facts on one published page.

    Family/bridge pages carry neither meta and are undated. A page that carries
    only one of the two metas, a value that cannot be read, cadence below 1, or
    a newest date in the future is UNKNOWN — never pass and never stale.
    """
    class FreshnessMeta(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values={"data-newest": [], "data-cadence-days": []}
        def handle_starttag(self, tag, attrs):
            if tag != "meta":
                return
            attributes=dict(attrs)
            name=attributes.get("name")
            if name in self.values:
                self.values[name].append(attributes.get("content"))
    parser=FreshnessMeta()
    try:
        parser.feed(page)
        parser.close()
    except (ValueError, TypeError):
        return "unknown", "unreadable published freshness metadata"
    dates=parser.values["data-newest"]
    cadences=parser.values["data-cadence-days"]
    if not dates and not cadences:
        return "undated", None
    if len(dates) != 1 or not isinstance(dates[0], str):
        return "unknown", "invalid published date" if dates else "missing published date"
    if len(cadences) != 1 or not isinstance(cadences[0], str):
        return "unknown", "invalid published cadence" if cadences else "missing published cadence"
    try:
        newest_s=dates[0]
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", newest_s):
            raise ValueError("invalid date")
        newest = dt.date.fromisoformat(newest_s)
    except ValueError:
        return "unknown", "invalid published date"
    behind = (today - newest).days
    if behind < 0:
        return "unknown", "invalid published date"
    try:
        if not re.fullmatch(r"[0-9]+", cadences[0]):
            raise ValueError("invalid cadence")
        cadence = int(cadences[0])
        if cadence < 1:
            raise ValueError("invalid cadence")
        limit = ceiling(cadence)
    except (ValueError, OverflowError):
        return "unknown", "invalid published cadence"
    if behind > limit and PAUSED_PHRASE not in _visible(page):
        return "stale", (newest_s, behind, limit)
    return "ok", None


def main() -> int:
    started = time.monotonic()
    ALERT.parent.mkdir(parents=True, exist_ok=True)
    directory = check_directory(ALERT.parent / "feeds-directory-latest.json", timeout=300)
    status, body = fetch(SITEMAP)
    if status != 200:
        # Network-unavailable or unread sitemap: UNKNOWN, never HTTP 0 broken,
        # and never a reason to erase a prior finding.
        problem = "UNKNOWN: cannot read the published sitemap"
        print(problem, file=sys.stderr)
        _retain_unknown(problem, 0)
        return 2
    urls = _sitemap_urls(body)
    if not urls:
        problem = "UNKNOWN: published sitemap empty or malformed"
        print(problem, file=sys.stderr)
        _retain_unknown(problem, 0)
        return 2

    today = dt.date.today()
    late, broken, unknowns, checked, undated = [], [], [], 0, 0
    for u in urls:
        if time.monotonic() - started > SERVICE_BUDGET_SEC - 45:
            unknowns.append((u, "time budget exhausted; remaining sitemap pages unchecked"))
            break
        code, page = fetch(u)
        checked += 1
        if code == 0:
            unknowns.append((u, page or "unreachable"))
            continue
        if code != 200:
            broken.append((u, code))
            continue
        kind, detail = _classify_page(page, today)
        if kind == "undated":
            undated += 1          # family and bridge pages carry no data date
            continue
        if kind == "unknown":
            unknowns.append((u, detail))
            continue
        if kind == "stale":
            # A page that says it is behind is doing its job. Only a page that
            # is behind AND silent about it is a problem.
            # The phrase is imported, never retyped. This probe spent its first
            # run calling fifteen honest pages silently stale because it looked
            # for "collection is paused" while the pages say "collection has
            # paused". A watchdog that cries wolf is worse than no watchdog:
            # the next real one gets ignored.
            newest_s, behind, limit = detail
            late.append((u, newest_s, behind, limit))

    print(f"checked {checked} published pages: {len(late)} silently stale, "
          f"{len(broken)} not answering, {len(unknowns)} unknown, "
          f"{undated} carry no data date")
    for u, d, b, lim in late:
        print(f"  STALE {u} says {d}, {b} days behind, limit {lim}")
    for u, c in broken:
        print(f"  BROKEN {u} answered {c}")
    for u, why in unknowns:
        print(f"  UNKNOWN {u} {why}")
    if directory["status"] == "pass":
        n = (directory["report"] or {}).get("ok", 0)
        print(f"directory: {n} hrefs verified")
    else:
        print(f"directory: {directory['status']} {directory['problem']}")

    hard = bool(late or broken or directory["status"] == "fail")
    if hard:
        lines = [
            "# feeds live freshness CRITICAL",
            "",
            f"when: {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
            f"checked: {checked} published pages",
            "",
        ]
        for u, d, b, lim in late:
            lines.append(f"- STALE and silent about it: {u} — says {d}, {b} days behind, limit {lim}")
        for u, c in broken:
            lines.append(f"- NOT ANSWERING: {u} — {c}")
        for u, why in unknowns:
            lines.append(f"- UNKNOWN: {u} — {why}")
        if directory["status"] == "fail":
            lines.append(f"- {directory['problem']}")
        # Directory UNKNOWN must not replace a real freshness finding.
        elif directory["status"] == "unknown":
            lines.append(f"- {directory['problem']}")
        _write_alert(lines)
        return 1

    if directory["status"] != "pass" or unknowns:
        if directory["status"] != "pass":
            problem = directory["problem"]
        elif unknowns:
            problem = "UNKNOWN: published page check incomplete"
        else:
            problem = "UNKNOWN: published page unreachable"
        print(problem, file=sys.stderr)
        _retain_unknown(problem, checked, unknowns)
        return 2

    ALERT.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
