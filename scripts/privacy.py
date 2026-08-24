#!/usr/bin/env python3
"""Keep a home address off a page we charge money for.

Business registration is public record. Reprinting it is not the problem. The
problem is the shape we reprint it in: a city's file hands you a company if you
already know its name, and our page hands a stranger a list. When a row is a
person trading under their own name and the address on it is their flat, that
list is a door number next to a person's name, sold by us. The city did not do
that; we would be the ones doing it.

Two rules, and neither of them deletes a real fact from the store:

  1. Every published address is cut back to the street. `957 Fell St Apt 3`
     becomes `957 Fell St`. Street level is all a seller needs to know where a
     business is. The unit number is the bit that turns a listing into somebody's
     front door, and nothing a buyer does with this feed needs it.

  2. A row that is BOTH a person's own name AND an address with a unit on it is
     not published at all. The page says how many it withheld and why, because a
     count that quietly shrinks is the other way to lie.

A suite, a PMB or a named building is left exactly as it is. Those are offices.
Cutting them would cost a buyer real information and protect nobody.

The person test errs on the side of dropping a row. It has no list of first
names in it, on purpose: a list of common first names would have passed
`Rony Rodriguez` and stopped at `Ehimwenma Osawe`, and the person whose name is
rare is the one who can least afford us getting it wrong. So the test is
"nothing here says company", which also catches a handful of small businesses
named like people. Those get dropped too. That trade is deliberate -- a dropped
company row costs a buyer one line, and a printed home address costs somebody
their address.

Nothing in here writes to any store. It only decides what a page may print.
"""
from __future__ import annotations

import re

# Words that make the tail of an address an office rather than a home. These are
# kept on the page and never count as a home unit.
#
# The second row of them is Chicago's, and it is the reason this list exists at
# all: the city writes `4100 S ASHLAND AVE OUTDOORS` for a stall on the pavement
# and `INSIDE CVS 1234` for a counter in a chemist. Both look like a unit
# designator to a machine and neither is anybody's flat. Reading them as one
# would have withheld a street trader's pitch as if it were a home address --
# protecting nobody and costing a buyer the one detail that says where to go.
COMMERCIAL_TAIL = re.compile(
    r"^(STE|SUITE|PMB|BLDG|BUILDING|OFFICE|DEPT|DEPARTMENT|SPACE|SPC"
    r"|OUTDOORS?|INSIDE|GROUND|LOBBY|GARAGE|PARKING|KIOSK|CART|MOBILE"
    r"|VARIOUS|CITYWIDE|PUBLIC)\b", re.I)

# Words that start a unit designator. Cut here, whatever follows.
UNIT_MARKER = re.compile(
    r"(?:^|\s|,)(APT|APARTMENT|UNIT|FL|FLR|FLOOR|RM|ROOM|TRLR|TRAILER|LOT|"
    r"BSMT|BASEMENT|REAR|FRNT|FRONT|SIDE|UPPR|UPPER|LOWR|LOWER|#)", re.I)

# The last word of a street name, in the spellings these four city files use.
# Anything printed after the last one of these is a unit designator, not a
# street, so it is cut unless it is one of the office words above.
STREET_TYPE = re.compile(
    r"\b(AVE|AVENUE|ST|STREET|BLVD|BOULEVARD|RD|ROAD|DR|DRIVE|PL|PLACE|CT|COURT|"
    r"LN|LANE|WAY|PKWY|PARKWAY|TER|TERRACE|SQ|SQUARE|HWY|HIGHWAY|EXPY|EXPRESSWAY|"
    r"CIR|CIRCLE|PLZ|PLAZA|TRL|TRAIL|ALY|ALLEY|WALK|LOOP|ROW|PATH|BRDG|BRIDGE|"
    r"CRES|CRESCENT|MEWS|GRN|GREEN|PARK|PROMENADE|EMBARCADERO)\b\.?", re.I)

# A word that means the name in front of it is a business, not a person. The
# list is long because a false "this is a person" costs a buyer a row, and it is
# the cheaper of the two mistakes.
COMPANY_WORD = re.compile(
    r"\b(LLC|L\.?L\.?C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|"
    r"LP|LLP|PLLC|PC|PA|TRUST|PARTNERS|PARTNERSHIP|GROUP|HOLDINGS|ENTERPRISES?|"
    r"ASSOCIATES?|SERVICES?|SOLUTIONS?|CONSULTING|CONSULTANTS?|PROPERTIES|"
    r"VENTURES?|FOUNDATION|INTERNATIONAL|INDUSTRIES|SYSTEMS|MANAGEMENT|CENTER|"
    r"CENTRE|STUDIOS?|SALON|CAFE|KITCHEN|MARKET|MEDIA|REALTY|AUTO|MOTORS|"
    r"TRANSPORT|TRUCKING|DELIVERY|LOGISTICS|CONSTRUCTION|PLUMBING|ROOFING|"
    r"CLEANING|LANDSCAPING|DESIGN|EXTERIORS?|INTERIORS?|BAKERY|CATERING|"
    r"PHOTOGRAPHY|PHOTOS|FITNESS|WELLNESS|THERAPY|CARE|TECH|MEDTECH|DIGITAL|"
    r"CLUB|SHOP|STORE|BAR|GRILL|PIZZA|NAILS|BEAUTY|BARBER|SPA|GYM|LAW|DENTAL|"
    r"MEDICAL|CLINIC|AGENCY|STAFFING|SECURITY|ELECTRIC|HVAC|PAINTING|REMODELING|"
    r"CONTRACTING|BUILDERS?|DEVELOPMENT|CAPITAL|INVESTMENTS?|FUND|BANK|INSURANCE|"
    r"TRAVEL|TOURS?|RENTALS?|LEASING|EQUIPMENT|SUPPLY|WHOLESALE|RETAIL|FOODS?|"
    r"FARMS?|RANCH|ART|GALLERY|MURALS|EVENTS?|PRODUCTIONS?|ENTERTAINMENT|MUSIC|"
    r"FILMS?|INSIGHTS|PRESENTS|MOVEMENT|RESERVE|LABS?|WORKS|WORKSHOP|COLLECTIVE|"
    r"PROJECT|EXPRESS|GLOBAL|PRIME|ELITE|PLUS|PRO|USA|SF|NYC|LLC\.)\b", re.I)

# A joining word nobody has in the middle of their name. "House Of Sonoma" is
# not a person; "Mary Jane Smith" is.
CONNECTOR = {"OF", "THE", "AND", "FOR", "ON", "AT", "BY", "TO", "IN", "WITH",
             "MY", "YOUR", "OUR", "US", "WE", "ALL", "A", "AN", "DE", "&"}

_NAME_TOKEN = re.compile(r"^[A-Za-z][A-Za-z'’\-\.]*$")

# Seattle writes `5114 29TH AVE NE`. The NE is which quarter of the city the
# street is in -- it is part of the street's name and there is only one 29th Ave
# NE. Read as a unit designator it would have cut the address down to
# `5114 29TH`, which is not an address at all, and it would have counted eight
# ordinary Seattle houses as flats. So a tail made only of these is kept.
DIRECTIONAL = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
               "NORTH", "SOUTH", "EAST", "WEST",
               "NORTHEAST", "NORTHWEST", "SOUTHEAST", "SOUTHWEST"}


def street_only(address: str | None) -> tuple[str | None, str]:
    """Cut an address back to the street.

    Hands back the address to print and the piece that was cut off, so a caller
    can count what it dropped instead of guessing. An empty second value means
    nothing was cut and the row is printed exactly as the city wrote it.
    """
    if address is None:
        return None, ""
    raw = str(address).strip()
    if not raw:
        return address, ""

    cuts = []

    # A unit word says outright that what follows it is a unit.
    m = UNIT_MARKER.search(raw)
    if m and not COMMERCIAL_TAIL.match(raw[m.start(1):]):
        cuts.append(m.start(1))

    # Anything printed after the last street word is a unit as well, whether or
    # not it is labelled. Chicago labels none of them: `2036 W ROSCOE ST 1`.
    last = None
    for sm in STREET_TYPE.finditer(raw):
        last = sm
    if last is not None and last.end() < len(raw):
        tail = raw[last.end():].lstrip(" ,.-")
        if tail and not COMMERCIAL_TAIL.match(tail):
            cuts.append(last.end())

    # Whichever comes first. `300 N LA SALLE DR LL100 & 1ST FL` carries an
    # unlabelled unit before the labelled one, and cutting at the label alone
    # would leave `LL100 & 1ST` sitting on the page.
    if not cuts:
        return raw, ""
    cut_at = min(cuts)

    # Pull any compass direction at the front of the tail back onto the street,
    # where it belongs. If that is all the tail was, nothing is a unit here.
    tail_tokens = raw[cut_at:].strip(" ,.-").split()
    taken = 0
    while taken < len(tail_tokens) and tail_tokens[taken].upper().strip(".,") in DIRECTIONAL:
        taken += 1
    if taken:
        if taken == len(tail_tokens):
            return raw, ""
        for tok in tail_tokens[:taken]:
            cut_at = raw.index(tok, cut_at) + len(tok)

    kept = raw[:cut_at].rstrip(" ,.-#")
    dropped = raw[cut_at:].strip(" ,.-")
    if not kept:                      # the whole thing was a unit; keep it whole
        return raw, ""
    return kept, dropped


def has_unit(address: str | None) -> bool:
    """True when the address carries a unit that is not an office suite."""
    return bool(street_only(address)[1])


def looks_personal(name: str | None) -> bool:
    """True when the entity name reads as a person trading under their own name.

    Deliberately generous. See the note at the top of this file: there is no
    first-name list, so a rare name is treated the same as a common one.
    """
    if not name:
        return False
    s = str(name).strip()
    if not s or re.search(r"\d", s):
        return False
    if re.search(r"[&/@,+]", s):
        return False
    if COMPANY_WORD.search(s):
        return False
    tokens = [t for t in re.split(r"\s+", s) if t]
    if not 2 <= len(tokens) <= 3:
        return False
    if any(t.upper().strip(".") in CONNECTOR for t in tokens):
        return False
    return all(_NAME_TOKEN.match(t) for t in tokens)


def suppress(name: str | None, address: str | None) -> bool:
    """A person's own name next to a home address. This row is not published."""
    return looks_personal(name) and has_unit(address)


def street_note(example: str = "957 Fell St") -> str:
    """What the page says about cutting every address back to the street.

    This one is printed whether or not a row was withheld. The page edits every
    address it prints, so a page that withheld nobody has still changed what the
    city published, and a buyer is owed that sentence either way. Splitting it
    out of withheld_note() is the point: the old shared sentence only appeared
    when the withheld count was above zero, so most pages truncated addresses
    and said nothing about it.
    """
    return (f"Every address on this page is cut back to the street: we print {example}, never "
            f"the flat or unit number the city prints after it. A suite or a PMB stays, because "
            f"an office is not a home. Nothing has been removed from the city's file or from "
            f"our copy of it -- this is a rule about what we republish, not about what we hold.")


def withheld_note(n: int, out_of: str) -> str:
    """What the page says about the rows it did not print.

    `out_of` names the set the count was taken over, and it is required, not
    optional. That is the whole repair. The count is honest but it is not taken
    over the rows a reader can see: a generator screens a whole arrival day, or
    every permit new in a copy, and then prints a capped table out of what
    survives. Printing "2 rows withheld" under a caption reading "12 shown"
    invites the reader to do 12 minus 2, which is wrong -- on Chicago both
    withheld rows sorted below the cut and the visible table did not change by
    a single row. Naming the denominator is what makes the sentence true.

    It says the count, the set it was counted over, and the rule, and stops
    there. An earlier draft did the arithmetic -- "so the table shows 12 rows
    and not 13" -- and that was false wherever the table is capped: withholding
    a row there does not shorten the table, it lets the next row up take the
    place. A claim about what the table would otherwise have looked like is not
    made, because it cannot be made truthfully from this side of the cap.

    Never rounded, never softened, and never printed at all when it is zero: a
    page boasting that it protected nobody is noise.
    """
    if n <= 0:
        return ""
    rows = "row" if n == 1 else "rows"
    those = "That one is" if n == 1 else f"Those {n} are"
    return (f"{n} {rows} withheld: residential address. {those} counted across {out_of}, not "
            f"across the rows printed above -- the printed table is the shorter list, and you "
            f"cannot subtract one number from the other. Where the name on a record is a "
            f"person's own and the address beside it carries a flat or unit number, we do not "
            f"publish that row at all.")
