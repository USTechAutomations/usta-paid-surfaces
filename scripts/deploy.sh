#!/usr/bin/env bash
# Ship the built /feeds/ folder to its own Cloud Run service.
#
# The only build path that works on this project: build with Cloud Build to
# gcr.io, then deploy that image by name. A --source deploy and a local docker
# push both get refused on this account.
#
# ACCOUNT, and it is not optional. The default active gcloud account on this
# machine is a service account, and it cannot read the Cloud Build staging
# bucket: the build dies with "The user is forbidden from accessing the bucket
# [usta-prod_cloudbuild]", which reads like a broken build rather than the
# wrong login. Both commands below are pinned to the owner account instead of
# relying on whatever `gcloud config set account` last left behind. Override it
# with DEPLOY_ACCOUNT= if this ever moves.
set -euo pipefail
TAG="${1:?usage: deploy.sh <tag>}"
ACCOUNT="${DEPLOY_ACCOUNT:-admin@ustechautomations.com}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$HOME/.hermes/state/feeds"
exec 9>"$HOME/.hermes/state/feeds/deploy.lock"
flock -n 9 || { echo "Another feeds deployment holds the lock" >&2; exit 1; }

python3 scripts/check_site.py
python3 scripts/build_site.py

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp deploy/Dockerfile deploy/nginx.conf "$BUILD_DIR/"
cp -a dist "$BUILD_DIR/site"
python3 scripts/preserve_independent_overlays.py prepare --candidate "$BUILD_DIR" --account "$ACCOUNT"

gcloud builds submit "$BUILD_DIR" --tag "gcr.io/usta-prod/usta-feeds:${TAG}" \
  --account "$ACCOUNT" --quiet
python3 scripts/preserve_independent_overlays.py check-head --candidate "$BUILD_DIR" --account "$ACCOUNT"
gcloud run deploy usta-feeds \
  --image "gcr.io/usta-prod/usta-feeds:${TAG}" \
  --region us-central1 --platform managed \
  --allow-unauthenticated --port 8080 --account "$ACCOUNT" --quiet

python3 scripts/preserve_independent_overlays.py verify-public --candidate "$BUILD_DIR" --account "$ACCOUNT"
