# Surface map — what exists, what is worth building

Filing cabinet. Not a mall. Different buyers do not shop across rows.

**Finished page** = already live for humans; do not rebuild. **Stub** = structure only (price, buyer, mailto, sample slot); Fable polishes later. **Parked** = do not build.

## A. Finished (leave the live page)

| Product | Buyer | Price | Live URL | Sample | Notes |
|---|---|---|---|---|---|
| Blog listings | Software vendors | $350 / $700 | https://ustechautomations.com/blog-sponsorship | n/a (menu) | **Only counted cash.** 11 payments. Do not copy. |
| Permits library | Mixed | free | https://ustechautomations.com/permits | jumble | Too many kinds of page. Do not add leaves. |
| Grid tracker | Energy / interconnection | free | https://ustechautomations.com/permits/grid | PASS | Funnel to queue feed. |
| Queue change feed | Same as grid | $175/mo | https://ustechautomations.com/permits/offers/permits-queue-sentinel | PASS | Stripe Buy works. File not auto-sent. |
| Phoenix fee report | Phoenix contractors | $249 | `/permits/offers/permits-market-report` | FAIL | Spec, no city fee. |
| Close file | Auditors w/ their sheets | $249 | `/permits/offers/permits-close-file` | FAIL | Needs buyer files. |
| Deadline watch | Infra owners | $175/mo | `/permits/offers/permits-deadline-watch` | FAIL | 0 public rows. |
| Quake attestation | Researchers / reporters | $249 | `/permits/offers/quake-record-attestation` | PASS | Stripe Buy. |
| TTB weekly list | Beverage compliance | $349/mo | `/permits/offers/ttb-permit-ledger` | FAIL | Counts, no named appear/disappear. |
| Crawler policy | Publishers | $175/mo | `/permits/offers/crawler-policy-sentinel` | UNKNOWN | Invoice, not Stripe. |
| Permit rankings | Public / SEO | free | `/permits/rankings` | live board | Current counts, not a change file. |
| Permit pulse | Public | free | `/permits/research/permit-pulse/2026-08` | live | CC-BY monthly. Do not sell the free edition. |
| Datacenter archive | Siting analysts | free research | `/permits/datacenter` | live | Evidence pages. Paid watch is a stub below. |
| B2B pricing archive | Software vendors | free research | `/permits/pricing-archive` | live | Paid window is a stub below. |
| AI terms archive | AI vendors / counsel | free research | `/permits/promise-archive` | live | Paid window is a stub below. |
| SEC 8-K watch | Audit / IR | free research | `/permits/sec-8k` | live | Paid watch is a stub below. |
| AZ contractor roster receipt | AZ GC / compliance | scope page | `/permits/arizona-contractor-roster-receipt` | scope | Paid repeating roster is a stub below. |
| Foundry custom builds | Small businesses | $200–$450 | https://ustechautomations.com/offers | 11 jobs | One-off jobs. Buttons go to `/partner`. Not a feed. |
| Product SaaS cards | “10k teams” story | $32 / $124 / $457 | `/pricing` `/partner` | n/a | **Theirs.** Do not touch. |
| Permits host | Machines | n/a | https://permits.ustechautomations.com | JSON | Not the human shop. |
| Agents host | Machines | listed, off | https://agents.ustechautomations.com | `live: false` | Do not fake on. |

## B. Structure stubs (this repo) — not finished pages

These are the high-probability **repeatable** products. Many buyers, one page. Built as folders + facts. Fable finishes look. Do not sell hard until sample is PASS.

| id | Product | Buyer | Price | Same as live | Sample now | Build |
|---|---|---|---|---|---|---|
| grid | Queue changes | Energy / interconnection software | $175/mo | queue sentinel + `/permits/grid` | PASS (named movers) | Stub exists |
| quakes | Earthquake archive | Researchers / reporters | $249 | quake attestation | PASS (hv75020387 2.33→1.75) | Stub exists |
| ttb | TTB appear/disappear | Beverage compliance | $349/mo | TTB ledger | FAIL | Stub exists |
| crawler | AI-crawler policy | Publishers / SEO | Not for sale (24 Aug 2026) | crawler sentinel | UNKNOWN | Built, 10 pages. Off sale: collection stopped 24 Aug, so a monthly price promised months that will not arrive. The `/permits/offers/crawler-policy-sentinel` row above is a DIFFERENT estate and still prints $175/month. |
| dc-siting | Datacenter siting watch | Grid / siting analysts | $175/mo | `/permits/datacenter` + phantom-load file | PASS (15-campus table on disk) | **New stub** |
| ai-prices | AI list-price window | AI vendors / researchers | $175/mo | none | PASS (Gemma 4 31B 0.36→0.35) | **New stub** |
| permit-metros | Metro issued-permit changes | Contractor software / proptech | $175/mo | rankings + pulse (free current) | FAIL (we have counts, not week diffs) | **New stub** |
| vendor-prices | B2B price-page changes | Software vendors | $175/mo | `/permits/pricing-archive` | FAIL | **New stub** |
| ai-terms | AI policy/terms changes | AI vendors / counsel | $175/mo | `/permits/promise-archive` | FAIL | **New stub** |
| sec-8k | 8-K auditor/officer changes | Audit / IR / software | $175/mo | `/permits/sec-8k` | FAIL | **New stub** |
| az-contractors | AZ ROC roster changes | AZ GCs / insurers | $175/mo | roster receipt | FAIL | **New stub** |

## C. Parked — do not build

| Idea | Why parked |
|---|---|
| `/placements` second rate card | Same as blog-sponsorship |
| `/clocks` main-site path | Same as grid + queue sentinel |
| One-job permit / rebate file | One contractor, one address |
| One-hospital price join | One hospital; no national crawl |
| GitHub checkers as SKUs | Tiny tools, not a path |
| Fiverr / AWS data-exchange | Unknown cash; not this factory |
| Trust scores / public F-grades | No would-pay; reputation risk |
| Distressed-leads / PropStream clone | Second national fight |
| Pinned free-archive clocks (FR, EDGAR, USGS streamgage, …) | Publisher already archives |
| Foundry extra arms | Custom jobs; wait for one paid |
| Agents x402 on | Switch off; do not fake |
| $32 SaaS cards | Product team; not counted demand |

## Probability (why B is the build list)

High: already has buyers-in-waiting **or** a live sample **or** a live free funnel — grid, quakes, dc-siting, ai-prices, blog (already finished).

Medium: live research page + a repeating file we already seal — ttb, crawler, permit-metros, vendor-prices, ai-terms, sec-8k, az-contractors.

Low / skip: anything in table C.
