#!/usr/bin/env python3
"""Make every check in check_site.py go red, one at a time.

    python3 scripts/check_site_selftest.py
    python3 scripts/check_site_selftest.py --only 187      # one case, with output

A check that has only ever been seen to pass has not been shown to work. The
gate has 47 places it can refuse a build and, until this file existed, seven of
them had ever been demonstrated to refuse anything. The other forty were taken
on trust -- which is the same fault the price checks had, sitting unexamined in
the rest of the file.

HOW IT WORKS. The whole estate is copied to a temporary folder. The gate is run
against the untouched copy first and must pass: that is the "allows the thing it
is not for" half, and it is shared by every case rather than rewritten forty
times. Then, for each case, ONE thing is broken in the copy, the gate is run
again, and it must refuse for the stated reason. The copy is thrown away and
rebuilt between cases, so no case can inherit another's damage.

Nothing here touches the real estate, and nothing writes to catalog.json -- the
copy is what gets edited.

WHY THE MUTATIONS LOOK ODD IN PLACES. The gate stops at its first refusal, so a
case has to break the thing under test and nothing earlier. Where that forced an
awkward mutation, the case says why in its own name. Where it made a check
impossible to reach at all, the case is marked UNREACHABLE and reported rather
than worked around -- a check that cannot be made to go red is either dead code
or is guarding something that cannot happen, and we should know which.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
ESTATE = ("families", "catalog.json", "extras.json", "index.html")
MODULES = ("check_site.py", "privacy.py", "merge_catalog_adds.py")

MAILTO = "mailto:operations@ustechautomations.com"
ADDR_PAGE = "families/new-entities/chicago/index.html"      # prints addresses, withholds 2
FAM = "families/ttb/index.html"                             # an ordinary priced family
KID = "families/ttb/texas/index.html"                       # one of its children
PAID = "families/grid/index.html"                           # a family with a real pay link
PARKED = "families/az-contractors/index.html"               # the one parked family
BRIDGE = "families/how-we-seal/index.html"                  # a bridge page, not a family
HUB = "index.html"

MIN_PAGE = """<!doctype html><html><head><title>{t}</title>
<meta name="description" content="A page that exists only inside a test.">
<meta property="og:description" content="A page that exists only inside a test.">
<meta name="twitter:description" content="A page that exists only inside a test.">
<meta name="data-newest" content="2026-08-23">
<meta name="data-cadence-days" content="1">
</head><body><p>{body}</p>
<a href="mailto:operations@ustechautomations.com">write to us</a></body></html>"""


class Estate:
    """A throwaway copy of the repo, and the small edits a case makes to it."""

    def __init__(self, box: Path):
        self.box = box

    def read(self, rel: str) -> str:
        return (self.box / rel).read_text(encoding="utf-8")

    def write(self, rel: str, body: str) -> None:
        p = self.box / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def sub(self, rel: str, old: str, new: str, count: int = 0) -> None:
        raw = self.read(rel)
        if old not in raw:
            raise LookupError(f"{rel} does not contain {old!r}, so this case cannot run")
        self.write(rel, raw.replace(old, new) if not count else raw.replace(old, new, count))

    def re_sub(self, rel: str, pat: str, new: str) -> None:
        raw = self.read(rel)
        out, n = re.subn(pat, new, raw)
        if not n:
            raise LookupError(f"{rel} has nothing matching {pat!r}, so this case cannot run")
        self.write(rel, out)

    def before_body_end(self, rel: str, snippet: str) -> None:
        self.sub(rel, "</body>", snippet + "</body>", count=1)

    def drop(self, rel: str) -> None:
        (self.box / rel).unlink()

    def catalog(self, fn) -> None:
        p = self.box / "catalog.json"
        cat = json.loads(p.read_text(encoding="utf-8"))
        fn(cat)
        p.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def family(self, fid: str, fn) -> None:
        def edit(cat):
            fn(next(f for f in cat["families"] if f["id"] == fid))
        self.catalog(edit)

    def extras_add(self, fid: str) -> None:
        p = self.box / "extras.json"
        rows = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"id": fid})
        p.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    def bend_privacy(self, snippet: str) -> None:
        """Break the classifier itself, without editing the cases that test it."""
        p = self.box / "scripts" / "privacy.py"
        p.write_text(p.read_text(encoding="utf-8") + "\n\n" + snippet + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The cases. One per place the gate can refuse a build.
#
# Each is (line in check_site.py, what is broken, the mutation, a phrase that
# must appear in the refusal). The line number is what makes this auditable:
# run the file, and anything not listed here has never been shown to fire.
# ---------------------------------------------------------------------------
ADDR_CELL = "3600-3614 S KEDZIE AVE"
QUAKES = "families/quakes/index.html"
LONG_DESC = ("A search line deliberately padded past the hundred and fifty-five character "
             "ceiling so that the length check has something to refuse, with no amount of "
             "money anywhere in it at all.")

BEND_UNIT = """
_orig_street_only = street_only
def street_only(raw):
    kept, dropped = _orig_street_only(raw)
    return kept, dropped or "APT 9"      # sees a flat number in every address
"""
BEND_KEPT = """
_orig_street_only = street_only
def street_only(raw):
    kept, dropped = _orig_street_only(raw)
    return kept + " X", dropped          # right about the flat, wrong about the street
"""
BEND_PERSON = """
def looks_personal(name):
    return True                          # reads a company as a person
"""
BEND_SUPPRESS = """
def suppress(name, addr):
    return True                          # withholds every row, including real ones
"""


def cases() -> list[tuple]:
    C = []

    def add(line, name, fn, expect):
        C.append((line, name, fn, expect))

    # -- the classifier, tested before any page it produced -------------------
    add(133, "the address rule starts seeing a flat number in every address",
        lambda e: e.bend_privacy(BEND_UNIT), "now reads")
    add(138, "the address rule keeps the wrong part of the street",
        lambda e: e.bend_privacy(BEND_KEPT), "and the page must show")
    add(143, "the name rule starts reading a company as a person",
        lambda e: e.bend_privacy(BEND_PERSON), "as a person's own name")
    add(148, "the whole rule starts withholding rows that are not homes",
        lambda e: e.bend_privacy(BEND_SUPPRESS), "deletes a real registration")

    # -- what reaches a published page ---------------------------------------
    add(187, "a flat number survives into a published address cell",
        lambda e: e.sub(ADDR_PAGE, ADDR_CELL, ADDR_CELL + " APT 3", count=1),
        "prints a flat or unit number")
    add(199, "addresses are shortened and the page never admits it",
        lambda e: e.sub(ADDR_PAGE, "cut back to the street", "tidied up"),
        "never says so")
    add(203, "a page prints addresses and declares no withheld count",
        lambda e: e.re_sub(ADDR_PAGE, r'<meta name="data-withheld" content="\d+">', ""),
        "declares no data-withheld count")
    add(208, "rows are withheld and the page never mentions it",
        lambda e: e.sub(ADDR_PAGE, "2 rows withheld", "2 rows set aside"),
        "the page never says so")
    add(212, "the page's withheld count and the generator's disagree",
        lambda e: e.sub(ADDR_PAGE, 'content="2"', 'content="5"', count=1),
        "row(s) withheld but its generator declared")

    # -- pay links ------------------------------------------------------------
    add(229, "a page carries a pay link and the catalog declares no checkout",
        lambda e: e.family("grid", lambda f: f.pop("checkout", None)),
        "declares no checkout")
    add(234, "the checkout record has written terms but no address to pay at",
        lambda e: e.family("grid", lambda f: f["checkout"].pop("url", None)),
        "checkout record declares no url")
    add(238, "the page's pay link is not the one the catalog declared",
        lambda e: e.family("grid", lambda f: f["checkout"].__setitem__(
            "url", "https://ustechautomations.com/permits/offers/somewhere-else/buy")),
        "pay links the catalog never declared")
    add(241, "a pay link that has never been fetched and found working",
        lambda e: e.family("grid", lambda f: f["checkout"].pop("verified", None)),
        "never verified")
    add(244, "a pay link last proved working too long ago",
        lambda e: e.family("grid", lambda f: f["checkout"].__setitem__(
            "verified", "2020-01-01")),
        "days ago")
    # Pins today's date as well, so the age check above cannot fire first.
    add(246, "a pay link whose last check did not say it was live",
        lambda e: e.family("grid", lambda f: f["checkout"].update(
            {"status": "unknown", "verified": str(__import__("datetime").date.today())})),
        "its last check said")

    # -- the search line ------------------------------------------------------
    add(263, "a page ships with no search line at all",
        lambda e: e.re_sub(
            FAM, r'<meta (?:name|property)="(?:og:|twitter:)?description" content=".*?">', ""),
        "no meta description")
    add(266, "a search line long enough to be cut off mid-word",
        lambda e: e.re_sub(FAM, r'<meta name="description" content=".*?">',
                           f'<meta name="description" content="{LONG_DESC}">'),
        "characters, over")
    add(268, "a page ships three different answers to the same question",
        lambda e: e.re_sub(FAM, r'<meta property="og:description" content=".*?">',
                           '<meta property="og:description" content="A different line.">'),
        "different descriptions")
    # Only reachable on a child page: on a family page the newer rail check at
    # line 386 catches a stray amount in the search line first. Reported, not
    # worked around.
    add(286, "a child page offers a price in search results that we do not sell",
        lambda e: e.re_sub(
            KID, r'(<meta (?:name|property)="(?:og:|twitter:)?description" content=")',
            r'\g<1>$4321. '),
        "search line offers")

    # -- the hub ---------------------------------------------------------------
    add(435, "the hub loses the address a buyer writes to",
        lambda e: e.sub(HUB, MAILTO, "mailto:nobody@example.com"),
        "hub missing operations@ mailto")
    add(442, "the hub grows a claim we cannot stand behind",
        lambda e: e.before_body_end(HUB, "<p>SOC 2 certified.</p>"),
        "hub contains forbidden")

    # -- every family in the catalog -------------------------------------------
    add(446, "a family is in the catalog and its page was never built",
        lambda e: e.drop(FAM), "missing ")
    add(450, "a family page loses the address a buyer writes to",
        lambda e: e.sub(FAM, MAILTO, "mailto:nobody@example.com"),
        "missing mailto")
    add(455, "a family we cannot collect still shows a price",
        lambda e: e.before_body_end(PARKED, "<p>Yours for $99.</p>"),
        "parked but still shows a dollar price")
    # The page says it four times, three of them capitalised, and the check reads
    # the page in lower case. Removing one of the four leaves the check green and
    # makes a perfectly live check look dead -- so the mutation has to take out
    # every spelling of it.
    add(457, "a family we cannot collect never says it is unavailable",
        lambda e: e.re_sub(PARKED, r"(?i)not available", "coming along nicely"),
        "never says it is not available")
    # The price is taken off the page entirely rather than changed, because
    # changing it trips the newer price-rail check at line 382 first.
    add(459, "a family page stops showing the price the catalog sells it at",
        lambda e: e.sub(QUAKES, "$249", ""), "missing price")
    add(462, "a family page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(FAM, "<p>Trusted by Fortune 500 teams.</p>"),
        "contains forbidden")
    add(469, "the catalog says the sample works and the page says it does not",
        lambda e: e.before_body_end(FAM, "<p>Sample not ready yet.</p>"),
        "page says sample not ready")
    add(472, "the sample is not proved and the page does not warn anyone",
        lambda e: e.family("ttb", lambda f: f.__setitem__("sample_status", "fail")),
        "must say sample not ready")

    # -- the bridge pages ------------------------------------------------------
    add(481, "a bridge page is listed and was never built",
        lambda e: e.drop(BRIDGE), "missing ")
    add(484, "a bridge page loses the address a buyer writes to",
        lambda e: e.sub(BRIDGE, MAILTO, "mailto:nobody@example.com"),
        "missing mailto")
    add(487, "a bridge page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(BRIDGE, "<p>We are HIPAA aligned.</p>"),
        "contains forbidden")
    add(491, "a bridge page is built and nothing on the hub links to it",
        lambda e: e.sub(HUB, "how-we-seal", "how-we-hid-it"),
        "not linked from the hub")

    # -- the child pages -------------------------------------------------------
    # This one needs a whole small family built around it: a folder with a child
    # in it, listed as a bridge page and linked from the hub, so that every
    # earlier check passes and the only thing left wrong is that no catalog
    # entry describes it.
    def orphan_with_children(e: Estate) -> None:
        e.write("families/zz-orphan/index.html", MIN_PAGE.format(t="Zed", body="A test page."))
        e.write("families/zz-orphan/kid/index.html", MIN_PAGE.format(t="Zed kid", body="A test page."))
        e.extras_add("zz-orphan")
        e.before_body_end(HUB, "<!-- zz-orphan -->")

    add(517, "a folder full of child pages that no catalog entry describes",
        orphan_with_children, "in neither catalog.json nor a catalog-add fragment")

    def children_with_no_parent(e: Estate) -> None:
        e.write("families/zz-frag/kid/index.html", MIN_PAGE.format(t="Zed kid", body="A test page."))
        e.write("catalog-add-zz-frag.json", json.dumps({
            "id": "zz-frag", "name": "Zed", "buyer": "nobody", "cadence": "never",
            "price": "Not for sale", "sample_status": "pass", "group": "Test",
            "short": "Zed", "who": "nobody"}, indent=2))

    add(519, "child pages with no family page above them, so nothing links to them",
        children_with_no_parent, "children are unreachable")
    add(523, "a family we cannot collect still has child pages selling it",
        lambda e: e.write("families/az-contractors/kid/index.html",
                          MIN_PAGE.format(t="Zed kid", body="A test page.")),
        "parked but has child pages")
    add(529, "a child page loses the address a buyer writes to",
        lambda e: e.sub(KID, MAILTO, "mailto:nobody@example.com"), "missing mailto")
    add(532, "a child page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(KID, "<p>Trusted by Fortune 500 teams.</p>"),
        "contains forbidden")
    add(534, "a child page shows a different price from the family above it",
        lambda e: e.sub(KID, "$99/mo", "$0/mo"), "does not show its parent's price")
    add(536, "a child page carries no read date, so nothing can prove it is current",
        lambda e: e.sub(KID, 'name="data-newest"', 'name="data-newest-was-here"'),
        "nothing can prove it is current")
    # The overlap, proved rather than asserted. Put the same defect on a FAMILY
    # page and the newer check at line 386 catches it first, which is why the
    # case at 286 had to use a child page. 286 still earns its place: it is the
    # only thing guarding the child pages, and 386 does not walk them.
    add(386, "the same defect on a family page is caught by the newer check first",
        lambda e: e.re_sub(
            FAM, r'(<meta (?:name|property)="(?:og:|twitter:)?description" content=")',
            r'\g<1>$4321. '),
        "names $4321 in its tab title or its search line")
    return C


# The seven refusal points proved in the other file rather than this one, so
# that the coverage count below is the whole gate and not just this file's half.
ELSEWHERE = {
    353: "check_prices_selftest.py -- a built folder in neither list",
    377: "check_prices_selftest.py -- a priced page in no catalog",
    382: "check_prices_selftest.py -- a page that disagrees with the catalog",
    386: "check_prices_selftest.py -- a dead price in the tab title or search line",
    409: "check_prices_selftest.py -- the price list names a product we do not sell",
    414: "check_prices_selftest.py -- the price list quotes last week's price",
    420: "check_prices_selftest.py -- a product missing from the price list",
}


def refusal_points() -> dict[int, str]:
    """Every line of check_site.py that can stop a build, read from the file.

    Counted from the syntax tree rather than by searching for the word, because
    the definition of fail() is not a place the gate can refuse and a comment
    mentioning it is not either. This is what makes the coverage number below
    honest: add a check tomorrow and this file will name it as unproven.
    """
    import ast
    src = (ROOT / "scripts" / "check_site.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "fail":
            out[node.lineno] = lines[node.lineno - 1].strip()[:70]
    return out


def honest_cases() -> list[tuple]:
    """Honest content that the gate must NOT refuse.

    The other half of the job, and the one that decides whether a gate survives
    contact with a deadline. A check that blocks an honest page gets loosened by
    the next person in a hurry, and a loosened check protects nothing. These are
    pages we could plausibly want to publish tomorrow. Every one of them must
    pass. Any that does not is a finding about the check, not about the page.
    """
    return [
        ("a page honestly denying a claim we do not make",
         lambda e: e.before_body_end(
             BRIDGE, "<p>We do not hold HIPAA-covered records, and we never will.</p>")),
        ("a page we cannot collect quoting someone else's fee as a fact",
         lambda e: e.before_body_end(
             PARKED, "<p>The state charges $9 for a copy of the roster.</p>")),
        ("a business address with a suite number in it",
         lambda e: e.sub(ADDR_PAGE, ADDR_CELL, "123 MARKET ST STE 5", count=1)),
        ("one more honest child page under a family that already sells",
         lambda e: e.write("families/ttb/zz-honest/index.html",
                           MIN_PAGE.format(t="Zed", body="A test page. $99/mo."))),
        ("a family page that prints an amount as data, not as its price",
         lambda e: e.before_body_end(
             FAM, "<table><tr><th>Fee</th></tr><tr><td>$1,250.00</td></tr></table>")),
    ]


def build(box: Path) -> None:
    """A complete, working copy of the estate. Never the real one."""
    shutil.rmtree(box, ignore_errors=True)
    (box / "scripts").mkdir(parents=True)
    for name in ESTATE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, box / name)
        else:
            shutil.copy2(src, box / name)
    for name in MODULES:
        shutil.copy2(ROOT / "scripts" / name, box / "scripts" / name)


def gate(box: Path) -> tuple[int, str]:
    p = subprocess.run([PY, str(box / "scripts" / "check_site.py")],
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", type=int, help="run one case, by its line number")
    ap.add_argument("--keep", action="store_true", help="leave the broken copy on disk")
    args = ap.parse_args()

    box = Path("/tmp/claude-1000/-home-gmullins/b2c537f1-91c1-43e9-91e0-7aa1f7fde2c6"
               "/scratchpad/gate-selftest")
    todo = [c for c in cases() if args.only is None or c[0] == args.only]
    if not todo:
        raise SystemExit(f"no case for line {args.only}")

    # The shared half: the estate as it stands must pass. Without this, a case
    # that refuses for some unrelated reason would look like a success.
    build(box)
    code, out = gate(box)
    if code != 0:
        raise SystemExit(f"the untouched copy does not pass, so no case below means "
                         f"anything:\n{out}")
    print(f"the untouched copy of the estate passes (exit 0). {len(todo)} case(s) to break it.\n")

    bad, unreachable = [], []
    for line, name, mutate, expect in todo:
        build(box)
        e = Estate(box)
        try:
            mutate(e)
        except LookupError as err:
            unreachable.append((line, name, f"the mutation could not be made: {err}"))
            print(f"  SKIP  {line:>4}  {name}\n        {err}")
            continue
        code, out = gate(box)
        if args.only:
            print(out + "\n")
        if code == 0:
            unreachable.append((line, name, "the gate still passed"))
            print(f"  RED?  {line:>4}  {name}\n        UNREACHABLE: the gate passed anyway")
        elif expect not in out:
            first = out.splitlines()[-1] if out else "(nothing)"
            bad.append((line, name, first))
            print(f"  WRONG {line:>4}  {name}\n        refused, but for another reason: {first[:140]}")
        else:
            print(f"  PASS  {line:>4}  {name}")

    # The other half: honest pages the gate must let through.
    wrongly_refused = []
    if args.only is None:
        print("\n  and now content the gate must NOT refuse:")
        for name, mutate in honest_cases():
            build(box)
            try:
                mutate(Estate(box))
            except LookupError as err:
                wrongly_refused.append((name, f"could not set up: {err}"))
                continue
            code, out = gate(box)
            if code == 0:
                print(f"  PASS  {name}")
            else:
                why = out.splitlines()[-1]
                wrongly_refused.append((name, why))
                print(f"  BLOCK {name}\n        {why[:150]}")

    if not args.keep:
        shutil.rmtree(box, ignore_errors=True)

    total = len(todo)
    proved_here = {line for line, _, _, _ in todo} - {l for l, _, _ in bad} \
        - {l for l, _, _ in unreachable}
    points = refusal_points()
    covered = proved_here | set(ELSEWHERE)
    unproven = {l: t for l, t in points.items() if l not in covered}

    print(f"\n{'=' * 70}")
    print(f"cases run                 : {total}")
    print(f"checks proved to go red   : {total - len(bad) - len(unreachable)}")
    print(f"refused for another reason: {len(bad)}")
    print(f"could not be made to fire : {len(unreachable)}")
    print("-" * 70)
    here = len(proved_here & set(points))
    there = len(set(ELSEWHERE) & set(points))
    both = len(proved_here & set(ELSEWHERE) & set(points))
    print(f"places the gate can refuse a build : {len(points)}")
    print(f"  proved to go red                 : {len(covered & set(points))}")
    print(f"  NEVER SHOWN TO GO RED            : {len(unproven)}")
    print(f"  refuse honest content            : {len(wrongly_refused)}")
    print(f"  ({here} proved here, {there} in check_prices_selftest.py"
          f"{f', {both} in both' if both else ''})")
    print("=" * 70)
    for line, src in sorted(unproven.items()):
        print(f"  check_site.py:{line} has never been shown to refuse anything\n      {src}")
    for name, why in wrongly_refused:
        print(f"  REFUSES HONEST CONTENT: {name}\n      {why}")
    for line, name, why in unreachable:
        print(f"  line {line}: {name}\n      {why}")
    for line, name, why in bad:
        print(f"  line {line}: {name}\n      {why}")
    raise SystemExit(1 if bad or unreachable or wrongly_refused
                     or (unproven and args.only is None) else 0)


if __name__ == "__main__":
    main()
