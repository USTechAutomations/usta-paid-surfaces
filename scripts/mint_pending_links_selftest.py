#!/usr/bin/env python3
"""The pure gates of mint_pending_links.py, proved on good AND bad inputs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mint_pending_links as m  # noqa: E402

GOOD_LINK = {"id": "plink_x", "url": "https://buy.stripe.com/abc", "active": True,
             "after_completion": {"type": "redirect", "redirect": {"url": m.AFTER_PAYMENT_URL}}}
GOOD_PRICE = {"unit_amount": 4900, "currency": "usd", "recurring": {"interval": "month"}}


def cat(**rows):
    return {"families": [{"id": k, **v} for k, v in rows.items()]}


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")


# 1. pending: only TO-MINT rows with a real dollar price
c = cat(a={"price": "$49/mo", "checkout": {"url": "TO-MINT"}},
        b={"price": "$49/mo", "checkout": {"url": "https://buy.stripe.com/live"}},
        c={"price": "ask", "checkout": {"url": "TO-MINT"}},
        d={"price": "$200 - $450", "checkout": {"url": "TO-MINT"}},
        e={"price": "$49/mo", "checkout": {"terms": "email product, no url"}},
        f={"price": "$49/mo"})
check(m.pending(c) == ["a"], f"pending picked {m.pending(c)}")

# 2. newly_armed: only the asked ids that now carry https
after = cat(a={"checkout": {"url": "https://buy.stripe.com/new"}}, z={"checkout": {"url": "TO-MINT"}})
check(m.newly_armed({}, after, ["a", "z"]) == {"a": "https://buy.stripe.com/new"}, "newly_armed")

# 3. stamped_live: needs status live AND today's stamp
today = "2026-09-06"
check(m.stamped_live(cat(a={"checkout": {"status": "live", "verified": today}}), "a", today) is None, "good stamp refused")
check(m.stamped_live(cat(a={"checkout": {"status": "unverified"}}), "a", today), "unverified passed")
check(m.stamped_live(cat(a={"checkout": {"status": "live", "verified": "2026-09-05"}}), "a", today), "stale stamp passed")
check(m.stamped_live(cat(), "a", today), "missing row passed")

# 4. link_faults: the good link passes; each single fault is caught by name
check(m.link_faults(GOOD_LINK, GOOD_PRICE, 4900, "monthly") == [], "good link faulted")
bad = [
    ({**GOOD_PRICE, "unit_amount": 4800}, GOOD_LINK, "amount"),
    ({**GOOD_PRICE, "currency": "eur"}, GOOD_LINK, "currency"),
    ({**GOOD_PRICE, "recurring": None}, GOOD_LINK, "monthly"),
    (GOOD_PRICE, {**GOOD_LINK, "active": False}, "switched off"),
    (GOOD_PRICE, {**GOOD_LINK, "after_completion": {"type": "hosted_confirmation"}}, "redirect"),
    (GOOD_PRICE, {**GOOD_LINK, "url": "https://example.com/x"}, "buy.stripe.com"),
    ({}, GOOD_LINK, "amount"),
]
for price, link, word in bad:
    f = m.link_faults(link, price, 4900, "monthly")
    check(f and any(word in x for x in f), f"fault not caught: {word} -> {f}")
check(m.link_faults(GOOD_LINK, GOOD_PRICE, 4900, "one_time"), "one_time over a monthly price passed")
check(m.link_faults(GOOD_LINK, {**GOOD_PRICE, "recurring": None}, 4900, "one_time") == [], "good one_time faulted")

# 5. button_count counts real hrefs only
check(m.button_count('<a href="https://buy.stripe.com/x">Subscribe</a> buy.stripe.com in prose') == 1, "button_count")
check(m.button_count("no button here, just buy.stripe.com text") == 0, "button_count false positive")

print("ok -- pending, arming, live stamp, Stripe read-back and button count all gate the way they should")
