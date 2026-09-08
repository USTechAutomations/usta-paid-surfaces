# Sources — customs-broker-exam-bank

Two sources feed this family. Both are US federal government works and both are in
the public domain under **17 U.S.C. § 105** ("Copyright protection under this title
is not available for any work of the United States Government"). Neither source
imposes commercial terms; the licence quote below is that statute.

---

## 1. The exam papers and official answer keys (CBP)

- **URL:** https://www.cbp.gov/document/publications/past-customs-broker-license-examinations-answer-keys
- **What we take:** the exam PDF and the official answer-key PDF for each of the
  last five sittings — 2024-05, 2024-10, 2025-04, 2025-10, 2026-04. They sit in
  `fv5_data_cble/` in the repo; the exact per-file URLs are listed in
  `fv5_data_cble/SOURCES.md`.
- **Licence / terms:** public domain as a US government work — *"Copyright
  protection under this title is not available for any work of the United States
  Government"* (17 U.S.C. § 105). CBP publishes these papers and keys for the
  public; there is no commercial-use restriction to quote because there is none.
- **Fetch method:** the page and PDFs were fetched **through the session's web
  fetch tool (a browser route), not curl.** `cbp.gov` answers **HTTP 403** to a
  plain curl from this host — that is a fact recorded here, not a wall to be
  evaded. The files were downloaded once and copied into `fv5_data_cble/`.
- **Status code seen:** `403` to curl from this host; `200` through the browser
  route used to download them.
- **Cadence:** **manual, twice a year.** The exam sits each April and October, so
  after each sitting an operator downloads the new exam+key PDFs into
  `fv5_data_cble/` and runs `refresh.py`. `refresh.py` prints
  `source_ok=<held>/<due>` and, when a newer sitting is due by the calendar but
  its PDFs are not in the folder, prints the CBP URL above to fetch them from.
- **Date checked:** 2026-09-07.

## 2. The regulation text the keys cite (eCFR)

- **URL:** `https://www.ecfr.gov/api/versioner/v1/full/<YYYY-MM-DD>/title-19.xml?part=<part>&section=<section>`
- **What we take:** the exact Title 19 CFR section text that CBP's official key
  cites for a question, at the CFR edition the exam paper was written against
  ("Revised as of April 1, YYYY", read off the paper; never a future date).
- **Licence / terms:** public domain as a US government work (17 U.S.C. § 105).
  The eCFR is published by the Office of the Federal Register / GPO for public use.
- **Fetch method:** HTTPS GET with an `Accept-Encoding: gzip` request header (the
  endpoint returns an error without it) and a descriptive User-Agent. The
  gzipped XML is decompressed, reduced to plain text, and cached under
  `~/.hermes/state/fv5/customs-broker-exam-bank/ecfr/` keyed by date + section, so
  a re-run does not re-hit the API.
- **Status code seen:** `200` from this host.
- **Cadence:** on demand during a refresh; served from the on-disk cache after the
  first fetch of a given date+section.
- **Date checked:** 2026-09-07.

---

**No source with no terms ships.** Both sources above carry the same public-domain
basis, quoted above. If a future sitting's PDFs arrived under different terms, they
would be quoted here before any page drew on them.
