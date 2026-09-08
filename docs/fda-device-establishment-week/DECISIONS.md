# Decisions
[sourced: task] Build this FDA family on the assigned branch; no deploy, push, network, paid actions, or platform changes.
[sourced: c5_5] Shared family template is absent. Use the copied sibling and existing render_family house template as fallback.
[derived] Registration listings repeat establishments: key by registration_number + fei_number and union product codes / establishment types; inconsistent scalar registration values refuse the export.
[derived] Keep source timestamps as export dates, never collection dates. Privacy uses a conservative business-word allowlist and output column whitelist. Do not emit raw records.
[derived] Missing prior history means UNKNOWN; synthetic removed rows are tests only. The staged page will withhold its sample until a genuine comparison is supplied.
[derived] Network transport and scheduling are outside this offline artifact. Default state destination follows the task, but every run here supplies sandbox --out.
[derived] Never replace sealed output; compare identical bytes on rerun, refuse drift. Validate the complete input pair before writing. Linux flock prevents concurrent writers.
[sourced: BET.json] Price $49/mo; checkout literal TO-MINT; no purchase button or invented fulfilment promise.
[measured: c23_2, exit 0] Full input contains 334839 listings; 299 lack both identity fields, including 272 business-word listings. Exclude these unmatchable listings and count missing_identity_records in snapshot metadata. Never invent an identifier. Coverage is explicitly narrower than every source listing.
[measured: c29_0, exit 0] One identity has conflicting name/owner values in the supplied real export. Exclude the entire identity, not an arbitrary winning row. Unsafe spreadsheet-prefix values likewise suppress the whole identity. Both exclusions are counted in metadata and suppressed across both sides of a comparison to avoid false appeared/vanished claims. Source hashes retain provenance; no private raw row is shipped.
