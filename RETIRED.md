# Retired feeds

A feed listed here is gone from `catalog.json`, gone from `families/`, and gone
from the front page. Its addresses still answer, as retired pages, because
`published-addresses.txt` is only ever added to.

**This file is where a retired feed's evidence lives.** The catalog row is the
description of a product we sell; when there is no product the row goes, and if
the row is the only place the reasoning was written down then deleting it
destroys the reason along with the price. So the row is copied here first,
word for word, and then removed.

Nothing in here is a decision. It is the record of one already taken.

---

## ai-prices — AI list-price window

- **Retired** 2026-08-24, by the operator, after the publisher's terms were read
  for the first time.
- **Pages**: 1 feed page + 17 child pages, all now retired stubs.
- **Sentence shown on those pages**: see `retired-reasons.json`.
- **Was priced at** the amount recorded in the row below; the payment link named
  in it was switched off by the team lead on 2026-08-24 and its product and
  price were left alone, so no second link can be minted by accident.

### The catalog row as it stood, word for word

```
id: "ai-prices"
name: "AI list-price window"
buyer: "AI vendors and researchers"
cadence: "daily seals"
price: "Not for sale yet"
sample_status: "fail"
live: ""
group: "Software and AI pages"
short: "AI list-price window"
who: "AI vendors and researchers."
checkout: {}
```

### The note on that row, word for word

```
OFF SALE 2026-08-24. This is a permission decision, not a data-quality one: the feed itself is healthy (64 sealed dates 2026-06-11 to 2026-08-22, median gap 1 day).
WHY: every published price on this feed comes from ONE source, the openrouter model list. That publisher's written Terms of Service, at https://openrouter.ai/terms, Last Updated 2026-07-29, read live on 2026-08-24 by two readers independently, forbid the exact thing this collector does: "develop, support or use software, devices, scripts, robots or any other means or processes (such as crawlers, browser plugins, add-ons or any other automated technology) to scrape or copy any information on the Site or the Services". The same list also forbids access "for purposes of reselling API access to Models or otherwise developing a competing service". Their own opening paragraph puts the address we call inside "the Service". Verdict: REFUSAL. Three verdicts were available and this is not the unknown one.
THE ROBOTS FILE DOES NOT SAVE THIS AND THIS ROW MUST NEVER SAY IT DOES. Their machine rules file says Allow: / . A rules file is about traffic, not rights, and it never overrides written terms.
WE HAD NEVER READ THOSE TERMS. Not once. The collector holds no terms file, no licence file and no permission note, and its own method write-up mentions permission, terms, licence, copyright and resale zero times. The refusal was found on 2026-08-24, not breached knowingly.
NOTHING WAS DESTROYED IN STRIPE. The payment link, its price and its product are all still active. Find it by its stamp, never mint a second one:
  link  https://buy.stripe.com/7sY9AM14O0a6afOdTA0sU0N
  stamp feeds_family=ai-prices
ANYONE HOLDING THAT ADDRESS CAN STILL START A $175/MO SUBSCRIPTION. Switching it off is an operator decision and has not been taken.
SEPARATE AND STILL OPEN, do not fold these into the above: (1) the collector still fetches the OpenAI, Anthropic and Mistral price pages that our own 2026-08-11 review PARKED, newest copy 2026-08-24, and we hold 66 saved full copies of each; (2) it sends a Chrome-on-Linux browser signature instead of our own bot name on every fetch, which is the same fault we stopped a different source for on 2026-08-07; (3) the Groq address now forwards to a home page and may be being sealed as a price page.
TO SELL THIS AGAIN: obtain written permission from the publisher, or rebuild the feed on a source that grants reuse. Fixing the wording does not fix this one.
2026-08-24 -- SAMPLE WITHDRAWN AND THE SUPPLIER TAKEN OFF THE PAGE. The lane is RETIRED, not paused, so it has no reason to keep publishing a free compilation cut from a source that refused us. sample_status moved pass -> fail, which unlinks families/ai-prices/sample.csv and sample.json on the next build and stops the page linking them. The page also stopped naming the publisher: the two sentences that did were reworded, so nothing on it now says whose list this is.
WHY 'fail' AND NOT A NEW WORD. There are three statuses this estate knows -- pass, fail/unknown, parked -- and each carries its own assertion in check_site.py. 'fail' is the nearest true one: there is no sample file. It is not the RIGHT word (nothing failed; we took the file down on purpose) and inventing a fourth word would have walked the family past the assertion instead of satisfying it, so the page says out loud that the label is the nearest one available and what actually happened. 'parked' was considered and rejected: parked means we cannot collect the source at all, it forbids any dollar amount on the page, and it forbids child pages -- this family has 15 of them.
STILL OPEN AND NOT MINE TO DECIDE: this family and its 15 child pages still publish the refused publisher's prices, free, roughly 26 dollar amounts on the parent alone. Taking the sample down does not touch that. Whether the pages come down is a takedown decision, named here rather than taken.
```

### Corrections to that note, found when the pages came down

- It says **15 child pages**, twice. There were **17**: the count in
  `published-addresses.txt` and the folder count both said 17, and the note
  was never recounted after it was written. The number was quoted, not counted.
- It named `sample_status: fail` as the nearest available label. That reasoning
  is now moot: the family has no row and no folder, so there is no status to set.
- **The note's last word on the payment link is stale, and dangerously so.** It
  says in capitals that anyone holding the address can still start a subscription
  and that switching it off "has not been taken". It was taken later the same day:
  the team lead reports switching the link off and reading it back. I cannot read
  the payment platform from this lane, so from here the link's state is **reported
  off, not verified by me** — treat the sentence in the block above as a snapshot
  of the morning, not as today's answer.
- The item it left open — *"this family and its 15 child pages still publish the
  refused publisher's prices, free"* — is what this retirement closes.
