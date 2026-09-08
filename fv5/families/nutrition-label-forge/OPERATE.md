# OPERATE — the standing prompt for a $0 maintenance run

Read this, do the checks, change nothing else.

## Weekly

1. `python3 fv5/families/nutrition-label-forge/refresh.py`
   Expect `source_ok=5/5` and `cites_ok=30/30`. Anything less is the story of the
   week; write it down rather than fixing it quietly.
2. `python3 fv5/families/nutrition-label-forge/selftest.py`
   It runs the browser test. `SELFTEST PASS` or stop.
3. `python3 scripts/check_site.py`

## When a cited rule's text changes

`refresh.py` compares all 30 quotes against the newest edition the eCFR
versioner actually serves, not against the pinned edition they were taken from.
A quote that no longer matches word for word becomes `"status": "drifted"` in
`data/citations.json` and flips `data/status.json.drift`, which puts a dated
banner on every page delivered from then on.

That banner is the correct behaviour and it can stand for a while. The repair is:
read the paragraph on the eCFR, decide whether the change touches what the
calculator does, and only then move `ECFR_DATE` in `label_build.py` forward and
re-run `refresh.py`. If the change touches the arithmetic — a rounding rule, a
Daily Value, a reference amount — the calculator is wrong until it is fixed, and
the honest move is to say so on the page before fixing anything.

## The kill rule

0 checkouts **and** 0 non-bot sub-page fetches by day 30 from first publication:
stop work on this family. The pages stay up, `refresh.py` keeps them honest, and
nobody spends another hour on it.

## The double rule

2 payments in 30 days: expand, inside the family's 30%-of-revenue budget line.
In priority order, and only ever the top one:

1. **Dual-column panels.** 21 CFR 101.9(e) requires them at 200-300% of the
   reference amount, the rule page is already there, and the drawing code is not.
   This is the most common reason a buyer would need a second tool.
2. **The remaining reference-amount categories as their own pages.** 11 of the
   21 categories hold fewer than five product lines and are grouped today. If
   traffic lands on a grouped page, split it and thicken it with 101.12(f).
3. **The simplified format** from 101.9(f), for a product where most nutrients
   round to zero.

Do not add: a branded-food database, a recipe store, an ingredient-statement
generator, an allergen generator, or anything that answers a compliance question.
Each one is either somebody else's label, an account system, or a verdict.

## Never

* Never publish a sentence saying a label complies or an exemption applies.
* Never derive added sugars.
* Never write the price into a page; it lives in `catalog.json`.
* Never mint the pay link from here.
