# Buyer directory integration — 2026-09-09

The existing feeds hub separates actual checkout buttons from prices that need an availability discussion. It links all93 source catalog families, keeps independently published tool links, groups by buyer task, and adds progressively enhanced search. With JavaScript disabled, the full directory remains usable. It does not claim that a priced, public or fetched page is a sale or evidence of demand.

Scope: `index.html`, `scripts/build_hub.py`, and the shared-stylesheet check. The checker parses real stylesheet links and accepts the existing `styles.css?v=...` convention; it still refuses unowned hosts, comments, misleading basenames and non-stylesheet links. `tests/test_brand_stylesheet.py` preserves that boundary.

Validation: whole-site truth checker passed (863 slice pages;80 sample files behind40 priced families), strict hub brand checks passed,12 responsive light/dark states had no overflow or measured contrast failures, and9 interaction/no-JavaScript checks passed. Reviewed before/after screenshots are retained in the session evidence.

Owned publication used a local COPY-only Docker overlay on the freshly fetched serving digest, preserving root CSS, sitemap and unrelated peer files. Initial revision95 became96 during review;96 had identical scoped bytes and was used as the base. Revision97 then served all11 intended directory/catalog files with HTTP200 and exact matching hashes. This did not deploy the team-owned main website.

The same release restores truthful PathLab/Workshop catalog JSON routes while preserving unavailable paid processing as503. Workshop browser tools remain free. Those catalog source changes belong to the existing B/C platform repositories.

Evidence: `/home/gmullins/advisor-plans/business-integration-20260909/release/directory-catalog-result.json`, `catalog-public-readback.json`, and `evidence/directory-browser-public.json`. Re-fetch current state before relying on this historical record.
