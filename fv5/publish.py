#!/usr/bin/env python3
"""Push freshly-built private pages out to the live site.

The delivery job writes buyer pages into the MAIN checkout of the site
(`/home/gmullins/code/usta-paid-surfaces`, not this worktree). This script is
what actually publishes them: it pulls the latest main, stages only the private
page folders, commits, pushes, runs the site's own deploy, and then fetches the
newest private page and refuses to call it done unless it answers 200.

Only the `families/*/p/` folders are staged, so this can never publish anything
else that happens to be sitting in the tree.

Default is a DRY RUN that just prints the commands. `--live` runs them. NOTHING
in this file runs during the scaffold build.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# The live site is served from the MAIN checkout, never from a worktree.
REPO = Path("/home/gmullins/code/usta-paid-surfaces")
DEPLOY = "scripts/refresh_and_deploy.sh"


def _newest_private_url() -> str | None:
    """The public URL of the most recently written private page, or None."""
    pages = sorted(REPO.glob("families/*/p/*/index.html"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not pages:
        return None
    # families/<family>/p/<slug>/index.html
    slug = pages[0].parent.name
    family = pages[0].parent.parent.parent.name
    return f"https://ustechautomations.com/feeds/{family}/p/{slug}/"


def _count_private_pages() -> int:
    return len(list(REPO.glob("families/*/p/*/index.html")))


def _run(cmd: list[str], *, live: bool, cwd: Path | None = None) -> int:
    if not live:
        where = f"  (in {cwd})" if cwd else ""
        print("would run:", " ".join(cmd) + where)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually pull/commit/push/deploy")
    args = ap.parse_args()
    live = args.live

    n = _count_private_pages() if REPO.is_dir() else 0
    steps = [
        ["git", "-C", str(REPO), "pull", "--rebase", "--autostash"],
        ["git", "-C", str(REPO), "add", "families/*/p/"],
        ["git", "-C", str(REPO), "commit", "-m", f"fv5 deliveries: {n} private page(s)"],
        ["git", "-C", str(REPO), "push", "origin", "main"],
        ["bash", DEPLOY],
    ]
    for cmd in steps:
        cwd = REPO if cmd[0] == "bash" else None
        rc = _run(cmd, live=live, cwd=cwd)
        if live and rc != 0:
            print(f"STOPPED: `{' '.join(cmd)}` exited {rc}; nothing further run", file=sys.stderr)
            return 1

    url = _newest_private_url()
    if not url:
        print("no private pages on disk to verify")
        return 0
    if not live:
        print(f"would then: curl -sI {url}  (require HTTP 200)")
        return 0

    out = subprocess.run(["curl", "-sI", "--max-time", "30", url],
                         capture_output=True, text=True)
    first = out.stdout.splitlines()[0] if out.stdout else ""
    print(f"newest private page {url}\n  {first}")
    if " 200" not in first:
        print("STOPPED: the newest private page did not answer 200 after publish", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
