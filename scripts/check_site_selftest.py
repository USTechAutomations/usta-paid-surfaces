#!/usr/bin/env python3
"""Make every check in check_site.py go red, one at a time.

    python3 scripts/check_site_selftest.py
    python3 scripts/check_site_selftest.py --only 187      # one case, with output

A check that has only ever been seen to pass has not been shown to work. When
this file was written the gate had 47 places it could refuse a build and seven
of them had ever been demonstrated to refuse anything; the other forty were
taken on trust, which is the same fault the price checks had, sitting unexamined
in the rest of the file. It is 53 places now, and the count is not typed here --
it is read out of check_site.py on every run, so a check added tomorrow is named
as unproven rather than silently assumed to work.

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
ESTATE = ("families", "catalog.json", "extras.json", "index.html", "DELIVERY.md")
MODULES = ("check_site.py", "privacy.py", "merge_catalog_adds.py", "outbound_guard.py",
           # check_site.py reads the "whole file is on this page" sentence out of the
           # builder that writes it rather than retyping it, and render_family.py is
           # what that builder imports. Leave either behind and the copy in the box
           # cannot import its own gate: the untouched run dies on an ImportError and
           # every case in this file is voided rather than failed.
           "slice_free_time.py", "render_family.py")

MAILTO = "mailto:operations@ustechautomations.com"
ADDR_PAGE = "families/new-entities/chicago/index.html"      # prints addresses, withholds 2
FAM = "families/ttb/index.html"                             # an ordinary priced family
KID = "families/ttb/texas/index.html"                       # one of its children


def _a_paid_page() -> str:
    """A family that really takes cards today, found rather than remembered.

    THIS WAS A TYPED-IN NAME AND IT WENT BLIND. It said `families/grid` --
    true when it was written, and on 2026-08-24 `grid` was taken off sale, so
    its pay button came off the page. Six cases here reach for that button.
    Every one of them stopped testing anything that day, and the file did not
    go red: a mutation that cannot find its target changes nothing, the gate
    passes the unchanged page, and a case whose subject has vanished reports
    "the gate still passed". The estate had just LOST a control and the proof
    of that control reported success.

    So the subject is derived: a family the catalog says is live, whose built
    page really carries the button. If no family qualifies, this says so and
    stops -- an estate with no pay button anywhere is a thing to be told about,
    never a reason to quietly certify six checks that ran on nothing.
    """
    import json as _json
    cat = _json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    for fam in sorted(cat["families"], key=lambda f: f["id"]):
        c = fam.get("checkout") or {}
        if c.get("status") != "live":
            continue
        page = ROOT / "families" / fam["id"] / "index.html"
        if page.exists() and "btn btn-buy" in page.read_text(encoding="utf-8"):
            return f"families/{fam['id']}/index.html"
    print("CANNOT RUN: no family both declares a live checkout and shows a pay "
          "button on its built page, so every case about pay buttons here would "
          "mutate nothing and pass. If the estate really sells nothing right now "
          "that is the finding; if it sells something, this is a defect.",
          file=sys.stderr)
    raise SystemExit(2)


PAID = _a_paid_page()                                       # a family with a real pay link
PAID_ID = PAID.split("/")[1]                                # ...and that family's id
PARKED = "families/az-contractors/index.html"               # the one parked family
NOSALE = "families/recalls/index.html"                       # one of the twelve not for sale
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


def priced_subject() -> tuple[str, str]:
    """A family the catalog prices in dollars, and that amount, read at run time.

    This case used to be pinned to `families/quakes/index.html` and the amount
    "$249". On 2026-08-25 that product was withdrawn -- it charged for dated
    copies of records USGS serves free -- and its price became "Not for sale".
    The mutation then removed a string that was no longer on the page, so the
    gate had nothing to refuse and the case reported the gate as dead when what
    had actually died was the subject. A pinned subject always ends this way:
    the day the page it names stops being the page it describes, the test starts
    complaining about itself and nobody can tell which of the two is broken.

    So the subject is derived. The first family, in id order, that the catalog
    prices with an amount AND whose built page carries that amount, is the one
    whose price gets taken off. If no family is priced at all, this refuses
    rather than reporting a check it could not fire.
    """
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fams = cat["families"] if isinstance(cat, dict) else cat
    for fam in sorted(fams, key=lambda f: f["id"]):
        price = str(fam.get("price", ""))
        page = ROOT / "families" / fam["id"] / "index.html"
        if "$" in price and page.is_file() and price in page.read_text(encoding="utf-8"):
            return f"families/{fam['id']}/index.html", price
    raise SystemExit(
        "STOP: no family on this site is priced in dollars with that price on its\n"
        "page, so the check that a page must show the price the catalog sells it\n"
        "at has no subject. Do not delete the case: price something, or say in the\n"
        "catalog that nothing is priced any more and why.")


PRICED_PAGE, PRICED_AMOUNT = priced_subject()
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


def _an_on_page_family() -> str | None:
    """The family the catalog marks "on-page", found rather than remembered.

    Same reason as _a_paid_page(): a typed-in family name goes blind the day
    that family changes status, the mutation below finds nothing to break, the
    gate passes the unchanged copy, and a live check gets reported as one that
    cannot be made to fire. Derived here so the case dies loudly instead.
    """
    import json as _json
    cat = _json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    for fam in sorted(cat["families"], key=lambda f: f["id"]):
        if fam.get("sample_status") == "on-page":
            return fam["id"]
    return None


def _drop_on_page_phrase(e: "Estate") -> None:
    fid = _an_on_page_family()
    if fid is None:
        raise LookupError("no family in the catalog is marked on-page, so there is "
                          "nothing this case can take the sentence off")
    import check_site as _g
    e.sub(f"families/{fid}/index.html", _g.ON_PAGE_PHRASE,
          "we print a good deal of it here")


def _child_under_on_page(e: "Estate") -> None:
    fid = _an_on_page_family()
    if fid is None:
        raise LookupError("no family in the catalog is marked on-page, so there is "
                          "nothing this case can hang a child page under")
    e.write(f"families/{fid}/kid/index.html",
            MIN_PAGE.format(t="Zed kid", body="A test page."))


def _on_page_says_not_ready(e: "Estate") -> None:
    """Put the promise of a sample back onto the page that is its own sample.

    This is the shape that actually shipped. On 2026-08-25 the free-time page
    carried "Sample not ready" twice while the directory card linking to it said
    "All of it, free", and this gate passed the estate: only the "pass" branch
    forbade the phrase, so moving a family to on-page dropped the one rule that
    would have caught it. The case is written as a mutation of the real estate,
    not a fixture, so it goes on proving the fix on whichever family is on-page
    next.
    """
    fid = _an_on_page_family()
    if fid is None:
        raise LookupError("no family in the catalog is marked on-page, so there is "
                          "nothing this case can put the phrase back onto")
    e.before_body_end(f"families/{fid}/index.html", "<p>Sample not ready yet.</p>")


def _a_paid_family_with_a_sample() -> str:
    """A family that takes money and ships a sample file, found rather than named.

    The three cases below all break the same file, and none of them may name it.
    On 2026-08-25 the estate had four such families and two of them were being
    edited by somebody else in the same hour; a week from now it may have three
    or six, under different ids. A pinned name would have made these three cases
    quietly stop testing anything on the day their family was renamed or taken
    off sale, exactly as the pay-button cases did when grid went off sale.

    So the subject is worked out the same way the gate works it out: priced in
    dollars, not a kind="build" product, not parked, with a sample.csv on disk.
    """
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fams = cat["families"] if isinstance(cat, dict) else cat
    for fam in sorted(fams, key=lambda f: f["id"]):
        if "$" not in str(fam.get("price", "")) or fam.get("kind") == "build":
            continue
        if fam.get("sample_status") in {"parked", "on-page"}:
            continue
        if (ROOT / "families" / fam["id"] / "sample.csv").is_file():
            return fam["id"]
    raise LookupError(
        "no family on this estate is both priced in dollars and shipping a "
        "sample file, so there is no sample for these cases to break. If that "
        "is really true the finding is that nothing here sells a file any more; "
        "it is never a reason to delete the cases.")


def _empty_a_paid_sample(e: "Estate") -> None:
    """Cut a paid family's sample.csv back to its column names and nothing else.

    Not an empty file -- a header-only one, which is the shape an empty sample
    actually takes when the writer runs and the feed collected nothing. A check
    that only looked at whether the path exists, or at the file's size, would
    see this one as healthy.
    """
    rel = f"families/{_a_paid_family_with_a_sample()}/sample.csv"
    e.write(rel, e.read(rel).splitlines()[0] + "\n")


def _drop_a_paid_sample(e: "Estate") -> None:
    e.drop(f"families/{_a_paid_family_with_a_sample()}/sample.csv")


def _scramble_a_paid_sample(e: "Estate") -> None:
    """Leave the CSV alone and make the JSON copy unreadable.

    The gate reads sample.csv first, so breaking that one here would refuse from
    a different line and this case would credit the wrong check.
    """
    e.write(f"families/{_a_paid_family_with_a_sample()}/sample.json",
            '{"rows": [ this is not json at all')


def cases() -> list[tuple]:
    C = []

    def add(line, name, fn, expect):
        C.append((line, name, fn, expect))

    # -- the classifier, tested before any page it produced -------------------
    add(245, "the address rule starts seeing a flat number in every address",
        lambda e: e.bend_privacy(BEND_UNIT), "now reads")
    add(250, "the address rule keeps the wrong part of the street",
        lambda e: e.bend_privacy(BEND_KEPT), "and the page must show")
    add(255, "the name rule starts reading a company as a person",
        lambda e: e.bend_privacy(BEND_PERSON), "as a person's own name")
    add(260, "the whole rule starts withholding rows that are not homes",
        lambda e: e.bend_privacy(BEND_SUPPRESS), "deletes a real registration")

    # -- what reaches a published page ---------------------------------------
    add(299, "a flat number survives into a published address cell",
        lambda e: e.sub(ADDR_PAGE, ADDR_CELL, ADDR_CELL + " APT 3", count=1),
        "prints a flat or unit number")
    add(311, "addresses are shortened and the page never admits it",
        lambda e: e.sub(ADDR_PAGE, "cut back to the street", "tidied up"),
        "never says so")
    add(315, "a page prints addresses and declares no withheld count",
        lambda e: e.re_sub(ADDR_PAGE, r'<meta name="data-withheld" content="\d+">', ""),
        "declares no data-withheld count")
    add(320, "rows are withheld and the page never mentions it",
        lambda e: e.sub(ADDR_PAGE, "2 rows withheld", "2 rows set aside"),
        "the page never says so")
    add(324, "the page's withheld count and the generator's disagree",
        lambda e: e.sub(ADDR_PAGE, 'content="2"', 'content="5"', count=1),
        "row(s) withheld but its generator declared")

    # -- pay links ------------------------------------------------------------
    add(341, "a page carries a pay link and the catalog declares no checkout",
        lambda e: e.family(PAID_ID, lambda f: f.pop("checkout", None)),
        "declares no checkout")
    add(346, "the checkout record has written terms but no address to pay at",
        lambda e: e.family(PAID_ID, lambda f: f["checkout"].pop("url", None)),
        "checkout record declares no url")
    add(350, "the page's pay link is not the one the catalog declared",
        lambda e: e.family(PAID_ID, lambda f: f["checkout"].__setitem__(
            "url", "https://ustechautomations.com/permits/offers/somewhere-else/buy")),
        "pay links the catalog never declared")
    add(353, "a pay link that has never been fetched and found working",
        lambda e: e.family(PAID_ID, lambda f: f["checkout"].pop("verified", None)),
        "never verified")
    add(356, "a pay link last proved working too long ago",
        lambda e: e.family(PAID_ID, lambda f: f["checkout"].__setitem__(
            "verified", "2020-01-01")),
        "days ago")
    # Pins today's date as well, so the age check above cannot fire first.
    add(358, "a pay link whose last check did not say it was live",
        lambda e: e.family(PAID_ID, lambda f: f["checkout"].update(
            {"status": "unknown", "verified": str(__import__("datetime").date.today())})),
        "its last check said")

    # -- the search line ------------------------------------------------------
    add(375, "a page ships with no search line at all",
        lambda e: e.re_sub(
            FAM, r'<meta (?:name|property)="(?:og:|twitter:)?description" content=".*?">', ""),
        "no meta description")
    add(378, "a search line long enough to be cut off mid-word",
        lambda e: e.re_sub(FAM, r'<meta name="description" content=".*?">',
                           f'<meta name="description" content="{LONG_DESC}">'),
        "characters, over")
    add(380, "a page ships three different answers to the same question",
        lambda e: e.re_sub(FAM, r'<meta property="og:description" content=".*?">',
                           '<meta property="og:description" content="A different line.">'),
        "different descriptions")
    # Only reachable on a child page: on a family page the newer rail check at
    # line 554 catches a stray amount in the search line first. Reported, not
    # worked around.
    add(425, "a child page offers a price in search results that we do not sell",
        lambda e: e.re_sub(
            KID, r'(<meta (?:name|property)="(?:og:|twitter:)?description" content=")',
            r'\g<1>$4321. '),
        "search line offers")

    # -- one page, one list ----------------------------------------------------
    # The mirror of the folder-in-neither-list case above. A folder in both lists
    # gets built twice and the build dies on "file already exists", naming
    # neither of the two files you have to open. Both cases use the SAME
    # mutation as the honest case further down -- put a family in extras.json
    # too -- and the only difference is the kind="build" marker. That is
    # deliberate: if the check could not tell those two apart it would not be a
    # check, it would be a coin toss.
    add(548, "a family is named in both product lists",
        lambda e: e.extras_add("ttb"),
        "named in both catalog.json and extras.json")
    add(548, "the one legal overlap loses the marker that makes it legal",
        lambda e: e.family("offers", lambda f: f.pop("kind")),
        "named in both catalog.json and extras.json")

    # -- the hub ---------------------------------------------------------------
    add(637, "the hub loses the address a buyer writes to",
        lambda e: e.sub(HUB, MAILTO, "mailto:nobody@example.com"),
        "hub missing operations@ mailto")
    add(643, "the hub grows a claim we cannot stand behind",
        lambda e: e.before_body_end(HUB, "<p>SOC 2 certified.</p>"),
        "hub contains forbidden")

    # -- every family in the catalog -------------------------------------------
    # First, before any of the branches below are asked. Each of them tests the
    # status against one particular value, so a typo matches none of them, drops
    # every demand that value carries, and the estate still reports ok.
    add(658, "a family's sample status is a value no gate in this file knows",
        lambda e: e.family("ttb", lambda f: f.__setitem__("sample_status", "on-pag")),
        "sample status no gate in this file knows")
    add(662, "a family is in the catalog and its page was never built",
        lambda e: e.drop(FAM), "missing ")
    add(666, "a family page loses the address a buyer writes to",
        lambda e: e.sub(FAM, MAILTO, "mailto:nobody@example.com"),
        "missing mailto")
    add(685, "a family we cannot collect still shows a price",
        lambda e: e.before_body_end(PARKED, "<p>Yours for $99.</p>"),
        "parked but still shows a dollar price")
    # The page says it four times, three of them capitalised, and the check reads
    # the page in lower case. Removing one of the four leaves the check green and
    # makes a perfectly live check look dead -- so the mutation has to take out
    # every spelling of it.
    add(687, "a family we cannot collect never says it is unavailable",
        lambda e: e.re_sub(PARKED, r"(?i)not available", "coming along nicely"),
        "never says it is not available")
    # The price is taken off the page entirely rather than changed, because
    # changing it trips the price-rail check (line 550) first. The page and the
    # amount are derived, never named -- see priced_subject().
    add(689, "a family page stops showing the price the catalog sells it at",
        lambda e: e.sub(PRICED_PAGE, PRICED_AMOUNT, ""), "missing price")
    add(691, "a family page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(FAM, "<p>Trusted by Fortune 500 teams.</p>"),
        "contains forbidden")
    add(699, "the catalog says the sample works and the page says it does not",
        lambda e: e.before_body_end(FAM, "<p>Sample not ready yet.</p>"),
        "page says sample not ready")
    add(702, "the sample is not proved and the page does not warn anyone",
        lambda e: e.family("ttb", lambda f: f.__setitem__("sample_status", "fail")),
        "must say sample not ready")
    # "on-page" drops the demand above -- the page is not waiting on a sample, so
    # it must not be made to say it is. What it carries instead is a claim to a
    # buyer, that nothing is held back, and this is the check that the page
    # actually makes it. Without it the status would ship checked by no rule.
    add(710, "a family says its whole file is on its page, and the page never says so",
        _drop_on_page_phrase, "never says so")
    # And the other half of the same claim. The sentence above being present says
    # nothing about what else the page says, so both could be on it at once -- and
    # both WERE, which is what this case exists to stop happening twice.
    add(726, "a family whose page is its own sample also promises a sample is coming",
        _on_page_says_not_ready, "no sample is coming")

    # -- the bridge pages ------------------------------------------------------
    add(737, "a bridge page is listed and was never built",
        lambda e: e.drop(BRIDGE), "missing ")
    add(740, "a bridge page loses the address a buyer writes to",
        lambda e: e.sub(BRIDGE, MAILTO, "mailto:nobody@example.com"),
        "missing mailto")
    add(742, "a bridge page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(BRIDGE, "<p>We are HIPAA aligned.</p>"),
        "contains forbidden")
    # The banned-phrase check was taught to tell a denial from a boast, so the
    # expensive half of that change is proving it did not become a way through.
    # Every one of these is a claim wearing a denial's clothes, and every one of
    # them must still be refused. If any of these ever goes green, the fix has
    # turned into a hole and the hole is worse than the false alarm it replaced.
    add(742, "a boast that opens with a denial and then makes the claim anyway",
        lambda e: e.before_body_end(
            BRIDGE, "<p>We do not just meet SOC 2 requirements, we exceed them.</p>"),
        "contains forbidden")
    add(742, "a denial about one thing with the claim bolted on after an 'and'",
        lambda e: e.before_body_end(
            BRIDGE, "<p>We do not cut corners and we are SOC 2 certified.</p>"),
        "contains forbidden")
    add(742, "a claim made by negating the doubt instead of the claim",
        lambda e: e.before_body_end(
            BRIDGE, "<p>Our HIPAA compliance is not in question.</p>"),
        "contains forbidden")
    add(742, "an honest denial in one sentence and the claim in the next",
        lambda e: e.before_body_end(
            BRIDGE, "<p>We are not slow. We are SOC 2 certified.</p>"),
        "contains forbidden")
    add(742, "the banned phrase hidden in a link, where no reader can see it",
        lambda e: e.before_body_end(
            BRIDGE, '<p>We do not use a partner scheme. '
                    '<a href="/partner?ref=2">join</a></p>'),
        "contains forbidden")
    add(746, "a bridge page is built and nothing on the hub links to it",
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

    add(776, "a folder full of child pages that no catalog entry describes",
        orphan_with_children, "in neither catalog.json nor a catalog-add fragment")

    def children_with_no_parent(e: Estate) -> None:
        e.write("families/zz-frag/kid/index.html", MIN_PAGE.format(t="Zed kid", body="A test page."))
        e.write("catalog-add-zz-frag.json", json.dumps({
            "id": "zz-frag", "name": "Zed", "buyer": "nobody", "cadence": "never",
            "price": "Not for sale", "sample_status": "pass", "group": "Test",
            "short": "Zed", "who": "nobody"}, indent=2))

    add(778, "child pages with no family page above them, so nothing links to them",
        children_with_no_parent, "children are unreachable")
    add(782, "a family we cannot collect still has child pages selling it",
        lambda e: e.write("families/az-contractors/kid/index.html",
                          MIN_PAGE.format(t="Zed kid", body="A test page.")),
        "parked but has child pages")
    add(790, "a family whose whole file is on its own page grows a child page",
        _child_under_on_page, "but has child pages")
    add(797, "a child page loses the address a buyer writes to",
        lambda e: e.sub(KID, MAILTO, "mailto:nobody@example.com"), "missing mailto")
    add(799, "a child page grows a claim we cannot stand behind",
        lambda e: e.before_body_end(KID, "<p>Trusted by Fortune 500 teams.</p>"),
        "contains forbidden")
    add(801, "a child page shows a different price from the family above it",
        lambda e: e.sub(KID, "$99/mo", "$0/mo"), "does not show its parent's price")
    add(803, "a child page carries no read date, so nothing can prove it is current",
        lambda e: e.sub(KID, 'name="data-newest"', 'name="data-newest-was-here"'),
        "nothing can prove it is current")
    # -- the button itself ----------------------------------------------------
    # Every pay-link check above can only see a page that HAS a pay address on
    # it. Take the address away and all six go quiet while the page still shows
    # a button saying Subscribe. These are the cases that were unrefusable
    # yesterday, and the reason for each one is in its own name.
    def _paid_url(e: Estate) -> str:
        """The address this page's own button really points at.

        NOT a typed-in one. These two cases used to look for a
        `ustechautomations.com/permits/...` address, because the family they
        pointed at back then paid through our own rail. Every family that takes
        cards today pays through Stripe, so that pattern matched nothing, the
        mutation changed nothing, and both cases reported that the gate still
        passed -- on a page nobody had broken.
        """
        return next(f for f in json.loads(e.read("catalog.json"))["families"]
                    if f["id"] == PAID_ID)["checkout"]["url"]

    def button_to_nowhere(e: Estate) -> None:
        e.sub(PAID, f'href="{_paid_url(e)}"', 'href="#"')

    def button_to_the_inbox(e: Estate) -> None:
        e.sub(PAID, f'href="{_paid_url(e)}"', f'href="{MAILTO}"')

    def button_somewhere_else(e: Estate) -> None:
        """Move ONE of the two buttons, so the pay-link checks stay green.

        The page keeps a real declared pay address on its other button, which is
        all check_pay_links ever looks at, so nothing above notices that the
        first thing a reader sees now leads somewhere else entirely.
        """
        url = next(f for f in json.loads(e.read("catalog.json"))["families"]
                   if f["id"] == "ttb")["checkout"]["url"]
        e.sub(FAM, f'href="{url}"', 'href="https://ustechautomations.com/feeds/ttb"',
              count=1)

    add(903, "a page shows a pay button and clicking it does nothing",
        button_to_nowhere, "goes nowhere")
    add(903, "a pay button dressed as a checkout that quietly goes to the inbox",
        button_to_the_inbox, "goes nowhere")
    add(907, "a button sends the buyer to an address the catalog never declared",
        button_somewhere_else, "not the checkout this page's catalog row declares")
    # count=1 so only the button's own wording moves. The price rail, the tab
    # title and the search line all still say $99, which is what every price
    # check in this gate reads -- none of them has ever looked at a button.
    add(915, "a button offers to charge an amount we do not sell at",
        lambda e: e.sub(FAM, "$99 a month", "$149 a month", count=1),
        "offering to charge $149"),
    add(919, "a monthly subscription with a button that says it is paid once",
        lambda e: e.sub(FAM, "Subscribe — $99 a month", "Buy once — $99", count=1),
        "one of them is a subscription and the other is paid once")
    # The quiet one, and the one that actually happened: the children under five
    # families grew buttons and the hand-written parents above them did not, so
    # every buyer landing on the family page was still sent to an email thread
    # while the catalog said the product took a card.
    # Found by an audit of this very check, hours after it was written, and the
    # worst of the three: "$9" is a SUBSTRING of "$99/mo", so a substring test
    # waved through a button understating the price ten times over. Every price
    # we sell was open to it -- $249 -> $24, $175 -> $17, $59 -> $5.
    add(915, "a button understates the price by a factor of ten",
        lambda e: e.sub(FAM, "$99 a month", "$9 a month", count=1),
        "offering to charge $9"),
    # Single quotes are what anyone hand-writing one line of HTML reaches for,
    # and the pay-link check above still cannot see them: its pattern requires a
    # double quote. So this address is invisible to everything except the button
    # check, which is the point of the case.
    add(907, "a checkout address written in single quotes, invisible to the pay-link check",
        lambda e: e.before_body_end(
            FAM, "<p><a class='btn btn-buy' href='https://buy.stripe.com/nOtReAl'>"
                 "Subscribe &mdash; $99 a month</a></p>"),
        "not the checkout this page's catalog row declares"),
    # A <button> is a pay button to every reader and was not an <a>, so reading
    # only anchors let one straight through.
    add(903, "a hand-written button element that offers to subscribe and does nothing",
        lambda e: e.before_body_end(FAM, "<p><button>Subscribe now</button></p>"),
        "goes nowhere"),
    add(962, "a checkout we proved working, and the page still shows no button",
        lambda e: e.re_sub(PAID, r"(?s)<a class=\"btn btn-buy.*?</a>", ""),
        "shows no pay button at all")
    # The same refusal reached from the other side, and the reason the condition
    # is "any declared address" and not "a proved one". A link is chargeable the
    # moment it is minted. Left declared with no button and no verification, it
    # is money sitting in Stripe that no customer can reach and no check here
    # used to mention.
    def minted_and_unreachable(e: Estate) -> None:
        e.family("crawler", lambda f: f.__setitem__("checkout", {
            "url": "https://buy.stripe.com/nOtReAl",
            "lands_on": "buy.stripe.com",
            "label": "Subscribe — $175 a month",
            "terms": "Cancel any time.",
            "after": "You get the feed from the next run.",
            "status": "unverified"}))

    add(962, "a link is minted and declared, and no page anywhere points at it",
        minted_and_unreachable, "nothing anywhere points a buyer at it")

    # The overlap, proved rather than asserted. The same defect on a CHILD page
    # is caught by the child-price check (line 715); on a FAMILY page the price
    # checks get there first, at line 554. Both cases earn their place: line 715
    # is the only thing guarding the child pages, and the price checks do not
    # walk them.
    add(587, "the same defect on a family page is caught by the newer check first",
        lambda e: e.re_sub(
            FAM, r'(<meta (?:name|property)="(?:og:|twitter:)?description" content=")',
            r'\g<1>$4321. '),
        "names $4321 in its tab title or its search line")
    # A record that is NOT selling, carrying a checkout address in its prose.
    # This is not hypothetical: quakes was held on 24 Aug and its address was
    # left in a note so nothing would be re-minted, and within the hour an audit
    # grepped the catalog, saw a live-looking address on the quakes row, and
    # reported it as a chargeable checkout no page could reach. Both address
    # shapes this estate uses are proved, because the two-hop /buy shape is the
    # one every grep in this repo has historically failed to see.
    #
    # Both cases now mutate crawler, and the reason is worth writing down. The
    # first one used to mutate quakes, which was the family the incident
    # happened to. The quakes hold was cleared on 2026-08-24 and its checkout
    # url came back, and this check deliberately skips any row that HAS a url --
    # a remembered address is only dangerous on a row that is not selling. So
    # the case stopped firing, and it stopped firing because the gate was right,
    # not because it broke. Pointing it at a row that still has no url keeps the
    # bare buy.stripe.com shape proved. Do not re-point it at whichever family
    # is held this month: pick one from catalog.json whose checkout has no url,
    # or the case dies again the day that hold lifts.
    add(992, "a product not for sale keeps a Stripe address written out in a note",
        lambda e: e.family("crawler", lambda f: f["checkout"].__setitem__(
            "note", "Not for sale yet. The link is "
                    "https://buy.stripe.com/28E9AM4h0bSOcnW6r80sU0D "
                    "and it does not need minting again.")),
        "spells out a checkout address"),
    add(992, "a product sold by email keeps a two-hop /buy address in a note",
        lambda e: e.family("crawler", lambda f: f["checkout"].__setitem__(
            "note", "Sold by email for now. The address, when we want it, is "
                    "https://ustechautomations.com/permits/offers/crawler-policy-sentinel/buy")),
        "spells out a checkout address"),

    # -- the rule that keeps a blocked source out of a paid file --------------
    add(1031, "the instructions the file-packer reads are deleted",
        lambda e: e.drop("DELIVERY.md"),
        "is missing"),
    add(1039, "a blocked source is quietly dropped from those instructions",
        lambda e: e.write("DELIVERY.md",
                          e.read("DELIVERY.md").replace("Marin", "the county")),
        "no longer names them"),
    add(1026, "the guard that refuses a blocked file is emptied out",
        lambda e: e.sub("scripts/outbound_guard.py", "BLOCKED_SOURCES = {",
                        "BLOCKED_SOURCES = {}\n_WAS = {", count=1),
        "would not load"),

    # -- the sample file a paying stranger downloads --------------------------
    #
    # Three ways the same thing goes wrong: the file is there and holds nothing,
    # the file is not there at all, and the file is there and cannot be read.
    # The subject is derived in _a_paid_family_with_a_sample() rather than typed,
    # for the reason every other derived subject in this file exists: a family id
    # written down here stops being the right family the day the estate reprices
    # something, and a mutation that cannot find its target changes nothing,
    # leaves the gate passing, and reports a live check as one that cannot fire.
    add(1147, "a family that takes money has no sample file at all",
        _drop_a_paid_sample, "on disk to open"),
    add(1157, "a family that takes money has a sample file nobody can read",
        _scramble_a_paid_sample, "cannot be read"),
    add(1163, "a family that takes money ships a sample with nothing in it",
        _empty_a_paid_sample, "holds 0 data rows"),
    return C


# The seven refusal points proved in the other file rather than this one, so
# that the coverage count below is the whole gate and not just this file's half.
ELSEWHERE = {
    512: "check_prices_selftest.py -- a built folder in neither list",
    578: "check_prices_selftest.py -- a priced page in no catalog",
    583: "check_prices_selftest.py -- a page that disagrees with the catalog",
    587: "check_prices_selftest.py -- a dead price in the tab title or search line",
    610: "check_prices_selftest.py -- the price list names a product we do not sell",
    615: "check_prices_selftest.py -- the price list quotes last week's price",
    621: "check_prices_selftest.py -- a product missing from the price list",
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


def refusal_patterns() -> dict[int, "re.Pattern"]:
    """What each refusal point's message looks like, as something to match against.

    Pinning a case to a line number is what makes the coverage claim auditable,
    and it is also the thing that rots: insert a function above and every pin
    below it slides. A pin that lands on nothing is caught before the run. A pin
    that slides onto ANOTHER refusal point is the dangerous one -- the case still
    goes red, still reports PASS, and quietly credits the wrong check while the
    real one is reported as never proven, which is an invitation to delete a
    check that works.

    So do not trust the number. Every refusal message is built from an f-string
    whose fixed words are known here; the parts that are filled in at run time
    become wildcards. After a case goes red, the message it produced is matched
    against the pattern for the line it claims to have hit. Credit is given for
    the line that actually refused, not the line somebody typed.
    """
    import ast
    src = (ROOT / "scripts" / "check_site.py").read_text(encoding="utf-8")
    out = {}
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "fail" and node.args):
            continue
        arg = node.args[0]
        parts = arg.values if isinstance(arg, ast.JoinedStr) else [arg]
        pat = ""
        for v in parts:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                # Whitespace is folded because a message wrapped across source
                # lines arrives as one line, and because f-strings are joined
                # without a space between them.
                pat += r"\s*".join(re.escape(w) for w in v.value.split())
                if v.value[-1:].isspace() or v.value[:1].isspace():
                    pat += r"\s*"
            else:
                pat += ".*?"
        out[node.lineno] = re.compile(pat, re.S)
    return out


# Honest content the gate refuses on purpose, ruled on rather than fixed.
# These still run, still print, and still show as blocked. What they do not do
# is sit in the same bucket as a surprise, because somebody has already looked
# at this one and decided the strict reading is the one we want.
PARKED_FALSE_ALARMS = {
    "a page we cannot collect quoting someone else's fee as a fact":
        "PARKED 2026-08-23. The parked-family money check reads every dollar "
        "amount on the page, so it also bites a parked page that honestly "
        "quotes someone else's fee. No parked page carries a third-party fee "
        "today, so nothing is blocked right now -- the fault is latent. Left "
        "strict deliberately: loosening it in a hurry risks letting a real "
        "price ship on a page we cannot deliver, which is the worse trade.",
}


def extra_working_button(e: Estate) -> None:
    """A correct pay button, added by hand to a page that already sells."""
    url = next(f for f in json.loads(e.read("catalog.json"))["families"]
               if f["id"] == "ttb")["checkout"]["url"]
    e.before_body_end(FAM, f'<p><a class="btn btn-buy" href="{url}">'
                           f'Subscribe &mdash; $99 a month</a></p>')


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
        ("a flat denial with nothing else in the sentence",
         lambda e: e.before_body_end(BRIDGE, "<p>We are not SOC 2 certified.</p>")),
        ("a denial of who we sell to",
         lambda e: e.before_body_end(BRIDGE, "<p>We do not sell to the Fortune 500.</p>")),
        ("a denial written with 'never' instead of 'not'",
         lambda e: e.before_body_end(BRIDGE, "<p>We never claim HIPAA compliance.</p>")),
        # The reason the whole rule exists. families/offers/ is in both lists on
        # purpose: catalog.json holds its price and its written terms so they are
        # checked like every other product's, and extras.json is what actually
        # builds its page. It is allowed by its kind="build" marker and not by
        # its name, so a second product tomorrow is allowed on the same terms --
        # which is what this case adds, using the very mutation the refusal case
        # above uses. Same edit, opposite verdict, and the marker is the only
        # thing between them.
        ("a second product deliberately in both lists, marked as built elsewhere",
         lambda e: (e.extras_add("ttb"),
                    e.family("ttb", lambda f: f.__setitem__("kind", "build")))),
        # Still refused, on purpose. See PARKED_FALSE_ALARMS above.
        ("a page we cannot collect quoting someone else's fee as a fact",
         lambda e: e.before_body_end(
             PARKED, "<p>The state charges $9 for a copy of the roster.</p>")),
        ("a business address with a suite number in it",
         lambda e: e.sub(ADDR_PAGE, ADDR_CELL, "123 MARKET ST STE 5", count=1)),
        ("one more honest child page under a family that already sells",
         lambda e: e.write("families/ttb/zz-honest/index.html",
                           MIN_PAGE.format(t="Zed", body="A test page. $99/mo."))),
        # The other half of the button check. A gate that only ever refuses
        # buttons is a ban on selling, so a correct one -- written by hand,
        # without any generator involved -- has to be waved straight through.
        ("one more working pay button, hand-written on a page that sells",
         extra_working_button),
        # Widening the detector to <button> must not make every button on the
        # site a pay button. An ordinary control that does not offer to take
        # money is not this check's business.
        ("an ordinary button on a page that sells, doing something other than selling",
         lambda e: e.before_body_end(
             FAM, '<p><button class="copy">Copy this link</button></p>')),
        # And the twelve families that are not for sale must be able to point at
        # the inbox in plain words without that counting as a broken button.
        ("a page we do not sell yet, offering the email route in so many words",
         lambda e: e.before_body_end(
             NOSALE, '<p><a href="mailto:operations@ustechautomations.com">'
                     'Buy a copy by email</a> once this one opens.</p>')),
        ("a family page that prints an amount as data, not as its price",
         lambda e: e.before_body_end(
             FAM, "<table><tr><th>Fee</th></tr><tr><td>$1,250.00</td></tr></table>")),
        # The other half of the held-record rule. Saying how to FIND a link is
        # exactly what we want a held record to do -- the whole point of the
        # check is to push people towards the stamp and away from the address.
        # If this were refused, the check would be a ban on writing anything
        # useful down, and the next person in a hurry would delete it.
        ("a held product saying how to find its link by the stamp it was minted with",
         lambda e: e.family("quakes", lambda f: f["checkout"].__setitem__(
             "note", "Held. The link exists and is live. Find it by its Stripe stamp, "
                     "permits_sku=quake-record-attestation. Nothing needs minting again."))),
        # And a held record may still name the surface a link lives on. That is
        # a page address, not a checkout address, and refusing it would leave a
        # held record unable to say where the money is being taken today.
        ("a held product naming the other estate's offer page, which is not a checkout",
         lambda e: e.family("quakes", lambda f: f["checkout"].__setitem__(
             "note", "Held here. The permits estate still sells it from "
                     "ustechautomations.com/permits/offers/quake-record-attestation, "
                     "which is not this repo's page to change."))),
    ]


def build(box: Path) -> None:
    """A complete, working copy of the estate. Never the real one."""
    shutil.rmtree(box, ignore_errors=True)
    (box / "scripts").mkdir(parents=True)
    # The fragments come too. A family may live in catalog-add-<id>.json instead
    # of catalog.json, and a copy that leaves those behind is not the estate: the
    # family arrives with no home, the untouched copy fails on it, and every case
    # below is voided. That is not a hypothetical -- it happened the first hour a
    # fragment existed, and it will happen again on whichever family is added
    # next, so this is a glob and not a list of names.
    for name in (*ESTATE, *sorted(p.name for p in ROOT.glob("catalog-add-*.json"))):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, box / name)
        else:
            shutil.copy2(src, box / name)
    for name in MODULES:
        shutil.copy2(ROOT / "scripts" / name, box / "scripts" / name)


def button_free_families(box: Path) -> list[str]:
    """The families whose page carries no pay button at all.

    Counted with the gate's OWN detector rather than a copy of it, so the number
    cannot quietly drift from what the gate actually sees. Without this the
    "twelve not-for-sale pages are allowed to have no button" claim is empty:
    the untouched copy passing only proves the gate is quiet, not that there was
    anything for it to be quiet about.
    """
    code = ("import json,sys;sys.path.insert(0,'scripts');import check_site as g;"
            "from pathlib import Path;"
            "print(json.dumps(sorted(f['id'] for f in g.CATALOG['families'] "
            "if not g.buy_buttons("
            "(Path('families')/f['id']/'index.html').read_text(encoding='utf-8')))))")
    r = subprocess.run([PY, "-c", code], cwd=box, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("could not count the button-free pages:\n" + r.stderr)
    return json.loads(r.stdout)


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
    # Every case is pinned to a line of check_site.py, which is what makes the
    # coverage claim auditable -- and also what rots the moment somebody inserts
    # a function above it. Drifted numbers do not announce themselves: the case
    # quietly credits whatever check now sits on that line, and a live check gets
    # reported as never proven, which is an invitation to delete it. So check the
    # pins before running anything, and refuse to report a score off stale ones.
    pinned = {c[0] for c in cases()} | set(ELSEWHERE)
    points = refusal_points()
    patterns = refusal_patterns()
    drifted = sorted(pinned - set(points))
    if drifted:
        raise SystemExit(
            "STOP. These line numbers no longer point at a place the gate can "
            "refuse a build, so every number this test prints would be wrong:\n  "
            + "\n  ".join(str(d) for d in drifted)
            + "\ncheck_site.py has moved under this test. Re-pin the cases "
              "before trusting a single result.")

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
    silent = button_free_families(box)
    if len(silent) < 10:
        raise SystemExit(f"only {len(silent)} family page(s) carry no pay button, so the "
                         f"'a page with no button is allowed' half of the button check is "
                         f"not really being exercised: {silent}")
    print(f"the untouched copy of the estate passes (exit 0), with {len(silent)} family "
          f"pages carrying no pay button at all and the gate saying nothing about any of "
          f"them.\n{len(todo)} case(s) to break it.\n")

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
        elif not patterns[line].search(out):
            # Red for the right words, from the wrong line. This is what a
            # drifted pin looks like once the numbers still land on a refusal
            # point, and it is the reason the message is matched and not just
            # the exit code.
            first = out.splitlines()[-1] if out else "(nothing)"
            bad.append((line, name,
                        f"refused, but not from the line this case is pinned to: {first}"))
            print(f"  PIN?  {line:>4}  {name}\n        the refusal did not come from "
                  f"check_site.py:{line}: {first[:120]}")
        else:
            print(f"  PASS  {line:>4}  {name}")

    # The other half: honest pages the gate must let through.
    wrongly_refused = []
    parked_refused = []
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
            elif name in PARKED_FALSE_ALARMS:
                why = out.splitlines()[-1]
                parked_refused.append((name, why))
                print(f"  PARK  {name}\n        {why[:150]}")
            else:
                why = out.splitlines()[-1]
                wrongly_refused.append((name, why))
                print(f"  BLOCK {name}\n        {why[:150]}")

    if not args.keep:
        shutil.rmtree(box, ignore_errors=True)

    total = len(todo)
    proved_here = {line for line, _, _, _ in todo} - {l for l, _, _ in bad} \
        - {l for l, _, _ in unreachable}
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
    print(f"  refuse honest content, ruled on  : {len(parked_refused)}")
    print(f"  ({here} proved here, {there} in check_prices_selftest.py"
          f"{f', {both} in both' if both else ''})")
    print("=" * 70)
    for line, src in sorted(unproven.items()):
        print(f"  check_site.py:{line} has never been shown to refuse anything\n      {src}")
    for name, why in wrongly_refused:
        print(f"  REFUSES HONEST CONTENT: {name}\n      {why}")
    for name, why in parked_refused:
        print(f"  PARKED, STILL REFUSES HONEST CONTENT: {name}\n      {why}"
              f"\n      {PARKED_FALSE_ALARMS[name]}")
    for line, name, why in unreachable:
        print(f"  line {line}: {name}\n      {why}")
    for line, name, why in bad:
        print(f"  line {line}: {name}\n      {why}")
    raise SystemExit(1 if bad or unreachable or wrongly_refused
                     or (unproven and args.only is None) else 0)


if __name__ == "__main__":
    main()
