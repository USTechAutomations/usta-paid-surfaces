# usta-paid-surfaces

Subdomain factory for **repeatable** paid change feeds. Many buyers, one page per product. Not the product website. Not `/permits/offers` card mill. Not a one-job permit file.

Until DNS: https://ustechautomations.github.io/usta-paid-surfaces/

Intended host: `https://feeds.ustechautomations.com/` — see `DNS.md`. A human must add the CNAME.

Fable polishes look (`FABLE.md`). Structure, prices, samples, and mailto stay in this repo’s facts.

```bash
python3 scripts/check_site.py
python3 scripts/new_family.py slug --name "Name" --price '$175/mo' --buyer "who"
```

Do not add Stripe buttons. Do not edit `~/code/USTA`.
