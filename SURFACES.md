# Internal map — every paid surface we actually have

Canonical table: `MAP.md`. This file is the short filing cabinet. It is **not** a store. A grid buyer will not shop TTB. A blog vendor will not shop quakes. Do not build a mall.

Public rule: one product (or one tight buyer family) per page. This map is how we stop duplicating `/clocks`, one-job packets, and extra cards under `/permits/offers`.

## Counted cash (the blog lane)

| Surface | Who it is for | Public URL | Status |
|---|---|---|---|
| Blog listings | Software vendors, named gap on a named post | https://ustechautomations.com/blog-sponsorship | Live. 11 payments. Do not copy to a second rate card. |

## Permits engine (already on the main site)

| Surface | Who it is for | Public URL | Status |
|---|---|---|---|
| Permits index | Mixed — too many kinds of page in one house | https://ustechautomations.com/permits | Live. Research library. Do not add more leaves. |
| Grid tracker (free) | Energy / interconnection | https://ustechautomations.com/permits/grid | Live. Good sample. |
| Queue change feed | Same buyers as grid | https://ustechautomations.com/permits/offers/permits-queue-sentinel | Live. Stripe Buy. File not auto-sent. |
| Phoenix fee report | Phoenix contractors | `/permits/offers/permits-market-report` | Live Buy. Sample FAIL. |
| Close file | Auditors with their own sheets | `/permits/offers/permits-close-file` | Live Buy. Sample FAIL. |
| Deadline watch | Infra owners | `/permits/offers/permits-deadline-watch` | Live Buy. Sample FAIL. |
| Quake attestation | Researchers / reporters | `/permits/offers/quake-record-attestation` | Live Buy. Sample PASS. |
| TTB weekly list | Beverage compliance | `/permits/offers/ttb-permit-ledger` | Invoice only. Sample FAIL. |
| Crawler policy | Publishers | `/permits/offers/crawler-policy-sentinel` | Invoice only. Sample UNKNOWN. |
| Permits subdomain | Machines / canonicals | https://permits.ustechautomations.com | Live, not the human shop. |
| Agents | Machines | https://agents.ustechautomations.com | Pay switch off. |

## Change-feed hub (this repo)

Intended public host: `feeds.ustechautomations.com` (DNS not applied). Until then: github.io.

Use this repo to **organize** the repeatable feeds (including the permits-owned ones above) so Fable can polish one product at a time. The hub page is a directory, not a bundle you sell together.

| Folder | Same product as | Public until DNS |
|---|---|---|
| `families/grid/` | Queue sentinel + `/permits/grid` | `.../families/grid/` |
| `families/quakes/` | Quake attestation | `.../families/quakes/` |
| `families/ttb/` | TTB ledger | `.../families/ttb/` |
| `families/crawler/` | Crawler sentinel | `.../families/crawler/` |

Do not invent a fifth shop. Point the stub at the live permits URL until the stub is better, then the stub becomes the public product.

## Other

| Surface | Who | URL | Status |
|---|---|---|---|
| Foundry custom builds | Small businesses, one-off jobs | https://ustechautomations.com/offers | Live. Buttons go to `/partner`. Not a change feed. |
| Product app | SaaS $32 cards | `/pricing` `/partner` | Theirs. Leave it. |
| `/placements` | Blog vendors | github.io copy | Parked. Duplicate of blog-sponsorship. |
| One-job permit file | One contractor, one address | disk only | Parked. One-off. |

## How to add something

1. Put a row in this file first (buyer, URL, live/parked).
2. If it is a repeatable change feed, `scripts/new_family.py` and a real sample.
3. Do not add a new main-site path or subdomain until the row exists here.
