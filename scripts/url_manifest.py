#!/usr/bin/env python3
"""Write the list of public addresses this estate ships, out of the built site.

    python3 scripts/url_manifest.py            # writes urls.json and URLS.md
    python3 scripts/url_manifest.py --check    # writes nothing, just re-derives

The list is DERIVED, every time, by walking dist/ on disk. It is never typed and
never edited by hand. A typed list of URLs goes stale the first time a page is
added or renamed, and then it is worse than no list at all: it reports a page
that no longer exists as healthy, and says nothing about the one that replaced
it. Everything below -- the address, the family, the price, whether there is a
pay button -- is read out of the built HTML that a visitor will actually be
served.

Three things are recorded per page, because these are the three questions a
buyer asks in order:

  * where is it            the public address under /feeds
  * what does it cost      the price rail as printed, or "Not for sale yet"
  * can I buy it now       a real pay button, or an honest email-only page

That last one matters because this estate is deliberately a mix. Most pages say
in plain words that there is no pay button yet. A few carry one. Nobody should
have to open two hundred pages to find out which is which.

Output:
    urls.json   the machine copy, and the input to scripts/check_urls.py
    URLS.md     the same rows as a table a person can read
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SITE = "https://ustechautomations.com"
BASE_PATH = "/feeds"

PRICE_RAIL = re.compile(r'<dd class="price">(.*?)</dd>', re.S)
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
LOC = re.compile(r"<loc>(.*?)</loc>")
NOINDEX = re.compile(r'<meta[^>]+name="robots"[^>]+content="[^"]*noindex', re.I)
TAG = re.compile(r"<[^>]+>")


def _gate_constant(name: str) -> tuple:
    """Lift one constant out of scripts/check_site.py without running it.

    The build gate already decides what counts as a pay link, and two copies of
    that decision in two files drift apart. The day they do, this manifest
    starts calling a live checkout an email-only page.

    It is read rather than imported because importing the gate loads
    catalog.json as a side effect, and that file belongs to somebody else
    tonight. Parsing the assignment gets the one shared truth without opening a
    file we were told to stay out of.
    """
    tree = ast.parse((ROOT / "scripts" / "check_site.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise SystemExit(f"scripts/check_site.py no longer defines {name}; "
                     "this manifest cannot agree with a gate it cannot read")


PAY_HOSTS = _gate_constant("PAY_HOSTS")
PAY_PATHS = _gate_constant("PAY_PATHS")


class Disagreement(Exception):
    """The built site and its own sitemap do not describe the same estate."""


def _text(fragment: str) -> str:
    import html as _html
    return re.sub(r"\s+", " ", _html.unescape(TAG.sub(" ", fragment))).strip()


def _pay_links(raw: str) -> list[str]:
    """Every real pay link on a page, by the build gate's own definition.

    The two lists it matches against are lifted straight out of the gate. See
    _gate_constant above for why they are read rather than imported.
    """
    out = set()
    for u in re.findall(r'href="(https?://[^"]+)"', raw):
        host = u.split("/")[2]
        if any(h in host for h in PAY_HOSTS):
            out.add(u)
        elif u.split("?")[0].rstrip("/").endswith(PAY_PATHS):
            out.add(u)
    return sorted(out)


def _bridge_ids() -> set[str]:
    extras = ROOT / "extras.json"
    if not extras.is_file():
        return set()
    return {e["id"] for e in json.loads(extras.read_text(encoding="utf-8"))}


def rows() -> list[dict]:
    if not DIST.is_dir():
        raise SystemExit("dist/ is not built. Run: python3 scripts/build_site.py")
    bridges = _bridge_ids()
    out = []
    for page in sorted(DIST.rglob("index.html")):
        rel = page.relative_to(DIST).parent
        parts = rel.parts
        path = BASE_PATH if not parts else f"{BASE_PATH}/{'/'.join(parts)}"
        raw = page.read_text(encoding="utf-8")

        m = PRICE_RAIL.search(raw)
        price = _text(m.group(1)) if m else ""
        pay = _pay_links(raw)
        # The pages that do not sell say so in words, and this is that sentence.
        # It is checked against the pay links rather than trusted, because a
        # page carrying both a button and a promise of no button is a defect we
        # want named, not quietly resolved in favour of whichever we read first.
        says_none = "No pay button" in raw
        if pay and says_none:
            raise Disagreement(
                f"{path} carries a pay button AND says it has none: {pay}")

        if not parts:
            kind = "hub"
        elif len(parts) == 1:
            kind = "bridge" if parts[0] in bridges else "family"
        else:
            kind = "slice"

        title = TITLE.search(raw)
        out.append({
            "url": SITE + path,
            "path": path,
            "family": parts[0] if parts else "",
            "kind": kind,
            "title": _text(title.group(1)) if title else "",
            # As printed on the page. "Not for sale yet" is a real answer, not a
            # missing one, and is left in the buyer's own words.
            "price": price or "n/a",
            "sells": "$" in price,
            # The hub sells nothing and is not pretending to: it is the directory.
            "pay": ("directory" if not parts else
                    "pay button" if pay else
                    "email only" if says_none else "no cta found"),
            "pay_url": pay[0] if pay else "",
            "built_from": str(page.relative_to(ROOT)),
        })
    return out


def cross_check(manifest: list[dict]) -> list[str]:
    """The sitemap is a second opinion, so disagreement is a finding.

    build_site.py writes both the pages and the sitemap in one run, so they
    should never differ. If they do, something published a page nobody can find
    or advertised one that was never built, and that is worth stopping for.

    With ONE exception, and it is not a loophole: a retired address. An address
    we published before and no longer build still has to answer, so build_site.py
    writes it a page saying plainly it has nothing to show, and deliberately
    leaves it out of the sitemap -- the promise is that the address answers, not
    that a search engine should index an empty page. Those pages carry
    noindex, and that is how they are told apart here. Without this, every
    retired address reads as a page nobody can find, and four of them did on
    2026-08-24: a real fix looked like four new faults.

    The exception runs one way only. A retired page that IS in the sitemap is
    still reported, because then we have asked a search engine to index a page
    whose whole content is that there is nothing here.
    """
    sm = DIST / "sitemap.xml"
    if not sm.is_file():
        return ["dist/sitemap.xml is missing"]
    listed = {u.rstrip("/") for u in LOC.findall(sm.read_text(encoding="utf-8"))}
    built = {r["url"].rstrip("/") for r in manifest}
    retired = {r["url"].rstrip("/") for r in manifest
               if NOINDEX.search((ROOT / r["built_from"]).read_text(encoding="utf-8"))}
    notes = []
    for u in sorted(built - listed - retired):
        notes.append(f"built but not in the sitemap: {u}")
    for u in sorted(listed - built):
        notes.append(f"in the sitemap but not built: {u}")
    for u in sorted(retired & listed):
        notes.append(f"retired and still in the sitemap, so we are asking for it to be "
                     f"indexed: {u}")
    return notes


def markdown(manifest: list[dict], notes: list[str]) -> str:
    sells = [r for r in manifest if r["sells"]]
    buttons = [r for r in manifest if r["pay"] == "pay button"]
    holding = [r for r in manifest if r["pay"] == "email only"]
    lines = [
        "# Every page this estate publishes",
        "",
        "Derived from `dist/` by `scripts/url_manifest.py`. Not typed, not edited",
        "by hand. Re-run it after any build and this file is current again.",
        "",
        f"- **{len(manifest)} pages**, every one of them an address under `{BASE_PATH}`",
        f"- **{len(sells)}** carry a price; **{len(manifest) - len(sells)}** say they are not for sale yet, "
        "are free to read, or are the hub itself",
        f"- **{len(buttons)}** have a pay button; **{len(holding)}** are honest holding pages that ask "
        f"you to email instead; **{len(manifest) - len(buttons) - len(holding)}** is the hub, which sells "
        "nothing and does not pretend to",
        "",
    ]
    if notes:
        lines += ["## The built pages and the sitemap disagree", ""]
        lines += [f"- {n}" for n in notes] + [""]
    else:
        lines += ["The sitemap lists exactly these pages and no others.", ""]

    order = {"hub": 0, "family": 1, "slice": 2, "bridge": 3}
    for fam in sorted({r["family"] for r in manifest}, key=lambda f: (f != "", f)):
        group = sorted([r for r in manifest if r["family"] == fam],
                       key=lambda r: (order[r["kind"]], r["path"]))
        lines += [f"## {fam or 'the hub'}", "",
                  "| Address | Price | Buy |", "|---|---|---|"]
        for r in group:
            lines.append(f"| `{r['path']}` | {r['price']} | {r['pay']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    manifest = rows()
    notes = cross_check(manifest)
    if "--check" not in sys.argv:
        (ROOT / "urls.json").write_text(
            json.dumps({"site": SITE, "base_path": BASE_PATH,
                        "pages": len(manifest), "notes": notes,
                        "rows": manifest}, indent=2) + "\n", encoding="utf-8")
        (ROOT / "URLS.md").write_text(markdown(manifest, notes) + "\n", encoding="utf-8")
    sells = sum(1 for r in manifest if r["sells"])
    buttons = sum(1 for r in manifest if r["pay"] == "pay button")
    print(f"{len(manifest)} pages, {sells} priced, {buttons} with a pay button")
    for n in notes:
        print(f"MISMATCH: {n}", file=sys.stderr)
    raise SystemExit(1 if notes else 0)


if __name__ == "__main__":
    main()
