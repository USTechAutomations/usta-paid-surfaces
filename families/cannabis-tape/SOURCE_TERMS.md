# Source terms — California cannabis licence search

Read 2026-09-06. Do not guess. Quotes are from the pages named.

## Source URL named in the idea

https://www.cannabis.ca.gov/resources/search-for-licensed-business/

That page says, in its own words:

> The License Search Tool is updated daily and contains information about all of the businesses licensed by the Department of Cannabis Control.

It names the live search as https://search.cannabis.ca.gov/. The page body has no terms-of-use paragraph of its own. Its footer "Conditions of Use" link goes to https://www.ca.gov/use/. Its footer "Privacy Policy" link goes to https://www.cannabis.ca.gov/dcc-privacy-policy/.

## robots.txt

https://www.cannabis.ca.gov/robots.txt (fetched 2026-09-06):

```
User-agent: *
Sitemap: https://www.cannabis.ca.gov/sitemap.xml
```

No `Disallow` line.

https://search.cannabis.ca.gov/robots.txt (fetched 2026-09-06):

```
User-agent: *
Disallow: /static/
```

`/static/` is the search app's CSS and JavaScript. The public licence JSON the search app itself calls is not disallowed.

The JSON host `https://as-dcc-pub-cann-w-p-002.azurewebsites.net` returned HTTP 404 for `/robots.txt` on 2026-09-06, so there is no robots file there to obey.

## Conditions of use linked from the source page

https://www.ca.gov/use/ — "Conditions of use | CA.gov", dated December 7, 2000, fetched 2026-09-06.

Ownership:

> In general, information presented on this website, unless otherwise indicated, is considered in the public domain. It may be distributed or copied as permitted by law. However, the State does make use of copyrighted data (e.g., photographs) which may require additional permissions prior to your use.

No sentence on that page uses sell, resale, commercial republication, or a ban on copying the licence list. The licence records are not marked as photographs or as third-party copyrighted data.

Also on that page, under the monitoring note:

> Unauthorized attempts to modify any information stored on this system, to defeat or circumvent security features, or to utilize this system for other than its intended purposes are prohibited and may result in criminal prosecution.

The source page states the tool's intended purposes include "Search for licensed cannabis businesses". The search app exposes a public JSON list and an Export control. This collector reads that same public JSON, one page at a time, with a named User-Agent. It does not log in, does not modify the system, and does not hit `/static/`.

## DCC privacy policy linked from the source page

https://www.cannabis.ca.gov/dcc-privacy-policy/ — effective 6/14/2023, revised 12/30/2024, fetched 2026-09-06.

> We do not sell your information or distribute it to anyone outside of DCC unless required by law or necessary to process your online request.

That sentence is about information DCC collects from website visitors, not about reuse of the public licence list. No clause on that page forbids copying the licence search records.

## What was looked for and not found

No licence, Creative Commons statement, "open data" banner, or "you may not sell a file of these rows" sentence on the source URL, on https://search.cannabis.ca.gov/, or on the two linked policies, about the licence records themselves.

## Verdict

**PERMITTED** — quote from https://www.ca.gov/use/ (linked as Conditions of Use from the source URL, read 2026-09-06): "In general, information presented on this website, unless otherwise indicated, is considered in the public domain. It may be distributed or copied as permitted by law."
