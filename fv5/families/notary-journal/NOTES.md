# notary-journal — build notes (2026-09-08)

## What is done

- 51 free pages: 50 states + the District of Columbia, one page each, plus the
  family page. Every page carries the source link, the fetch date, the price
  and the "not affiliated / not legal advice" line.
- The family page **is** the journal app: one HTML file, script and data inline,
  68 KB against the 900 KB budget. No external script anywhere.
- The app keeps entries in the browser under `fv6.notary-journal.`, sealed with
  AES-GCM under a key stretched from the user's passphrase (PBKDF2, 200,000
  rounds). The passphrase is asked on every open. A wrong one gives nothing.
- Entries are append-only. A mistake is fixed with a correction entry that
  points at the original. Numbers are sequential and never reused.
- Backup is compulsory: after the first entry of a day, saving is refused until
  today's sealed backup file has been downloaded or a save folder is granted.
- Free use stops at 25 entries. The 26th is refused with a message that says the
  existing entries are still there.
- Paid page = the same app with the limit off, the buyer's state pre-picked, and
  a line saying the page is theirs and does not expire. No 12-month wording.
- `refresh.py`, `fulfil.py`, `selftest.py`, `browser_test.py`, `custom_fields.json`,
  three fixtures, `SOURCES.md`, `MISSION.md`, `OPERATE.md`, `README.md` all written.

## Counts

| Thing | Count |
|---|---|
| State pages | 51 |
| States whose own words are on the page | 18 |
| States recorded unread | 33 |
| States where the paid copy is offered | 11 |
| States recorded "electronic journal not allowed" | 1 (Nevada) |
| States recorded unsettled | 39 |

## CITE-CHECK

1. **33 states have no quote from the state's own text.** Their pages say so in
   plain words, their `electronic_allowed` is `unclear`, and the paid copy is
   not offered for them. They are: Alabama, Alaska, Arkansas, Colorado,
   Connecticut, Georgia, Hawaii, Idaho, Illinois, Indiana, Iowa, Kentucky,
   Louisiana, Maine, Maryland, Massachusetts, Michigan, Minnesota, Mississippi,
   Missouri, Nebraska, New Hampshire, New York, Rhode Island, South Carolina,
   South Dakota, Tennessee, Texas, Utah, Vermont, West Virginia, Wisconsin,
   Wyoming. Each one's HTTP status and the reason are in `SOURCES.md`.

2. **Texas is not the good fixture the brief asked for.** The brief named Texas
   as `known_good`. The Texas statute site answers 200 but sends an empty
   application shell — 250,874 bytes of HTML with no statute text in it, at
   every address tried. The research pack names a second address for the same
   section on `law.justia.com`; that one answers **HTTP 403**, a bot wall, which
   the walls in the brief say to record rather than evade. So Texas has two
   documented refusals, is `unclear`, and its Buy block is hidden. `fixtures/known_good.json` is **Pennsylvania** instead, and
   `fixtures/known_bad.json` is **Nevada**, with Texas written up in that file
   as a second bad case. This is a deviation from the brief and it needs a human
   decision: either accept Pennsylvania, or point me at a Texas address that
   serves the text of the statute rather than an application.

3. **Terms quotes are thin.** `SOURCES.md` wants a licence or terms sentence per
   source. Automatic extraction found a usable one for only 4 of the 18 cited
   sources, and one of those four is junk. The other 14 are recorded as "no
   terms sentence found", not invented. Anything published from those sources is
   the state's own statutory text, which is the safest class of material to
   quote, but the gap is real and is not closed.

## What is stubbed or deliberately left out

- **No pay button exists anywhere.** `checkout.url` is `TO-MINT`. When the link
  is minted, `OPERATE.md` says exactly where the button may go: the family page
  and the 11 permitted state pages, never on a state recorded not-allowed,
  vendor-only or unsettled.
- **No `no_offer` flag on the sub-pages.** `scripts/render_slice.py` hardcodes a
  sentence about publishers permitting copying only outside a commercial
  publication. That sentence is untrue for statutory text, and that file is not
  in my writable path, so I did not use the flag. Instead every page carries
  neutral contact wording and each state page states in plain words whether the
  paid copy is offered for that state.
- **Thumbprints are not captured**, by design. The app says a required thumbprint
  must be taken on paper.

## Two things the team lead should know about the shared build scripts

1. `python3 scripts/build_slices.py` with no arguments rebuilds every family. On
   this host today that run finishes with exit 0 but leaves
   `families/ttb/sample.csv` holding only its header row, which then fails
   `scripts/check_site.py` with "ttb sells at $99/mo and holds 0 data rows".
   That is another family's source, not mine. I reverted it and built with
   `--only notary-journal`, which leaves the estate green.
2. `python3 scripts/build_slices.py --only <id>` overwrites `var/set-aside.json`
   with just that one family's scope, wiping the other 470-odd lines. I restored
   that file. A whole-estate run will rewrite it properly.

## Deliberate choices about other families' files

This branch changes exactly two files outside its own family:
`catalog.json` (one appended row) and `families/coverage/index.html` (the shared
price list, which the honesty gate requires to list any family that sells).
`index.html` and `var/set-aside.json` were rebuilt by the shared scripts, carried
only other families' movements, and were restored to base so this branch does not
ship someone else's changes.


## The research pack arrived late

`~/reports/fv6-2026-09-08/research/S5-notary-journal.md` was not there when this
build started and was found near the end. It has now been read and acted on:

- Its six mirror addresses are wired in as a third place the fetcher looks. Only
  Texas needed one, and Texas refused. Full table in `SOURCES.md`.
- Its two secondary sources, the National Notary Association bulletin and the
  NotaryAct comparison table, set no flag on any page. The pack itself calls the
  first "best-practice, not a statute".
- Its California reading, that California is paper-only for in-person acts, is
  **not** encoded. California's own text on our page is about who owns the
  journal, not about format, so California stays `unclear` and its Buy block
  stays hidden. That is the safe direction. A human who wants California marked
  paper-only should point me at the sentence in Gov. Code 8206 that says it.
- Its rival prices are worth a look before the pay link is minted: one rival
  charges $14 a month billed yearly, another $20 a year. This family asks $49
  once, which undercuts both over any period longer than about four months.
