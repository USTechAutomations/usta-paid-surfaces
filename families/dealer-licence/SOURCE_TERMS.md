# Source terms — Texas motor-vehicle dealer licensee list

Read 2026-09-06. Do not guess. Quotes are from the pages named, fetched that day.

Source named by the idea: `https://texasdmv.my.salesforce-sites.com/dealers`

Related pages also read the same day:

- List page that offers the spreadsheet: `https://texasdmv.my.salesforce-sites.com/dealers/motorvehicledealerliststaging`
- Salesforce host robots: `https://texasdmv.my.salesforce-sites.com/robots.txt`
- TxDMV site robots: `https://www.txdmv.gov/robots.txt` (allows `/dealers`)
- TxDMV disclaimer (the written terms for using the TxDMV site): `https://www.txdmv.gov/site-policies/disclaimer`
- TxDMV site policies (privacy and security): `https://www.txdmv.gov/site-policies`
- TxDMV Driver’s Privacy Protection Act page: `https://www.txdmv.gov/site-policies/drivers-privacy-protection-act`
- TxDMV dealers hub that links “Motor Vehicle Dealers List”: `https://www.txdmv.gov/dealers`

## What the source is

The Salesforce site is TxDMV’s public licensee lookup (LACE). The Independent (GDN) list page says a complete spreadsheet of active Independent (GDN) motor-vehicle dealers is available for download. Fetched 2026-09-06, that spreadsheet was named `Motor Vehicle Dealer-2026-Sep-06-05-30-01.xls` and the page said “Data is current as of 09/06/2026”. The file also carries Franchise rows and Expired rows; those facts are from the file, not from the page title.

## Quotes

### Salesforce robots.txt (fetched 2026-09-06)

```
User-agent: googlebot
Allow: /

User-agent: *    # applies to all robots
Allow: /?*un=*&pw=*
Allow: /?*pw=*&un=*
Allow: /secur/frontdoor.jsp?*sid=*
Allow: /secur/contentDoor?*sid=*
Allow: /secur/myDomainDoor?*sid=*
Allow: /secur/LoginInterstitial.apexp
Allow: /secur/login_portal.jsp?*pw=*
Allow: /sserv/login.jsp?*pw=*
Allow: /login.jsp?*pw=*
Allow: /login/login.jsp?*pw=*
Allow: /secur/login_page.jsp?*pw=*
Disallow: /      # disallow indexing of all pages
```

The file’s own comment on `Disallow: /` is “disallow indexing of all pages”. For any user-agent that is not googlebot, `Disallow: /` is a crawl block of the host, including `/dealers`.

### List page — public spreadsheet, privacy, copyright (fetched 2026-09-06)

“A complete spreadsheet of active Independent(GDN) Motor Vehicle Dealers is available for download if the dealer search does not return the desired results. Data is current as of 09/06/2026.”

Link text on that page: “Download Independent(GDN) Motor Vehicle Dealers List” → `/dealers/servlet/servlet.FileDownload?...`

Privacy Statement on the same page:

“The Texas Department of Motor Vehicles maintains information collected through this form. With few exceptions, Texas Government Code Chapter 559 entitles you to: (a) request to be informed about this information, and (b) have TxDMV correct information about you that is incorrect. Chapter 552 of the Government Code entitles you to receive and review this information. You must submit requests for information in writing.”

Footer on the same page: “© Copyright 2016, Texas Department of Motor Vehicles. All rights reserved.”

### TxDMV disclaimer (fetched 2026-09-06)

“Use of the Texas Department of Motor Vehicles ("TxDMV") Web site ("Site") is governed by the following terms, conditions, and disclaimers ("Terms"). Users of this Site agree to abide by these Terms.”

“TxDMV does not endorse any of the commercial products or services referenced in this Site. Any mention of commercial products or services is for information purposes only.”

No sentence on that page grants or forbids copying, selling, or reselling the licensee list.

### TxDMV privacy and security policy (fetched 2026-09-06)

“This web site is an official Texas Department of Motor Vehicles (TxDMV) computer system operated for authorized use only and provided as a public service.”

“This policy applies to all pages beginning with www.txdmv.gov and www.dmv.state.tx.us.”

“Note: This policy does not apply whenever visitors leave the TxDMV domains and follow a link to another site, including the sites of state agencies and local governments.”

The Salesforce licensee list is on `texasdmv.my.salesforce-sites.com`, not `www.txdmv.gov`.

### Driver’s Privacy Protection Act page (fetched 2026-09-06)

“Federal law prohibits the Texas Department of Motor Vehicles (TxDMV or department) from disclosing your personal information to the general public. This law, the Driver’s Privacy Protection Act (DPPA), makes it illegal to sell or redisclose personal information obtained from TxDMV motor vehicle records and prohibits the use of the information to contact individuals.”

“The Texas Department of Motor Vehicles does not maintain driver’s license, driving history, accident, or violation/citation records, only information tied directly to the titling, registration, and permitting of motor vehicles in Texas.”

Looked for a sentence that names the dealer *licensee* list (business licences, GDN numbers) as a motor-vehicle record under that Act, or that grants or forbids selling a dated copy of that list. Did not find one. The quoted ban is about personal information from motor-vehicle records.

### What was looked for and not found

No terms-of-use, data-licence, or “you may / may not sell this list” sentence on the source URL, the spreadsheet list page, the TxDMV disclaimer, or the TxDMV privacy policy that names the licensee roster and either permits commercial reuse or forbids it. The copyright footer reserves rights in the website; it does not say what a stranger may do with the public spreadsheet the same page offers for download. Contractor terms that forbid commercial use of “TxDMV Data” apply to TxDMV contractors, not to this public lookup. DPPA text is about personal information from motor-vehicle records, not a named grant or ban on the licensee spreadsheet.

## Verdict

UNKNOWN — looked at the source URL, its robots.txt, the list page that offers the spreadsheet, the TxDMV disclaimer, the TxDMV privacy policy, and the TxDMV DPPA page on 2026-09-06. No clause was found that permits selling a weekly diff of the licensee list, and no clause was found that forbids it. Robots.txt on the Salesforce host disallows crawling (`Disallow: /` for `User-agent: *`). The same list page offers the spreadsheet as a public download.

The collector therefore does one GET of robots.txt, one GET of the list page (to read the current download address, which changes), and one GET of that spreadsheet, with a User-Agent that names us. It does not walk the search form, does not page results, and does not send a second GET of the same file in one run.
