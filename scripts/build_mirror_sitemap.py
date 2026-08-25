#!/usr/bin/env python3
"""Build sitemap.xml for the GitHub Pages mirror, from the committed tree.

The mirror's robots.txt has promised this file since the estate went up, and
until 25 Aug 2026 the promise pointed at a 404: the sitemap machinery in
build_site.py serves the main site's /feeds/ prefix and writes into dist/,
which this estate never publishes. The mirror publishes whatever is committed
on main, so its sitemap has to describe the COMMITTED tree -- pages are read
with `git show :path`, never off the working copy, because a working copy here
routinely carries another writer's uncommitted drift and a sitemap built from
it would describe an estate nobody can fetch.

Three rules carried over from the /feeds/ sitemap, same reasons:

- A retired address stays out. retired-reasons.json is the list; an address is
  out when it matches an entry exactly or sits underneath one, which covers
  both a single retired page and a whole retired feed without reading prose.
  The pages themselves stay up as gravestones -- the promise is that the
  address answers, not that we keep inviting people to it.
- lastmod is read back off the page (the data-newest meta), never computed
  here. A build-time stamp would mark every page changed on every rebuild,
  which is false and teaches a search engine to discount the field.
- A page with no data date gets no lastmod. A missing date is honest; a
  guessed one is a freshness lie.

build_mirror_sitemap_selftest.py compares the committed sitemap against a
fresh build every suite run, so a page landing without a sitemap rebuild goes
red there instead of rotting quietly.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://ustechautomations.github.io/usta-paid-surfaces"
NEWEST = re.compile(r'<meta name="data-newest" content="(\d{4}-\d{2}-\d{2})">')


def committed_pages() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "index.html", "families/*/index.html",
         "families/*/*/index.html"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout.split()
    return sorted(out)


def retired_addrs() -> list[str]:
    return [r["addr"] for r in json.loads((ROOT / "retired-reasons.json").read_text())]


def is_retired(addr: str, retired: list[str]) -> bool:
    return any(addr == r or addr.startswith(r + "/") for r in retired)


def committed_text(path: str) -> str:
    return subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout


def build() -> tuple[str, int, int, list[str]]:
    retired = retired_addrs()
    urls: list[str] = []
    dated = 0
    skipped: list[str] = []
    for path in committed_pages():
        addr = "" if path == "index.html" else path[: -len("/index.html")]
        fam = addr[len("families/"):] if addr.startswith("families/") else addr
        if fam and is_retired(fam, retired):
            skipped.append(fam)
            continue
        loc = f"{BASE}/" if not addr else f"{BASE}/{addr}/"
        m = NEWEST.search(committed_text(path))
        if m:
            dated += 1
            urls.append(f"<url><loc>{loc}</loc><lastmod>{m.group(1)}</lastmod></url>")
        else:
            urls.append(f"<url><loc>{loc}</loc></url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return xml, len(urls), dated, skipped


def main() -> int:
    xml, n, dated, skipped = build()
    if n == 0:
        print("REFUSING: a sitemap with zero pages describes no estate. Nothing was written.")
        return 1
    (ROOT / "sitemap.xml").write_text(xml, encoding="utf-8")
    print(f"wrote sitemap.xml: {n} pages, {dated} with a data date, "
          f"{len(skipped)} retired address(es) kept out"
          + (f" ({', '.join(skipped)})" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
