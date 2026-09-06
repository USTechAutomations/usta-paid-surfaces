# Source terms — new federal prime awards this week

Read 2026-09-06. Do not guess. Quotes are from the pages named.

## Pages opened

- Publisher about / licensing (SPA shell HTTP 200; licensing text from the site's own source that that page loads): https://www.usaspending.gov/about (HTTP 200, 2026-09-06). Source file: https://raw.githubusercontent.com/fedspendingtransparency/usaspending-website/master/src/js/components/about/Licensing.jsx (HTTP 200, 2026-09-06)
- Dun & Bradstreet limitation: https://www.usaspending.gov/db_info (HTTP 200 SPA, 2026-09-06). Source file: https://raw.githubusercontent.com/fedspendingtransparency/usaspending-website/master/src/js/components/about/DBInfo.jsx (HTTP 200, 2026-09-06)
- API root: https://api.usaspending.gov/ (HTTP 200, 2026-09-06)
- API endpoints index: https://api.usaspending.gov/docs/endpoints (HTTP 200, 2026-09-06)
- Award search resource: https://api.usaspending.gov/api/v2/search/spending_by_award/ (HTTP 405 on GET, Allow: POST, OPTIONS, 2026-09-06). Contract: https://raw.githubusercontent.com/fedspendingtransparency/usaspending-api/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award.md (HTTP 200, 2026-09-06)
- www.usaspending.gov robots: https://www.usaspending.gov/robots.txt (HTTP 200, 2026-09-06)
- api.usaspending.gov robots: https://api.usaspending.gov/robots.txt (HTTP 404, 2026-09-06)
- API README (DATA Act / public): https://github.com/fedspendingtransparency/usaspending-api/blob/master/README.md (HTTP 200, 2026-09-06)

## robots.txt (quoted)

www.usaspending.gov, read 2026-09-06:

> User-agent: *
> Disallow: /*.php*
> Disallow: /*?*

The collector does not GET www.usaspending.gov. It POSTs `https://api.usaspending.gov/api/v2/search/spending_by_award/`, which is not a www.usaspending.gov path and is not a `*.php*` path.

api.usaspending.gov/robots.txt returned HTTP 404 on 2026-09-06 (body: "The requested resource was not found on this server."). No Disallow rule was retrieved for the API host. The endpoints index states: "Endpoints do not currently require any authorization."

## Written terms on USAspending (quoted)

From the Licensing section of the About page, via the site's own `Licensing.jsx` (the text https://www.usaspending.gov/about loads), read 2026-09-06:

> The U.S. Department of the Treasury, Bureau of the Fiscal Service is committed to providing open data to enable effective tracking of federal spending. The data on this site is available to copy, adapt, redistribute, or otherwise use for non-commercial or for commercial purposes, subject to the Limitation on Permissible Use of Dun & Bradstreet, Inc. Data noted on the homepage.

From https://www.usaspending.gov/db_info via `DBInfo.jsx`, read 2026-09-06:

> "D&B Open Data" is defined as the following data elements: Business Name, Street Address, City Name, State/Province Name, Country Name, County Code, State/Province Code, State/Province Abbreviation, and ZIP/Postal Code.

> D&B hereby grants you, the user, a license for a limited, non-exclusive use of D&B data within the limitations set forth herein. By using this website you agree that you shall not use D&B Open Data without giving written attribution to the source of such data (i.e., D&B) and shall not access, use or disseminate D&B Open Data in bulk, (i.e., in amounts sufficient for use as an original source or as a substitute for the product and/or service being licensed hereunder).

> Except for data elements identified above as D&B Open Data, under no circumstances are you authorized to use any other D&B data for commercial, resale or marketing purposes (e.g., identifying, quantifying, segmenting and/or analyzing customers and prospective customers). Systematic access (electronic harvesting) or extraction of content from the website, including the use of "bots" or "spiders", is prohibited.

What we do with that limitation, counted not guessed:

- We do not request or write DUNS numbers.
- We do not write street, city, ZIP, or any address line. Recipient Location is read only to take `state_code`; the rest of that object is discarded.
- We name D&B on the family page as required if a business name or state abbreviation on a row is D&B Open Data.
- The sold file is federal award fields (award id, dates, agency, NAICS, PSC, obligated amount, set-aside) plus a company recipient name and two state codes. It is not a D&B company directory.
- Collection uses the official public API, not a crawl of www.usaspending.gov.

From the API README, read 2026-09-06:

> This API is utilized by USAspending.gov to obtain all federal spending data which is open source and provided to the public as part of the DATA Act.

No sentence on the API root, the endpoints index, or the spending_by_award contract uses "forbidden", "may not sell", or "non-commercial only" about the award-search JSON.

## Verdict

PERMITTED — “The data on this site is available to copy, adapt, redistribute, or otherwise use for non-commercial or for commercial purposes, subject to the Limitation on Permissible Use of Dun & Bradstreet, Inc. Data noted on the homepage.” (USAspending About / Licensing, https://www.usaspending.gov/about, text from the site's Licensing.jsx, read 2026-09-06). The D&B page is honoured by dropping DUNS and every street/city/ZIP field, naming D&B, and using the authorised API rather than harvesting the website.
