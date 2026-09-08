#!/usr/bin/env bash
# Install and arm the three fv5 user timers. THE OPERATOR RUNS THIS, not Claude:
# the scaffold build writes it and never executes it.
#
#   fv5-fulfil    every 10 minutes   build paid pages for buyers who have paid
#   fv5-health    daily at 06:00     prove every live family is sellable + fresh
#   fv5-refresh   Saturdays 03:00    rebuild every family, gate, publish
#
# These are USER units (no root). They run as your login session's systemd.
set -Eeuo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/systemd"
DEST="$HOME/.config/systemd/user"

mkdir -p "$DEST"
cp "$SRC"/fv5-fulfil.service "$SRC"/fv5-fulfil.timer \
   "$SRC"/fv5-health.service "$SRC"/fv5-health.timer \
   "$SRC"/fv5-refresh.service "$SRC"/fv5-refresh.timer "$DEST/"

systemctl --user daemon-reload
systemctl --user enable --now fv5-fulfil.timer fv5-health.timer fv5-refresh.timer

echo "installed and armed:"
systemctl --user list-timers | grep fv5
