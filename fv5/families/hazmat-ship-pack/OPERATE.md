# hazmat-ship-pack — standing operating prompt

Read this before touching the family. It assumes a $0 maintenance budget.

## Every week

1. `python3 fv5/families/hazmat-ship-pack/refresh.py --limit 40`
   Fetches only sections it does not already hold, so a normal week is cheap.
   Read the one line it prints:
   * `rows=` should stay near 2,480. A drop of more than 5% means the table's
     XML changed shape — read `hmt_build.parse_hmt` before trusting the pages.
   * `cites_ok=` below the total means a rule we quote has changed its words.
   * `source_ok=` climbs as the Part 173 cache fills; it never needs to reach
     the total, because the free pages only print section numbers.
2. `python3 fv5/families/hazmat-ship-pack/selftest.py` — exit 0 or stop.
3. `python3 scripts/check_site.py` — exit 0 or stop.

## When a cited rule's text changes

`refresh.py` marks that row `drifted` in `data/citations.json` and sets
`data/status.json.drift = true`. The delivered page then carries a dated banner
naming the section and saying the pack reflects the text as of the stamp.
**Never edit the stored quote to match the new text.** Read the section at the
eCFR, decide whether the sentence the page builds on still holds, and either
change the sentence or change the citation deliberately. A quote that silently
follows the rule is worth nothing.

## The kill rule

If by **day 30 after the pay link goes live** there have been **0 checkouts and
0 non-bot fetches of any sub-page**: stop work on this family. The pages stay up
— they cost nothing and they are true — but no more building, no more expansion,
no more refresh runs beyond the weekly one. Write the date and the counts in
`NOTES.md` and move on.

## The double rule

If **2 payments land within 30 days**, expand, spending no more than 30% of what
this family has taken. In priority order:

1. Raise the index budget from 200 to 400 in `scripts/slice_hazmat_ship_pack.py`
   (the constant `INDEX_BUDGET`) and let the ranking pick the extra 200. Costs
   nothing but build time.
2. Cache the rest of Part 173 so the paid worksheet stops saying "we do not hold
   the text of this section". Run `refresh.py` with no `--limit` a few times.
3. Add the marking rules (§§ 172.300–172.338) as a seventh part of the
   worksheet, same shape: heading and opening paragraph, link to the eCFR.

Do **not** spend the money on air or sea coverage. It is not a budget question;
those rulebooks may not be reproduced at any price.

## What never changes

Road only. Labels are proofs. Exceptions and packaging stay behind the paywall;
the free page keeps the table row and the glossary. No page states a conclusion
about a buyer's shipment. No natural person is ever the subject of a page.
