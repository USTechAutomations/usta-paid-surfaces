# ai-disclosure-notice

Rules and ready wording for telling people when they are dealing with a machine.
Free to read and free to use in the browser. **$49 once** for the files the buyer
hosts on their own site.

## What is here

| File | What it does |
|---|---|
| `notice_build.py` | the whole body of knowledge: 11 sources, 56 quoted passages, 30 rule clauses, 8 notice templates, and the code that decides which of them match a set of answers |
| `refresh.py` | re-reads the government sites, re-checks every quote word for word, rewrites `data/*.json` |
| `../../scripts/slice_ai_disclosure_notice.py` | turns all of that into the family page and 12 sub-pages |
| `fulfil.py` | builds the private page a buyer gets after paying |
| `selftest.py` | everything that has to be true before this ships |
| `browser_test.py` | drives the free generator in a real browser and checks what appears on screen |
| `data/` | the four files the pages read, written by `refresh.py` |
| `fixtures/` | one paid checkout, one set of answers that should match a lot, one that should match nothing |

## Run it

```bash
cd /home/gmullins/code/usta-paid-surfaces
python3 fv5/families/ai-disclosure-notice/refresh.py ; echo RAW=$?
python3 fv5/families/ai-disclosure-notice/selftest.py ; echo RAW=$?
python3 scripts/build_slices.py ; echo RAW=$?
python3 scripts/check_site.py ; echo RAW=$?
```

`refresh.py --dry-run` checks the quotes against the bytes already on disk and
touches no network. That is the mode the tests use, so a government site being
down never fails a test run.

## How it decides anything

Every rule clause carries a `match` block saying what makes it relevant: which
uses it reaches, whether an obvious-robot exemption ends it, whether it only
bites above a million users, or whether it turns on something the form does not
ask. The same block is read twice, once by Python when the data is built and
once by JavaScript on the page. `selftest.py` runs both against the same two
fixtures, so the two copies cannot drift apart without a test going red.

## The rule this family lives by

**No page says what the reader's own legal position is.** A row says whether it
matches the answers typed into the form. It never says a law applies to you, that
you must do something, or that a draft is enough. `selftest.py` holds a list of
40 banned phrases and fails the build if any of them reaches any page, free or
paid. That list is in `VERDICT_BANNED`.

## Where the answers go

Nowhere. The form writes to one key in the browser tab, `fv6.ai-disclosure-notice.inputs`,
and the tab forgets it when it closes. Nothing is posted anywhere. The private
page a buyer gets pre-fills from that key once and then wipes it.

## What this is not

Not legal advice. Not a hosted disclosure page. Not a badge, not a certificate,
and not a list of organisations that bought it. There is nothing for us to keep
alive after the sale, which is the point.
