#!/usr/bin/env python3
"""Fetch every declared checkout link and record whether it is really live.

A pay button is the one thing on these pages that must never be wrong. The gate
refuses to publish a checkout the catalog did not declare, and refuses to publish
a declared one that this script has not recently proved working.

WHAT IT ASKS BEFORE IT CERTIFIES

Fetching the address answers one question: does this link respond. It does not
answer whether the thing behind the link may be sold at all. On 2026-08-24 those
two answers came apart. A payable product for air permits was minted at 02:55,
and by the afternoon the ladder was refusing that surface outright -- its Arizona
half is not lawful to read, so `priced` passes while `lawful` fails. The payment
address answered 200 the whole time and would have been stamped `live` on the
next run, which is the stamp check_site.py reads before it ships a pay button.
A working link to something we may not sell is not a working checkout.

So the ladder is asked first, and the stamp is withheld from any surface it
refuses. WITHHELD, not reversed: nothing is un-stamped, nothing is torn down and
no existing record is cleared. Refusing to renew is enough, and it is the safe
direction -- removing a stamp is a step towards changing what a customer can buy,
while declining to add one only leaves the existing date to age out on its own,
which check_site.py already handles.

Run:  python3 scripts/verify_checkouts.py          (check and stamp)
      python3 scripts/verify_checkouts.py --dry    (check, change nothing)
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "catalog.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline as P  # noqa: E402
from pipeline import build_blindspots, build_veto  # noqa: E402


def probe(url: str, lands_on: str | None) -> tuple[str, str]:
    """Return (status, detail). 'live' only when the whole chain really works.

    Our pay buttons are two hops: the button points at our own /buy address and
    our server bounces the buyer to Stripe with an order tag attached. Fetching
    the first hop and seeing a 200 proves nothing, because our server answers a
    request form with 200 as well when a product is on hold. So we follow every
    redirect and insist the buyer ends up on the host the catalog named.
    """
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
             "--max-time", "25", url],
            capture_output=True, text=True, timeout=40,
        )
    except subprocess.TimeoutExpired:
        return "unknown", "the request timed out, so we cannot say either way"
    if out.returncode != 0:
        return "unknown", f"curl could not complete: {out.stderr.strip()[:120]}"
    code, _, final = out.stdout.partition(" ")
    final = final.strip()
    if code != "200":
        if code in {"402", "403", "404", "410"}:
            return "dead", f"answered {code}"
        return "unknown", f"answered {code}"
    if lands_on:
        host = final.split("/")[2] if "://" in final else ""
        if lands_on not in host:
            # This is the crawler-feed failure: the product is on hold, so the
            # button quietly lands on a request form instead of a checkout.
            return "dead", f"answered 200 but ended on {host or final!r}, not {lands_on}"
        return "live", f"bounced to {host} and that page answered 200"
    return "live", f"answered 200 (ended at {final})"


def refused_by_ladder(fid: str, vetoed: dict) -> str | None:
    """The sentence for why the ladder refuses this surface, or nothing.

    `vetoed` is what build_veto() returned, and it is a REQUIRED argument with
    no default. A default of {} would mean any caller that forgot to pass it
    certified every checkout it fetched with no ladder behind the stamp -- the
    exact state this file was in before today, and one that looks identical from
    the outside because every line it prints is still true. Forgetting it is now
    a TypeError at the call site instead.
    """
    hits = vetoed.get(fid, [])
    if not hits:
        return None
    return "; ".join(f"{h['higher']} passes while {h['lower']} fails -- {h['why']} "
                     f"({h['detail']})" for h in hits)


def unanswered_by_ladder(fid: str, blind: dict) -> str | None:
    """The sentence for a money gate standing over an UNKNOWN one, or nothing.

    A SEPARATE FUNCTION FROM refused_by_ladder ON PURPOSE, and the first version
    of this was not: it reused that one and printed "priced passes while lawful
    FAILS" over a gate whose verdict is `unknown`. The verdict, the exit code and
    every other check would have stayed green while the tool told a person the
    opposite of what the ladder said. An unknown that gets described as a failure
    is not more cautious -- it is a different claim, and it is false.

    `blind` is required and has no default, for the same reason as the other one.
    """
    hits = blind.get(fid, [])
    if not hits:
        return None
    return "; ".join(f"{h['higher']} passes while {h['lower']} is UNKNOWN -- {h['why']} "
                     f"({h['detail']})" for h in hits)


def main() -> int:
    dry = "--dry" in sys.argv

    # ASKED BEFORE ANYTHING IS FETCHED, and asked once. This reads the ladder off
    # the stores and the pages on this disk; it opens no network connection and
    # it touches nothing in Stripe.
    #
    # THERE IS NO FLAG TO SWITCH THIS OFF. No --force, no --ignore-veto, no
    # --anyway. That is deliberate and it is the whole value of the check. The
    # one moment anybody would reach for such a flag is the moment a surface is
    # refused and somebody wants the button shipped regardless, which is the
    # single case this exists to stop. A flag would also make the refusal look
    # like a preference. It is not one: `lawful` failing means we do not have
    # evidence we may read the source, and no argument on a command line changes
    # what evidence exists. If a refusal is wrong, the fix is in the ladder or in
    # the thing it read, and both are visible in `pipeline.py --check`.
    #
    # --dry is not a way round it either. --dry stamps nothing at all, so it can
    # only ever be more cautious than a refusal, never less.
    vetoed, estate_down = build_veto()

    # THE SECOND QUESTION, and it deliberately gets a different answer from the
    # first. These are surfaces where a money gate passes over a gate that came
    # back UNKNOWN -- the state `ai-prices` was in, at `blocked on lawful`, the
    # whole time it sold at $175 a month. An unknown that nothing acts on is
    # indistinguishable from a yes, so it is said here, loudly, at the moment a
    # pay button is being certified.
    #
    # IT DOES NOT WITHHOLD THE STAMP, AND THAT IS A DECISION, NOT AN OVERSIGHT.
    # Families are in this state right now, and the ones with a pay button on
    # them are already selling. Withholding their stamps ages their `verified`
    # dates out and takes the pay buttons off live products. That is money
    # coming off the estate, and money coming off the estate is an operator's
    # call, not a script's. A measured fault refuses; an unanswered question is
    # reported to the person who can answer it. The refusal above still
    # withholds.
    #
    # THE COUNT IS DELIBERATELY NOT WRITTEN HERE. This comment said "five
    # families ... every one of them is already selling"; hours later it was
    # three, and one of those three was priced with no pay button, so both
    # halves of the sentence had gone false while reading as fact. The run
    # prints the real list below every time it goes; a number typed into a
    # comment is a number nobody recounts.
    blind, blind_down = ({}, None) if estate_down else build_blindspots()
    estate_down = estate_down or blind_down
    if estate_down:
        # The ladder itself could not be read. That is UNKNOWN, and unknown never
        # rounds up to "nothing is refused". Certifying a pay button on the back
        # of an unread ladder is exactly the thing being prevented.
        print(f"NOTHING STAMPED: {estate_down}")
        return 1

    cat = json.loads(CAT.read_text(encoding="utf-8"))
    # THE DATE THAT GOES IN THE CATALOG, AND THE CLOCK IT COMES OFF.
    # `scripts/check_site.py` reads the `verified` stamp's AGE before it will
    # ship a pay button, so this date is an input to a money decision. It is
    # taken on this machine's local clock, which is seven hours behind UTC, and
    # the payment platform's own activity log is stamped in UTC. Within a few
    # hours of midnight those two name different days. A bare date here would be
    # an unlabelled unit on the one line where being a day out matters, so the
    # clock is printed next to it.
    today = dt.date.today().isoformat()
    print(f"stamping with {today} ({P.clock()})")
    changed = 0
    checked = 0
    withheld: list[str] = []
    dark: list[str] = []
    for fam in cat["families"]:
        c = fam.get("checkout")
        if not c:
            continue
        url = c.get("url") or ""
        if not url or url == "TO-MINT" or not str(url).startswith("https://"):
            # Written terms for a product sold through an email thread, or a
            # mint placeholder that is not yet a chargeable address.
            print(f"{fam['id']:16} no-link  terms are written down; sold by email, nothing to fetch")
            continue
        checked += 1
        status, detail = probe(c["url"], c.get("lands_on"))
        print(f"{fam['id']:16} {status:8} {detail}")
        if status != "live":
            print(f"  ^ {fam['id']} will NOT ship a pay button until this is fixed")
        unanswered = unanswered_by_ladder(fam["id"], blind)
        if unanswered:
            dark.append(f"{fam['id']}: {unanswered}")
            print(f"  ^ {fam['id']} is selling with an UNANSWERED question under it, and "
                  f"this stamp does not answer it: {unanswered}")
        refusal = refused_by_ladder(fam["id"], vetoed)
        if refusal:
            withheld.append(f"{fam['id']}: {refusal}")
            print(f"  ^ {fam['id']} REFUSED BY THE LADDER, so no live stamp is written "
                  f"even though the address answered: {refusal}")
        if not dry:
            c["checked"] = today
            # The only line the refusal changes. `checked` above is a record of
            # having looked and is true either way; `status` and `verified` are
            # the certificate check_site.py reads before it ships a pay button,
            # and a refused surface does not get one written today. Whatever the
            # record already holds is left exactly as it is -- not cleared, not
            # set to dead, not touched. This withholds a stamp; it never removes
            # one.
            if not refusal:
                c["status"] = status
                if status == "live":
                    c["verified"] = today
            changed += 1
    if not dry and changed:
        CAT.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nstamped {changed} checkout records in catalog.json")
    if dark:
        print("\nSELLING WITH AN UNANSWERED QUESTION UNDER IT -- stamped anyway, and "
              "nothing here withdraws anything:")
        for line in dark:
            print(f"  {line}")
        print("  Nothing on this disk can say whether these may be sold. Withdrawing one "
              "is money and an operator decides it.")
    if withheld:
        print("\nREFUSED BY THE LADDER -- fetched, but no live stamp written and "
              "nothing existing was changed:")
        for line in withheld:
            print(f"  {line}")
    if not checked:
        print("no checkout records declared yet")
    elif dry:
        # This used to key off `changed`, which stays 0 in --dry, so a dry run that
        # had just probed two live checkouts still announced that none were declared.
        print(f"\nchecked {checked} checkout records; --dry, so nothing was stamped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
