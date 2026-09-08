# Mission — trademark-watch

## What we sell

Twelve months of watch on **one** US trademark application or registration, for
**$175, once**. Not a subscription. The buyer is the applicant or owner of the
mark (or someone acting for them). After they pay, we watch that one serial
number for a year: we re-read the public USPTO record about once a week, and we
email them when its status changes, when a similar mark is filed in the same
class, or when an opposition or office-action deadline is coming up. They also
get a private watch page that stays current for the year.

## Why anyone buys it

An owner who has filed a mark wants to know, early, when something happens to it
— a refusal, a publication for opposition, a look-alike filing by someone else.
The USPTO publishes all of this for free, but only as a firehose: a daily bulk
file of every application in the country. Nobody watches one mark by reading that
by hand every day. We do the watching and send a plain-English heads-up.

## The public pages

For every company-owned application in the daily file that has a watch-worthy
event (published for opposition, or an office action), we publish one free page:
the mark, its serial, filing date, status, class, owner, last event, and the
similar marks filed in its class in the last 90 days. Those pages are how an
owner finds us — by searching for their own mark — and they show exactly the kind
of update a paid watch delivers.

## What we never do

- We never make a natural person the subject of a page. Applications owned by an
  individual are withheld entirely, not renamed. Only company-owned marks get a
  page.
- We never claim to be the USPTO, to be affiliated with it, or to be a law firm.
  Every page carries that denial. This is monitoring, not legal advice, and not a
  filing on anyone's behalf.
- We never say data is live USPTO data when it is not. When we fall back to the
  synthetic fixture, every page says so.

## Definition of done

`refresh.py` builds the store and the public pages; `fulfil.py` turns a paid
Stripe session into a private watch page and a watch record; `selftest.py`
checks the shape of all of it; `build_slices.py`, `check_site.py` and
`build_hub.py` accept the family. The checkout is staged (`TO-MINT`), so the
public pages route to an email thread until the pay link is minted.
