# LA appeal packet: parked, September 13, 2026

The original paid appeal packet is **not accepted for sale**. The catalog sample status is `fail`; checkout remains `off_sale` with an empty URL. The existing Stripe link was deactivated and read back `active=false` on September 12. Both public offer and after-payment paths returned 404 again September 13. No link was reactivated or replacement product authorized by this qualification work.

The existing `selftest.py` passes on an isolated fixture copy, but it explicitly tests the unsupported rule `recorded_in = base_year - 1`. Ten independent qualification checks found one supported-address pass and nine failures, raw exit 2. Evidence, original bytes, current provider responses and exact commands: `/home/gmullins/reports/marketplace-closure-20260912/la-packet/`.

## Concrete defects

- `_num` / `_money` turn missing or malformed amounts into zero.
- `Source._query` accepts a missing feature collection or truncated results as complete empty data.
- `pick_subject` silently chooses one parcel from equally plausible distinct parcels.
- `OUT_FIELDS` has no recording date or sale price. `recorded_year`, `comp_record` and the public preview infer transaction years from base years; `parity.js` compares the preview against the same fixture assumptions. The inference and transaction-type/outlier classifications lack positive source evidence.
- `build_packet` supplies zero fixtures and personal property without requesting those source fields.
- The generated AAB100 mapping labels section 5 with the section 6 reason. The current county form distinguishes assessment type from appeal reason.
- `render_packet_html` advises attaching the support table at filing. The county's current AAB100 instructions explicitly say not to attach hearing evidence to the application.

The original page/preview/sample/delivery source still contains these claims and is **unaccepted**. Do not publish it because the fixture selftest passes. The new catalog status deliberately makes existing sample/readiness checks refuse this family; no gate was weakened.

## Lawful scope is unresolved

County eGIS terms fetched September 13 allow commercial adaptation and distribution of county data subject to their terms. This supports the data license, not the personalized form selection, legal-rights statements or filing recommendations in the current packet.

California Business and Professions Code 6400 regulates compensated legal-document/self-help services, including companies; section 6401 lists exemptions. This source inspection found no evidence establishing an applicable qualification or exemption for this implementation. Applicability remains **UNKNOWN**, not a finding of illegality. Under the operator's standing rule, a legal gray area is parked; it is not an approval request or a request to run the current service past somebody.

Sources fetched this run:

- [County GIS terms](https://egis-lacounty.hub.arcgis.com/pages/terms-of-use), also obtained from the county ArcGIS terms item `799d631faeae4703949b0061cef7a611/data`.
- [County AAB resources](https://bos.lacounty.gov/services/assessment-appeals/aab-resources/), linking the AAB100 revision 12 (05-24) used for field/instruction comparison.
- [California BPC 6400](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=6400.) and [6401](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=6401.).
- [Current county parcel service](https://cache.gis.lacounty.gov/cache/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0?f=pjson) and [historical roll item](https://www.arcgis.com/sharing/rest/content/items/70d93266f45a4080a97b285a471493cd?f=pjson). The historical service has a distinct RecordingDate field; it does not validate base-year arithmetic. The attempted counterexample query timed out and is UNKNOWN.

## What would have to change

Keep this shelf parked unless an already lawful, explicitly supported scope for the same product is established. Do not substitute a generic paid public-records reference and call the appeal packet fulfilled. Within such a qualified scope, independently demonstrate actual record/date/value provenance, ambiguous-address refusal, unavailable and truncated input handling, current form correspondence, useful supported output and buyer isolation. Then repair the original offer, preview, sample and delivery surfaces together, apply the existing brand/truth checks, and run actual delivery and canonical `/ship` acceptance before any reactivation. Fixing a 404 alone is insufficient.
