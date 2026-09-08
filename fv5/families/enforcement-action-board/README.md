# enforcement-action-board — how to run it

Public boards of the newest formal U.S. EPA enforcement actions, one per state,
plus a national board of the 100 largest federal penalties in the last 90 days.
The pages are free; the paid product is one Featured "Get help" slot per state,
$350 for 12 months. See `MISSION.md` for what it sells and `SOURCES.md` for where
the data comes from.

## Run the puller (pulls EPA, seals the data)

```
# Everything (all 51 states + national). Takes ~2.5 minutes over the network.
python3 fv5/families/enforcement-action-board/refresh.py

# First N states only (a quick live check):
python3 fv5/families/enforcement-action-board/refresh.py --limit 50

# Count only, offline, from the sealed file (this is what selftest runs):
python3 fv5/families/enforcement-action-board/refresh.py --dry-run
```

It writes `data/board.json` (about 1.4 MB, committed) and prints one line:
`REFRESH id=enforcement-action-board rows=<n> pages=<n> source_ok=<n>/<m> stamp=<ISO>`.
It never overwrites a good sealed file with an empty pull, and it counts the
boards through the same slice module the site build uses.

## Build the public pages

The HTML is written by the estate builder, which reads the sealed file through
`scripts/slice_enforcement_action_board.py`:

```
python3 scripts/build_slices.py      # writes families/enforcement-action-board/**
python3 scripts/check_site.py        # gates: prices, privacy, freshness, sources
python3 scripts/build_hub.py         # relinks the hub
```

## Fulfil one paid checkout (make the buyer's private page)

```
python3 fv5/families/enforcement-action-board/fulfil.py \
    --fixture fv5/families/enforcement-action-board/fixtures/session_paid.json
```

`fulfil(session)` returns `{"title", "html", "state_update"}`. On a clean sale it
confirms the firm, the state, the public board link, the 12-month end date and the
exact Get help line, and returns `state_update = {"featured": {...}}`. If the state
is already held by another firm it returns the "slot already taken" refund page and
`state_update = None`. It reads the featured store from
`~/.hermes/state/fv5/enforcement-action-board/featured.json` if present, else the
fixture at `fixtures/featured.json`. The buyer's email never appears on the page.

## Prove it

```
python3 fv5/families/enforcement-action-board/selftest.py
```

Exits 0 only when the dry-run works, fulfil renders a noindex page with no email
leak and refuses to double-sell, every board has a title/`<h1>`/EPA source
link/freshness date, the indexable page count is at or under 200, and no shown row
is a natural person.

## Timers

- **Monthly:** `refresh.py` then `build_slices.py` → `check_site.py` → `build_hub.py`.
  Refreshes the boards from EPA and rebuilds the pages.
- **On payment:** the framework calls `fulfil(session)` and applies its
  `state_update` to the featured store. No timer moves money and no automatic
  refund code exists — money out is the operator's.

## What the operator must do once

1. **Mint the checkout link.** `catalog.json` has `checkout.status = "TO-MINT"`
   and `checkout.url = ""`, so there is no pay button yet — the slot is sold by
   email until a $350 / 12-month SKU exists in the installed permits-engine
   release and the URL is filled in and verified.
2. **OSHA is off.** Boards are EPA-only until the OSHA CSV pull is built; the
   page says so. Nothing to do unless you want OSHA added.
