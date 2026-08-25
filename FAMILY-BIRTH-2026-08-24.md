# A new family cannot be born in two steps — 2026-08-24

**Append corrections to this note with their own dated heading. Never edit a line above.**

## The finding

A **priced** family must land its catalog row and its page in **one change**. Landing
either half on its own makes `scripts/check_site.py` refuse, and that script runs before
the build in `scripts/refresh_and_deploy.sh` line 120 with `|| die`, so the refusal
freezes the deploy for the **whole estate** — 232 built pages across 29 families — not
just for the new one.

A **free** family (no dollar amount on its page) is the exception: it can be born in two
steps through a `catalog-add-<id>.json` fragment, because one agent owns `catalog.json`.

## Proved, 2026-08-24, five landing orders on throwaway copies of the repo

Every run used a `tar`-piped copy. The live tree was never mutated.

| # | What landed | `check_site.py` exit | What it said |
|---|---|---|---|
| 1 | catalog row only, no page | `1` | `FAIL: missing .../families/yard-season/index.html` |
| 2 | page only, no row, no fragment | `1` | `FAIL: families/yard-season/ is built and published but appears in none of catalog.json, a catalog-add-yard-season.json fragment or extras.json, so nothing checks its price, its sample or its status.` |
| 3 | row + page, prices disagree | `1` | `FAIL: families/yard-season/ shows '$249' in its price rail and catalog.json says 'Not for sale yet'.` |
| 3b | row + page, prices agree | `0` | green |
| 4 | **priced** page + fragment, `catalog.json` untouched | `1` | `FAIL: families/yard-season/ prints a price of its own ('$249') and has no entry in catalog.json, so no check in this file has ever compared that amount with anything.` |
| 5 | **free** page + fragment, `catalog.json` untouched | `0` | green |

Case 3 is not a birth defect. It is the price check working: the copied page still carried
the donor family's price rail. Making the two agree turned it green (3b).

## The part that is easy to get wrong

Case 2's refusal names the fragment as a way out. Case 4 proves that way out is closed the
moment the page prints a dollar amount — a **different** check in the same file demands a
`catalog.json` entry before any amount may appear. So the fragment is a real escape hatch
for a free family and a false one for a priced family, and the message that advertises it
does not say so.

## The rule to follow

- Free family: fragment and page may land separately.
- Priced family: `catalog.json` row and `families/<id>/index.html` land in the **same
  change**, with the same price string in both.
- Never fix a price mismatch by editing a shared price constant. One constant is read by up
  to 37 products, so moving it to fix one page silently moves the other 36. Give the SKU its
  own value.
