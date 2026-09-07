# Sources — apify-public-records

Every source here is US Government public-domain data. Status codes below were
probed from this build environment on **2026-09-07**. Nothing is fabricated: a
403 is recorded as a 403, and a source we cannot read live is not written into the
committed sample.

---

## 1. OSHA severe-injury reports

- **URL (page):** `https://www.osha.gov/severeinjury`
- **URL (data):** `https://www.osha.gov/sites/default/files/severeinjury.csv`
- **Licence:** US Government work, public domain. OSHA publishes the severe-injury
  dataset for public use. The public dataset contains employer/establishment
  fields; it does **not** contain injured-worker names, and none are added.
- **Fetch method:** HTTP GET of the CSV, parsed with the standard-library CSV
  reader; address columns dropped on the way in.
- **Cadence:** OSHA updates the file periodically; a run reads whatever the file
  holds on the day of the run.
- **Status on 2026-09-07:** page **HTTP 403**, CSV **HTTP 403** — osha.gov blocks
  automated fetches from this environment. This is recorded, not evaded. A real
  run on Apify fetches live; local `apify run` uses the labelled synthetic fixture
  at `actors/osha-severe-injury-reports/fixtures/sample_input_result.json`. This
  source is **not** part of the committed /feeds sample.

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

## 3. NRC spill notices

- **URL:** `https://nrc.uscg.mil/DownLoad.aspx` (data behind the download form on
  `https://nrc.uscg.mil/`)
- **Licence:** US Government work, public domain (National Response Center incident
  data). The subject is an incident; no caller name is kept.
- **Fetch method:** the data is **not** a plain file. `DownLoad.aspx` answers with
  an ASP.NET postback form; the actor loads the form, captures its
  `__VIEWSTATE` / `__EVENTVALIDATION` tokens, posts them back, and parses the CSV
  it returns. Field names can shift year to year, so the parser is defensive.
- **Cadence:** annual files; a run reads the year implied by the requested date
  range.
- **Status on 2026-09-07:** **HTTP 200**, `text/html` — a form, not a file, so the
  live pull is driven inside the actor and local `apify run` falls back to the
  labelled synthetic fixture at
  `actors/nrc-spill-notices/fixtures/sample_input_result.json`. This source is
  **not** part of the committed /feeds sample.
