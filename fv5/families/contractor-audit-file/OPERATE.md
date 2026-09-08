# Operate — contractor audit file

The standing instruction for a $0 maintenance run. Read this before touching
anything in the family.

## Weekly

1. `python3 fv5/families/contractor-audit-file/refresh.py` — one line out.
   Check three numbers in it:
   - `source_ok=<n>/<m>` falling means a site that used to answer has stopped.
   - `cites_ok=<n>/<m>` falling means a quote's words have changed.
   - `pages=<n>` falling means a jurisdiction dropped out of the free estate.
2. `python3 fv5/families/contractor-audit-file/selftest.py` — must print
   `SELFTEST ok`. The verdict gate is inside it. If it fails, stop and fix
   before anything is rebuilt; a page that states a conclusion is the one
   failure this family cannot ship.

## When a cited rule's text changes

`refresh.py` sets that citation row to `drifted` and `data/status.json.drift` to
true. The delivered page then carries a dated banner naming the rule that moved.
Do **not** hand-edit the quote. Re-run refresh, read the official page yourself,
and if the section has been amended or renumbered, update the address in
`data/sources_seed.json` and re-run. If the section is gone, drop the row: a
jurisdiction with no readable test gets no page.

## How to expand the free estate

Only ever by adding a jurisdiction whose own official page answers this host
with the section we cite. The order of work, cheapest first:

1. Re-try the 15 addresses recorded `unreachable` in `SOURCES.md`; a site that
   refused this host once may answer later. Never work around a `403`.
2. For the 11 rows recorded `wrong-page`, find the correct section address on
   the same official site and change it in `data/sources_seed.json`.
3. For the 14 rows recorded `no-passage`, widen the anchors in
   `rules_build.py` — but narrowly. A loose anchor once lifted a sentence about
   leased-employee brokers out of the Kansas code and would have published it as
   a prong of the worker test. Every anchor change must be re-read by eye.

Never add a state by writing the test out yourself.

## The kill rule

0 checkouts **and** 0 non-bot fetches of any sub-page by day 30 from first
publication → stop work on this family. The pages stay up; nobody spends another
hour on them.

## The double rule

2 payments in 30 days → expand inside the family, within the 30%-of-revenue
budget line. Expansion means more jurisdictions by the route above, and nothing
else. Do not add a scoring feature, a likelihood indicator, a traffic light, or
anything else that edges toward telling the buyer what the worker is. That is
the product boundary, not a backlog item.
