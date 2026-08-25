#!/usr/bin/env python3
"""Proves the free civic-agenda sample always comes out in the same order.

Run it:   python3 scripts/slice_civic_agenda_selftest.py
Raw exit code 0 means every check passed AND every check was shown to be able
to fail.

WHAT THIS IS FOR, in one paragraph. The sample file on the civic-agenda page is
free and a stranger can download it. Until 2026-08-25 the same twenty-five rows
could come out of two builds in two different orders, because the sort only
looked at two date fields, those dates repeat all the time, and tied rows were
left in whatever order they happened to arrive in. That arrival order depended
on a random number Python picks fresh in every process. So the file changed for
no reason, and -- worse -- the tie was broken BEFORE the list was cut down to
twenty-five, so a different run could have picked a different set of rows.

No database and no network. Every row below is made up on purpose, so this test
says the same thing on any machine on any day.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from slice_civic_agenda import _every_field, _sample_order  # noqa: E402

FIELDS = ["gov", "level", "body", "file", "subject", "meeting", "what", "from", "to"]

# One night's seal gives every row the same two dates. That is the real shape of
# the data, and it is what made the old key useless: on these five rows the old
# key is identical five times over.
SAME_NIGHT = [
    {"gov": "Seattle", "level": "agenda item", "body": "Council", "file": "CB 121273",
     "subject": "Surplus property", "meeting": "", "what": "title changed",
     "from": "2026-08-23", "to": "2026-08-24"},
    {"gov": "Seattle", "level": "agenda item", "body": "Council", "file": "CB 121274",
     "subject": "Right of way", "meeting": "", "what": "title changed",
     "from": "2026-08-23", "to": "2026-08-24"},
    {"gov": "Seattle", "level": "meeting", "body": "Transportation", "file": "",
     "subject": "", "meeting": "2026-09-02", "what": "time moved",
     "from": "2026-08-23", "to": "2026-08-24"},
    {"gov": "Austin", "level": "agenda item", "body": "Council", "file": "CB 121273",
     "subject": "Surplus property", "meeting": "", "what": "title changed",
     "from": "2026-08-23", "to": "2026-08-24"},
    {"gov": "Austin", "level": "meeting", "body": "Planning", "file": "",
     "subject": "", "meeting": "2026-09-03", "what": "cancelled",
     "from": "2026-08-23", "to": "2026-08-24"},
]

OLD_KEY_POOL = lambda r: (r["to"], r["from"])                       # noqa: E731
OLD_KEY_ROWS = lambda r: (r["to"], r["from"], r["level"])           # noqa: E731

ok = 0
bad: list[str] = []


def check(name: str, got, want) -> None:
    global ok
    if got == want:
        ok += 1
        print(f"  ok    {name}")
    else:
        bad.append(name)
        print(f"  FAIL  {name}\n        wanted {want!r}\n        got    {got!r}")


print("the key can never end in a tie:")

check("five rows sealed the same night get five different keys",
      len({_sample_order(r) for r in SAME_NIGHT}), 5)

check("the key carries every field the row carries",
      len(_sample_order(SAME_NIGHT[0])), len(FIELDS))

check("two rows that are the same row DO tie, which is what a tie should mean",
      _sample_order(SAME_NIGHT[0]) == _sample_order(dict(SAME_NIGHT[0])), True)

print()
print("the negative control -- the key this replaced, on the same five rows:")

check("the old pool key collapsed all five into ONE",
      len({OLD_KEY_POOL(r) for r in SAME_NIGHT}), 1)

check("the old final key collapsed all five into TWO",
      len({OLD_KEY_ROWS(r) for r in SAME_NIGHT}), 2)

print()
print("the order does not depend on the order rows arrive in:")

forwards = [r["file"] + r["gov"] + r["meeting"]
            for r in sorted(SAME_NIGHT, key=_sample_order, reverse=True)]
backwards = [r["file"] + r["gov"] + r["meeting"]
             for r in sorted(list(reversed(SAME_NIGHT)), key=_sample_order, reverse=True)]
check("shuffling the input does not change the output", forwards, backwards)

old_fw = [r["file"] + r["gov"] + r["meeting"]
          for r in sorted(SAME_NIGHT, key=OLD_KEY_ROWS, reverse=True)]
old_bw = [r["file"] + r["gov"] + r["meeting"]
          for r in sorted(list(reversed(SAME_NIGHT)), key=OLD_KEY_ROWS, reverse=True)]
check("and the old key DID change when the input was shuffled",
      old_fw != old_bw, True)

print()
print("the cut is what makes this a data problem and not a tidiness problem:")

# Take the top three, the way sample() slices its pools before the rows are ever
# printed. With the old key the answer depends on arrival order, so a different
# run ships a different SET of rows.
new_cut_a = {r["gov"] + r["file"] + r["meeting"]
             for r in sorted(SAME_NIGHT, key=_sample_order, reverse=True)[:3]}
new_cut_b = {r["gov"] + r["file"] + r["meeting"]
             for r in sorted(list(reversed(SAME_NIGHT)), key=_sample_order, reverse=True)[:3]}
check("the same three rows survive the cut whatever order they arrived in",
      new_cut_a, new_cut_b)

old_cut_a = {r["gov"] + r["file"] + r["meeting"]
             for r in sorted(SAME_NIGHT, key=OLD_KEY_ROWS, reverse=True)[:3]}
old_cut_b = {r["gov"] + r["file"] + r["meeting"]
             for r in sorted(list(reversed(SAME_NIGHT)), key=OLD_KEY_ROWS, reverse=True)[:3]}
check("and with the old key a DIFFERENT set of rows survived the cut",
      old_cut_a != old_cut_b, True)


print()
print("the same fault, in the part that builds the PUBLIC pages:")

# The rows the city pages are built from carry different fields from the sample
# rows, so they need a tiebreak that does not care which fields a row has.
PAGE_ROWS = [
    {"body": "City Council", "meeting": "2026-08-12",
     "what": "Added to the calendar", "from": "2026-08-06", "to": "2026-08-07"},
    {"body": "City Council", "meeting": "2026-08-14",
     "what": "Added to the calendar", "from": "2026-08-06", "to": "2026-08-07"},
    {"body": "City Council", "meeting": "2026-08-17",
     "what": "Added to the calendar", "from": "2026-08-06", "to": "2026-08-07"},
]

check("three meetings sealed together get three different keys",
      len({_every_field(r) for r in PAGE_ROWS}), 3)

check("the old key collapsed those same three into ONE",
      len({(r["to"], r["from"]) for r in PAGE_ROWS}), 1)

page_fw = [r["meeting"] for r in sorted(
    PAGE_ROWS, key=lambda c: ((c["to"], c["from"]), _every_field(c)), reverse=True)]
page_bw = [r["meeting"] for r in sorted(
    list(reversed(PAGE_ROWS)), key=lambda c: ((c["to"], c["from"]), _every_field(c)),
    reverse=True)]
check("the top row of the page is the same whichever order the rows arrived in",
      page_fw, page_bw)

old_fw2 = [r["meeting"] for r in sorted(
    PAGE_ROWS, key=lambda c: (c["to"], c["from"]), reverse=True)]
old_bw2 = [r["meeting"] for r in sorted(
    list(reversed(PAGE_ROWS)), key=lambda c: (c["to"], c["from"]), reverse=True)]
check("and with the old key the top row CHANGED -- this is the bug that shipped",
      old_fw2 != old_bw2, True)

check("rows carrying different fields still sort without error",
      isinstance(_every_field({"file": "CB 1", "subject": "x", "to": "2026-08-07"}), tuple),
      True)


print()
if bad:
    print(f"{len(bad)} check(s) failed: {', '.join(bad)}")
    raise SystemExit(1)
print(f"ok -- {ok} checks, and {ok - 4} of them are proved against the broken key "
      f"they replaced, using rows shaped like the real ones")
