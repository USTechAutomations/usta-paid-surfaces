# apify-public-records

Three public-records scrapers sold on the **Apify Store**, with the /feeds family
page as their shop-window. See `MISSION.md` for the why, `SOURCES.md` for the
sources and their terms, and each `actors/<name>/README.md` for that scraper's
input, output and cost.

## How this family is different from the rest of the estate

Every other family sells through a Stripe checkout on this site and delivers a
file. This one does **not**. The Apify Store brings the buyer, runs the scraper on
its own servers, **bills the buyer per run**, takes its cut, and pays the operator
the rest. So:

- There is **no Buy button and no Stripe checkout** on the family page. Until the
  three listings are live on the Store, the page is on its honest "email us for
  the Store links" path.
- **Identity and payout are the operator's.** The actors are pushed to the
  operator's own Apify account and Apify pays that account. This build was **not
  logged in to Apify**, so nothing was pushed; the exact publish steps are staged
  in `PUBLISH.sh`.
- **Price:** each scraper is pay-per-event — **$0.50** to start a run plus
  **$0.005** per record — declared in each actor's `.actor/actor.json`
  (`pricingInfos`). A run is capped hard at **1,000 records** with a run timeout.

## The free sample is real

The one source we can read live and in full is **EPA Envirofacts SDWIS**, so the
free sample on the page is real Arizona community water systems with their
violation counts, sealed by `refresh.py`. OSHA (HTTP 403 to us) and NRC (an
ASP.NET download form) are described honestly and are **not** in the committed
sample; local `apify run` for those two uses clearly-labelled synthetic fixtures.

## Two honest deviations from the family spec (S2)

1. **The catalog price carries no `$` sign** (`"Pay-per-run on the Apify Store"`).
   A dollar amount in the catalog price, tab title or a button would make the
   honesty gate treat this as a Stripe-priced family and demand a price-list entry
   and a pay link this externally-billed family does not have. The exact
   `$0.50 / $0.005` prices are stated in the page body and in every actor README,
   where the gate allows them.
2. **`checkout.url` is empty** until a listing is actually live on the Store.
   An empty url keeps the page on the email path; a real
   `https://apify.com/<username>/<actor>` URL goes in only after the operator has
   opened it in a browser (see `PUBLISH.sh`).

## The 10 guardrails, as applied here

1. **Index budget** — 1 indexable page (no sub-pages); `selftest.py` enforces ≤200.
2. **No natural persons** — every subject is a firm, facility, water system or
   incident. Water systems carry an EPA-issued PWSID (an org id); `selftest.py`
   counts persons as name-looks-personal AND no PWSID → 0.
3. **Disclaimer on the page** — "Not affiliated with OSHA, the EPA or the US Coast
   Guard… Not legal, tax or professional advice," with the EPA source and the
   sealed date.
4. **Source-or-it-doesn't-ship** — the sample links its EPA source URL; every
   returned record also carries a `source_url`.
5. **Terms + accuracy text** — the checkout terms (delivery, that records can lag
   the source) render on the page; there is no Buy button to sit beside.
6. **Refunds** — "refundable on request within 14 days through Apify" text, and
   **no** automatic refund code (`fulfil.py` returns `state_update: None`).
7. **Delivery** — the Apify run hands the buyer the table the moment it finishes;
   `fulfil.py` renders a noindex page saying so.
8. **Per-source terms** — a licence quote for each source in `SOURCES.md`.
9. **Freshness stamp + stale banner** — the page shows the sealed date and, past
   60 days (2× the ~monthly cadence), a "this sample is old" banner
   (`stale_banner()` in the slice module).
10. **Token cap** — no model step runs in the build; the optional local-model copy
    prompts log to `~/.hermes/state/fv5/apify-public-records/tokens.jsonl` and stop
    past 2M tokens/run via `tokenlog.py`.

## Files

- `refresh.py` — probe the three sources, re-seal the EPA sample, re-render the page.
- `fulfil.py` — the "billed by the Store" page (external billing; no delivery here).
- `selftest.py` — the honesty gate for this family (exit 0 = safe to ship).
- `custom_fields.json` — the two questions asked if a Store buyer is routed here.
- `actors/<name>/` — the three Apify actors (code, input schema, pricing, Docker).
- `PUBLISH.sh` — the exact, un-run steps to push and publish under the operator's
  account.
- `PROMPTS/` — local-model prompts to draft and check Store listing copy.
