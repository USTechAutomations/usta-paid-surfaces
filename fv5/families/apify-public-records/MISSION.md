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
   count of safe-drinking-water violations. This remains the existing free sample on the page; current OSHA and NRC runtime acceptance is recorded separately.
3. **NRC spill notices** — one row per initial, unvalidated report with a listed material in the accepted2026 receipt-year workbook, with source provenance and explicit unknowns.

Current prices and caps are the actor-specific provider schedules. NRC and OSHA start events were removed on12 September2026; their remaining result event is0.005USD. See current acceptance before making a runtime claim.

The line we do not cross: every row is a firm, a facility, a water system or an
incident — never a private person. No operator, caller, worker-name or street-address field is published in actor output. OSHA original government bytes are retained locally for only the three most recent successful source collections; the public source copy drops address and narrative columns. A row that read as a private individual is
withheld, not renamed. The scrapers claim no affiliation with OSHA, the EPA or the
Coast Guard, and offer no legal, tax or professional advice.
