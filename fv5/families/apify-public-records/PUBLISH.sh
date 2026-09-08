#!/usr/bin/env bash
# Publish the three public-records actors to the Apify Store, under the OPERATOR's
# own Apify account. Nothing here is run automatically: the builder was not logged
# in, so these are the exact steps to run by hand when you are ready.
#
# Identity + payout are YOURS: the actors are pushed to whatever Apify account this
# machine is logged into, priced in each actor's `.actor/actor.json`, and Apify
# pays that account. This script never embeds a token and never reads a secret
# file. Run it from this directory:
#
#   bash PUBLISH.sh
#
set -euo pipefail
cd "$(dirname "$0")"

ACTORS=(osha-severe-injury-reports epa-sdwis-water-systems nrc-spill-notices)

# 1) Make sure you are logged in as the operator. `apify login` prompts for your
#    API token (Apify Console -> Settings -> Integrations). If APIFY_TOKEN is
#    already set in your shell, `apify login` will use it.
if ! apify info >/dev/null 2>&1; then
  echo ">> Not logged in. Running 'apify login' (paste your Apify API token)."
  apify login
fi
echo ">> Logged in as:"; apify info | sed -n '1,6p'

# 2) Push each actor as a PRIVATE actor first (build + upload). Pay-per-event
#    pricing is declared in each actor's .actor/actor.json (pricingInfos:
#    run-start $0.50, result-item $0.005) and a hard maxItems cap of 1000.
for a in "${ACTORS[@]}"; do
  echo ">> Pushing $a ..."
  ( cd "actors/$a" && apify push )
done

cat <<'NEXT'

>> Pushed. To finish, in the Apify Console for EACH actor:
   1. Open the actor -> Publication -> set it Public on the Apify Store.
   2. Confirm Monetization shows Pay-per-event with:
        run-start   = $0.50
        result-item = $0.005
      (these come from .actor/actor.json; adjust in the Console if needed).
   3. Copy the public listing URL, which looks like:
        https://apify.com/<your-username>/<actor-name>

>> Then wire the family page to the Store. In catalog.json, on the
   "apify-public-records" row, set the OSHA actor's public URL as the checkout:

     "checkout": {
        ...,
        "url": "https://apify.com/<your-username>/osha-severe-injury-reports",
        "status": "EXTERNAL",
        "verified": "<today's date>"
     }

   Leave it empty until the listing is actually live: an empty url keeps the page
   on its honest "email us for the Store links" path, and the honesty gate is
   happy with that. Only paste a URL you have opened in a browser yourself.
NEXT
echo ">> Done."
