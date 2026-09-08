#!/usr/bin/env bash
# Publish the two open-source seeds as public GitHub repos (the loop's starting
# point). Run on the same day the /feeds pages go live, so the READMEs link to
# pages that exist. Safe to re-run: an existing repo just gets the update.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="USTechAutomations"
for pair in "acacheck:loops/aca" "schemahand:loops/schemahand"; do
  name="${pair%%:*}"; src="${pair##*:}"
  work="$(mktemp -d)"
  cp -r "$ROOT/$src"/. "$work/"
  rm -rf "$work"/__pycache__ "$work"/tests/__pycache__ "$work"/.venv 2>/dev/null || true
  if gh repo view "$ORG/$name" >/dev/null 2>&1; then
    echo "$ORG/$name exists; pushing update"
  else
    gh repo create "$ORG/$name" --public --description "$(sed -n 3p "$work/README.md" | cut -c1-120)" >/dev/null
  fi
  (cd "$work" && git init -q && git add -A \
     && git -c user.name="USTA bot" -c user.email="operations@ustechautomations.com" commit -qm "seed" \
     && git branch -M main && git remote add origin "https://github.com/$ORG/$name.git" \
     && git push -qu origin main --force)
  echo "published https://github.com/$ORG/$name"
  rm -rf "$work"
done
