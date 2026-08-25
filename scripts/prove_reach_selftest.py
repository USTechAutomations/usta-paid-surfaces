#!/usr/bin/env python3
"""Prove the unreachable-money check, both ways, on whatever we are selling today.

THE SUBJECT IS PICKED AT RUN TIME AND IS NEVER A NAMED FAMILY. This test used to
be pinned to `grid`, and the day grid came off sale it went red and stayed red --
not because the rule broke, but because the page it watched stopped being the page
it described. That is what a pinned subject always does eventually: it turns a
test about the estate into a test about itself, and the only way to read it is to
know which of the two it is complaining about. So the fixture is now whichever
family the catalog says is on sale right now, read off disk, still a real page and
never a mock.

Two page shapes exist and both must be covered, so the subject is picked twice:

  BORROWED  its button points somewhere that is not buy.stripe.com -- an address
            the permits estate minted. This is the shape that used to hide: a rule
            that greps for buy.stripe.com cannot see it at all, so a check that
            works on the others and not on this one reads as coverage while
            covering nothing.
  OURS      its button points straight at a Stripe address we minted for /feeds.

If either shape has no family on sale today, this test REFUSES. It does not
quietly drop the case it can no longer build -- a run that silently covers one
shape looks exactly like a run that covers both.

What the old pin bought that deriving does NOT buy: grid was hand-written, so no
change to the page-building machinery could reach it. Nothing in the catalog says
which pages have a generator, so that property is not derivable here and is not
claimed. What IS preserved is the borrowed-address shape, which is the half that
actually did the hiding.

Two runs, one file different:
  arm    the real page, button intact          -> the checkout is reached
  strip  the same page with the button removed -> the checkout is UNREACHABLE

No network and no Stripe. The redirect walk is a stub, because what is being
proved is the counting, and a rule you can only test when the internet is up is
a rule nobody runs.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_site import buy_buttons  # noqa: E402
from prove_checkouts import page_addresses, reach_report  # noqa: E402

# Stand-in for wherever the borrowed address lands. Its real destination lives in
# another estate's file and is not this repo's to depend on; what the case turns
# on is only that following the button ends somewhere that is NOT one of ours,
# which is asserted below rather than assumed.
BORROWED_DEST = "https://buy.stripe.com/stand-in-for-the-permits-estate-link"
DEAD = "https://buy.stripe.com/thisoneisgone"


def selling_today() -> list[tuple[str, str]]:
    """Every family the catalog prices whose real page shows one pay button.

    Read with the gate's own button detector, so this test and check_site.py can
    never disagree about what a pay button is.
    """
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fams = cat["families"] if isinstance(cat, dict) else cat
    out = []
    for fam in sorted(fams, key=lambda f: f["id"]):
        page = ROOT / "families" / fam["id"] / "index.html"
        # A price is a price only when it names an amount -- build_hub.py and
        # render_slice.py both say it in these words. "Not for sale yet" is a
        # sentence and it is TRUTHY, so testing the field for emptiness counts a
        # withdrawn family as one on sale.
        if "$" not in fam.get("price", "") or not page.is_file():
            continue
        # A page usually shows the same button twice, top and bottom. That is one
        # address, not two -- counting placements here would put a true number
        # next to a false word.
        addrs = {href for href, _label in buy_buttons(page.read_text(encoding="utf-8"))}
        if len(addrs) == 1:
            out.append((fam["id"], addrs.pop()))
    return out


# The address a stand-in borrowed button points at when no live family has one.
# It is the exact shape the earthquake product used until it was withdrawn:
# the permits estate's two-hop address, which is NOT buy.stripe.com and is
# therefore invisible to any rule that greps for that host. Nothing fetches it.
STAND_IN_BORROWED = "https://ustechautomations.com/permits/offers/quake-record-attestation/buy"


def borrowed_declaration() -> dict:
    """What the catalog says out loud about the borrowed-address shape."""
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    return cat.get("borrowed_shape") or {}


def subjects():
    """Pick one family of each shape.

    Returns (borrowed_or_None, ours). A None borrowed slot is allowed ONLY when
    the catalog says in so many words that no family sells through a borrowed
    address today -- and it is refused the moment that statement stops being true.
    """
    on_sale = selling_today()
    borrowed = [x for x in on_sale if "buy.stripe.com" not in x[1]]
    ours = [x for x in on_sale if "buy.stripe.com" in x[1]]
    decl = borrowed_declaration()
    declared_gone = decl.get("in_use") is False

    if not ours:
        raise SystemExit(
            "STOP: this test needs at least one family on sale whose button points\n"
            "straight at Stripe, and the catalog offers none. Do not weaken the test:\n"
            "put a family back on sale, or delete this test and say why.")

    if borrowed:
        if declared_gone:
            # The catalog's word and the catalog's own rows disagree. That is the
            # failure this declaration exists to make loud: a stale "false" here
            # would let the borrowed half be skipped while a real borrowed button
            # was live on the site -- exactly the coverage-that-covers-nothing this
            # whole test was written about.
            raise SystemExit(
                "STOP: catalog.json says borrowed_shape.in_use is false, and "
                f"{len(borrowed)} family(ies) on sale point at a borrowed address: "
                f"{', '.join(f for f, _ in borrowed)}.\n"
                "One of the two is wrong. If a borrowed button is genuinely live, set\n"
                "in_use to true in the same commit that priced it. Do not edit this test.")
        return borrowed[0], ours[0]

    if not declared_gone:
        raise SystemExit(
            "STOP: this test needs one family on sale whose pay button points at a\n"
            "borrowed (non-Stripe) address, and one whose button points straight at\n"
            "Stripe. Today the catalog offers "
            f"{len(borrowed)} borrowed and {len(ours)} Stripe-direct.\n"
            "Both shapes have hidden unreachable money before, so a run covering only\n"
            "one of them is not this test. Do not delete the case that has no subject:\n"
            "either put a family of that shape back on sale, or say out loud in the\n"
            "catalog that the shape no longer exists.")

    # Declared gone. Run the borrowed half anyway, against a stand-in built from a
    # real page, and say so loudly. What a stand-in still proves is the half that
    # did the hiding: an address that is not buy.stripe.com is seen at all, is
    # followed, and is classed as not-ours. What it cannot prove is that a page of
    # this shape exists on the live site -- which is precisely what the catalog
    # has just declared it does not.
    return None, ours[0]


def check(name: str, got, want) -> bool:
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        wanted {want!r}\n        got    {got!r}")
    return ok


def fixture(fam: str, buy: str, strip: bool, swap_from: str | None = None) -> Path:
    """A tiny built site: the real page of `fam`, plus a not-for-sale page.

    `swap_from` builds the stand-in borrowed page: the real page off disk with its
    real Stripe button address replaced by `buy`. Only the address changes -- the
    markup, the labels and everything else stay exactly as the generator wrote
    them, so the harvest is still reading a real page and not a mock of one.
    """
    box = Path(tempfile.mkdtemp(prefix="reach-"))
    (box / fam).mkdir(parents=True)
    raw = (ROOT / "families" / fam / "index.html").read_text(encoding="utf-8")
    if swap_from:
        # Belt and braces, and it is worth saying which. main() takes swap_from
        # off the same page this reads, so on the path the test actually walks
        # this refusal CANNOT fire -- drilled 2026-08-25 by mutating the page and
        # getting a green run, which is the honest answer and not a caught bug.
        # It fires when called directly with an address the page does not carry,
        # also drilled, and it is what would catch a future change that derived
        # swap_from from the catalog instead. A guard that cannot fire today is
        # left in only because it is written down here that it cannot.
        raw, n = re.subn(re.escape(swap_from), buy, raw)
        if not n:
            raise SystemExit(
                f"STOP: could not build the stand-in borrowed page -- {swap_from} is not\n"
                f"on families/{fam}/index.html, so nothing was swapped and the borrowed\n"
                "case would run against a Stripe address while calling it borrowed.")
        if swap_from in raw:
            raise SystemExit(
                f"STOP: {swap_from} is still on the stand-in page after the swap.")
    if strip:
        # Exactly what taking the button off looks like: the anchor becomes an
        # email link. Nothing else about the page changes.
        raw, n = re.subn(r'<a class="[^"]*\bbtn-buy\b[^"]*"[^>]*>.*?</a>',
                         '<a class="mail" href="mailto:operations@ustechautomations.com">'
                         'Email us for the checkout link</a>', raw, flags=re.S)
        # A strip that strips nothing would make the whole "both ways" claim a lie
        # in the quietest possible way: every case would pass because the button
        # was never removed. Refuse rather than report.
        if not n:
            raise SystemExit(
                f"STOP: could not take the button off the {fam} fixture -- the markup on\n"
                f"families/{fam}/index.html has changed shape. Fix this strip, do not\n"
                "weaken the cases that depend on it.")
        if buy in raw:
            raise SystemExit(
                f"STOP: {buy} is still on the stripped {fam} fixture, so the two runs are\n"
                "not actually different and every case below would pass for free.")
    (box / fam / "index.html").write_text(raw, encoding="utf-8")
    # A not-for-sale family: no price, no button, and it must draw no complaint.
    (box / "quiet-family").mkdir()
    (box / "quiet-family" / "index.html").write_text(
        '<h1>Quiet family</h1><p>Not for sale yet.</p>'
        '<a href="mailto:operations@ustechautomations.com">Email us</a>', encoding="utf-8")
    return box


def main() -> int:
    picked, (ofam, obuy) = subjects()
    # Print the subjects. A derived fixture that does not say what it chose is a
    # test nobody can check, and "it passed" would not say on what.
    print(f"subjects picked from catalog.json at run time:")
    if picked is None:
        decl = borrowed_declaration()
        bfam, bbuy, swap_from = ofam, STAND_IN_BORROWED, obuy
        print(f"  borrowed shape: NO LIVE SUBJECT -- running against a STAND-IN")
        print(f"      catalog.json says borrowed_shape.in_use is false, "
              f"declared {decl.get('declared_on', '(no date)')}")
        print(f"      why none today: {decl.get('why_none_today', '(not stated)')}")
        print(f"      stand-in: the {ofam} page off disk with its button address")
        print(f"                swapped to {STAND_IN_BORROWED}")
        print(f"      COVERED by the stand-in: a non-Stripe address is seen at all,")
        print(f"                followed, and classed as not-ours -- the half that hid.")
        print(f"      NOT COVERED: that a page of this shape exists on the live site.")
        print(f"                That is exactly what the catalog has declared it does not.")
    else:
        bfam, bbuy = picked
        swap_from = None
        print(f"  borrowed shape: {bfam:<18} -> {bbuy}")
    print(f"  ours (Stripe):  {ofam:<18} -> {obuy}\n")

    ours = {obuy: ofam}
    if BORROWED_DEST in ours:
        raise SystemExit("STOP: the stand-in destination collides with a real link of ours.")

    def walker(url: str):
        """Stand-in for following the redirects. Only these addresses exist."""
        return {
            bbuy: (BORROWED_DEST, "200"),
            BORROWED_DEST: (BORROWED_DEST, "200"),
            obuy: (obuy, "200"),
            DEAD: (DEAD, "404"),
        }.get(url, (None, "no such address"))

    good = fixture(bfam, bbuy, strip=False, swap_from=swap_from)
    gone = fixture(bfam, bbuy, strip=True, swap_from=swap_from)
    ok = True
    try:
        # --- ARMED: the real page, exactly as it ships -----------------------
        print(f"{bfam} armed -- the real page off disk:")
        seen = page_addresses(good)
        ok &= check("the harvest sees the button on the real page", sorted(seen), [bbuy])
        ok &= check(f"and it is the {bfam} page it came off", seen[bbuy], [bfam])
        r = reach_report(seen, {bfam: bbuy}, ours, walker)
        ok &= check("following it lands on the checkout", sorted(r["reached"]), [BORROWED_DEST])
        ok &= check(f"so nothing {bfam} declares is unreachable", r["declared_unreached"], [])
        ok &= check("the checkout is named as borrowed, not ours", r["borrowed"], [BORROWED_DEST])
        ok &= check("no dead buttons", r["broken"], {})
        ok &= check("the not-for-sale page with no button draws no complaint",
                    "quiet-family" in str(r), False)

        # --- STRIPPED: same page, button removed ------------------------------
        print(f"\n{bfam} stripped -- the identical page with the button taken off:")
        seen = page_addresses(gone)
        ok &= check("the harvest now sees no address at all", seen, {})
        r = reach_report(seen, {bfam: bbuy}, ours, walker)
        ok &= check(f"the catalog still declares it, so {bfam} is refused as unreachable",
                    r["declared_unreached"], [bfam])
        ok &= check("and nothing is reached", r["reached"], {})

        # --- the fault this rewrite exists to fix -----------------------------
        # The old version built "reached" by walking the catalog. Feed it the
        # catalog with no pages at all and it still found the link, which is how
        # a family hides: the check asked the catalog whether the catalog was
        # reachable and the catalog said yes.
        print("\nthe old fault, so it cannot come back:")
        r = reach_report({}, {bfam: bbuy}, {BORROWED_DEST: bfam}, walker)
        ok &= check("with zero built pages, a declared row is UNREACHABLE",
                    r["declared_unreached"], [bfam])
        ok &= check("and a minted link of ours is UNREACHABLE too",
                    r["ours_unreached"], [BORROWED_DEST])

        # --- the other two shapes ---------------------------------------------
        print("\nthe other two ways money goes missing:")
        r = reach_report({DEAD: [ofam]}, {}, ours, walker)
        ok &= check("a button pointing at a dead checkout is refused",
                    sorted(r["broken"]), [DEAD])
        orphan = "https://buy.stripe.com/orphan"
        r = reach_report({obuy: [ofam]}, {ofam: obuy}, {obuy: ofam, orphan: bfam}, walker)
        ok &= check("a link we minted that no page shows is refused",
                    r["ours_unreached"], [orphan])
        ok &= check("while the one a page does show is not", obuy in r["ours_unreached"], False)
        ok &= check("and it is not called borrowed either", r["borrowed"], [])
    finally:
        shutil.rmtree(good, ignore_errors=True)
        shutil.rmtree(gone, ignore_errors=True)

    print("\nok" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
