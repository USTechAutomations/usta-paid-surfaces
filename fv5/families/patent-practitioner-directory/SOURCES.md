# Sources

## USPTO Office of Enrollment and Discipline (OED) practitioner roster

- **URL (bulk download):** https://oedci.uspto.gov/OEDCI/practitionerRoster?hid_action=download
- **URL (portal the download button lives on):** https://oedci.uspto.gov/OEDCI/
- **What it is, quoted from the portal:** "The listings contain contact
  information for active attorneys, agents, design and limited recognition
  practitioners authorized to practice before the U.S. Patent and Trademark
  Office."
- **Update cadence, quoted from the portal:** "The roster file is updated
  nightly."
- **Licence / terms, quoted from https://www.uspto.gov/terms-use-uspto-websites**
  (the general USPTO Terms of Use the OED portal operates under; the OED
  portal page itself carries no separate licence text of its own):
  "Pursuant to federal law, most government-produced materials appearing on
  this website are not subject to copyright restrictions within the United
  States and are therefore in the public domain." and "Public domain
  information may be freely distributed and copied, but it is requested that
  in any subsequent use the United States Patent and Trademark Office
  (USPTO) be given appropriate acknowledgement." The roster is the USPTO's
  own record of its own registrants, not third-party content, so the
  "WARNING: Not all materials... are works of the U.S. government" exception
  on that same page does not apply to it.
- **Fetch method:** `urllib.request` GET, no login, no API key, no auth
  header beyond a `User-Agent` string; response is a ZIP containing
  `WebRoster.txt`, comma-separated, no header row, confirmed 16 columns
  (name, suffix, organization, address, city, state, country, zip, phone,
  registration number, registration type, government-employee flag).
- **Status code seen:** `200`, live, on 2026-09-07. Fetched 53,690 rows
  (7,956,159 bytes unzipped).
- **Cadence we read it at:** every `refresh.py` run (matches the source's own
  nightly cadence; we do not cache longer than one site build).
- **What we withhold that the source includes:** the source lists each
  practitioner's own name, street address, and phone number. This family
  never prints any of those three fields for any individual; see
  `MISSION.md` and every page's own "What this page cannot tell you" section.

No other source is used. `PROMPTS/NONE.md` confirms no model call is part of
this pipeline, so there is no model-provider terms entry to add here.
