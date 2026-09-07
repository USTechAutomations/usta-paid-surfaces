# Sources — enforcement-action-board

Every board is built only from the sources below. A source with no terms quote
does not ship.

## 1. EPA ECHO enforcement-case web service  (the whole of the board data)

- **URLs**
  - `https://echodata.epa.gov/echo/case_rest_services.get_cases?output=JSON&p_state=<CODE>&p_from_date=<MM/DD/YYYY>&p_to_date=<MM/DD/YYYY>`
  - `https://echodata.epa.gov/echo/case_rest_services.get_qid?output=JSON&qid=<QID>&responseset=1000&pageno=<N>&qcolumns=2,4,6,9,10,11,12,13,17,22,23,24,25`
  - Per-case report link printed on the boards: `https://echo.epa.gov/enforcement-case-report?id=<ActivityID>`
- **What it is:** the U.S. EPA's Enforcement and Compliance History Online (ECHO)
  formal enforcement-case search. Two-step: `get_cases` returns a query id, then
  `get_qid` pages the rows (1000 per page). Columns are trimmed with `qcolumns`.
- **Fetch method:** HTTPS GET, JSON output, User-Agent
  `USTechAutomations-fv5/1.0`. No account, no key. Rows come back unsorted and are
  sorted by us. One state per query plus one national 90-day query.
- **Status code seen:** `200` on every state query and the national query,
  fetched **2026-09-07** (see the REFRESH line: `source_ok=52/52`).
- **Licence / terms quote (EPA web services page,
  `https://echo.epa.gov/tools/web-services`, HTTP 200, 2026-09-07):**
  > "Public web services support the ECHO website and are available to web
  > developers. The services allow developers to design custom applications
  > utilizing a live feed of data from ECHO."
- **Data disclaimer quote (EPA disclaimers,
  `https://www.epa.gov/web-policies-and-procedures/epa-disclaimers`, HTTP 200,
  2026-09-07):**
  > "...no warranty expressed or implied can be made regarding the accuracy or
  > utility of the data on any other system or for general or scientific
  > purposes, nor shall the act of distribution constitute any such warranty. The
  > Agency reserves the right to revise EPA-stewarded datasets pursuant to further
  > analysis and review."
- **Copyright:** works of the U.S. federal government carry no copyright
  (17 U.S.C. § 105); ECHO records are public federal records reproduced verbatim.
- **Cadence:** monthly. Each run seals its own dated copy to
  `data/board.json`; the boards read only that copy.
- **What the record does NOT carry:** the case dataset has no city, no state, and
  no street for the party in the columns the service returns, so the boards show
  no town and say so. The state a board is about is the state we queried.

## 2. OSHA — attempted, not ingested (EPA-only for now)

- **URL:** `https://enforcedata.dol.gov/views/data_catalogs.php` (DOL bulk
  enforcement catalog → `osha_inspection` / `osha_violation` CSV).
- **Status code seen:** the catalog page answered `200` on **2026-09-07**.
- **Why it is not on the boards yet:** pulling and size-guarding the OSHA
  inspection CSV (skip files over 300 MB) is not built. Per S3 this is best-effort
  only, so the boards are EPA-only and the family page says so in these words:
  "OSHA actions will appear when the file is reachable." No 403 or bot wall was
  hit; the attempt and its result are recorded in `data/board.json` under `osha`.
- **Terms:** DOL enforcement data are U.S. federal public records; a terms quote
  will be added here before any OSHA row is ever shown, because a source with no
  terms quote does not ship.
