#!/usr/bin/env bash
# Re-read every clock, rewrite every page, gate it, and publish only if the
# gates pass.
#
# Why this exists: a dated-change feed that stops moving is worse than no page
# at all, because the page keeps claiming a number that is no longer true. This
# script is the thing that keeps the published pages honest without a human
# doing it by hand.
#
# It refuses to publish rather than publish something stale or wrong. A refusal
# writes an alert file the truth watchdog reads.
set -Eeuo pipefail

REPO="/home/gmullins/code/usta-paid-surfaces"
ALERT_DIR="$HOME/.hermes/state/alerts"
ALERT="$ALERT_DIR/feeds-refresh.md"
PROJECT="usta-prod"
SERVICE="usta-feeds"
REGION="us-central1"

# The account is pinned, not inherited.
#
# Whichever account gcloud happens to have marked "active" is ambient state the
# timer has no say over. On 2026-08-23 that was a service account which cannot
# reach the Cloud Build staging bucket, so the build died with a permissions
# error that had nothing whatever to do with this repo or these pages. Naming the
# account here makes a scheduled run reproduce a by-hand run exactly.
DEPLOY_ACCOUNT="admin@ustechautomations.com"
STAMP="$(date -u +%Y%m%d-%H%M%S)"

mkdir -p "$ALERT_DIR"

# A refusal that does not name its cause is how a thing stays broken for a week.
# The second argument is whatever the failing tool actually printed; it goes into
# the alert file AND onto stderr, because the two are read by different people.
die() {
  local why="$1"
  local said="${2:-}"
  {
    echo "# feeds refresh REFUSED"
    echo
    echo "when: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "why: $why"
    if [ -n "$said" ]; then
      echo
      echo "what the tool actually said:"
      echo
      echo '```'
      echo "$said"
      echo '```'
    fi
    echo
    echo "Nothing was published. The pages already live are unchanged."
  } > "$ALERT"
  echo "REFUSED: $why" >&2
  if [ -n "$said" ]; then
    printf '%s\n' "$said" >&2
  fi
  exit 1
}

# Run a gcloud step, keep everything it says, and refuse with those words if it
# fails. Redirecting only stdout to /dev/null, as this script used to, throws the
# error away at exactly the moment it is worth having.
run_gcloud() {
  local why="$1"
  shift
  local log
  log="$(mktemp)"
  if ! "$GCLOUD" "$@" >"$log" 2>&1; then
    local said
    said="$(tail -n 30 "$log")"
    rm -f "$log"
    die "$why" "$said"
  fi
  rm -f "$log"
}

# Find gcloud by absolute path before anything else needs it.
#
# systemd's user manager does not inherit an interactive shell's PATH, and the
# Cloud SDK installs into a directory that PATH does not carry. So under the
# timer this script could not see gcloud at all, while by hand it always could.
# That is why publishing worked every time a person ran it and had never once
# worked on schedule: the timer's first and only run died here. Bash wrote
# "gcloud: command not found" to a different journal identifier than the unit,
# so `journalctl -u feeds-refresh` -- the obvious place to look -- showed a bare
# "the container build failed" and nothing else.
GCLOUD="$(command -v gcloud 2>/dev/null || true)"
if [ -z "$GCLOUD" ]; then
  for candidate in \
    "$HOME/google-cloud-sdk/bin/gcloud" \
    /usr/lib/google-cloud-sdk/bin/gcloud \
    /usr/local/google-cloud-sdk/bin/gcloud \
    /snap/bin/gcloud
  do
    if [ -x "$candidate" ]; then
      GCLOUD="$candidate"
      break
    fi
  done
fi
if [ -z "$GCLOUD" ]; then
  die "gcloud is not installed anywhere this script can see" \
      "PATH was: $PATH"
fi

cd "$REPO"

# 1. Re-read the clocks and rewrite every family and slice page.
python3 scripts/build_slices.py || die "rebuilding the pages from the databases failed"

# 1b. The three pages that describe the whole shop are counted from every clock
#     at once, so they go stale the same way a feed page does. Rebuild them, then
#     the hub, so a feed that stopped or started shows up on the front page too.
python3 scripts/build_about.py || die "rebuilding the coverage and refusals pages failed"
python3 scripts/build_hub.py || die "rebuilding the front page failed"

# 2. Refuse a fake or undeclared pay link, a lost price, a lost honesty line.
python3 scripts/check_site.py || die "the page rules gate said no"

# 3. Build the deployable folder. This runs the fact-preservation gate and the
#    freshness gate; either one failing stops us here.
python3 scripts/build_site.py || die "the build gate said no"

# 4. Nothing to publish is a success, not a failure.
#
# This used to ask git whether anything had changed. It could not work: the
# deploy folder is in .gitignore, and the slice pages are generated files git
# has never been told about, so git saw nothing move and the script would have
# reported "no change" every single day while the dates on the pages marched on.
# A daily refresh that silently never publishes is the worst of both worlds --
# it looks healthy and the live pages rot.
#
# So we compare the built folder against the last build we actually got a live
# 200 for. The stamp is written only after that check passes, so a publish that
# half-failed is retried on the next run instead of being remembered as done.
rm -rf deploy/site
cp -a dist deploy/site
STATE_DIR="$HOME/.hermes/state/feeds"
mkdir -p "$STATE_DIR"
STAMP_FILE="$STATE_DIR/published.sha256"
NEW_HASH="$(cd dist && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
OLD_HASH="$(cat "$STAMP_FILE" 2>/dev/null || true)"
if [ -n "$OLD_HASH" ] && [ "$NEW_HASH" = "$OLD_HASH" ]; then
  echo "no change since the last publish"
  rm -f "$ALERT"
  exit 0
fi

# 5. Publish. This is the only path that works on this project: build the image
#    by tag, then point the service at it. A --source deploy is refused and a
#    local docker push is refused.
run_gcloud "the container build failed" \
  builds submit deploy \
  --tag "gcr.io/$PROJECT/$SERVICE:$STAMP" \
  --project "$PROJECT" \
  --account "$DEPLOY_ACCOUNT"

run_gcloud "the publish step failed" \
  run deploy "$SERVICE" \
  --image "gcr.io/$PROJECT/$SERVICE:$STAMP" \
  --region "$REGION" --project "$PROJECT" \
  --platform managed --quiet \
  --account "$DEPLOY_ACCOUNT"

# 6. Prove it actually answers before calling it done.
code="$(curl -s -o /dev/null -w '%{http_code}' https://ustechautomations.com/feeds)"
[ "$code" = "200" ] || die "published but the live page answered $code" \
  "GET https://ustechautomations.com/feeds returned HTTP $code, not 200. The new
image is live on $SERVICE but is not serving the page, so the published stamp was
not written and the next run will try again."

echo "$NEW_HASH" > "$STAMP_FILE"
rm -f "$ALERT"
echo "published $STAMP"
