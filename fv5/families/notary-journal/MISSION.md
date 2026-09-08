# Mission — notary journal

**What it sells.** One private web page carrying a notary journal that runs
entirely in the buyer's own browser, with no entry limit. $49, paid once. The
same tool is free on the public page, limited to 25 entries, so nobody pays
before using the thing they are paying for.

**Who buys it.** A notary public or a loan-signing agent who has to keep a
journal and does not want the record sitting on somebody else's server. They
arrive searching for their own state's rule.

**What is free.** 51 pages, one per state and the District of Columbia, each
quoting that state's own words about keeping a journal, with the address the
words came from and the date we read them.

**Delivery promise.** The private page is written within 15 minutes of payment.
It is the same tool with the limit off and the buyer's state already selected,
and the entries they already made in the free tool open on it with the same
passphrase, because it is the same browser and the same store. The page says it
does not expire; there is no renewal and nothing to cancel.

**Guardrails applied.**

* No page says what a reader's own position is. Pages show the state's words and
  the address they came from, and stop. `selftest.py` fails the build on a list
  of verdict sentences, extended for this domain.
* A state whose text we could not read is `unclear`, its page says so, and the
  paid copy is not offered for it. 33 of 51 are in that position today.
* Entries are sealed in the browser under a passphrase the buyer types. Nothing
  is uploaded. Nobody here can read an entry or reset a passphrase, and the page
  says so before anyone types one.
* A browser deletes data on its own, so the tool asks for an encrypted backup
  and refuses a new entry until one has been saved that day.
* No thumbprint is captured. Where a state's text asks for one, the page says it
  has to be taken on paper.
