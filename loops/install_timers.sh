#!/usr/bin/env bash
# Install and arm the three loops timers for this user. Safe to re-run.
# Run only after loops/ is on main at ~/code/usta-paid-surfaces (the units point there).
set -Eeuo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/systemd"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"
cp "$SRC"/loops-*.service "$SRC"/loops-*.timer "$DEST/"
systemctl --user daemon-reload
systemctl --user enable --now loops-metrics.timer loops-revoke.timer loops-evolve.timer
echo "armed:"
systemctl --user list-timers | grep loops-
