# nutrition-label-forge

A free Nutrition Facts panel calculator and exemption reader on a public page,
and a $49 file pack for one product behind a Stripe link.

## Layout

| File | What it does |
|---|---|
| `label_build.py` | Parses the eCFR XML and the two FoodData Central zips into `data/*.json`. Never called directly in normal operation. |
| `panel.py` | The whole in-page tool as one bundle: search, calculator, rounding, %DV, the three SVG panel formats, the exemption reader, browser storage. `tool_html(paid=…)` returns the fragment. |
| `refresh.py` | Re-reads both sources, rebuilds the data, rebuilds the free pages, re-checks all 30 quoted rules. Prints one line. |
| `fulfil.py` | The private page a buyer gets. Returns a body fragment for `fv5/lib/ppp.py` to wrap. |
| `selftest.py` | The ship gate, including the verdict gate and the browser test. |
| `browser_test.py` | Chromium, port 8603, both fixtures, the real page. |
| `data/` | `foods.json` (2,500 foods), `racc.json`, `rules.json`, `rounding.json`, `dv.json`, `citations.json`, `status.json`. |
| `fixtures/` | `session_paid.json`, `known_good.json` (a granola), `known_bad.json` (zero servings). |

The public pages are built by `scripts/slice_nutrition_label_forge.py` through
`scripts/build_slices.py`.

## Running it

```bash
python3 refresh.py --dry-run --limit 5   # cache only, writes nothing
python3 refresh.py                       # full rebuild
python3 selftest.py                      # the ship gate
python3 fulfil.py --fixture fixtures/session_paid.json > /tmp/paid.html
```

## The two things worth knowing

**Added sugars has no source.** Not one of the 8,156 Foundation and SR Legacy
rows read carries it. The buyer types it, the page says why, and no code here
guesses it.

**The drift check reads the newest edition, not the pinned one.** The eCFR
versioner is date-addressed and 404s past its last published issue, so asking it
for "today" fails and asking it for the pinned edition compares a quote against
itself. `refresh.py` reads the titles endpoint, takes the date the eCFR says
title 21 is up to date as of, and checks every quote against that.
