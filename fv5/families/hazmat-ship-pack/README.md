# hazmat-ship-pack

One UN number, the federal table row, and the road-shipping worksheet. $49 once.

## Layout

| File | What it does |
|---|---|
| `hmt_build.py` | Fetches and parses the eCFR XML. The 14 columns and their plain-English glosses live here. No network in the parser itself. |
| `refresh.py` | Fetches what is missing, writes `data/*.json`, re-checks every quote, rebuilds every free page. Prints one line. |
| `fulfil.py` | Builds the private worksheet from the two Stripe custom fields. Offline and deterministic. |
| `selftest.py` | Nine checks including the verdict gate. Exit 0 or the family does not ship. |
| `browser_test.py` | Drives the family page's search box in headless Chromium on port 8601. |
| `../../../scripts/slice_hazmat_ship_pack.py` | Builds the family page and every free UN page. Holds the written index-budget ranking. |

## Running it

```
python3 fv5/families/hazmat-ship-pack/refresh.py --dry-run --limit 5   # parse only
python3 fv5/families/hazmat-ship-pack/refresh.py --limit 50            # fetch + rebuild
python3 fv5/families/hazmat-ship-pack/selftest.py                      # prove it
python3 fv5/families/hazmat-ship-pack/fulfil.py --fixture fv5/families/hazmat-ship-pack/fixtures/session_paid.json
```

Run every command from the repository root.

## Data files

`data/hmt.json` (the parsed table), `data/sp.json` (column 7 text),
`data/sections.json` (Part 172 and 173 headings, opening paragraphs and stated
label colours), `data/citations.json` (every quoted rule with its exact words and
fetch date), `data/status.json` (counts, stamp and drift flag). Raw XML is kept
outside the repository under `~/.hermes/state/fv5/hazmat-ship-pack/`.

## The two rules that shape everything

**Road only.** The air and sea rulebooks are copyrighted and forbid extraction.
They are never quoted or summarised here.

**No verdicts.** Nothing tells a buyer what their shipment is, needs or is
excused from. `selftest.py` fails the build on a list of phrases that would.
