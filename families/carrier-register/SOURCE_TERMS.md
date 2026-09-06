# Source terms — motor-carrier authority register

Read 2026-09-06. Do not guess. Every quote is from a page fetched this day.

## 1. Named source URL

URL: https://li-public.fmcsa.dot.gov/LIVIEW/pkg_REGISTER.prc_reg_list

Fetched 2026-09-06 with User-Agent `USTechAutomations-collector/1.0 (+https://ustechautomations.com/feeds; operations@ustechautomations.com)`. HTTP 200. Title: "FMCSA Register Selection".

The date table on that page had header cells "Date" and "Options" and **zero date rows** [counted 2026-09-06]. Footer printed "September 6, 2026". Help text on the same page (quoted):

> The FMCSA Register lists all of the decisions and notices that were released on a specific date. There are two ways to access the FMCSA Register, either through the Report option or the HTML Detail option.

No "terms of use", "licence", "license", "copyright", "commercial", "resale", or "robots" clause appears in that page body [counted: those words are absent from the 10,082-byte HTML except the footer link labels "Privacy Policy" and "Web Policies and Important Links"].

Footer links (not the register itself):

- https://www.fmcsa.dot.gov/Online-Privacy-Policy.aspx
- https://www.fmcsa.dot.gov/about/WebPoliciesAndImportantLinks.htm

Both returned HTTP 403 from this host on 2026-09-06 ("Access Denied"). The written policies behind those links were **not read**.

Dated HTML for a named day is at `pkg_REGISTER.prc_reg_detail?pd_date=DD-MON-YYYY`. 05-SEP-2026 and 01-SEP-2026 through 06-SEP-2026 each answered 200 and printed "Grant Decision Notices" with table body `NONE` [counted]. 25-FEB-2026 answered 200 with grant rows (parser self-check: 37 FITNESS-ONLY rows in the first table chunk, no phone copied into name/city/state).

## 2. robots.txt at the source host

URL: https://li-public.fmcsa.dot.gov/robots.txt

Fetched 2026-09-06. HTTP 404. Body (quoted in full):

> The requested URL /robots.txt was not found.

https://li-public.fmcsa.dot.gov/LIVIEW/robots.txt also 404.

https://www.fmcsa.dot.gov/robots.txt returned HTTP 403 from this host. Not read.

No robots disallow of `/LIVIEW/` was found, because no robots file exists on the host that serves the register.

## 3. Same-agency open-data file used for this week's grant rows

After MOTUS, the LIVIEW Grant Decision Notices table prints NONE on the days we fetched in September 2026. The weekly file is built from the same agency's public Motus AuthHist table, which is the dated grant/status history.

Dataset: Motus AuthHist - All With History  
Page: https://data.transportation.gov/Trucking-and-Motorcoaches/Motus-AuthHist-All-With-History/yu5v-wbh6  
Metadata fetched 2026-09-06: https://data.transportation.gov/api/views/yu5v-wbh6.json

Quoted from that JSON, Common Core:

> "Public Access Level": "public"

Quoted from Common Core 3 on the same record:

> "Rights": "public"

Quoted from the same record:

> "License": "https://project-open-data.cio.gov/unknown-license/"

Name/city/state (never street, never phone) are joined from Motus Carrier - All With History, https://data.transportation.gov/Trucking-and-Motorcoaches/Motus-Carrier-All-With-History/inys-ebih, same publisher, same Common Core public-access fields on that portal.

robots.txt for that host, fetched 2026-09-06 from https://data.transportation.gov/robots.txt (HTTP 200), quoted:

> User-agent: *
> Crawl-delay: 1

`/resource/` and `/api/views/` are not on the Disallow list of that file [counted 2026-09-06]. Collector waits at least 1 second between requests to that host.

## 4. What was looked for and not found

- A terms-of-use or data-policy paragraph **on the LIVIEW register page**: not present.
- A robots.txt **on li-public.fmcsa.dot.gov**: not present (404).
- The live FMCSA "Web Policies and Important Links" and "Privacy Policy" pages: 403 from this host, unread.
- The live FMCSA Copyright/Attribution Notice: 403 from this host, unread.
- Any sentence on the fetched register HTML that forbids copying, commercial use, or resale: not present.

The Virginia Tech FMCSA Data Repository at fmcsadatarepository.vtti.vt.edu forbids scraping. That is a **different host** and was not used.

## Verdict

**PERMITTED** — quote from Motus AuthHist metadata fetched 2026-09-06 at https://data.transportation.gov/api/views/yu5v-wbh6.json: `"Public Access Level": "public"` and `"Rights": "public"`. The LIVIEW register page named in the idea has no written terms of use (see §1–§2); that absence is not a prohibition. Rows we ship are the Granted actions from the public Motus AuthHist file, with street, phone, fax, and representative name stripped.
