# Private paid-file delivery

The producer now keeps buyer HTML outside Git and sends it to the existing loops
service. The public build excludes only legacy 20-hex buyer directories beneath
`families/<family>/p/`; public `p/thanks/` and product catalogs remain eligible.
`noindex` is an indexing preference, never an access control.

A checkout return page removes its query before loading external resources and
uses a no-referrer policy. It retains the checkout capability in family-scoped
sessionStorage, sends it only in the private retrieval POST body, and enables
**Open your file** only after checking the returned HTML digest. Opening keeps the
feeds origin so existing browser-local tool data is available. There are no
analytics scripts in this template. The initial Stripe return URL necessarily
contains the capability: do not collect its query in access-log exports or support
screenshots. Access recovery after loss of both the return URL and browser state
requires the existing human receipt workflow; a receipt email is not claimed to
contain a working private delivery link.

## Durable recovery

`~/.hermes/state/fv5/spool/` contains immutable HTML, its digest, family/session
hashes, purchase time and requested family state updates. Directories are 0700 and
files 0600. Raw checkout IDs are not stored there. State under any Git working tree
and symlink state paths are refused. Malformed or inconsistent records fail
explicitly rather than becoming a successful empty scan.

The driver first reconciles saved artifacts, even if the next Stripe scan returns
no sessions. It builds an unseen paid session once, atomically stores the output
and state update, uploads using a fresh attempt timestamp, then applies family
state and records completion. A remote hash receipt is required before delivery
is marked. Local flags separately track side effects and completion, so a crash
after the remote acknowledgement or a watch update can be retried. Watch,
featured and other state files are atomically replaced and deduplicated by
purchase and kind under the existing process lock. Corrupt state is preserved
and reported as an error. Legacy `written` rows are not delivery proof.

No code can reuse a build whose durable write never happened; such a failed build
is rebuilt. Once its spool write succeeded, retry reuses the exact artifact bytes.
A later successful session cannot move the scan watermark past an earlier error.
Build, scan, storage and delivery failures return nonzero. Explicit build-only
mode can leave output pending; it still returns nonzero on processing errors.
Standalone `publish.py --live` flushes remote uploads under the same process lock;
the regular fulfil driver completes any remaining local family side effects.

## Deployment order and rollback

1. Integrate the narrow loops router/store changes, preserving unrelated app/CORS
   work. Deploy the existing loops service with its existing Firestore database
   and signing secret; no new cloud resource is required. A production memory
   store refuses signed uploads. Probe health, unsigned upload rejection, wrong
   identity rejection and the owned synthetic signed upload/retrieval path.
2. Switch the scheduled producer to this source and its existing external state
   directory. Keep the real signing source local; never print its value. A
   synthetic test is not proof of a real payment or an actual buyer delivery.
3. Regenerate public thanks pages with `python3 fv5/build_thanks.py`, run strict
   brand and existing public truth/quality gates, and build the public image with
   the private exclusion guard. Parent owns this publication. Never upload the
   spool or an old private overlay. Preserve sitemap/crawl promotion gates.
4. Fetch the public return routes and run a synthetic owned browser flow. Keep
   original Stripe return URLs out of logs and evidence artifacts.

Rollback the customer return template before removing the new service routes.
Keep the private spool intact; do not restore public buyer HTML as a fallback.
An immutable upload conflict needs inspection of hashes and production ownership,
not an automatic overwrite. Do not rotate/revoke keys or rewrite Git history
without a concrete impact assessment and the appropriate owner coordination.

## Local verification

With `FV5_SELFTEST_NO_REAL=1 PYTHONDONTWRITEBYTECODE=1` and the existing Python
interpreter that provides FastAPI/httpx:

```
python fv5/selftest.py
python fv5/test_delivery_recovery.py
python fv5/test_private_delivery.py
python -m loops.service.tests.run_all
python scripts/test_private_build_exclusion.py
```

These use scratch files, fake checkouts and a local in-memory service. Production
Firestore permissions, deployment and real purchase-to-delivery remain separate
release evidence; none are inferred from these tests.
