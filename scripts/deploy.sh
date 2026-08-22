#!/usr/bin/env bash
# Ship the built /feeds/ folder to its own Cloud Run service.
#
# The only build path that works on this project: build with Cloud Build to
# gcr.io, then deploy that image by name. A --source deploy and a local docker
# push both get refused on this account.
set -euo pipefail
TAG="${1:?usage: deploy.sh <tag>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 scripts/check_site.py
python3 scripts/build_site.py

rm -rf deploy/site
cp -r dist deploy/site

gcloud builds submit deploy --tag "gcr.io/usta-prod/usta-feeds:${TAG}" --quiet
gcloud run deploy usta-feeds \
  --image "gcr.io/usta-prod/usta-feeds:${TAG}" \
  --region us-central1 --platform managed \
  --allow-unauthenticated --port 8080 --quiet
