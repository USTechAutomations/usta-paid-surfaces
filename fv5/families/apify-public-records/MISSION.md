# Mission — apify-public-records

Sell three small, honest public-records scrapers on the Apify Store, and use the
/feeds family page as their shop-window.

The Apify Store is a marketplace: it brings the buyer, runs the scraper on its own
servers, bills the buyer per run, takes its cut, and pays the operator the rest.
So this family is different from the rest of the estate — there is no Stripe
checkout here and nothing is delivered from this page. The page's job is to
explain the three scrapers plainly, show a real free sample, and send the buyer to
the Store.

The three scrapers:

1. **OSHA severe-injury reports** — one row per report: employer, city, state,
   industry code, and whether a hospitalisation or amputation was noted.
2. **EPA drinking-water systems** — one row per public water system, with its
   count of safe-drinking-water violations. This is the one source we can read
   live and in full, so it is the free sample on the page.
3. **NRC spill notices** — one row per pollution incident reported to the Coast
   Guard's National Response Center.

Each is pay-per-run: $0.50 to start, plus $0.005 per record, capped hard at 1,000
records with a run timeout so a run can never quietly run away.

The line we do not cross: every row is a firm, a facility, a water system or an
incident — never a private person. No operator name, no caller name, no home
address is ever kept or returned. A row that read as a private individual is
withheld, not renamed. The scrapers claim no affiliation with OSHA, the EPA or the
Coast Guard, and offer no legal, tax or professional advice.
