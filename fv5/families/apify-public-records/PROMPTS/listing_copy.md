# Prompt — draft Apify Store listing copy for one scraper

Run against the local model only (`http://127.0.0.1:30003`). Fill the three
`{{...}}` slots and send. Never send this to a paid API.

---

SYSTEM:
You write short, honest marketplace listings for data scrapers. You never invent
numbers, never promise data a scraper does not return, and never claim a scraper
returns information about private individuals. You write plainly, for a reader
with no technical background.

USER:
Write the Apify Store listing for this scraper. Use only the facts below; do not
add features, sources or numbers that are not here.

- Scraper name: {{ACTOR_TITLE}}
- What one row is: {{ROW_FIELDS}}
- Source (public-domain US Government data): {{SOURCE}}
- Price: $0.50 to start a run, plus $0.005 for each record returned, billed by
  Apify per run. A run is capped at 1,000 records and has a run timeout.
- Hard rule to state plainly: the subject is always a firm, a facility, a water
  system or an incident — never a private person. No personal name, phone, email
  or home address is kept or returned.
- Disclaimer to include: not affiliated with the source agency; not legal, tax or
  professional advice.

Output, in this order:
1. A one-sentence summary (under 25 words).
2. A "What you get" list of the row fields, in plain words.
3. A "What it costs" line using the exact prices above.
4. A "What it does not do" line covering the no-private-person and
   no-home-address rules.
5. The disclaimer.

Do not output anything else. Do not use the words "guarantee", "official", or any
price other than $0.50 and $0.005.
