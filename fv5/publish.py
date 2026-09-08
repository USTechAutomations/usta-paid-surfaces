#!/usr/bin/env python3
"""Push freshly-built private pages out to the live site.

The delivery job writes buyer pages into the MAIN checkout of the site
(`/home/gmullins/code/usta-paid-surfaces`, not this worktree). This script is
what actually publishes them:

  1. find which private pages are new or changed (only under `families/*/p/`),
  2. pull, stage ONLY those page folders, commit, push (so the repo has them),
  3. lay just those pages on top of the image that is serving the live site
     right now, and switch traffic to that (see fv5/lib/overlay_deploy.py),
  4. refuse to call it done unless every shipped page answers 200.

It never runs the whole-site build or `scripts/refresh_and_deploy.sh`, so a
buyer's delivery can no longer republish the rest of the site or anything
else that happens to be sitting in the tree.

Default is a DRY RUN that just prints the commands. `--live` runs them.
`--reship <families/x/p/slug/index.html>` adds an already-committed page to the
overlay (used to exercise the deploy path without a sale). NOTHING in this file
runs during the scaffold build.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import overlay_deploy  # noqa: E402

# The live site is served from the MAIN checkout, never from a worktree.
REPO = Path("/home/gmullins/code/usta-paid-surfaces")


def _new_private_pages(repo: Path) -> list[Path]:
    """Private pages that are untracked or modified, as repo-relative paths."""
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all",
                          "--", "families/*/p/"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"git status failed: {out.stderr.strip()}")
    pages: set[Path] = set()
    for line in out.stdout.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        p = Path(path)
        if p.name == "index.html" and len(p.parts) == 5 and p.parts[2] == "p":
            pages.add(p)
    return sorted(pages)


def _run(cmd: list[str], *, live: bool, cwd: Path | None = None) -> int:
    if not live:
        where = f"  (in {cwd})" if cwd else ""
        print("would run:", " ".join(cmd) + where)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually pull/commit/push/overlay")
    ap.add_argument("--reship", action="append", default=[], metavar="PAGE",
                    help="repo-relative private page to include even though it is already committed")
    args = ap.parse_args()
    live = args.live

    if not REPO.is_dir():
        print(f"STOPPED: {REPO} is not a directory", file=sys.stderr)
        return 1

    new_pages = _new_private_pages(REPO)
    reship = [Path(p) for p in args.reship]
    for p in reship:
        if not (REPO / p).is_file():
            print(f"STOPPED: --reship {p} is not a file in the repo", file=sys.stderr)
            return 1
    to_ship = sorted(set(new_pages) | set(reship))
    print(f"private pages: {len(new_pages)} new/changed, {len(reship)} reshipped, "
          f"{len(to_ship)} to overlay")

    if new_pages:
        n = len(new_pages)
        steps = [
            ["git", "-C", str(REPO), "pull", "--rebase", "--autostash"],
            ["git", "-C", str(REPO), "add", "--"] + [str(p.parent) for p in new_pages],
            ["git", "-C", str(REPO), "commit", "-m", f"fv5 deliveries: {n} private page(s)"],
            ["git", "-C", str(REPO), "push", "origin", "main"],
        ]
        for cmd in steps:
            rc = _run(cmd, live=live)
            if live and rc != 0:
                print(f"STOPPED: `{' '.join(cmd[:5])}...` exited {rc}; nothing deployed",
                      file=sys.stderr)
                return 1
    else:
        print("no new private pages to commit")

    try:
        return overlay_deploy.ship(REPO, to_ship, live=live)
    except overlay_deploy.OverlayError as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
