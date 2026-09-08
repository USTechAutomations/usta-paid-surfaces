#!/usr/bin/env bash
# Build and deploy the loops service to Cloud Run. Run from anywhere.
# Same shape as the neighbouring market-services deploy; the signing value is
# mounted from Secret Manager by name, never typed here.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACCOUNT="admin@ustechautomations.com"
PROJECT="usta-prod"
SVC="usta-loops"
TS="$(date +%Y%m%d-%H%M%S)"
IMG="gcr.io/${PROJECT}/${SVC}:${TS}"
cd "$ROOT"
gcloud builds submit . --config=loops/cloudbuild.yaml --substitutions=_IMG="$IMG" \
  --account "$ACCOUNT" --project "$PROJECT" --quiet
gcloud run deploy "$SVC" --image "$IMG" --account "$ACCOUNT" --project "$PROJECT" \
  --region us-central1 --service-account market-services-sa@usta-prod.iam.gserviceaccount.com \
  --port 8080 --allow-unauthenticated --min-instances 0 --max-instances 3 \
  --memory 512Mi --cpu 1 --concurrency 40 --timeout 30 \
  --set-secrets LOOPS_SIGNING_SECRET=loops-signing-secret:latest \
  --set-env-vars LOOPS_STORE=firestore,LOOPS_FS_DATABASE=loops,LOOPS_PUBLIC_BASE=https://ustechautomations.com/feeds,LOOPS_CORS_ORIGINS=https://ustechautomations.com \
  --quiet
gcloud run services describe "$SVC" --region us-central1 --account "$ACCOUNT" --project "$PROJECT" --format='value(status.url)'
