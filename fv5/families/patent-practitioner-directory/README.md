# Patent Practitioner Directory — how to run it

## Refresh the data and rebuild the pages
```bash
python3 fv5/families/patent-practitioner-directory/refresh.py
```
Pulls the live USPTO OED roster, writes
`fv5/families/patent-practitioner-directory/data/roster_summary.json`, then
hands off to `scripts/build_slices.py --only patent-practitioner-directory`
to rewrite the family page and every city page. Prints one line:
`REFRESH id=... rows=... kept=... pages=... personal_names_folded=...
source_ok=n/m source=... stamp=...`.

Flags:
- `--limit N` — cap on raw roster rows read (a smoke test; a small N can
  honestly yield 0 qualifying cities, since a city needs 25+ practitioners).
- `--dry-run` — use the bundled fixture, never touch the network.
- `--no-build` — write the data file only, skip the page rebuild (what
  `selftest.py` uses).

If the live USPTO endpoint is unreachable, it falls back to the last raw
pull cached at `~/.hermes/state/fv5/patent-practitioner-directory/raw/`, then
to the bundled fixture, and says which it used.

## Render one paid confirmation page
```bash
python3 fv5/families/patent-practitioner-directory/fulfil.py \
  --fixture fv5/families/patent-practitioner-directory/fixtures/session_paid.json
```
Prints the private confirmation-page HTML to stdout. Checks
`featured_store.py`'s shared featured-slot file first: if the named city's
slot is already held, the buyer gets a "slot taken, refund on request" page
instead of a confirmation, and nothing is claimed.

## Self-test
```bash
python3 fv5/families/patent-practitioner-directory/selftest.py
```

## What the operator has to do once
The catalog row for this family has `checkout.status = "TO-MINT"` and an
empty `checkout.url` — there is no live Stripe Payment Link yet. Until one
exists, every page shows the safe email-CTA fallback ("Email us for the $350
checkout link") instead of a Buy button. To go live: mint a $350 Stripe
Payment Link for this SKU with the three custom fields in
`custom_fields.json` (`firm_name`, `website`, `city_state`), then set
`checkout.url` (and flip `checkout.status`) on this family's row in
`catalog.json`, then re-run `scripts/build_slices.py`.

## Timers
None. This family installs no cron job or systemd timer; refresh runs only
when invoked by hand or by whatever site-wide job already calls
`refresh.py` scripts across families (none has been wired up for this
family in this build).
