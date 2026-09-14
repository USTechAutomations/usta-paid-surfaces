# apify-public-records

This family contains three Apify actor projects and an owned feeds sample. Current runtime evidence is in each actor's ACCEPTANCE.md or the marketplace-closure-20260912 report; historical scaffolding instructions are not provider state.

EPA SDWIS has hosted-source acceptance recorded in that report. NRC now uses the official2026 annual workbook and has provider output/failure acceptance; its default is0.3.3. OSHA default0.3.2 uses a daily validated source copy and has actual provider/source/CSV acceptance. Both public Store pages returned200 with the repaired product copy. Independent demand/payment remains UNKNOWN for all three. Do not describe all three as equally accepted.

Pricing is owned by each actor's actual Apify pricingInfos history, not .actor metadata. NRC and OSHA's start events were removed on12 September2026; the remaining dataset-item event is0.005USD. Preserve every earlier pricing record when updating a schedule. NRC and OSHA make no manual charge calls. Apify platform/account usage is separate. There is no need for a new publication acknowledgment or manual price-zero task.

The existing feeds sample is real EPA data. It is separate from the NRC actor; the absence of NRC rows there does not mean NRC still uses an ASP.NET form. See SOURCES.md for current source details. PUBLISH.sh and legacy refresh.py diagnostics have older assumptions; use immutable provider-build and actual-run evidence for marketplace acceptance.

## Billing and owned sample

Apify owns each actor's billing and current price display. NRC and OSHA have no start event and cost0.005USD per returned item; EPA retains its separate provider schedule. No new Stripe catalog is required. The owned feeds sample and its legacy scaffolding are separate from these tested marketplace builds. Free publication needs no operator acknowledgment; use actual provider/build/Store readback rather than the historical manual instructions in PUBLISH.sh.

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
