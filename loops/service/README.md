# The loops service

One small web program. It is the part of the five loops products that has to
live on a server, because the rest of them are plain files on a website and a
plain file cannot count anything or keep a secret.

It runs on Google Cloud Run at:

```
https://usta-loops-260481739341.us-central1.run.app
```

**It never stores a person.** No names, no email addresses, no phone numbers, no
network addresses. What it keeps is website names, pasted business rows, and
counts.

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
