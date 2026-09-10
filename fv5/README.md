# fv5 — shared plumbing for pay-then-get-a-private-page families

An **fv5 family** sells something delivered as a **private web page built after
payment**. No email is involved. A buyer pays through Stripe, lands on a "thanks"
page that retrieves their file using the checkout confirmation. A job on this
machine builds the file into private storage. See [DELIVERY_RECOVERY.md](DELIVERY_RECOVERY.md)
for the current access controls, retry state, verification and rollout order.

Everything here is **safe by default**: every tool does a dry run and touches
nothing unless you add `--live`.

## What each file does

- **`lib/stripe_read.py`** — read-only window onto Stripe. Lists the *paid*
  checkouts for one pay link and returns plain records that carry a one-way
  fingerprint of the buyer's email, never the email itself. Uses only the
  standard library.
- **`lib/ppp.py`** — wraps a family's file and builds the public return page.
  Its browser code retrieves through a capability-bearing POST, verifies the
  body digest and opens the file on the feeds origin. A hash path is not access
  control, and noindex does not make a public file private.
- **`lib/private_delivery.py`** — validated private spool, signed upload and
  immutable hash receipts using the existing loops service.
- **`lib/indexing.py`** — decides which public pages search engines may list
  (only the substantial ones, and only so many), to protect the domain.
- **`fulfil.py`** — resumes saved deliveries before scanning paid checkouts;
  persists output before side effects and reports unresolved failures nonzero.
- **`publish.py`** — retries signed uploads from the private spool under the
  same process lock. It never commits or publicly overlays buyer files.
- **`mint.py`** — creates a new family's Stripe pay link, proves it charges what
  the page says, then writes it into the catalog and runs the estate verifier.
- **`ledger.py`** — per family, money in vs money spent over 30 days, with a
  budget line (30% of revenue, floor $20).
- **`health.py`** — checks every live family is actually buyable and fresh;
  writes an alert and exits non-zero if anything is wrong.
- **`refresh.py`** — the weekly rebuild-and-publish job for all families.
- **`selftest.py`** — proves the plumbing works, almost entirely offline.
- **`systemd/` + `install_timers.sh`** — the three timers (deliver every 10 min,
  health daily, refresh weekly). Installation is separate from the build; existing free timers need no new approval.

## How a new family plugs in

Create a folder `fv5/families/<id>/` with four files:

1. **`custom_fields.json`** — the extra questions the checkout asks the buyer, in
   Stripe's custom-fields shape (e.g. "Website address to scan"). Use `[]` if it
   asks nothing. `mint.py` puts these on the pay link; `fulfil.py` reads the
   answers back from `session.custom_fields`.
2. **`fulfil.py`** — must define:
   - `LINK_ID_ENV_OR_CATALOG` — usually the family's catalog id (its pay link is
     resolved from the catalog). If it instead names a set environment variable,
     that variable holds the link id directly.
   - `PRODUCT_NAME` — a human name for the file.
   - `ETA_MINUTES` — how long the buyer's thanks page says to wait.
   - `def fulfil(session) -> str | None` — returns the file's HTML, or `None` if
     there is nothing to deliver for that buyer.
3. **`refresh.py`** — rebuilds the family's public sample; run weekly.
4. **`selftest.py`** — the family's own tests.

The family also needs, elsewhere in the repo: a `catalog.json` row (with a price
and `checkout.url` set to `"TO-MINT"`), its public page at
`families/<id>/index.html`, and a thanks page at `families/<id>/p/thanks/index.html`
built from `ppp.thanks_page_html(id, PRODUCT_NAME, ETA_MINUTES)`.

Then mint the link: `fv5/mint.py --only <id> --live`. From then on the delivery
timer serves buyers automatically.

## Dry run vs live

Every tool is a **dry run** by default and prints what it *would* do. Add
`--live` to actually do it:

```bash
python3 fv5/fulfil.py            # show what would be delivered
python3 fv5/fulfil.py --live     # build + private delivery (needs the Stripe-capable python)
python3 fv5/mint.py --only <id>          # show the pay-link request body
python3 fv5/mint.py --only <id> --live   # create it for real
python3 fv5/health.py            # read-only always
python3 fv5/ledger.py            # read-only always
python3 fv5/selftest.py          # offline tests + one tiny real Stripe read
```

The live delivery/health/mint paths read Stripe, so run them with the python that
has the Stripe library:
`"/home/gmullins/Claude CLI/lead-outreach/venv/bin/python"`.

## Where state lives

Under `~/.hermes/state/fv5/`:

- `<family>/sessions.jsonl` — append-compatible outcome history per checkout
  fingerprint. The same paid amount is recorded once across retries.
- `spool/` — immutable buyer artifacts and recovery flags, outside Git; private
  file permissions and symlink checks are enforced.
- `links.json` — cached map of pay-link URL → Stripe link id.
- `fulfil.lock` — the lock that stops two delivery runs overlapping.
- `ledger.json`, `health.json` — the latest ledger and health snapshots.

Alerts (when health fails) go to `~/.hermes/state/alerts/fv5.md`.
