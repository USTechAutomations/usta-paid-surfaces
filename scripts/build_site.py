#!/usr/bin/env python3
"""Build the deployable /feeds/ site from the repo pages.

Look only. Every price, date, permit id, event id and honesty sentence in the
source page must survive into the built page byte-for-byte. The build refuses
to write anything if a fact goes missing, so a restyle can never quietly
delete a number or soften a "sample not ready".

Structure produced:
    dist/index.html                 ->  ustechautomations.com/feeds/
    dist/<family>/index.html        ->  ustechautomations.com/feeds/<family>
    dist/<family>/<slug>/index.html ->  ustechautomations.com/feeds/<family>/<slug>
    dist/<family>/sample.json       ->  ustechautomations.com/feeds/<family>/sample.json
    dist/styles.css                 ->  ustechautomations.com/feeds/styles.css

Slice pages go through the same gates as their parents. They are the pages a
stranger lands on from search, so they are the last place a number should be
allowed to go missing.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import family_status  # noqa: E402
from freshness import NEWEST_META, check_freshness  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
# Every address we have ever published. See the comment at the top of the file
# itself. Nothing is ever taken out of it.
PUBLISHED = ROOT / "published-addresses.txt"

BASE = "https://ustechautomations.com/feeds"
GTM_ID = "GTM-KTB2LC8C"

GTM = (
    "<script>window.dataLayer=window.dataLayer||[];"
    "window.dataLayer.push({'page_surface':'feeds','page_family':'%s'});</script>"
    "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),"
    "event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),"
    "dl=l!='dataLayer'?'&l='+l:'';j.async=true;"
    "j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;"
    "f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','%s');</script>"
)

MASTHEAD = """<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="https://ustechautomations.com/">US Tech Automations</a>
    <p class="crumbs"><a href="{base}">Dated change feeds</a>{crumb}</p>
    <nav class="mast-nav" aria-label="Main">
      <a href="https://ustechautomations.com/ai-agents/data-extraction">AI Agents</a>
      <a href="https://ustechautomations.com/solutions/enterprise">Solutions</a>
      <a href="https://ustechautomations.com/platform/integrations-info">Platform</a>
      <a href="https://ustechautomations.com/resources/research">Resources</a>
      <a href="https://ustechautomations.com/pricing">Pricing</a>
      <a class="mast-cta" href="https://ustechautomations.com/partner">Talk to Our Team</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer class="site">
  <div class="wrap">
    <div class="foot-grid">
      <div class="foot-brand">
        <a class="wordmark" href="https://ustechautomations.com/">US Tech Automations</a>
        <p>We build, run, and support custom AI automation workflows for businesses that need results. Not another tool to manage.</p>
        <p><a href="mailto:operations@ustechautomations.com">operations@ustechautomations.com</a><br>
           <a href="tel:+15186847631">(518) 684-7631</a></p>
      </div>
      <div class="foot-col">
        <h4>AI Agents</h4>
        <ul>
          <li><a href="https://ustechautomations.com/ai-agents/data-extraction">Data Extraction</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/customer-service">Customer Service</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/sales">Sales</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/human-resources">Human Resources</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/recruitment">Recruitment</a></li>
        </ul>
      </div>
      <div class="foot-col">
        <h4>Solutions</h4>
        <ul>
          <li><a href="https://ustechautomations.com/solutions/startup">Startup</a></li>
          <li><a href="https://ustechautomations.com/solutions/midsized">Midsized</a></li>
          <li><a href="https://ustechautomations.com/solutions/enterprise">Enterprise</a></li>
          <li><a href="https://ustechautomations.com/templates">Templates</a></li>
          <li><a href="https://ustechautomations.com/partner">Contact</a></li>
        </ul>
      </div>
      <div class="foot-col">
        <h4>Free Data</h4>
        <ul>
          <li><a href="{base}">Dated change feeds</a></li>
          <li><a href="https://ustechautomations.com/permits/grid">Interconnection Queue</a></li>
          <li><a href="https://ustechautomations.com/permits/cost">Permit Costs</a></li>
          <li><a href="https://ustechautomations.com/permits/rankings">Contractor Rankings</a></li>
          <li><a href="https://ustechautomations.com/offers">Offers &amp; Evidence</a></li>
        </ul>
      </div>
    </div>
    <div class="foot-bottom">
{honest}
      <p>&copy; 2026 US Tech Automations &middot; <a href="https://ustechautomations.com/privacy">Privacy Policy</a> &middot; <a href="https://ustechautomations.com/terms">Terms of Service</a></p>
    </div>
  </div>
</footer>"""


def fail(msg: str) -> None:
    print(f"BUILD FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def visible(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    t = re.sub(r"(?is)<[^>]+>", " ", html)
    t = t.replace("&amp;", "&").replace("&middot;", "·").replace("&copy;", "©")
    return re.sub(r"\s+", " ", t).strip()


# Every token shaped like a fact: money, dates, ids, hashes, numbers with meaning.
FACT = re.compile(
    r"\$[\d,]+(?:\.\d+)?(?:/mo)?"          # prices
    r"|\b\d{4}-\d{2}-\d{2}\b"              # ISO dates
    r"|\b[A-Z]{2}-[A-Z]-\d{4,6}\b"         # TTB permit numbers
    r"|\b[a-z]{2}\d{7,9}\b"                # USGS event ids
    r"|\b\d{1,3}(?:,\d{3})+\b"             # thousands
    r"|\b\d+\.\d+\b"                       # decimals
)

HONESTY = (
    "sample not ready",
    "no pay button",
    "we will not invent",
    "empty on purpose",
    "holding page",
)


def facts_of(html: str) -> list[str]:
    return sorted(FACT.findall(visible(html)))


SLICE_NAME = re.compile(r'<meta name="data-slice-name" content="([^"]*)">')


def slice_index(fid: str, fam_dir: Path, raw: str) -> str:
    """Every child page of a feed, linked from the feed's own page.

    Generated here rather than typed into the family page, for a counted
    reason. On 2026-08-23, seven of the nineteen families linked their own
    slices because somebody had typed those links by hand, and twelve linked
    none. The result was that 107 of the 201 published pages had no inbound
    link from anywhere on the site: a reader on /feeds/grid could not reach
    Minnesota by clicking, only by guessing the address. A hand-typed
    navigation list goes out of date the first time a slice is added, so this
    one is built from the folders that actually shipped and cannot disagree
    with them.

    ORDER is alphabetical by the name each slice gives itself, in columns. The
    obvious alternative -- group the places apart from the cuts, states in one
    list and "prices that went up" in another -- was rejected on purpose:
    deciding what counts as a place needs a hand-kept list of place names, and
    a hand-kept list is exactly what broke navigation here in the first place.
    Alphabetical is how a person finds Minnesota among twenty-six states.

    The coverage page is held out at the end because it is a different kind of
    page: it describes the feed instead of cutting it.

    A slice that is NOT FOR SALE is still linked. Some are deliberately
    unpriced and say so on their own face. Leaving those out of the navigation
    would make the estate look tidier than it is, which is the opposite of what
    these pages are for.

    The words come from each slice's own data-slice-name, never retyped here,
    so this list cannot start calling a page something the page does not call
    itself.

    NOTHING IS ADDED where the family page ALREADY links every one of its
    children. On 2026-08-23 that was true of exactly one family, ai-prices,
    which carries a hand-written list with a sentence of description under
    each entry -- better reading than a bare list of names. Printing this
    block underneath it would have shown a visitor the same seventeen links
    twice, which is the wall this function exists to avoid.

    That skip is not a hand-kept exception and needs nobody to maintain it.
    The test is recomputed on every build against the folders that shipped,
    so the moment a new child page appears and the hand-written list does not
    mention it, the page stops linking all of its children and this block
    comes back on its own, carrying the new page with it. Tidy when the hand
    is keeping up; complete the instant it stops.
    """
    kids = [d for d in sorted(fam_dir.iterdir()) if d.is_dir() and (d / "index.html").is_file()]
    if not kids:
        return ""
    # Does the page already do this job itself? Counted, not assumed: a child
    # counts as linked only if some anchor on the page points at exactly it.
    linked = {m.group(1) for m in re.finditer(
        rf'href="(?:{re.escape(BASE)}|/feeds)/{re.escape(fid)}/([a-z0-9-]+)"', raw)}
    if all(d.name in linked for d in kids):
        return ""
    rows = []
    for d in kids:
        m = SLICE_NAME.search((d / "index.html").read_text(encoding="utf-8"))
        if not m:
            fail(f"{fid}/{d.name} has no data-slice-name, so it cannot be listed on its family page")
        rows.append((m.group(1), d.name))
    cover = [r for r in rows if r[1] == "coverage"]
    rest = sorted((r for r in rows if r[1] != "coverage"), key=lambda r: r[0].lower())
    items = "\n".join(
        f'        <li><a href="{BASE}/{fid}/{slug}">{name}</a></li>' for name, slug in rest
    )
    tail = ""
    if cover:
        name, slug = cover[0]
        tail = f'\n      <p class="note"><a href="{BASE}/{fid}/{slug}">{name}</a></p>'
    return (
        '\n\n  <div class="wrap">\n'
        '    <section class="group slice-index">\n'
        "      <h2>Every page in this feed</h2>\n"
        '      <ul class="slice-list">\n'
        f"{items}\n"
        "      </ul>"
        f"{tail}\n"
        "    </section>\n"
        "  </div>\n"
    )


def build_page(src: Path, family: str, crumb_label: str | None, path: str | None = None,
               extra_main: str = "") -> str:
    """Build one page. `path` is the address it lives at under /feeds.

    A family page's address is just its id, so it is left to default. A slice
    page passes "<family>/<slug>", which is also how this function knows it is
    one level deeper and has to rewrite its links from three dots up rather
    than two.
    """
    raw = src.read_text(encoding="utf-8")
    out = raw

    # The generated navigation goes in FIRST, before anything below runs, so it
    # is checked by exactly the gates every hand-written block is checked by:
    # the internal-doc leak test, the github.io test, the fact-preservation
    # test. Injecting it after those ran would have created one blessed path
    # through this function that nothing inspects, and that is how a bad link
    # ships. It carries no number, price or claim -- only links and the names
    # the slices already give themselves -- so the fact check has nothing new
    # to weigh and nothing old goes missing.
    if extra_main:
        if out.count("</main>") != 1:
            fail(f"{family}: expected exactly one </main> to put the page list before")
        out = out.replace("</main>", extra_main + "</main>", 1)

    # --- head: canonical, og:url, stylesheet, robots, GTM ---
    rel = "" if family == "hub" else (path or family)
    slug = f"/{rel}" if rel else ""
    canon = f"{BASE}{slug}"
    out = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{canon}">', out)
    out = re.sub(r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{canon}">', out)
    out = re.sub(r'<link rel="stylesheet" href="[^"]*">', f'<link rel="stylesheet" href="{BASE}/styles.css">', out)
    if 'name="robots"' not in out:
        out = out.replace("<meta charset=\"utf-8\">",
                          "<meta charset=\"utf-8\">\n  <meta name=\"robots\" content=\"index,follow\">", 1)
    out = out.replace("<head>", "<head>\n  " + GTM % (family, GTM_ID), 1)
    out = re.sub(r'<meta property="og:site_name" content="[^"]*">',
                 '<meta property="og:site_name" content="US Tech Automations">', out)
    # theme-color follows the main site, light and dark, not the old per-family accent
    out = re.sub(
        r'<meta name="theme-color" content="[^"]*">',
        '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">\n'
        '  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">',
        out,
    )

    # --- masthead ---
    crumb = "" if crumb_label is None else f'<span class="sep">/</span>{crumb_label}'
    out = re.sub(r"(?s)<header class=\"masthead\">.*?</header>",
                 lambda _m: MASTHEAD.format(base=BASE, crumb=crumb), out, count=1)

    # --- footer: keep the page's own honesty paragraphs, wrap the site footer around them ---
    m = re.search(r"(?s)<footer class=\"site\">.*?<div class=\"wrap\">(.*?)</div>\s*</footer>", out)
    if not m:
        fail(f"{family}: could not find the footer to replace")
    inner = m.group(1).strip()
    inner = re.sub(r'<p class="addr">.*?</p>', "", inner, flags=re.S).strip()
    honest_block = "\n".join("      " + ln.strip() for ln in inner.splitlines() if ln.strip())
    honest_block += (
        '\n      <p class="addr">US Tech Automations &middot; '
        "3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>"
    )
    honest_block = honest_block.replace('<p>', '<p class="foot-honest">', 1)
    out = re.sub(r"(?s)<footer class=\"site\">.*?</footer>",
                 lambda _m: FOOTER.format(base=BASE, honest=honest_block), out, count=1)

    # --- internal links: relative hub links become absolute /feeds/ links ---
    if "/" in rel:
        # A slice page sits one folder deeper than a family page, so on disk its
        # way back to the hub is three dots up and its way to a sibling slice is
        # one. Rewrite those first: the family-page rules below would not match
        # them, and a link left relative would 404 once the page is served from
        # /feeds/<family>/<slug> instead of the folder it was written in.
        fam_base = f"{BASE}/{rel.split('/')[0]}"
        out = re.sub(r'href="\.\./\.\./\.\./"', f'href="{BASE}"', out)
        out = re.sub(r'href="\.\./\.\./\.\./([a-zA-Z0-9_.-]+)"', rf'href="{BASE}/\1"', out)
        out = re.sub(r'href="\.\./([a-z0-9-]+)/"', rf'href="{fam_base}/\1"', out)
        out = re.sub(r'href="\.\./([a-zA-Z0-9_.-]+)"', rf'href="{fam_base}/\1"', out)
        out = re.sub(r'href="\.\./"', f'href="{fam_base}"', out)
    out = re.sub(r'href="\.\./\.\./families/([a-z0-9-]+)/"', rf'href="{BASE}/\1"', out)
    out = re.sub(r'href="families/([a-z0-9-]+)/"', rf'href="{BASE}/\1"', out)
    out = re.sub(r'href="\.\./\.\./"', f'href="{BASE}"', out)
    out = re.sub(r'href="\.\./\.\./([a-zA-Z0-9_.-]+)"', rf'href="{BASE}/\1"', out)

    # --- no internal engineering docs on a public page ---
    leaks = re.findall(r'href="([^"]*(?:\.md\b|github\.com/USTechAutomations)[^"]*)"', out)
    if leaks:
        fail(f"{family}: internal doc link would be public: {sorted(set(leaks))}")
    if "github.io" in out:
        fail(f"{family}: still points at the old github.io host")

    # --- fact preservation: nothing numeric or honest may vanish ---
    before, after = facts_of(raw), facts_of(out)
    missing = [f for f in before if after.count(f) < before.count(f)]
    if missing:
        fail(f"{family}: these facts did not survive the rebuild: {sorted(set(missing))}")
    vis_before, vis_after = visible(raw).lower(), visible(out).lower()
    for phrase in HONESTY:
        if vis_before.count(phrase) > vis_after.count(phrase):
            fail(f"{family}: lost honesty phrase {phrase!r}")
    return out


def check_one_home() -> None:
    """Every page is built from exactly one list, and this says which one first.

    Two lists build folders in dist: catalog.json builds a folder for each family,
    extras.json builds one for each bridge and trust page. A page named in both got
    its folder made twice and the build stopped at "File exists: dist/<id>", which
    names the symptom and not one of the two files you have to open to fix it.

    kind="build" is the one legal overlap: the catalog carries that entry's price
    and its written terms, extras.json builds its page, and the family loop below
    skips it. Any other id in both lists is a mistake, and it is cheaper to be told
    that here than to read a traceback from pathlib.
    """
    extras = ROOT / "extras.json"
    if not extras.is_file():
        return
    ext = {e["id"] for e in json.loads(extras.read_text(encoding="utf-8"))}
    clash = sorted(f["id"] for f in CATALOG["families"]
                   if f["id"] in ext and f.get("kind") != "build")
    if clash:
        fail(f"{', '.join(clash)} is named in both catalog.json and extras.json, so this "
             f"build would try to create dist/{clash[0]} twice. Decide which list owns the "
             f"page: catalog.json for a dated feed we sell, extras.json for a bridge or "
             f"trust page. If it is priced in the catalog but built elsewhere, mark it "
             f'kind: "build" and the family loop will skip it.')


def main() -> None:
    check_one_home()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copy2(ROOT / "styles.css", DIST / "styles.css")
    # No robots.txt in dist: the pages now live under the main domain, whose
    # root robots.txt is the only one crawlers read. A /feeds/robots.txt would
    # be dead weight that still named the old github.io host.

    built = []
    stopped: list[str] = []
    # Every id we actually published a page for, with the words its crumb uses.
    # A slice can only ship under a parent that is really on the site.
    parents: dict[str, str] = {}
    hub = build_page(ROOT / "index.html", "hub", None)
    (DIST / "index.html").write_text(hub, encoding="utf-8")
    built.append("/feeds/")

    for fam in CATALOG["families"]:
        fid = fam["id"]
        # A kind="build" entry is priced and described in the catalog, and built
        # somewhere else. families/offers/ is the one today: a door to 11 one-off
        # automation builds, with no clock, no data table and no freshness. It is
        # in catalog.json so that its price and its written terms are checked like
        # every other product's, and it is in extras.json because that is what
        # actually builds its page -- so walking it here too made the build try to
        # create dist/offers twice and stop.
        #
        # Do not "fix" a kind="build" entry by giving it a folder here, and do not
        # fix the collision by deleting either line: dropping the catalog line puts
        # a live $200-$450 page back beyond the reach of the price check and throws
        # away its terms, and dropping the extras line deletes the page itself.
        if fam.get("kind") == "build":
            continue
        src = ROOT / "families" / fid / "index.html"
        if not src.is_file():
            fail(f"missing source page for {fid}")
        crumb = fam["name"]
        # Its own child pages, linked. Built from the folders on disk rather
        # than from the catalog, because the catalog says what we meant to
        # publish and the folders say what we did.
        page = build_page(
            src, fid, crumb,
            extra_main=slice_index(fid, ROOT / "families" / fid, src.read_text(encoding="utf-8")),
        )
        # A family page is written by hand, so it cannot notice that its own
        # source stopped being read. The child pages compute that sentence every
        # build; this gives the parent the same protection. It is added here
        # rather than typed into the page so it goes away by itself the day the
        # reader starts again.
        st = family_status.status(fid)
        # A collector we switched off is a different problem from a collector
        # that is late, and the late test cannot see it: the day after we turn
        # one off its newest copy is a day old and everything looks fine. The
        # catalog row is where that decision is recorded, so the page says it
        # out loud on every build, with the dates read out of the store.
        # Put the same two freshness tags on the parent that every child page
        # carries. Without them the freshness gate skips family pages entirely
        # -- it reads a page with no data-newest as "not a data page" -- so the
        # priced front page of a feed was the one page in the estate nothing
        # checked. Read from the store, never typed, and left off a family that
        # has no store at all rather than guessed at.
        if st and isinstance(st.get("newest"), str) and st.get("cadence_days"):
            page = page.replace(
                '<link rel="canonical"',
                f'<meta name="data-newest" content="{st["newest"]}">\n'
                f'  <meta name="data-cadence-days" content="{st["cadence_days"]}">\n'
                f'  <link rel="canonical"', 1,
            )
        closed = fam.get("closed")
        if st and closed:
            page = page.replace(
                '<main id="main">',
                family_status.closed_notice(st, closed) + '\n\n<main id="main">', 1,
            )
            stopped.append(f'{fid} (closed, last copy {st["newest"]})')
        elif st and st["stopped"]:
            page = page.replace(
                '<main id="main">',
                family_status.notice(st) + '\n\n<main id="main">', 1,
            )
            stopped.append(f'{fid} (newest {st["newest"]}, {st["age_days"]}d)')
        outdir = DIST / fid
        outdir.mkdir(parents=True)
        (outdir / "index.html").write_text(page, encoding="utf-8")
        built.append(f"/feeds/{fid}")
        parents[fid] = crumb

    # The two bridge pages carry no sample and no catalog row, but they ship in
    # the same folder and go in the same sitemap.
    extras = ROOT / "extras.json"
    if extras.is_file():
        for e in json.loads(extras.read_text(encoding="utf-8")):
            eid = e["id"]
            src = ROOT / "families" / eid / "index.html"
            if not src.is_file():
                fail(f"missing source page for {eid}")
            page = build_page(src, eid, e["short"])
            outdir = DIST / eid
            outdir.mkdir(parents=True)
            (outdir / "index.html").write_text(page, encoding="utf-8")
            built.append(f"/feeds/{eid}")
            parents[eid] = e["short"]

    # --- slice pages: /feeds/<family>/<slug> ---
    # These are written by scripts/build_slices.py out of the sealed databases.
    # They get exactly the gates their parents get: the same fact check, the same
    # honesty check, the same link rewriting. Nothing here is a lighter path.
    for fam_dir in sorted((ROOT / "families").iterdir()):
        if not fam_dir.is_dir():
            continue
        fid = fam_dir.name
        slice_dirs = [d for d in sorted(fam_dir.iterdir()) if d.is_dir() and (d / "index.html").is_file()]
        if not slice_dirs:
            continue
        if fid not in parents:
            fail(
                f"{fid} has child pages but no page of its own on the site. "
                f"If it is a new family, run scripts/merge_catalog_adds.py and build its family page first."
            )
        for d in slice_dirs:
            src = d / "index.html"
            name = re.search(r'<meta name="data-slice-name" content="([^"]*)">', src.read_text(encoding="utf-8"))
            if not name:
                fail(f"{fid}/{d.name} has no data-slice-name; rebuild it with scripts/build_slices.py")
            crumb = f'<a href="{BASE}/{fid}">{parents[fid]}</a><span class="sep">/</span>{name.group(1)}'
            page = build_page(src, fid, crumb, path=f"{fid}/{d.name}")
            outdir = DIST / fid / d.name
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "index.html").write_text(page, encoding="utf-8")
            built.append(f"/feeds/{fid}/{d.name}")
        # The two permanent sample addresses ride along with the pages they came from.
        for name in ("sample.json", "sample.csv"):
            f = fam_dir / name
            if f.is_file():
                shutil.copy2(f, DIST / fid / name)

    # sitemap for the new prefix
    # Every published address, whole. Taking the last path segment used to turn
    # /feeds/grid/minnesota into /feeds/minnesota, which is not a page we serve.
    #
    # lastmod is READ BACK OFF THE PAGE WE JUST WROTE. It is not computed here
    # and it is never the build time or the file's modified time, and that rule
    # is the whole point of the field.
    #
    # Every page in this estate is rebuilt nightly whether or not its data
    # moved. A build-time stamp would therefore mark all 201 addresses as
    # changed today, every day. That is false, and it is also self-defeating: a
    # lastmod that always says today is one a search engine learns to discount,
    # so we would have given up the signal by using it. The date that belongs
    # here is the date of the newest sealed row behind the page, which is the
    # same date the page prints and the same date the freshness gate checks.
    # Reading it back off the built page rather than recomputing it means there
    # is one source for that fact instead of two that can drift.
    #
    # A page with no data date -- the hub, the coverage and policy pages, the
    # two bridge pages, a family we cannot collect at all -- gets NO lastmod.
    # The sitemap spec allows the field to be absent. A missing date is honest;
    # a guessed one would be the freshness lie in a new file.
    urls = ""
    dated = 0
    for p in built:
        rel = p[len("/feeds/"):].strip("/") if p.startswith("/feeds/") else p.strip("/")
        loc = BASE if not rel else f"{BASE}/{rel}"
        page_file = (DIST / "index.html") if not rel else (DIST / rel / "index.html")
        m = NEWEST_META.search(page_file.read_text(encoding="utf-8"))
        if m:
            dated += 1
            urls += f"<url><loc>{loc}</loc><lastmod>{m.group(1)}</lastmod></url>"
        else:
            urls += f"<url><loc>{loc}</loc></url>"
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>",
        encoding="utf-8",
    )
    print(f"built {len(built)} pages into {DIST}")
    print(f"sitemap: {len(built)} addresses, {dated} carrying a real lastmod, "
          f"{len(built) - dated} deliberately without one")
    if stopped:
        # Loud on purpose. Four feeds we take money for had a switched-off
        # reader on 2026-08-22 and nothing on the site said so.
        print(f"paused sources, and the family page now says so: {'; '.join(stopped)}")
    for p in built:
        print("  ", p)

    # A page that stopped being fed must say so. This is the last gate because it
    # reads the built pages, not the sources: it proves what would go live.
    check_freshness(DIST)


if __name__ == "__main__":
    main()
