# Operate — notary journal

The standing instruction for a maintenance run. It costs nothing to run and
should stay that way.

## Every week

```
python3 fv5/families/notary-journal/refresh.py --limit 60 ; echo RAW=$?
python3 fv5/families/notary-journal/selftest.py ; echo RAW=$?
```

`refresh.py` re-fetches every state's address, compares each quote with the
words on the page that day, and writes `data/status.json`. Read three things off
its line: `source_ok` (how many addresses answered), `cites_ok` (how many still
give up the provision), and whether `data/status.json` says `drift: true`.

**When a cited rule's text changes.** `refresh.py` marks that citation row
`drifted` and sets the drift flag. The delivered page then carries a dated
banner naming the state whose words moved, automatically. Read the state's page,
check the new words say what the row says they say, and if the flags changed,
let the next build write the state page again. A drift is not a fault; a silent
one would be.

**When a state that was unread starts answering.** It moves off `unclear` on its
own and its page changes with it. If its text permits an electronic journal, it
joins the states the paid copy is offered for. Check the new quote by eye before
that happens: the classifier is deliberately conservative, but conservative is
not the same as right.

## The rule that has to be applied by hand

`checkout.url` is `TO-MINT`. When the pay link is minted, put the button on the
family page and on the **11 state pages whose text permits an electronic
journal** only. Never on a state recorded not-allowed, vendor-only or unsettled.
Selling this as a statutory journal into a state whose own text says bound paper
is the one mistake here that would actually cost a buyer something.

## The kill rule

0 checkouts **and** 0 non-bot sub-page fetches by day 30 → stop work on it. The
pages stay up; they cost nothing and they are true. Do not expand it, do not
rewrite it, do not add states.

## The double rule

2 payments in 30 days → expand inside the family, inside the 30%-of-revenue
budget line. In order of what a buyer would actually get:

1. Clear the 33 unread states. That is hand work on the sites that answer with
   an application shell, and it is the single biggest gap in the product.
2. Fill in the terms quotes in `SOURCES.md` for the sources we already quote.
3. Only then anything new.
