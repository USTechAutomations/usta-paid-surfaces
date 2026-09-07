# trademark-watch

Twelve months of watch on one US trademark application, **$175 one-off**.

## Files

| File | What it does |
|---|---|
| `MISSION.md` | What this family sells and why. |
| `refresh.py` | Pulls the USPTO daily file (or the fixture), keeps a dated copy in `data/marks.json`, and rebuilds the public per-mark pages and the private watch pages. |
| `fulfil.py` | Turns one paid Stripe checkout session into a private watch page plus a watch record, and returns the report. |
| `selftest.py` | Checks the whole family without touching the network. |
| `marks.py` | Shared code: parse, filter (company-only, watch-worthy), similar marks, render pages. |
| `custom_fields.json` | The two fields Stripe collects at checkout: `serial` (required) and `mark_text` (optional). |
| `fixtures/sample_daily.xml` | Synthetic USPTO-shaped daily file (250 fake marks). |
| `fixtures/session_paid.json` | A paid checkout session, for `fulfil.py --fixture`. |
| `tools/make_fixture.py` | Regenerates `sample_daily.xml`. Deterministic, no network. |
| `SOURCES.md` | The USPTO source, its terms, and a dated log of source reachability. |
| `PROMPTS/` | None needed — this family is pure public data, no model calls. |
| `data/marks.json` | The dated store `refresh.py` writes. |

## Run it

```bash
python3 fv5/families/trademark-watch/refresh.py --limit 50
python3 fv5/families/trademark-watch/fulfil.py --fixture fv5/families/trademark-watch/fixtures/session_paid.json
python3 fv5/families/trademark-watch/selftest.py
```

## Pages

- Public, indexable: `families/trademark-watch/index.html` (the family page,
  built by `scripts/build_slices.py`) and one page per company-owned,
  watch-worthy mark at `families/trademark-watch/<slug>/index.html` (built by
  `refresh.py`).
- Private, never indexed: `families/trademark-watch/p/<private_slug>/index.html`
  (built by `fulfil.py` and kept fresh by `refresh.py`).

## Status

Checkout is `TO-MINT` (no pay link yet), so the public pages route to an email
thread. An operator mints the $175 one-off pay link and arms the catalog row.
