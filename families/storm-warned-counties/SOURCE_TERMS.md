# Source terms — National Weather Service alerts (storm-warned counties)

Read 2026-09-06. Do not guess. Quotes are from the pages named.

## Pages opened

- Live alerts feed named in the idea: https://api.weather.gov/alerts/active?status=actual (HTTP 200, application/geo+json, 2026-09-06)
- API host robots: https://api.weather.gov/robots.txt (HTTP 200, 2026-09-06)
- Publisher website robots: https://www.weather.gov/robots.txt (HTTP 404 HTML “Page Not Found”, 2026-09-06)
- Publisher disclaimer / data-use policy: https://www.weather.gov/disclaimer (HTTP 200, 2026-09-06)
- API documentation (User-Agent rule and pricing): https://www.weather.gov/documentation/services-web-api (HTTP 200, 2026-09-06)

## robots.txt

https://api.weather.gov/robots.txt, entire body, fetched 2026-09-06:

```
User-agent: *
Disallow: /
```

That file is 26 bytes. It disallows every path on the API host for every user-agent.

https://www.weather.gov/robots.txt returned HTTP 404 on 2026-09-06 (an HTML “Page Not Found” page, not a robots file). There is no robots file on the publisher website to obey.

The collector does not crawl the API host. It makes one GET of the documented `/alerts/active` endpoint with a named User-Agent, which is the access method the API’s own documentation requires (quoted below).

## Written terms on weather.gov (quoted)

From https://www.weather.gov/disclaimer, heading “Use of NOAA/NWS Data and Products”, read 2026-09-06:

> The information on National Weather Service (NWS) Web pages are in the public domain, unless specifically noted otherwise, and may be used without charge for any lawful purpose so long as you do not: 1) claim it is your own (e.g., by claiming copyright for NWS information -- see below), 2) use it in a manner that implies an endorsement or affiliation with NOAA/NWS, or 3) modify its content and then present it as official government material. You also cannot present information of your own in a way that makes it appear to be official government information.

Same page, copyright notice:

> As required by 17 U.S.C. § 403, third parties producing copyrighted works consisting predominantly of the material appearing in NWS Web pages must provide notice with such work(s) identifying the NWS material incorporated and stating that such material is not subject to copyright protection.

Same page, heading “Linking to Our Site”:

> The information on National Weather Service Web servers and Web sites is in the public domain, unless specifically annotated otherwise, and may be used freely by the public.

No sentence on that page uses “commercial”, “sell”, “resale”, or “paid file” as a ban on reuse of the public-domain records. The three limits are: do not claim copyright, do not imply NOAA/NWS endorsement, and do not present a modified copy as official government material. This product credits the National Weather Service by name, does not use the NWS name or visual identifier as a mark, and does not present the weekly file as an official NWS product.

## API documentation (quoted)

From https://www.weather.gov/documentation/services-web-api, heading “Pricing”, read 2026-09-06:

> All of the information presented via the API is intended to be open data, free to use for any purpose. As a public service of the United States Government, we do not charge any fees for the usage of this service, although there are reasonable rate limits in place to prevent abuse and help ensure that everyone has access.

Same page, heading “Authentication”:

> A User Agent is required to identify your application. This string can be anything, and the more unique to your application the less likely it will be affected by a security event. If you include contact information (website or email), we can contact you if your string is associated to a security event. This will be replaced with an API key in the future.

> User-Agent: (myweatherapp.com, contact@myweatherapp.com)

The collector sends a User-Agent naming ustechautomations.com and operations@ustechautomations.com, one request, with retries and at most one request a second.

## What was looked for and not found

No sentence on the disclaimer, the API documentation, or the 404 robots page on www.weather.gov forbids selling a derived county-level weekly file of warning events. The API host robots.txt disallows crawlers; it is not a terms-of-use clause and it is not a ban on the documented one-request API use.

## Verdict

PERMITTED — “The information on National Weather Service (NWS) Web pages are in the public domain, unless specifically noted otherwise, and may be used without charge for any lawful purpose” (https://www.weather.gov/disclaimer, heading “Use of NOAA/NWS Data and Products”, read 2026-09-06). The API documentation on the same date adds: “All of the information presented via the API is intended to be open data, free to use for any purpose.”
