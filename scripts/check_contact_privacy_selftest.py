#!/usr/bin/env python3
"""Prove the contact-address rule withholds emails and leaves everything else.

The address rule in privacy.py has its own suite. This one is separate on
purpose: it tests a different rule, and the address suite is not a file to
extend casually.

A rule that withholds everything would pass "no email reaches the page" and be
useless, so every case here is a pair of claims:

  * a change that moves an email address prints no email address, and
  * a change that moves anything else is quoted exactly as it was before.

The suite ends by replacing the rule with one that always withholds, and with
one that never does, and checking this file goes RED against both. A test that
cannot fail is not evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402

# (before, after, must the cell withhold?, what the case is about)
CASES = [
    ("Contact LobbyistRegistration@Columbus.gov", "Contact RSBrown@Columbus.gov", True,
     "the real Columbus row: a role address handed to a named officer"),
    ("Contact LobbyistRegistration@Columbus.gov", "Contact the Clerk", True,
     "an email removed -- the role address must not be printed on its way out"),
    ("Contact the Clerk", "Contact RSBrown@Columbus.gov", True,
     "an email added"),
    ("write to first.last+notices@sub.domain.co.uk today", "write to nobody", True,
     "a fiddly address: plus tag, subdomain, two-part country domain"),
    ("Zoning Committee", "Passed", False,
     "an ordinary status move, nothing to do with contacts"),
    ("Moved to the 29 Jun 2026 agenda", "Moved to the 6 Jul 2026 agenda", False,
     "a date move"),
    ("1695 DEWEY AVE. (43219)", "1701 DEWEY AVE. (43219)", False,
     "a street address, which is the OTHER rule's business and not this one's"),
    ("see attachment @ item 4", "see attachment @ item 5", False,
     "a bare @ that is not an address"),
    ("email us", "e-mail us", False,
     "the word email is not an email address"),
    (None, None, False,
     "two empty cells"),
]


def run(label: str) -> list[str]:
    bad = []
    for before, after, must_withhold, why in CASES:
        got = privacy.contact_change(before, after)
        withheld = got is not None
        if withheld != must_withhold:
            bad.append(f"{why}: expected {'withheld' if must_withhold else 'quoted'}, "
                       f"got {'withheld' if withheld else 'quoted'} ({label})")
            continue
        if withheld and privacy.EMAIL.search(got or ""):
            bad.append(f"{why}: the withholding sentence printed an address: {got!r}")
    return bad


def main() -> int:
    print("contact-address rule")
    bad = run("live")
    for b in bad:
        print(f"  FAIL  {b}")
    if bad:
        return 1
    for before, after, must, why in CASES:
        got = privacy.contact_change(before, after)
        print(f"  ok    {'withheld: ' + got if got else 'quoted as normal'} -- {why}")

    # Both negative controls. A rule stuck on either answer must turn this red.
    live = privacy.contact_change
    try:
        privacy.contact_change = lambda a, b: "the contact address changed"
        always = run("always withholds")
        privacy.contact_change = lambda a, b: None
        never = run("never withholds")
    finally:
        privacy.contact_change = live
    if not always or not never:
        print("\nSTOP. These cases do not tell a working rule from a broken one: "
              f"always-withhold trips {len(always)}, never-withhold trips {len(never)}. "
              "Both must be non-zero or this suite is not evidence.")
        return 1
    print(f"  negative control: always-withhold trips {len(always)} cases, "
          f"never-withhold trips {len(never)}. Both verdicts reachable.")
    print("\nok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
