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

## Correction, 2026-08-24 evening — the rule above is incomplete in three ways

Written after actually birthing `yard-season`. Nothing above is changed; these are the
three things the note did not know when it was written.

### 1. The builder cannot bootstrap a new family at all

`build_slices.py` asks the estate honesty gate before it writes anything, and that gate
runs `check_site.py`, which refuses on the very page the new family does not have yet:

```
BUILD STOPPED: scripts/check_site.py is failing: FAIL: missing families/yard-season/index.html
Nothing was written. The estate honesty gate has to pass before any page is rebuilt,
because a build on top of a page that is already lying just makes more of them.
```

So the normal builder cannot create the first copy of a page, and — proved by moving a
finished page out of the way and running the builder — **it cannot repair a deleted one
either**. The escape is to call `render_family.write(spec)` once by hand, then prove the
normal builder reproduces it. Do not take a passing `cmp` as that proof: if the builder
never touches the file, `cmp` compares the hand-written copy to itself and passes for the
wrong reason. Move the page away, run the builder, and see whether it comes back.

### 2. A birth needs a THIRD thing in the same change: a hub group that exists

The rule above says a priced family lands its catalog row and its page together. That is
still true and still not enough. `build_hub.py` keeps its own hand-written list of section
names, and a catalog row naming a group that is not on that list stops the hub build:

```
build_hub: 1 group name(s) in catalog.json have no section on the hub: How we work.
These feeds would not be drawn at all, while the count above the directory would still
include them.
```

The guard is right and says so plainly: *"Do not remove the family from the count to make
the numbers agree."* This is the same shape as a withdrawal having more surfaces than
anyone remembers — count the surfaces before landing, do not discover the third one from
the build refusing.

### 3. The module must not type anything the catalog row already carries

`slice_yard_season.py` was written with its own `"group"`, `"cadence"`, `"cadence_long"`
and `"buyer"` strings, copied from the catalog row. **The group had drifted within the
hour**: the catalog said one thing, the page's top line kept printing the name it was born
with, and the two are read by the same person on the same visit — the card on the directory
and the line at the top of the page. Nothing failed; both surfaces built green while
disagreeing.

Follow `slice_air_permits.py`, which reads `fam["group"]` with no fallback default. A
fallback is worse than nothing here: it publishes a typed guess instead of refusing. Five
modules in the estate still type their group; four read it.

**A value printed in two places is one value with two copies, and the copy nobody
recomputes is the one that goes wrong quietly.**
