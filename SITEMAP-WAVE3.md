# Wave 3 — sub-pages under /feeds

Decided 2026-08-22. This file is the contract every builder works from.

## Why these shapes

* The only real inbound form fill the estate has ever produced came from a **grid
  state page**. Geography slices are the proven shape. Everything else is a bet.
* 7,964 clicks on a vague "See what we can build" button produced 1 lead and $0.
  A page that does not name a real row is worth nothing, so no page ships without
  real rows.
* All 12 payments we have ever taken came from business-software companies, and
  every one came through an email thread. So every page carries BOTH the parent
  family's pay button AND the email thread.

## Hard rules (fail closed)

1. **No invented rows, ever.** Every row on every page is read live from the clock
   database at build time. Nothing is hand-typed into HTML.
2. **A slice ships only if it has 5 or more real named rows.** Under 5, the
   generator skips it and prints why. It does not pad.
3. **Every page states its own newest sealed read date and its cadence**, taken
   from the data, not from a constant.
4. **If a page's newest read is older than twice its cadence, the page must say so
   in plain words.** The freshness gate refuses to build otherwise.
5. **A pay link is only allowed if `catalog.json` declares it for that family and
   `verify_checkouts.py` proved it live.** A child page inherits its parent's
   checkout and nothing else.
6. **Do not edit the product website app.** Nothing outside this repo.

## Addressing

    /feeds/<family>              family page (already live)
    /feeds/<family>/<slug>       slice page          families/<family>/<slug>/index.html
    /feeds/<family>/coverage     what is and is not in this feed
    /feeds/<family>/sample.json  permanent sample address
    /feeds/<family>/sample.csv   permanent sample address

Slug is human words, no dimension prefix: `/feeds/grid/minnesota`,
`/feeds/grid/caiso`, `/feeds/ttb/wine-producer`, `/feeds/civic-agenda/chicago`.

Source pages use `../../../styles.css`; the build rewrites it to the absolute
`/feeds/styles.css` anyway, so the source stays viewable on disk.

## The map

### Cross-cutting (3 pages) — lead magnets, no price of their own
    /feeds/coverage                every feed, its newest read, its cadence, one table
    /feeds/what-we-dont-collect    the refusals: 21 pinned sources, 1 refused permission
    /feeds/how-we-seal             what a sealed dated copy is and how to check ours

### grid — interconnection queue changes, $175/mo, pay button live
Held: 206,425 dated project rows, 6 operators, 27 sealed runs, newest 2026-08-22.
    /feeds/grid/coverage
    6 operator pages   caiso isone nyiso spp miso ercot
    20 state pages     CA TX NY MA MI IL IN AR ME LA CT OK MN WI IA MS MO KS NH NE
Note: MISO was last read 2026-08-06 and ERCOT 2026-07-30. Those pages, and any
state page whose rows come only from them, must say the read is paused.

### ttb — alcohol permit changes, $349/mo
Held: 252,309 dated permit rows, 52 states, 4 trades, newest 2026-08-19.
    /feeds/ttb/coverage
    4 trade pages      wholesaler importer wine-producer distilled-spirits-plant
    15 state pages     CA FL NY TX WA OR PA IL VA NC MI CO OH NJ GA

### civic-agenda — NEW FAMILY, $175/mo
Held: 94,609 dated rows, 8 governments, 66 sealed runs, newest 2026-08-22.
    /feeds/civic-agenda              family page
    /feeds/civic-agenda/coverage
    8 government pages chicago seattle king-county mesa austin phoenix columbus la-county

### new-entities — new business filings, $175/mo
Held: 18,323 dated filings, 4 metros, newest 2026-08-22.
    /feeds/new-entities/coverage
    4 metro pages      los-angeles san-francisco chicago nyc

### dc-siting — data-centre siting applications, $175/mo
Held: 132,806 dated rows, newest 2026-08-22.
    /feeds/dc-siting/coverage
    2 state pages      texas arizona

### crawler — who blocks AI crawlers, $175/mo
Held: 27.2M dated robots.txt snapshots, 71 sealed runs, newest 2026-08-21.
    /feeds/crawler/coverage
    slice pages by the bot being blocked, real names only, 5-row floor

### quakes — earthquake record archive, $249 per named event, pay button live
Held: 13,126 dated event rows, 60 sealed runs, newest 2026-08-21.
    /feeds/quakes/coverage
    slice pages by region, real named events only

### markets-resolved — NEW FAMILY, $175/mo
Held: 113,995 dated market rows, 3 venues, 60 sealed runs, newest 2026-08-22.
    /feeds/markets-resolved
    /feeds/markets-resolved/coverage
    3 venue pages      kalshi polymarket manifold

### recalls — NEW FAMILY, $175/mo
Held: 5,783 dated recall rows, newest 2026-08-21.
    /feeds/recalls
    /feeds/recalls/coverage
    slice pages by recall class and by state, 5-row floor

## Staying current

`scripts/build_slices.py` re-reads every clock database and rewrites every page.
A timer runs it daily, then the fact gate, then the freshness gate, and only
deploys if both pass. A page whose source has gone quiet says so instead of
going stale in silence.
