# Fable — polish these pages. Do not change the facts.

Grok owns this repo’s **structure**: hosts, folders, prices, samples, mailto, honesty lines, the check script.

You own **look**: type, spacing, color, layout, mobile. Make each family feel like its own product, not a clone of `/permits/offers`.

## Where the files are

```
~/code/usta-paid-surfaces/
  index.html                 hub
  styles.css                 you may replace
  families/grid/index.html
  families/quakes/index.html
  families/ttb/index.html
  families/crawler/index.html
```

Live until DNS: https://ustechautomations.github.io/usta-paid-surfaces/

Intended host after a human adds DNS: https://feeds.ustechautomations.com/

## Do not change

- Prices (`$175/mo`, `$249`, `$349/mo`)
- Sample tables and event ids
- “Sample not ready” on TTB and crawler
- Mailto `operations@ustechautomations.com`
- No pay button / no Stripe / no `/partner`
- No SOC 2, Fortune 500, 10k teams, HIPAA
- No one-job permit packet, no one-hospital page
- Blog listings stay on `ustechautomations.com/blog-sponsorship`

HTML comments `<!-- FABLE: ... -->` mark safe visual zones.

## After you edit

```bash
python3 ~/code/usta-paid-surfaces/scripts/check_site.py
```

Must print `ok`. Then commit on this repo only. Never `~/code/USTA`.
