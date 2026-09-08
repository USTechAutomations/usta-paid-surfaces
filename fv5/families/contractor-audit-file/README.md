# contractor-audit-file

An audit-evidence file for worker classification. $49 once. No verdict, ever.

## The files

| File | What it does |
|---|---|
| `fetchlib.py` | fetch, cache, decode, and lift whole-sentence passages |
| `rules_build.py` | turns fetched pages into prong rows; holds the anchors |
| `pagedata.py` | the one place the free pages and the paid page read from |
| `refresh.py` | fetch → `data/*.json` → rebuild the free pages → one summary line |
| `fulfil.py` | renders the private page a buyer gets after paying |
| `selftest.py` | every gate, including the verdict gate |
| `browser_test.py` | drives the in-page tool in headless Chromium on port 8602 |
| `data/sources_seed.json` | the candidate official address per jurisdiction |
| `data/questions.json` | the 18 questions and the documents behind each |
| `data/rules.json` | what came back, per jurisdiction |
| `data/citations.json` | one row per quoted passage: url, exact words, date read |
| `data/status.json` | the run's counts and the drift flag |

The public pages are written by `scripts/slice_contractor_audit_file.py` through
`scripts/build_slices.py`. Nothing else writes them.

## Run it

```
python3 refresh.py --limit 50
python3 fulfil.py --fixture fixtures/session_paid.json
python3 selftest.py
```

## The one rule

No page, free or paid, may say what a worker is, is likely to be, or should be.
`selftest.py` removes every string that appears word for word in
`data/citations.json`, scans what is left for a list of forbidden sentences, and
separately checks that every block marked as a quote really is one of those
citation rows. A statute may say "is an employee". We may not.
