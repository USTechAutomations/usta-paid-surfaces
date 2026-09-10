# Source terms — Texas construction stormwater NOI week

Read 2026-09-06. Do not guess. Quotes are from the pages named.

## Pages opened

- Source named in the idea: https://www.tceq.texas.gov/permitting/stormwater/construction (HTTP 200, 2026-09-06)
- Retained primary EPA data dictionary: https://echo.epa.gov/tools/data-downloads/icis-npdes-download-summary (fetched 2026-09-10; `real-inputs/rights-evidence/epa-icis-npdes-download-summary.html`)
- Retained primary EPA data-licensing page: https://edg.epa.gov/epa_data_license.html (fetched 2026-09-10; `real-inputs/rights-evidence/epa-data-license.html`)
- Robots: https://www.tceq.texas.gov/robots.txt (HTTP 200, 2026-09-06)
- Website policies index: https://www.tceq.texas.gov/help/policies (HTTP 200, 2026-09-06)
- Public Domain and TCEQ Linking Policy: https://www.tceq.texas.gov/help/policies/linking_policy.html (HTTP 200, 2026-09-06)
- Site Disclaimer: https://www.tceq.texas.gov/help/policies/disclaimer_policy.html (HTTP 200, 2026-09-06)
- Water-quality general-permit query (TCEQ short link): https://www.tceq.texas.gov/goto/wq-dpa → https://www2.tceq.texas.gov/wq_dpa/index.cfm (connection cancelled / reset, 2026-09-06)
- Permit Search Portal: https://permit-search.tceq.texas.gov/ (HTTP 200 SPA; `/robots.txt` returns the SPA HTML, not a robots file; its JSON search requires an Authorization header, 2026-09-06)
- EPA ECHO file host robots: https://echo.epa.gov/robots.txt (HTTP 200, 2026-09-06)
- EPA ECHO API host robots: https://echodata.epa.gov/robots.txt (HTTP 200, 2026-09-06)

The construction page itself is a how-to. It names STEERS for filing and the water-quality general-permit query for looking up authorizations. It does not print a table of notices. The retained EPA ICIS data dictionary defines `PERMIT_NAME` as the name of the facility having the NPDES permit and `ISSUE_DATE` as the date the permit was issued.

## robots.txt on www.tceq.texas.gov (quoted)

> By default we allow robots to access all areas of our site already accessible to anonymous users

> User-agent: *
> Disallow: /@@tceq-search
> Disallow: /@@search
> Disallow: /search
> Disallow: /tceq-search

`/permitting/stormwater/construction` is not on that Disallow list. The collector does not hit the disallowed search paths.

www2.tceq.texas.gov (the general-permit query) did not return a robots file from this box: the connection was cancelled, then reset (HTTP/1.1). Permission to read that host is therefore UNKNOWN because the file was not retrieved.

permit-search.tceq.texas.gov has no robots.txt (the path returns the HTML app). Its `/psp-webservices/v1/search/permitsWithPages` endpoint answered 400: `Required header 'Authorization' is not present.` The collector does not call it.

## Written terms on TCEQ (context only)

From https://www.tceq.texas.gov/help/policies/linking_policy.html, heading "Public Domain and Linking to Our Website":

> The TCEQ maintains this website as a public service. Unless otherwise noted, content of our site is considered “public domain.”

> We have no restrictions on linking to our site as long as a fee is not charged to access our material. However, we would appreciate acknowledgment on your site of any items you use and to link to us in the proper context.

> EXCEPTION: The TCEQ logo is the intellectual property of the TCEQ and belongs to the State of Texas. […] Please do not use the TCEQ logo unless you receive express permission from the agency’s publishing manager.

No sentence on that page, on the policies index, or on the site disclaimer uses “commercial”, “sell”, “resale”, or “paid file” about the public-domain content. The fee sentence is about charging people to open TCEQ’s own material. This product does not put a lock on TCEQ’s page and does not use the TCEQ logo.

The same linking-policy quote is already the evidence behind `tceq_nsr_pending` ALLOW_PAID in `paid_file_sources.json` (decided_on 2026-08-25).

## Working read path (because TCEQ’s own query did not answer)

EPA publishes the federal copy of NPDES authorizations, including Texas construction general-permit coverages whose number starts `TXR15` and whose master permit is `TXR150000`. File: https://echo.epa.gov/files/echodownloads/npdes_downloads.zip (HTTP 200, last-modified 2026-09-06, `ICIS_PERMITS.csv` + `ICIS_FACILITIES.csv`).

echo.epa.gov robots.txt (quoted): `User-agent: *` / `Crawl-delay: 10`. Disallow covers `/search/`, Drupal paths, and some report apps. `/files/echodownloads/` is not disallowed.

echodata.epa.gov robots.txt (quoted): `User-agent: *` / `Disallow: *`. The collector does not call that host.

## EPA source-rights evidence

The retained EPA licensing page says: “Unless otherwise specified, all data
produced by the U.S EPA is by default in the public domain.” The retained EPA
ICIS download summary supplies the field definitions used by this candidate.
The candidate uses the EPA download as the source and does not rely on TCEQ's
separate linking policy to establish rights for an EPA file. No dataset-specific
contrary terms were present on the retained EPA download-summary page.

**Verdict: PERMITTED for this candidate, subject to the cited EPA standard
license and any dataset-specific terms that may be added by EPA later.** The
source URL, fetched timestamp, and both primary evidence pages are retained in
`real-inputs/rights-evidence/`.

## Schema correction (2026-09-10)

This candidate corrects the two published column names to the EPA ICIS fields
they actually come from:

- `operator` → `permit_name`. The value is `ICIS_PERMITS.PERMIT_NAME`, EPA's
  facility-name field for an NPDES permit. EPA publishes no operator field and
  none is inferred.
- `filing_date` → `permit_issue_date`. The value is `ICIS_PERMITS.ISSUE_DATE`,
  falling back only to `ORIGINAL_ISSUE_DATE`. It is the date EPA records the
  coverage as issued — not a filing date, and not a construction-start date.

Retained files written under the old `operator`/`filing_date` header are read by
`collect_stormwater_noi.read_rows()` and migrated through the retained EPA ICIS
source rows; no date is ever blanked, and the raw retained files in
`real-inputs/` are left unchanged. The source observation time recorded for a
cached copy is used as-is (`2026-09-06T16:28:21Z` for this seal) and is never
redated to the transformation time; it stays unknown when no fetch time was
recorded for a source artifact.
