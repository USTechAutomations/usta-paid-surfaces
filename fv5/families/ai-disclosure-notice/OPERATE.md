# OPERATE — ai-disclosure-notice

The standing instruction for a maintenance run. Everything here costs nothing to
run and needs no human unless a check fails.

## The weekly check

```bash
cd /home/gmullins/code/usta-paid-surfaces
python3 fv5/families/ai-disclosure-notice/refresh.py ; echo RAW=$?
python3 fv5/families/ai-disclosure-notice/selftest.py ; echo RAW=$?
```

`RAW=0` twice and there is nothing to do. The refresh line prints five numbers.
Read them in this order.

| Number | What it means | What to do if it moves |
|---|---|---|
| `rows=30` | how many rule clauses we carry | went down: a clause was dropped by mistake, check the last commit |
| `pages=12` | how many sub-pages the slice module makes | went down: a page stopped building, run the builder and read the error |
| `source_ok=8/11` | how many government sites we could read | went down: a site is down or has started refusing us, record it, do not work around it |
| `cites_ok=52/56` | how many quoted passages still match their source word for word | went down: a law changed, see below |
| `stamp=` | today's date, stamped onto every page | |

## When a quote drifts

`refresh.py` exits `1` and names the quote. That is the whole point of this
family, so it is a job, not an error. Do it in this order.

1. Open the source URL from `SOURCES.md` and read the clause with your own eyes.
2. If the words changed, update the `quote` in `CITES` inside `notice_build.py`
   and, if the rule itself changed, the matching row in `DUTIES`.
3. If the *rule* changed and not just the wording, the draft notice that quotes
   it may now be wrong. Check `NOTICES` before shipping.
4. Re-run the refresh and the selftest. Commit.

Until that is done the delivered page shows a dated banner saying a source moved
and which one. Nothing is corrected silently and nothing is hidden from a buyer.

## Sources that refuse us

Three of the eleven do not answer an ordinary request from this host. They are
listed in `SOURCES.md` with the exact refusal. **Never work around a refusal.**
If one of them starts answering, change its `fetch` to `"curl"` in
`notice_build.py` and let the quote checker do the rest.

## How to expand, cheaply, and only when asked for

In rough order of how little work each one is:

1. **More clauses in states we already carry.** Illinois has one row and no
   fetched text. If `ilga.gov` ever becomes readable, that row gets real quotes.
2. **More states.** Texas, Nevada and New Jersey have AI-disclosure bills. Each
   new one is a `DUTIES` row plus quotes plus a `REGIONS` entry, and a
   jurisdiction page appears on its own once it has five rows between clauses
   and quotes.
3. **More notice templates.** A voice-agent disclosure and a recruitment-screening
   notice are the two most asked for. Each is a `NOTICES` entry keyed to duties
   that already exist.

Do none of this speculatively. Expand a jurisdiction when a buyer asked for it,
not before.

## The kill rule

**At day 30 from first publication: if there have been zero checkouts and zero
non-bot fetches of the family page, take it off sale.** Not "review it", take it
off sale. Set `checkout.status` to `off` in `catalog.json`, rebuild, and record
the date. A page nobody reads and nobody buys is not a slow starter, it is an
answer.

Non-bot fetches means real readers with the crawler traffic taken out. If that
number cannot be measured, treat it as zero and apply the rule anyway.

## The double rule

**At two payments inside any 30 days, double the work on this family, not the
price.** In practice that means: add the next two states, add the two extra
notice templates above, and only then look at the price. Two buyers is evidence
the wording is worth having, not evidence it is underpriced.

## What never changes without a person saying so

The price, the decision not to host anything for the buyer, and the rule that no
page states a legal conclusion about the reader. Those three are the shape of the
product. A maintenance run does not touch them.
