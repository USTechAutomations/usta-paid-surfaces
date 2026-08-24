#!/usr/bin/env python3
"""Prove the unreachable-money check on grid, the hand-written page, both ways.

Why grid and not one of the generated families: every rule in this repo that has
quietly failed has failed on grid. It has no generator, so a change to the
page-building machinery never reaches it, and its pay button points at our own
/permits/offers/.../buy address rather than at Stripe, so anything that greps for
buy.stripe.com cannot see it either. A rule that works on the generated pages and
not on grid reads as coverage while covering nothing. So the fixture here is the
real families/grid/index.html off disk, not a mock of it.

Two runs, one file different:
  arm    the real page, button intact          -> the Stripe link is reached
  strip  the same page with the button removed -> the Stripe link is UNREACHABLE

No network and no Stripe. The redirect walk is a stub, because what is being
proved is the counting, and a rule you can only test when the internet is up is
a rule nobody runs.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prove_checkouts import page_addresses, reach_report  # noqa: E402

GRID_BUY = "https://ustechautomations.com/permits/offers/permits-queue-sentinel/buy"
GRID_STRIPE = "https://buy.stripe.com/cNiaEQ8xgg945Zy7vc0sU0L"
TTB_STRIPE = "https://buy.stripe.com/6oUdR29Bk1eaafOg1I0sU0M"
DEAD = "https://buy.stripe.com/thisoneisgone"

# Grid's link belongs to the permits estate; ttb's is one of ours. Both shapes
# have to be in the fixture or "borrowed" and "ours" are never told apart.
OURS = {TTB_STRIPE: "ttb"}


def walker(url: str):
    """Stand-in for following the redirects. Only these addresses exist."""
    return {
        GRID_BUY: (GRID_STRIPE, "200"),
        GRID_STRIPE: (GRID_STRIPE, "200"),
        TTB_STRIPE: (TTB_STRIPE, "200"),
        DEAD: (DEAD, "404"),
    }.get(url, (None, "no such address"))


def fixture(strip_grid: bool) -> Path:
    """A tiny built site: the real grid page, plus a not-for-sale page."""
    box = Path(tempfile.mkdtemp(prefix="reach-"))
    (box / "grid").mkdir()
    raw = (ROOT / "families" / "grid" / "index.html").read_text(encoding="utf-8")
    if strip_grid:
        # Exactly what taking the button off looks like: the anchor becomes an
        # email link. Nothing else about the page changes.
        raw, n = re.subn(r'<a class="[^"]*\bbtn-buy\b[^"]*"[^>]*>.*?</a>',
                         '<a class="mail" href="mailto:operations@ustechautomations.com">'
                         'Email us for the $99/mo checkout link</a>', raw, flags=re.S)
        # A strip that strips nothing would make the whole "both ways" claim a
        # lie in the quietest possible way: every case would pass because the
        # button was never removed. Refuse rather than report.
        if not n:
            raise SystemExit(
                "STOP: could not take the button off the grid fixture -- the markup on\n"
                "families/grid/index.html has changed shape. Fix this strip, do not\n"
                "weaken the cases that depend on it.")
    (box / "grid" / "index.html").write_text(raw, encoding="utf-8")
    # A not-for-sale family: no price, no button, and it must draw no complaint.
    (box / "recalls").mkdir()
    (box / "recalls" / "index.html").write_text(
        '<h1>Recalls</h1><p>Not for sale yet.</p>'
        '<a href="mailto:operations@ustechautomations.com">Email us</a>', encoding="utf-8")
    return box


def check(name: str, got, want) -> bool:
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        wanted {want!r}\n        got    {got!r}")
    return ok


def main() -> int:
    real = (ROOT / "families" / "grid" / "index.html").read_text(encoding="utf-8")
    if GRID_BUY not in real:
        raise SystemExit(
            "STOP: families/grid/index.html no longer shows " + GRID_BUY + ".\n"
            "This self-test is pinned to the real page, so either grid was rearmed at a\n"
            "different address or its button came off. Fix the pin, do not delete the case.")

    good = fixture(strip_grid=False)
    gone = fixture(strip_grid=True)
    ok = True
    try:
        # --- ARMED: the hand-written page, exactly as it ships ---------------
        print("grid armed -- the real hand-written page:")
        seen = page_addresses(good)
        ok &= check("the harvest sees grid's button on the hand-written page",
                    sorted(seen), [GRID_BUY])
        ok &= check("and it is the grid page it came off", seen[GRID_BUY], ["grid"])
        r = reach_report(seen, {"grid": GRID_BUY}, OURS, walker)
        ok &= check("following it lands on the Stripe link",
                    sorted(r["reached"]), [GRID_STRIPE])
        ok &= check("so nothing grid declares is unreachable", r["declared_unreached"], [])
        ok &= check("the Stripe link is named as borrowed, not ours",
                    r["borrowed"], [GRID_STRIPE])
        ok &= check("no dead buttons", r["broken"], {})
        ok &= check("the not-for-sale page with no button draws no complaint",
                    "recalls" in str(r), False)

        # --- STRIPPED: same page, button removed -----------------------------
        print("\ngrid stripped -- the identical page with the button taken off:")
        seen = page_addresses(gone)
        ok &= check("the harvest now sees no address at all", seen, {})
        r = reach_report(seen, {"grid": GRID_BUY}, OURS, walker)
        ok &= check("the catalog still declares it, so grid is refused as unreachable",
                    r["declared_unreached"], ["grid"])
        ok &= check("and nothing is reached", r["reached"], {})

        # --- the fault this rewrite exists to fix ----------------------------
        # The old version built "reached" by walking the catalog. Feed it the
        # catalog with no pages at all and it still found the link, which is
        # how grid and quakes hid: the check asked the catalog whether the
        # catalog was reachable and the catalog said yes.
        print("\nthe old fault, so it cannot come back:")
        r = reach_report({}, {"grid": GRID_BUY}, {GRID_STRIPE: "grid"}, walker)
        ok &= check("with zero built pages, a declared row is UNREACHABLE",
                    r["declared_unreached"], ["grid"])
        ok &= check("and a minted link of ours is UNREACHABLE too",
                    r["ours_unreached"], [GRID_STRIPE])

        # --- the other two shapes --------------------------------------------
        print("\nthe other two ways money goes missing:")
        r = reach_report({DEAD: ["ttb"]}, {}, OURS, walker)
        ok &= check("a button pointing at a dead checkout is refused",
                    sorted(r["broken"]), [DEAD])
        r = reach_report({TTB_STRIPE: ["ttb"]}, {"ttb": TTB_STRIPE},
                         {TTB_STRIPE: "ttb", "https://buy.stripe.com/orphan": "quakes"}, walker)
        ok &= check("a link we minted that no page shows is refused",
                    r["ours_unreached"], ["https://buy.stripe.com/orphan"])
        ok &= check("while the one a page does show is not",
                    TTB_STRIPE in r["ours_unreached"], False)
        ok &= check("and it is not called borrowed either", r["borrowed"], [])
    finally:
        shutil.rmtree(good, ignore_errors=True)
        shutil.rmtree(gone, ignore_errors=True)

    print("\nok" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
