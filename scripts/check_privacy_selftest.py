#!/usr/bin/env python3
"""Prove the address rule cuts real units and leaves real street names alone.

check_site.py already carries twelve address cases and refuses a build when one
of them breaks. This file exists because those twelve all happened to be true
of a rule that was also badly wrong: every unit word matched as a bare prefix,
so `FL` matched FLORIAN, `LOT` matched LOTUS and `UNIT` matched UNITY, and
`10942 E FLORIAN AVE` was published as `10942 E`. Twelve green cases and a live
defect at the same time is the whole argument for a case list that pushes on
both sides of the line instead of one.

So every case here is a pair of claims, not one:

  * a real unit designator is still cut, and
  * a street whose name merely STARTS with those letters is not.

A rule can pass either half on its own. `\\b` would pass the second half and
fail `APT3`, because `\\b` needs a word character on one side and a non-word
character on the other and `APT3` has letters on one side and a digit on the
other -- no boundary, no match, and a real flat number goes on the page. A rule
that cuts at every occurrence passes the first half and mangles four thousand
Los Angeles addresses. Only a rule that does both is right, and only a list that
tests both can tell you which one you have.

The suite ends by putting the old broken pattern back and checking that this
file goes RED against it. A test that cannot fail is not evidence, and the
cheapest way to be sure this one can is to run it against the bug it was
written for.

Nothing here writes to any store, and nothing here edits check_site.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402

# The pattern exactly as it stood before the fix. Kept so the last section can
# prove this file goes red against it. Do not "tidy" this into the live one.
BROKEN_UNIT_MARKER = re.compile(
    r"(?:^|\s|,)(APT|APARTMENT|UNIT|FL|FLR|FLOOR|RM|ROOM|TRLR|TRAILER|LOT|"
    r"BSMT|BASEMENT|REAR|FRNT|FRONT|SIDE|UPPR|UPPER|LOWR|LOWER|#)", re.I)

# (address, what the page must show, does it carry a unit, why this case is here)
#
# The four at the top are the reported defect, in the operator's own words. The
# rest are the other side of the same line: if a fix makes these pass by cutting
# less, it has to leave the unit cases below still cutting.
CASES = (
    # --- street names that merely begin with a unit word: nothing may be cut ---
    ("10942 E FLORIAN AVE", "10942 E FLORIAN AVE", False,
     "FLORIAN begins with FL and is a street, not a floor"),
    ("1200 W FLAGSTAFF DR", "1200 W FLAGSTAFF DR", False,
     "FLAGSTAFF begins with FL"),
    ("55 LOTUS LN", "55 LOTUS LN", False,
     "LOTUS begins with LOT"),
    ("9 UNITY CT", "9 UNITY CT", False,
     "UNITY begins with UNIT"),
    ("1048 W FLORENCE AVE", "1048 W FLORENCE AVE", False,
     "a real Los Angeles street the old rule cut to '1048 W'"),
    ("3622 N LOWRY ROAD", "3622 N LOWRY ROAD", False,
     "LOWRY begins with LOWR"),
    ("6905 FRONTERA TRL", "6905 FRONTERA TRL", False,
     "FRONTERA begins with FRONT; this row was withheld from a paid page"),
    ("231 S LOTUS AVENUE", "231 S LOTUS AVENUE", False,
     "a real filing withheld because LOTUS begins with LOT"),
    ("22 FLINTLOCK LANE", "22 FLINTLOCK LANE", False,
     "FLINTLOCK begins with FL"),
    ("781 LINDA FLORA DRIVE", "781 LINDA FLORA DRIVE", False,
     "the unit word need not be the first word to have caused a bad cut"),

    # --- real unit designators: these must still be cut ---
    ("957 Fell St Apt 3", "957 Fell St", True,
     "the ordinary case"),
    ("957 Fell St APT3", "957 Fell St", True,
     "APT3 -- no space and no word boundary, which is why \\b is the wrong fix"),
    ("1801 W ST JOHNS AVE UNIT 5", "1801 W ST JOHNS AVE", True,
     "a genuine UNIT 5"),
    ("1801 W ST JOHNS AVE UNIT A", "1801 W ST JOHNS AVE", True,
     "a genuine unit lettered rather than numbered"),
    ("300 N LA SALLE DR 2ND FL", "300 N LA SALLE DR", True,
     "FL as a real floor marker, which the fix must not lose"),
    ("300 N LA SALLE DR 2ND FLOOR", "300 N LA SALLE DR", True,
     "FLOOR: the pattern tries FL first, so this proves it backtracks"),
    ("300 N LA SALLE DR 2ND FLR", "300 N LA SALLE DR", True,
     "FLR: the same backtrack, one letter shorter"),
    ("957 Fell St #A", "957 Fell St", True,
     "a hash followed by a LETTER is still a flat -- # is exempt on purpose"),
    ("957 Fell St #3", "957 Fell St", True,
     "a hash followed by a digit"),
    ("2617 W FLETCHER ST 1", "2617 W FLETCHER ST", True,
     "both at once: FLETCHER is kept and the trailing 1 is still cut"),

    # --- offices and compass points stay whole, as they always did ---
    ("123 Market St Ste 5", "123 Market St Ste 5", False,
     "a suite is an office, not a home"),
    ("5114 29TH AVE NE", "5114 29TH AVE NE", False,
     "NE is which quarter of Seattle, not a unit"),
    ("4100 S ASHLAND AVE OUTDOORS", "4100 S ASHLAND AVE OUTDOORS", False,
     "a street trader's pitch"),
)

# The whole rule end to end. A person on a street that merely starts with a unit
# word must be published; a person at a real flat must not.
SUPPRESS_CASES = (
    ("MANUEL RODRIGUEZ", "1613 E FLORENCE AVENUE", False,
     "a real filing that was being withheld because FLORENCE begins with FL"),
    ("RAYMOND SIPOS", "22 FLINTLOCK LANE", False,
     "withheld because FLINTLOCK begins with FL"),
    ("JESUS V LOERA", "231 S LOTUS AVENUE", False,
     "withheld because LOTUS begins with LOT"),
    ("Rony Rodriguez", "15 S Broadway St Apt 7", True,
     "a person at a flat is still withheld"),
    ("Rony Rodriguez", "15 S Broadway St APT7", True,
     "and still withheld when the flat number is jammed against the word"),
    ("ACME HOLDINGS LLC", "500 Post St Apt 12", False,
     "a company at a flat is not a person's home"),
)


def run(label: str) -> list[str]:
    """Every case, both halves. Hands back a list of failures, worst first."""
    bad: list[str] = []
    for addr, want_kept, want_unit, why in CASES:
        kept, dropped = privacy.street_only(addr)
        if bool(dropped) != want_unit:
            verb = "no longer sees" if want_unit else "now sees"
            bad.append(f"{verb} a unit in {addr!r} ({why})")
        if kept != want_kept:
            bad.append(f"street_only({addr!r}) shows {kept!r}, must show "
                       f"{want_kept!r} ({why})")
    for name, addr, want, why in SUPPRESS_CASES:
        if privacy.suppress(name, addr) != want:
            verb = "no longer withholds" if want else "now withholds"
            bad.append(f"suppress() {verb} {name!r} at {addr!r} ({why})")
    return bad


def main() -> int:
    print(f"{len(CASES)} address cases, {len(SUPPRESS_CASES)} whole-rule cases\n")
    bad = run("live")
    for line in bad:
        print(f"  FAIL  {line}")
    if bad:
        print(f"\n{len(bad)} failure(s). Fix scripts/privacy.py, not this file.")
        return 1
    print(f"  all {len(CASES) + len(SUPPRESS_CASES)} cases behaved as stated")

    # Negative control. Put the old pattern back and require this file to notice.
    # If it does not, the cases above are decoration and the pass means nothing.
    live = privacy.UNIT_MARKER
    try:
        privacy.UNIT_MARKER = BROKEN_UNIT_MARKER
        caught = run("broken")
    finally:
        privacy.UNIT_MARKER = live
    if not caught:
        print("\nSTOP. These cases pass against the OLD broken pattern too, so "
              "they are not testing anything. The suite is not evidence until "
              "at least one case can tell the two apart.")
        return 1
    print(f"  negative control: the old pattern trips {len(caught)} of them, "
          f"so these cases can go red")

    # And the reverse: the old pattern must still get the real units right, or
    # the control above is passing for the wrong reason.
    missed = [c for c in caught if "APT" in c or "#" in c or "UNIT 5" in c]
    if missed:
        print("\nNote: the old pattern also failed a real-unit case, which is "
              "not what it was accused of. Read these before trusting the fix:")
        for m in missed:
            print(f"    {m}")
    print("\nok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
