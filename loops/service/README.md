# The loops service

One small web program. It is the part of the five loops products that has to
live on a server, because the rest of them are plain files on a website and a
plain file cannot count anything or keep a secret.

It runs on Google Cloud Run at:

```
https://usta-loops-260481739341.us-central1.run.app
```

The counter routes keep website names and aggregate counts. SchemaHand key access
stores immutable provider references and checkout/customer hashes in the existing
named Firestore database `loops`. Raw checkout IDs are used only in request memory.
The existing independent private artifact router is preserved for other workflows.
SchemaHand direct key access never consults that artifact store; its buyer gets a
key directly and produces paid handoff files locally in the browser.

## What each address does

### Is it alive

`GET /health` — answers `{"ok": true, ...}`, says whether it is using the
in-memory store or the real database, and lists which of the two hosted apps
are loaded.

### Counting

`GET /t?f=<product>&e=<event>` — hands back a picture one pixel wide, and writes
down four things: which product, which event, the name of the website that
loaded the picture, and today's date. It reads the website name out of the
`Referer` header and throws away the rest of the address. If the product name or
the event name is the wrong shape it writes nothing and answers with no content.

`POST /t` with `{"f": "...", "e": "..."}` does the same thing, for pages that
want to send the count as the visitor leaves.

Any website may load these, the embed scripts and the public Casepack configuration
GET described below. Other browser cross-origin access is limited to the sites
listed in `LOOPS_CORS_ORIGINS`. CORS is not server-side authorization.

### Pro keys

`POST /pro/verify` with `{"key": "lp1...."}` — answers whether that key is one we
signed and is still switched on:

```json
{"ok": true, "family": "casepack", "plan": "monthly"}
```

or `{"ok": false, "reason": "..."}` when it is not.

`POST /admin/revoke` — switches keys off when someone's subscription lapses. The
body is `{"refs": ["...12 characters..."], "ts": 1757000000}` and the header
`X-Loops-Sig` has to hold a signature of that exact body. Requests that are not
signed get `401`. Requests older than ten minutes get `400`. This is how the
machine at home reaches in; nobody else can.

`GET /metrics/<product>?since=YYYY-MM-DD` — hands back the counts for one
product. The `X-Loops-Sig` header has to hold a signature of the text
`<product>|<since>`, so a stranger cannot read our numbers.

### SchemaHand current purchase authority

`POST /pro/claim` with `{"family":"schemahand","session_id":"..."}` fresh-proves
its existing configured live checkout, exact product/price/quantity, subtotal and
automatic-tax total, payment intent and expanded latest charge. It binds the
existing `lp1` key bytes to immutable payment evidence in `loop_payment_authorities`.
Authority version is `schemahand-one-time-v1`; no artifact/spool is required.

`POST /pro/verify` for that key fresh-proves the same intent/expanded charge,
strict captured amount/status, refund/dispute fields and uncached revocation.
Expiry is verified checkout creation +365 days, matching the existing published
one-time term. Missing/malformed/unavailable evidence returns503, while a known
refund/dispute/expiry or revocation returns403. Success and failure are no-store.
The key must be checked again before each paid browser export; a prior positive
browser flag cannot prove access after refund or expiry. No positive server cache
or guessed monthly period is introduced. On Cloud Run, SchemaHand refuses503
before reading the provider unless the actual configured store is Firestore;
a misspelled storage setting cannot fall back to volatile paid authority.

An old unbound SchemaHand key returns UNKNOWN until the buyer revisits the existing
purchase return link or a separately proved backfill binds the checkout. Key bytes
remain stable. Other product families keep their previous implementations and
separate current-authority limitations; these changes do not validate them.

The reader uses the existing restricted credential, fixed Stripe origin and pinned
2024-06-20 API, bounded response parsing and no redirects. Charge evidence comes
from `payment_intents` expansion; the supported SchemaHand path never calls a
direct charge endpoint. Guest checkouts use a session-derived customer hash rather
than inventing a provider customer. Automatic tax is included in exact captured
cash while the base price remains 19900 cents; discount/shipping are refused.

The new private artifact transport/recovery repair remains a separately tested
infrastructure candidate pending a real file-product contract. It is not a
SchemaHand customer requirement and is not part of this release. Existing private
API behavior is preserved; its original upload receipt/capability checks do not
prove current expiry/refund authority and must not be reported as repaired. Tests
for the shared service retain its existing private-route suite, plus `test_schemahand_access`,
`test_payment_authority`, `test_payment_reader_bounds` and the emulator suite.

### The reorder sheet (casepack)

| Address | What it does |
|---|---|
| `POST /cp/config` | Saves a sheet. Answers with the sheet id, a private edit code, and the two lines to paste into a website. |
| `GET /cp/config/<id>` | Reads the sheet back. Never shows the edit code. |
| `POST /cp/config/<id>/edit` | Replaces the sheet. Needs the edit code. |
| `POST /cp/config/<id>/delete` | Deletes the sheet for real. Needs the edit code. |
| `POST /cp/config/<id>/pro` | Turns a paid key into a paid sheet: no badge, and room for 5,000 rows instead of 500. Needs the edit code and a casepack key. |

The public `GET /cp/config/<id>` answers with `Access-Control-Allow-Origin: *`
so a sheet embedded on a customer's different website can read it. This applies
only to the exact read route with a valid-shaped config ID, including its 404
answer when the sheet is missing or deleted. It excludes `edit_id` and `pro_ref`.
Read preflights allow GET and an optional content-type header; they never enable
credentialed requests. Creation, edit, delete, paid upgrade, metrics and admin
routes retain their existing origin restrictions and authorization checks.

This is public embed configuration, not private access-controlled content.
Knowing the public sheet ID does not authorize changing it: edit/delete still
require the separate edit code, and admin operations require their signature.

A sheet holds a website address, a title, a language (`en`, `es` or `both`) and
up to 500 rows. Each row has a code, a name, a unit and how many go in a case,
plus an optional note. No field may be longer than 80 characters.

Every answer that carries pasted data also carries this line:

> Data you paste stays in this link. Delete it any time.

`GET /embed/<name>.js` serves the small scripts that make the sheet appear on
someone else's website. Only files ending in `.js`, only from the `loops/embeds`
folder, cached for an hour.

### The ACA e-file check (acacheck)

`POST /aca/check` — send the XML file as the body, up to 5 MB. The file is read,
checked, and thrown away; it is never saved. Without a key you get the first 25
things that look wrong plus the total number. With an acacheck key you get all
of them. If the checker itself is not installed yet, the answer is `503` with
`"reason": "checker not installed"`.

## Settings

| Name | Default | What it is |
|---|---|---|
| `LOOPS_SIGNING_SECRET` | none | The secret that signs and checks pro keys. Hex, at least 32 characters. |
| `LOOPS_STORE` | `memory` | `memory` or `firestore`. |
| `LOOPS_FS_DATABASE` | `loops` | Which database to use when the store is `firestore`. |
| `LOOPS_CORS_ORIGINS` | `https://ustechautomations.com` | Comma-separated list of sites allowed to call it. |
| `LOOPS_SERVICE_BASE` | the Cloud Run address above | What to write into the paste-in lines. |
| `LOOPS_PUBLIC_BASE` | `https://ustechautomations.com/feeds` | Where the public pages live. |
| `LOOPS_EMBED_DIR` | `loops/embeds` | Where the embed scripts are kept. |

**With no signing secret the service still starts**, but it cannot do anything
with keys: `/pro/verify` always answers `{"ok": false, "reason": "no signing
secret"}`, and `/admin/revoke` and `/metrics/...` answer `503`. Everything else
works as normal. This is on purpose: a service that quietly refused every real
key would be much harder to notice than one that says so.

## Running it here

From the repo root:

```bash
loops/service/.venv/bin/python -m uvicorn loops.service.app:app --host 127.0.0.1 --port 8099 --no-access-log
```

`--no-access-log` matters. Without it the web server writes one line per request
holding the visitor's network address, and this system is not allowed to keep
one. The container in the `Dockerfile` already has it switched on.

With keys switched on (this is a throwaway secret, not the real one):

```bash
LOOPS_SIGNING_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))') \
  loops/service/.venv/bin/python -m uvicorn loops.service.app:app --host 127.0.0.1 --port 8099
```

Then:

```bash
curl -s http://127.0.0.1:8099/health
```

## Running the tests

```bash
bash loops/service/SMOKE.sh
```

That builds the virtual environment if it is missing, runs the pro-key tests and
the service tests, and starts the service for a moment to check that `/health`
really answers. It prints `SMOKE OK` on the last line when everything passed,
and stops with a number other than zero when anything failed.

## Files

| File | What it holds |
|---|---|
| `app.py` | Every address listed above. |
| `store.py` | The shape of the store, and the in-memory one used by tests. Owned by another worker. |
| `store_firestore.py` | The real database. Counting is done with counters, so a busy embed costs one document, not one per visit. |
| `Dockerfile` | How the container is built. Build it from the repo root. |
| `tests/` | The tests. No outside test framework: plain Python. |

Casepack paid access is derived on config reads and owner edits from the stored
upgrade reference and the current revocation store. Explicit revocation returns
`pro: false`; unknown, malformed or unavailable revocation evidence returns503.
Stored owner rows and edit credentials are preserved. Reads retain existing rows;
this is not a destructive expiry policy. A revoked owner's new edits use the free
row limit; oversized replacements are rejected before writing. Owner deletion still
works. A new valid key may explicitly upgrade the sheet; the service never silently
unrevokes a formerly revoked reference. Existing public config CORS and private
mutation restrictions still apply. Offline test: `loops.service.tests.test_casepack_revocation`.
The revocation store/cache remains the source of current status; this change does
not implement automatic restoration when a formerly unpaid subscription later pays.

### Concurrent release integration (2026-09-09)

The actual serving revision6 included `/pro/claim` and its read-only Stripe verifier before the shared checkout did. The private delivery release was merged with those serving bytes, preserving verified license retrieval, current subscription/refund checks, the CasePack CORS and paid-state fixes, and existing Firestore configuration. A full shared-checkout image would have silently removed the newer claim route. The deployed candidate therefore uses a COPY-only overlay on the current immutable image and an image-only update of the existing service; no Cloud Build or new cloud resource.

The merged service passed332 assertions and21 independent payment-claim tests. Source evidence, runtime receipts and production probes are in `/home/gmullins/advisor-plans/business-integration-20260909/release/`. Current runtime state must always be re-fetched rather than inferred from these historical notes.

### September10 source reconciliation (not a deployment claim)

The SchemaHand direct-access candidate preserves the existing claim route and
Casepack fixes while preserving the existing independent private-artifact router.
Source/runtime binding and actual browser export acceptance are recorded under
`advisor-plans/system-reconciliation-20260909/private-delivery-repair/`. A previous
private-artifact fixture was rejected as the representative customer journey
because its HTML duplicated a key the return page already retrieves directly.
No scheduled SchemaHand private artifact delivery or duplicate accounting producer
is activated. Preserve the existing `loops.key_delivery` family hold in fv5.
