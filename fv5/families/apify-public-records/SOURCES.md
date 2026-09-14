# Sources — apify-public-records

Every source here is US Government public-domain data. The EPA baseline below dates to **2026-09-07**; OSHA and NRC have explicitly dated **2026-09-12** acceptance sections. Nothing is fabricated: a
403 is recorded as a 403, and a source we cannot read live is not written into the
committed sample.

---

## 1. OSHA severe-injury reports — current source, 12 September 2026

The official page https://www.osha.gov/severe-injury-reports and linked https://www.osha.gov/sites/default/files/January2015toNovember2025.zip returned HTTP200 in the canonical isolated browser. The actual hosted direct request returned403; that route now fails explicitly instead of reporting empty success. A daily guarded collector publishes a minimized checksum-verified copy to the owned Apify store; the actor refuses copies older than48 hours. See collectors/osha/README.md for operation and rollback.

Original ZIP SHA a3f7f434e200fb956131f12277378e592993a25db3f328716fbece106f846bb0;105,996 counted source rows with dates2015-01-01 through2025-11-30. This public government file is historical, not a complete injury census. The public copy excludes street addresses and narratives. Original bytes are retained locally only for bounded acceptance/recovery; source fields are not a worker contact list.

Actual default0.3.2 hosted runRoP4xanoJ6VNeQUZo returned three records matching the independent source oracle, raw exit0. Current Store200 shows source lag, coverage and pricing. Source discovery, public delivery and commercial conversion are separate evidence; independent payment is still UNKNOWN. See actors/osha-severe-injury-reports/ACCEPTANCE.md.

## 2. EPA SDWIS drinking-water systems

- **URL:** `https://data.epa.gov/efservice/WATER_SYSTEM/STATE_CODE/AZ/PWS_TYPE_CODE/CWS/PWS_ACTIVITY_CODE/A/JSON`
  plus `https://data.epa.gov/efservice/VIOLATION/PWSID/<pwsid>/JSON`
- **Licence:** US Government work, public domain (EPA Envirofacts public data).
  The subject is a public water system, identified by its EPA-issued PWSID. No
  operator name, phone, email or street address is kept.
- **Fetch method:** HTTP GET of the Envirofacts REST service, JSON; one extra GET
  per system for its violation count.
- **Cadence:** Envirofacts is refreshed by EPA on its own schedule; a run reads it
  live.
- **Status on 2026-09-07:** **HTTP 200**, `application/json`. Read live and in
  full. **This is the free /feeds sample** and the EPA actor's live source.

## 3. NRC spill notices — current source correction, 12 September 2026

The obsolete DownLoad.aspx path returns an error page; it is not the current download mechanism. The official homepage https://nrc.uscg.mil/ returned HTTP200 and links directly to annual Excel files. https://nrc.uscg.mil/FOIAFiles/CY26.xlsx and https://nrc.uscg.mil/FOIAFiles/DataDictionary.xlsx both returned HTTP200 this run. The source SHA and counted coverage are in actors/nrc-spill-notices/ACCEPTANCE.md and the marketplace-closure-20260912/apify-recovery report.

The actor joins INCIDENT_COMMONS, MATERIAL_INVOLVED and INCIDENT_DETAILS by SEQNOS. Only the2026 receipt-year workbook has acceptance. Output keeps report/location/material fields and excludes caller names, street addresses, free-text narratives and responsible-party details. Reports are initial and unvalidated, as NRC states; a material entry is not proof of a confirmed release. Source failures are UNKNOWN, never successful empty results.

The NRC actor has real provider output acceptance. The family's older free EPA sample remains a separate artifact; it does not need to include NRC records. Legacy refresh.py still probes the obsolete NRC form for a diagnostic and must not be used as NRC product acceptance.

