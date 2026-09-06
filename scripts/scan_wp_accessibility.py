#!/usr/bin/env python3
"""Hosted weekly accessibility scan of a buyer's public pages.

No login. No personal data beyond customer_id and an email hash.
Obeys robots.txt. One request a second. Named User-Agent.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html as htmlmod
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

STORE = Path.home() / ".hermes" / "state" / "wp-accessibility-scan"
USER_AGENT = (
    "USTA-WP-Accessibility-Scan/0.1 "
    "(+https://ustechautomations.com/feeds/wp-accessibility-scan)"
)
MAX_PAGES = 41  # home plus up to 40 more
DELAY_SEC = 1.0
TIMEOUT_SEC = 15
SAMPLE_CAP = 25
CSV_FIELDS = ["page_url", "rule", "severity", "element", "fix"]
BLOCKED_LINE = (
    "This crawl did not render any pages: the site blocked our crawler "
    "or returned no readable pages."
)
SKIP_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".zip", ".gz", ".css", ".js", ".mjs", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".xml", ".json",
}
INPUT_SKIP_TYPES = {"hidden", "submit", "button", "reset", "image"}


# ------------------------------------------------------------------ checks


def _clip(s: str, n: int = 120) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _hex_to_rgb(val: str) -> tuple[int, int, int] | None:
    val = (val or "").strip().lower()
    m = re.match(r"^#([0-9a-f]{3})$", val)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
    m = re.match(r"^#([0-9a-f]{6})$", val)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.match(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", val)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _lum(rgb: tuple[int, int, int]) -> float:
    def f(c: int) -> float:
        x = max(0, min(255, c)) / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(a: str, b: str) -> float | None:
    ca, cb = _hex_to_rgb(a), _hex_to_rgb(b)
    if not ca or not cb:
        return None
    l1, l2 = _lum(ca), _lum(cb)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def _style_colors(style: str) -> tuple[str | None, str | None]:
    color = bg = None
    for part in (style or "").split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "color":
            color = v
        elif k in {"background-color", "background"} and not v.startswith("url"):
            bg = v.split()[0] if v else v
    return color, bg


class _Walker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang: str | None = None
        self.seen_html = False
        self.ids: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.imgs: list[tuple[bool, str]] = []
        self.links: list[dict] = []
        self.buttons: list[dict] = []
        self.inputs: list[dict] = []
        self.labels_for: set[str] = set()
        self.inline: list[tuple[str, str]] = []
        self._skip = 0
        self._label_wrap = 0
        self._a: dict | None = None
        self._btn: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag == "html":
            self.seen_html = True
            self.html_lang = ad.get("lang") or ad.get("xml:lang") or ""
        iid = ad.get("id")
        if iid:
            self.ids.append(iid)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.headings.append((int(tag[1]), _clip(f"<{tag}>")))
        if tag == "img":
            self.imgs.append(("alt" in ad, _clip(f"<img src=\"{ad.get('src', '')}\">")))
            if self._a is not None and ad.get("alt"):
                self._a["text"] += " " + ad.get("alt", "")
            if self._btn is not None and ad.get("alt"):
                self._btn["text"] += " " + ad.get("alt", "")
        if tag == "a":
            self._a = {
                "text": "",
                "aria": (ad.get("aria-label") or "").strip(),
                "snippet": _clip(
                    f"<a href=\"{ad.get('href', '')}\">"
                ),
            }
        if tag == "button":
            self._btn = {
                "text": ad.get("value", ""),
                "aria": (ad.get("aria-label") or "").strip(),
                "snippet": _clip("<button>"),
            }
        if tag == "input" and ad.get("type", "text").lower() == "button":
            self.buttons.append({
                "text": ad.get("value", ""),
                "aria": (ad.get("aria-label") or "").strip(),
                "snippet": _clip(f"<input type=\"button\">"),
            })
        if tag == "label":
            f = (ad.get("for") or "").strip()
            if f:
                self.labels_for.add(f)
            self._label_wrap += 1
        if tag in {"input", "select", "textarea"}:
            typ = ad.get("type", "text").lower() if tag == "input" else tag
            self.inputs.append({
                "id": (ad.get("id") or "").strip(),
                "name": (ad.get("name") or "").strip(),
                "type": typ,
                "aria": (ad.get("aria-label") or "").strip(),
                "labelledby": (ad.get("aria-labelledby") or "").strip(),
                "title": (ad.get("title") or "").strip(),
                "wrapped": self._label_wrap > 0,
                "snippet": _clip(f"<{tag} name=\"{ad.get('name', '')}\">"),
            })
        style = ad.get("style") or ""
        if style:
            self.inline.append((style, _clip(f"<{tag} style=\"{style}\">")))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if tag == "a" and self._a is not None:
            self.links.append(self._a)
            self._a = None
        if tag == "button" and self._btn is not None:
            self.buttons.append(self._btn)
            self._btn = None
        if tag == "label" and self._label_wrap:
            self._label_wrap -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._a is not None:
            self._a["text"] += data
        if self._btn is not None:
            self._btn["text"] += data


def findings_from_html(raw: str, page_url: str) -> list[dict]:
    """Return issue rows for one HTML page. A clean page returns []."""
    w = _Walker()
    try:
        w.feed(raw or "")
        w.close()
    except Exception:
        return [{
            "page_url": page_url,
            "rule": "parse-failed",
            "severity": "medium",
            "element": "",
            "fix": "The page HTML could not be parsed, so checks did not run on it.",
        }]
    out: list[dict] = []

    def add(rule: str, severity: str, element: str, fix: str) -> None:
        out.append({
            "page_url": page_url,
            "rule": rule,
            "severity": severity,
            "element": element,
            "fix": fix,
        })

    if not (w.html_lang or "").strip():
        add(
            "html-lang",
            "high",
            "<html>",
            'Add a lang attribute on the html tag, for example lang="en".',
        )
    for has_alt, snip in w.imgs:
        if not has_alt:
            add(
                "img-alt",
                "high",
                snip,
                "Add an alt attribute that names what the image shows, or alt=\"\" if it is only decoration.",
            )
    for link in w.links:
        text = (link["text"] or "").strip()
        if not text and not link["aria"]:
            add(
                "empty-link",
                "high",
                link["snippet"],
                "Put visible text or an aria-label on the link so a reader knows where it goes.",
            )
    for btn in w.buttons:
        text = (btn["text"] or "").strip()
        if not text and not btn["aria"]:
            add(
                "empty-button",
                "high",
                btn["snippet"],
                "Put visible text or an aria-label on the button.",
            )
    for field in w.inputs:
        if field["type"] in INPUT_SKIP_TYPES:
            continue
        if field["aria"] or field["labelledby"] or field["title"] or field["wrapped"]:
            continue
        if field["id"] and field["id"] in w.labels_for:
            continue
        add(
            "form-label",
            "high",
            field["snippet"],
            "Tie a label to this field with for/id, wrap it in a label, or add aria-label.",
        )
    prev = 0
    for level, snip in w.headings:
        if prev and level > prev + 1:
            add(
                "heading-skip",
                "medium",
                snip,
                "Do not skip heading levels; follow h1 with h2, then h3.",
            )
        prev = level
    seen: dict[str, int] = {}
    for iid in w.ids:
        seen[iid] = seen.get(iid, 0) + 1
    for iid, n in seen.items():
        if n > 1:
            add(
                "duplicate-id",
                "medium",
                f'id="{iid}"',
                "Give each id a unique value on the page.",
            )
    for style, snip in w.inline:
        color, bg = _style_colors(style)
        if not color or not bg:
            continue
        ratio = contrast_ratio(color, bg)
        if ratio is not None and ratio < 4.5:
            add(
                "low-contrast",
                "medium",
                snip,
                "Raise the contrast between text colour and background to at least 4.5 to 1.",
            )
    return out


# ------------------------------------------------------------------ crawl


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _today() -> str:
    return _now_utc().date().isoformat()


def _origin(url: str) -> tuple[str, str]:
    p = urllib.parse.urlparse(url)
    scheme = p.scheme or "https"
    netloc = p.netloc.lower()
    return scheme, netloc


def _norm(url: str, base: str) -> str | None:
    joined = urllib.parse.urljoin(base, url)
    p = urllib.parse.urlparse(joined)
    if p.scheme not in {"http", "https"}:
        return None
    path = p.path or "/"
    ext = Path(path).suffix.lower()
    if ext in SKIP_EXT:
        return None
    # Drop fragments; keep query (some WP pages key off it).
    clean = urllib.parse.urlunparse((p.scheme, p.netloc.lower(), path, "", p.query, ""))
    return clean


def same_site(url: str, home: str) -> bool:
    return urllib.parse.urlparse(url).netloc.lower() == urllib.parse.urlparse(home).netloc.lower()


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener()


def fetch(url: str, opener: urllib.request.OpenerDirector) -> tuple[int, str, str]:
    """Return (status, final_url, body). Body is '' on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with opener.open(req, timeout=TIMEOUT_SEC) as resp:
            status = getattr(resp, "status", 200) or 200
            final = resp.geturl() or url
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return int(e.code or 0), url, body
    except Exception:
        return 0, url, ""
    if "html" not in ctype and "xml" not in ctype and "text/plain" not in ctype:
        # Still try utf-8 if the server omitted a type.
        if ctype and "text/" not in ctype:
            return status, final, ""
    for enc in ("utf-8", "latin-1"):
        try:
            return status, final, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return status, final, raw.decode("utf-8", "replace")


def load_robots(home: str, opener: urllib.request.OpenerDirector) -> urllib.robotparser.RobotFileParser:
    scheme, netloc = _origin(home)
    robots_url = f"{scheme}://{netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        status, _, body = fetch(robots_url, opener)
        if status == 200 and body:
            rp.parse(body.splitlines())
        else:
            rp.parse(["User-agent: *", "Allow: /"])
    except Exception:
        rp.parse(["User-agent: *", "Allow: /"])
    return rp


def robots_allows(rp: urllib.robotparser.RobotFileParser, url: str) -> bool:
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        try:
            return rp.can_fetch("*", url)
        except Exception:
            return True


def _extract_hrefs(raw: str, base: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", raw, re.I):
        n = _norm(m.group(1), base)
        if n:
            found.append(n)
    return found


def _extract_sitemap_locs(raw: str, home: str) -> list[str]:
    locs = []
    for m in re.finditer(r"<loc>\s*([^<]+)\s*</loc>", raw, re.I):
        n = _norm(htmlmod.unescape(m.group(1).strip()), home)
        if n and same_site(n, home):
            locs.append(n)
    return locs


def sitemap_urls(home: str, rp: urllib.robotparser.RobotFileParser,
                 opener: urllib.request.OpenerDirector, last_fetch: list[float]) -> list[str]:
    scheme, netloc = _origin(home)
    candidates = [
        f"{scheme}://{netloc}/sitemap.xml",
        f"{scheme}://{netloc}/wp-sitemap.xml",
        f"{scheme}://{netloc}/sitemap_index.xml",
        urllib.parse.urljoin(home, "sitemap.xml"),
    ]
    # Also any Sitemap: lines from robots — RobotFileParser keeps them if present.
    extra = []
    try:
        extra = list(getattr(rp, "sitemaps", None) or [])
    except Exception:
        extra = []
    out: list[str] = []
    seen = set()
    for sm in candidates + extra:
        if not sm or sm in seen:
            continue
        seen.add(sm)
        if not robots_allows(rp, sm):
            continue
        _pace(last_fetch)
        status, final, body = fetch(sm, opener)
        if status != 200 or not body:
            continue
        out.extend(_extract_sitemap_locs(body, home))
        # One level of sitemap index.
        if "sitemapindex" in body.lower():
            for child in _extract_sitemap_locs(body, home)[:10]:
                if child in seen:
                    continue
                seen.add(child)
                if not robots_allows(rp, child):
                    continue
                _pace(last_fetch)
                st2, _, body2 = fetch(child, opener)
                if st2 == 200 and body2:
                    out.extend(_extract_sitemap_locs(body2, home))
    return out


def _pace(last_fetch: list[float]) -> None:
    if last_fetch[0] <= 0:
        last_fetch[0] = time.monotonic()
        return
    wait = DELAY_SEC - (time.monotonic() - last_fetch[0])
    if wait > 0:
        time.sleep(wait)
    last_fetch[0] = time.monotonic()


def crawl(home: str) -> tuple[list[dict], list[dict], bool]:
    """Fetch home plus up to 40 same-site pages.

    Returns (pages, crawl_log, blocked).
    pages: list of {url, status, html}
    blocked: True when zero pages were rendered.
    """
    home = home if "://" in home else "https://" + home
    if not home.endswith("/") and urllib.parse.urlparse(home).path == "":
        home += "/"
    opener = _opener()
    last_fetch = [0.0]
    log: list[dict] = []
    pages: list[dict] = []

    rp = load_robots(home, opener)
    if not robots_allows(rp, home):
        log.append({"url": home, "status": 0, "note": "robots.txt disallows this URL"})
        return [], log, True

    queue: list[str] = [home]
    seen: set[str] = set()
    # Seed from sitemap after the home fetch so we still honour 1 req/s.

    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not same_site(url, home):
            continue
        if not robots_allows(rp, url):
            log.append({"url": url, "status": 0, "note": "robots.txt disallows this URL"})
            continue
        _pace(last_fetch)
        status, final, body = fetch(url, opener)
        log.append({"url": url, "status": status, "final_url": final})
        if status != 200 or not body:
            continue
        if final and not same_site(final, home):
            continue
        pages.append({"url": final or url, "status": status, "html": body})
        if len(pages) == 1:
            for smu in sitemap_urls(home, rp, opener, last_fetch):
                if smu not in seen and same_site(smu, home):
                    queue.append(smu)
        for href in _extract_hrefs(body, final or url):
            if href not in seen and same_site(href, home):
                queue.append(href)

    blocked = len(pages) == 0
    return pages, log, blocked


# ------------------------------------------------------------------ reports


def _customer_dir(customer_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", customer_id or "unknown")[:80]
    d = STORE / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def report_html(findings: list[dict], pages: list[dict], blocked: bool,
                source_url: str, day: str) -> str:
    if blocked:
        lead = BLOCKED_LINE
    else:
        lead = (
            f"Automated checks of {len(pages)} page(s) on {htmlmod.escape(source_url)} "
            f"found {len(findings)} issue(s) on {day}. "
            "Automated checks find some of the issues the guidelines describe, not all. "
            "This is not a legal certificate."
        )
    rows = ""
    for r in findings:
        rows += (
            "<tr>"
            f"<td>{htmlmod.escape(r.get('page_url', ''))}</td>"
            f"<td>{htmlmod.escape(r.get('rule', ''))}</td>"
            f"<td>{htmlmod.escape(r.get('severity', ''))}</td>"
            f"<td><code>{htmlmod.escape(r.get('element', ''))}</code></td>"
            f"<td>{htmlmod.escape(r.get('fix', ''))}</td>"
            "</tr>\n"
        )
    table = (
        "<table><thead><tr>"
        "<th>Page</th><th>Rule</th><th>Severity</th><th>Element</th><th>Fix</th>"
        "</tr></thead><tbody>\n"
        f"{rows}</tbody></table>"
        if findings
        else "<p>No issue rows.</p>"
    )
    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>Accessibility scan {htmlmod.escape(day)}</title></head><body>\n"
        f"<p>{lead}</p>\n"
        f"{table}\n"
        "</body></html>\n"
    )


def write_csv(path: Path, findings: list[dict], blocked: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(findings)
    if blocked and not rows:
        rows = [{
            "page_url": "",
            "rule": "crawl-blocked",
            "severity": "high",
            "element": "",
            "fix": BLOCKED_LINE,
        }]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})


def write_snapshot(source_url: str, row_count: int, day: str, fetched_at: str) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    rec = {
        "snapshot_date": day,
        "source_id": "wp_accessibility_self_scan",
        "source_url": source_url,
        "row_count": row_count,
        "fetched_at": fetched_at,
    }
    path = STORE / f"snapshot_{day}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return path


def scan_one(customer_id: str, site_url: str, email_hash: str | None = None) -> dict:
    """Run one hosted scan. Never stores an email, only an optional hash."""
    del email_hash  # accepted and discarded beyond the subscriber file
    day = _today()
    fetched_at = _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    pages, log, blocked = crawl(site_url)
    findings: list[dict] = []
    for p in pages:
        findings.extend(findings_from_html(p["html"], p["url"]))
    dest = _customer_dir(customer_id)
    html_path = dest / f"report_{day}.html"
    csv_path = dest / f"report_{day}.csv"
    html_path.write_text(report_html(findings, pages, blocked, site_url, day), encoding="utf-8")
    write_csv(csv_path, findings, blocked)
    (dest / "crawl_log.json").write_text(
        json.dumps(log, indent=2) + "\n", encoding="utf-8"
    )
    snap = write_snapshot(site_url, len(findings), day, fetched_at)
    return {
        "customer_id": customer_id,
        "site_url": site_url,
        "day": day,
        "pages": len(pages),
        "findings": len(findings),
        "blocked": blocked,
        "html": str(html_path),
        "csv": str(csv_path),
        "snapshot": str(snap),
    }


def load_subscribers(path: Path | None = None) -> list[dict]:
    p = path or (STORE / "subscribers.json")
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{p} must be a JSON list")
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("customer_id") or "").strip()
        url = str(row.get("site_url") or "").strip()
        if not cid or not url:
            continue
        out.append({
            "customer_id": cid,
            "site_url": url,
            "email_hash": str(row.get("email_hash") or ""),
        })
    return out


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hosted weekly accessibility scan")
    ap.add_argument("--site", help="Site URL to scan")
    ap.add_argument("--customer-id", default="demo")
    ap.add_argument("--from-subscribers", action="store_true")
    args = ap.parse_args(argv)
    jobs = []
    if args.from_subscribers:
        jobs = load_subscribers()
        if not jobs:
            print("no subscribers", file=sys.stderr)
            return 1
    elif args.site:
        jobs = [{"customer_id": args.customer_id, "site_url": args.site, "email_hash": ""}]
    else:
        ap.error("pass --site URL or --from-subscribers")
    rc = 0
    for job in jobs:
        info = scan_one(job["customer_id"], job["site_url"], job.get("email_hash"))
        print(
            f"{info['customer_id']} pages={info['pages']} findings={info['findings']} "
            f"blocked={info['blocked']} csv={info['csv']}"
        )
        if info["blocked"]:
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
