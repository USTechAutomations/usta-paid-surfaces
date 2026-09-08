# notary-journal

Free: 51 pages, one per state and DC, quoting that state's own words about
keeping a notary journal. Paid, $49 once: the same in-browser journal with the
entry limit off.

```
python3 fv5/families/notary-journal/refresh.py --limit 60      # re-read every source
python3 fv5/families/notary-journal/selftest.py                # everything, including the browser
python3 fv5/families/notary-journal/browser_test.py            # just the browser
python3 fv5/families/notary-journal/fulfil.py --fixture fv5/families/notary-journal/fixtures/session_paid.json
python3 scripts/build_slices.py --only notary-journal          # write the pages
```

## The files

| File | What it does |
|---|---|
| `states_build.py` | Fetches each state's source, finds the journal provision in the words on the page, quotes it, and reads the flags off that quote. Everything else reads its output. |
| `refresh.py` | Runs the above weekly, compares each quote with the day's words, marks drift, rebuilds the pages. |
| `app_html.py` | The journal itself: one block of HTML with its script and its data inside it. The same block is the free tool and the paid one. |
| `fulfil.py` | The private page after payment: the same tool, no limit, the buyer's state selected. |
| `selftest.py` | The gate. Includes the verdict gate and the browser test. |
| `browser_test.py` | Headless Chromium: set a passphrase, save an entry, reload, unlock, backup, hit the free limit, refuse a paper-only state. |
| `data/states.json` | One row per state: the flags, the quote, the address, the date. |
| `data/citations.json` | url + quote + fetched + status, one row per state. |
| `data/status.json` | Last run: counts and the drift flag. |

## The one thing to know

18 of 51 states answered with a provision this machine could quote. The other 33
are recorded as unread and stay unsettled; their pages say so, and the paid copy
is not offered for them. That number is the product's honest state, not a bug to
be papered over.
