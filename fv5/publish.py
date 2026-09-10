#!/usr/bin/env python3
"""Flush the private delivery spool to the loops store. The retry driver.

The delivery job (fv5/fulfil.py) builds each buyer's file and SPOOLS it to an
outside-repo state directory before attempting delivery. This script is what
finalises delivery: it reads every pending spooled record and uploads it with a
signed, idempotent POST to the loops service, then reports how many are now
delivered and how many still need another run.

It no longer touches git, the public overlay or any subprocess: a buyer's file
is served by the loops store, never laid into the public image, and never
committed. Nothing here logs a URL, a capability, a key, or a byte of HTML —
only aggregate counts and outcome types.

Default is a DRY RUN that only reports what it would send. `--live` uploads.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # loops.* for the signer

import private_delivery as pd  # noqa: E402
from state_root import STATE_ROOT  # noqa: E402

# Same outside-repo state directory the delivery job spools into.
STATE = STATE_ROOT


def flush(spool: "pd.PrivateSpool", uploader: "pd.SignedUploader | None",
          live: bool) -> dict:
    """Deliver every pending record. Returns aggregate counts only."""
    counts = {"pending_in": 0, "delivered": 0, "conflict": 0,
              "refused": 0, "still_pending": 0}
    for record in spool.pending():
        counts["pending_in"] += 1
        if not live:
            counts["still_pending"] += 1
            continue
        result = pd.deliver(spool, record, uploader)
        outcome = result.get("outcome")
        if outcome == pd.DELIVERED:
            counts["delivered"] += 1
        elif outcome == pd.CONFLICT:
            counts["conflict"] += 1
        elif outcome == pd.REFUSED:
            counts["refused"] += 1
        else:
            counts["still_pending"] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually upload (default: dry run)")
    ap.add_argument("--state-dir", default=str(STATE), help="the delivery spool directory")
    args = ap.parse_args()

    pd.secure_dir(Path(args.state_dir))
    lock_fd = os.open(Path(args.state_dir) / "fulfil.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        print("delivery is already running", file=sys.stderr)
        return 1
    # The process owns this descriptor until exit, matching fulfil.py's lock.
    spool = pd.PrivateSpool(args.state_dir)
    uploader = pd.SignedUploader() if args.live else None
    counts = flush(spool, uploader, live=args.live)

    print(f"spool: {counts['pending_in']} pending in; "
          f"delivered {counts['delivered']}, conflict {counts['conflict']}, "
          f"refused {counts['refused']}, still pending {counts['still_pending']}")

    if not args.live:
        if counts["pending_in"]:
            print(f"dry run: {counts['pending_in']} record(s) would be uploaded. Re-run with --live.")
        return 0

    # A conflict, a refusal or anything still pending is an unresolved delivery.
    unresolved = counts["still_pending"] + counts["conflict"] + counts["refused"]
    if unresolved:
        print(f"STOPPED: {unresolved} delivery(ies) unresolved; returning non-zero.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
