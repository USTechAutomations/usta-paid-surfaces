# Static route boundaries — September 9, 2026

The server refuses the exact legacy `/family/p/<20 lowercase hex>/...` shape even if an obsolete paid file accidentally enters a later image. This is a server-level return guard, so a subsequently added prefix location cannot bypass it. The build also excludes that exact path. Public `p/thanks/` pages and the Hazmat product catalog remain accessible. A public `noindex` header is not access control.

The unslashed Frozen Custody product address now redirects to its trailing-slash address while preserving query parameters. Its sample hrefs are relative; without the slash they resolve to `/feeds/sample.csv`, which returned404 during this run. The actual family sample returned200. This repairs the URL base without altering the customer page or its scientific claims.

Six acceptance cases ran against native nginx with a deliberately present synthetic private file: both obsolete buyer paths404, thanks200, public Hazmat catalog200, product redirect308 with preserved query, and CSV200 with text/csv. The publication overlay applies these same rules to the actual current config and preserves every unrelated route. Evidence: `/home/gmullins/advisor-plans/business-integration-20260909/evidence/delivery-nginx-tests.json`. Public release readback is recorded in that session's release receipts.
