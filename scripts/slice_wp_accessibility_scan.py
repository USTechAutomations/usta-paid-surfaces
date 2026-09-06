#!/usr/bin/env python3
"""Hosted weekly WordPress accessibility scan, one page, no child pages.

Reads ~/.hermes/state/wp-accessibility-scan/ demo report CSVs written by
scripts/scan_wp_accessibility.py. The public sample is the newest demo report
capped at 25 rows.
"""
from __future__ import annotations

import csv
import glob
import html
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "wp-accessibility-scan"
STORE = Path(os.path.expanduser("~/.hermes/state/wp-accessibility-scan"))
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
ZIP_HREF = (
    "https://ustechautomations.com/feeds/wp-accessibility-scan/"
    "wp-accessibility-scan-0.1.0.zip"
)
CSV_FIELDS = ["page_url", "rule", "severity", "element", "fix"]
PAD_ROW = {
    "page_url": "https://ustechautomations.com/feeds/",
    "rule": "crawl-empty",
    "severity": "info",
    "element": "",
    "fix": "Automated checks found no issues on the pages we could read.",
}


def _e(s) -> str:
    return html.escape(str(s or ""))


def _d(iso: str) -> str:
    iso = (iso or "")[:10]
    if len(iso) < 10 or iso[4] != "-":
        return iso
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def newest_report() -> Path:
    files = sorted(glob.glob(str(STORE / "*" / "report_????-??-??.csv")))
    if not files:
        raise RuntimeError(
            f"{FAMILY}: no report_*.csv in {STORE}; run scan_wp_accessibility.py"
        )
    return Path(files[-1])


def newest_snapshot() -> Path:
    files = sorted(glob.glob(str(STORE / "snapshot_????-??-??.json")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no snapshot_*.json in {STORE}")
    return Path(files[-1])


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_ROWS: list[dict] | None = None
_REP_FILE: Path | None = None


def report_rows() -> list[dict]:
    global _ROWS, _REP_FILE
    if _ROWS is None:
        _REP_FILE = newest_report()
        _ROWS = _read(_REP_FILE)
    return _ROWS


def copy_date() -> str:
    stem = newest_report().stem  # report_YYYY-MM-DD
    return stem.split("_", 1)[1]


def snapshot_count() -> int:
    return len(glob.glob(str(STORE / "snapshot_????-??-??.json")))


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest demo report, capped at 25 rows. Pad one honest row if empty."""
    rows = report_rows()
    if not rows:
        rows = [PAD_ROW]
    headers = list(CSV_FIELDS)
    body = [[row.get(h, "") for h in headers] for row in rows[:SAMPLE_CAP]]
    return headers, body


def _rule_counts(rows: list[dict]) -> list[list[str]]:
    n: dict[str, int] = {}
    for r in rows:
        k = (r.get("rule") or "rule not in our copy").strip() or "rule not in our copy"
        n[k] = n.get(k, 0) + 1
    return [[_e(k), str(v)] for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]


def family_spec() -> dict:
    week = report_rows()
    later = copy_date()
    n_week = len(week)
    n_snaps = snapshot_count()
    stamp = f"copy of {_d(later)}"
    head = ["Page", "Rule", "Severity", "Fix"]
    shown = week[:TABLE_CAP]
    body = [[
        _e(r.get("page_url") or "blank"),
        _e(r.get("rule") or "blank"),
        _e(r.get("severity") or "blank"),
        _e(r.get("fix") or "blank"),
    ] for r in shown]
    pages = sorted({(r.get("page_url") or "").strip() for r in week if (r.get("page_url") or "").strip()})
    if n_week == 0:
        how = (
            f"The {_d(later)} demo scan of our own /feeds/ pages found no issue rows. "
            "A week we cannot read is still written as a dated file that says so."
        )
    else:
        how = (
            f"The {_d(later)} demo scan of our own /feeds/ pages found {n_week} issue "
            f"rows across {len(pages)} pages. We hold {n_snaps} sealed "
            "weekly snapshot so far."
        )
    desc = (
        f"{n_week} findings in the {_d(later)} demo scan. "
        f"Weekly hosted scan. $49/mo."
    )
    assert len(desc) <= MAX_DESC, len(desc)
    shown_n = min(TABLE_CAP, n_week)
    sample_n = min(SAMPLE_CAP, n_week) if n_week else 1
    secs = [
        section(
            "What this is",
            None,
            "      <p>This is a free WordPress plugin plus a hosted weekly scan of the "
            "public pages we can fetch. It is not a legal certificate, not an overlay "
            "widget, and not a guarantee that a site meets any guideline. "
            f"<strong>{how}</strong></p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Automated checks find some of the issues the guidelines "
            "describe, not all.</strong> A person still has to read the file. We do not "
            "log in, we do not store personal data, and we do not change how the front "
            "of a site looks.</p>\n"
            "      </div>",
        ),
        section(
            "Get the free plugin",
            "GPL-2.0, no key",
            "      <p>The plugin is free software under GPL-2.0. It adds a Tools screen "
            "that checks the site's own front page, or any URL on the same site you type. "
            "Every check runs with no key. A listing on wordpress.org is pending review, "
            "so until that lands you can install the zip.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><a href="{ZIP_HREF}">Download the 0.1.0 plugin zip</a>'
            '<span class="sub">Install it on a WordPress site you own. Tools → '
            "Accessibility scan. The hosted-scan link is a checkbox, off by default, "
            "and the plugin never calls our servers.</span></li>\n"
            "      </ul>",
        ),
        section(
            "What the weekly scan checks",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Images without alt text</strong>"
            '<span class="sub">An img tag with no alt attribute.</span></li>\n'
            "        <li><strong>Empty links and empty buttons</strong>"
            '<span class="sub">No visible text and no aria-label.</span></li>\n'
            "        <li><strong>Form fields without a label</strong>"
            '<span class="sub">No for/id pair, wrapping label, or aria-label.</span></li>\n'
            "        <li><strong>Missing lang on the html tag</strong>"
            '<span class="sub">Screen readers need to know the language.</span></li>\n'
            "        <li><strong>Heading level skips</strong>"
            '<span class="sub">An h1 followed by an h3, for example.</span></li>\n'
            "        <li><strong>Duplicate ids</strong>"
            '<span class="sub">Two elements sharing one id.</span></li>\n'
            "        <li><strong>Low-contrast inline colours</strong>"
            '<span class="sub">Only where both text colour and background are set and '
            "can be read as numbers. Ratio below 4.5 to 1 is flagged.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>Automated checks find some of the issues the guidelines "
            "describe, not all.</strong> We do not run a browser overlay. We fetch public "
            "HTML, obey robots.txt, and write a file.</p>\n"
            "      </div>",
        ),
        section(
            f"Demo scan of 6 Sep 2026" if later == "2026-09-06" else f"Demo scan of {_d(later)}",
            f"{n_week} issue rows" if n_week else "no issue rows",
            f"      <p>These rows are from a scan of https://ustechautomations.com/feeds/ "
            f"run on {_d(later)}. The first {shown_n or 0} are printed here; the sample "
            f"file below carries {sample_n} of them; a paying site gets the full weekly "
            f"file for the address named on the payment form.</p>\n"
            + (
                table(
                    head, body,
                    f"{shown_n} of the {n_week} issue rows this week",
                    stamp,
                )
                if n_week
                else "      <p>No issue rows on this copy.</p>\n"
            )
            + (
                "\n      <p>Rules in this week's file:</p>\n"
                + table(["Rule", "Rows"], _rule_counts(week),
                        f"All rules in this week's file", stamp)
                if n_week
                else ""
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One hosted scan a week</strong>"
            '<span class="sub">We fetch the public home page plus up to 40 more pages '
            "on the same site, at one request a second, and email a CSV. A site we "
            "cannot read is reported as such.</span></li>\n"
            "        <li><strong>Page, rule, severity, element, fix</strong>"
            '<span class="sub">Columns: page_url, rule, severity, element, fix. No login, '
            "no personal data, no street, no person's name.</span></li>\n"
            "        <li><strong>The free plugin stays free</strong>"
            '<span class="sub">Same class of checks inside WordPress admin, GPL-2.0, '
            "no locked features.</span></li>\n"
            "        <li><strong>An honest blocked week</strong>"
            '<span class="sub">If our crawler is blocked, the file says so in its first '
            "line. That month is refunded on request.</span></li>\n"
            "      </ul>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Website services",
        "cadence": "monthly",
        "cadence_long": (
            "one hosted whole-site scan a week, billed monthly. A site we cannot "
            "read is reported as such. A week that finds nothing is sent as 0 plus the date"
        ),
        "crumb": "WP accessibility scan",
        "h1": "Weekly hosted accessibility scan for WordPress sites",
        "buyer": (
            "WordPress site owners and small web shops who must answer accessibility "
            "complaints and want a downloadable audit file, not an overlay widget"
        ),
        "desc": desc,
        "lede": (
            "This is a free WordPress plugin plus a hosted weekly scan of the public "
            "pages we can fetch. It is not a legal certificate, not an overlay widget, "
            "and not a guarantee that a site meets any guideline. "
            f"{n_week} issue rows sit in the {_d(later)} demo scan of our own /feeds/ pages."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("WordPress accessibility weekly scan"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask for a scan of one public URL we already fetched. We reply with the "
            "finding count before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "Tell us the site address. The first report arrives within 7 days.",
        "foot": (
            "Every count on this page was read out of the sealed demo scan named above. "
            "Automated checks find some of the issues the guidelines describe, not all."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> Tell us the site address on "
            "the payment form; the first report arrives within 7 days."
        ),
        "sample_note": (
            "cut out of the dated demo scan we ran ourselves. Automated checks find "
            "some of the issues the guidelines describe, not all."
        ),
        "sample_rest": "the paid file is that week's full report for the site you name",
    }


def _main() -> int:
    r = report_rows()
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"report   {_REP_FILE} ({len(r)} rows)")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
