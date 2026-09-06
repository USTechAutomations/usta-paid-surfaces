# Source terms — Harmonized Tariff Schedule revision seal

Read 2026-09-06. Do not guess. Quotes are from the pages named.

## Pages opened

- HTS host (the live schedule): https://hts.usitc.gov/ (HTTP 200, 2026-09-06)
- HTS host robots path: https://hts.usitc.gov/robots.txt (HTTP 200, 2026-09-06; body is the same HTML app as the home page, `content-type: text/html`, not a robots file)
- Change Record download named in the idea: https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Change%20Record (HTTP 200, 103,445 bytes, `%PDF-1.6`, 2026-09-06)
- Current-release export: https://hts.usitc.gov/reststop/exportList?from=0100&to=0200&format=CSV&styles=false (HTTP 200, CSV, 2026-09-06)
- Current release name: https://hts.usitc.gov/reststop/currentRelease (HTTP 200, JSON `2026HTSRev18` / "Revision 18 (2026)", 2026-09-06)
- USITC main site home: https://www.usitc.gov/ (HTTP 403 Access Denied, 2026-09-06, with a browser User-Agent and with ours)
- USITC robots: https://www.usitc.gov/robots.txt (HTTP 403, 2026-09-06)
- USITC policies path: https://www.usitc.gov/policies (HTTP 403, 2026-09-06)
- USITC copyright path: https://www.usitc.gov/copyright (HTTP 403, 2026-09-06)
- USITC privacy path: https://www.usitc.gov/privacy (HTTP 403, 2026-09-06)
- data.gov dataset: https://catalog.data.gov/dataset/harmonized-tariff-schedule-of-the-united-states-2025 (HTTP 200, 2026-09-06; page title on that URL is Harmonized Tariff Schedule of the United States (2026))
- Licence URL named on that dataset: http://www.usa.gov/publicdomain/label/1.0/ → https://www.usa.gov/government-copyright (HTTP 200, 2026-09-06)
- 17 U.S.C. § 105: https://www.copyright.gov/title17/92chap1.html (HTTP 200, 2026-09-06)

## robots.txt on hts.usitc.gov (quoted)

The path answered HTTP 200 with HTML, not a robots file. The first bytes are:

> `<!DOCTYPE html><html lang="en"><head>`
> `<title>Harmonized Tariff Schedule</title>`

There is no `User-agent` line and no `Disallow` line in that body. `/reststop/exportList` and `/reststop/file` are therefore not disallowed by a robots file, because no robots file exists on this host.

www.usitc.gov/robots.txt answered HTTP 403, so permission on that host is UNKNOWN. The collector does not call www.usitc.gov.

## Written terms on the publisher's policy page

Not retrieved. https://www.usitc.gov/policies, /copyright, /privacy, and the site home all answered HTTP 403 from this machine on 2026-09-06 (Access Denied). No sentence from those pages can be quoted.

## Written terms on the data.gov listing (quoted)

From https://catalog.data.gov/dataset/harmonized-tariff-schedule-of-the-united-states-2025, Complete Metadata, read 2026-09-06:

> rights This dataset is a U.S. Government Work and is not covered by copyright in the United States of America

> license http://www.usa.gov/publicdomain/label/1.0/

> accessLevel public

> publisher { "name" : "Office of Tariff Affairs and Trade Agreements" , "@type" : "org:Organization" , "subOrganizationOf" : { "name" : "U.S. International Trade Commission"

The same page describes the dataset as:

> This dataset is the current 2026 Harmonized Tariff Schedule plus all revisions for the current year.

No sentence on that page uses “commercial”, “sell”, “resale”, or “paid file” to forbid a dated copy.

## Federal copyright statute (quoted)

From https://www.copyright.gov/title17/92chap1.html, § 105 Subject matter of copyright: United States Government works, read 2026-09-06:

> Copyright protection under this title is not available for any work of the United States Government, but the United States Government is not precluded from receiving and holding copyrights transferred to it by assignment, bequest, or otherwise.

From https://www.usa.gov/government-copyright, read 2026-09-06:

> Government work is something created by a U.S. government officer or employee as part of their official duties.

The Harmonized Tariff Schedule is published by the United States International Trade Commission, a federal agency. The data.gov listing names it a U.S. Government Work.

## Verdict

PERMITTED — “This dataset is a U.S. Government Work and is not covered by copyright in the United States of America” (data.gov dataset Harmonized Tariff Schedule of the United States, https://catalog.data.gov/dataset/harmonized-tariff-schedule-of-the-united-states-2025, read 2026-09-06). The USITC policies page itself could not be quoted (HTTP 403). The weekly file credits the United States International Trade Commission as the publisher.
