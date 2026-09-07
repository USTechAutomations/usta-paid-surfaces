#!/usr/bin/env python3
"""Rebuild every fv5 family's public data once a week, gate it, and publish.

Runs, in order: each family's own `refresh.py` (which re-reads its source and
rewrites its public sample), then the estate's slice builder, its site-rules
gate, and its hub builder. Only if all of that passes does it commit, push and
deploy.

Like fv5/publish.py this operates on the MAIN checkout of the site
(`/home/gmullins/code/usta-paid-surfaces`), never on a worktree, because it
pushes to main.

Default is a DRY RUN that prints the commands. `--live` runs them and stops at
the first failure. NOTHING here runs during the scaffold build.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/gmullins/code/usta-paid-surfaces")
FAMILIES_DIR = REPO / "fv5" / "families"


def _family_refresh_scripts() -> list[Path]:
    if not FAMILIES_DIR.is_dir():
        return []
    return sorted(c / "refresh.py" for c in FAMILIES_DIR.iterdir()
                  if (c / "refresh.py").is_file())


def _run(cmd: list[str], *, live: bool, cwd: Path | None = None) -> int:
    if not live:
        where = f"  (in {cwd})" if cwd else ""
        print("would run:", " ".join(cmd) + where)
        return 0
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually rebuild, commit, push, deploy")
    args = ap.parse_args()
    live = args.live

    steps: list[tuple[list[str], Path | None]] = []
    for script in _family_refresh_scripts():
        steps.append((["python3", str(script)], REPO))
    for script in ("scripts/build_slices.py", "scripts/check_site.py", "scripts/build_hub.py"):
        steps.append((["python3", script], REPO))
    steps += [
        (["git", "-C", str(REPO), "add", "-A"], None),
        (["git", "-C", str(REPO), "commit", "-m", "fv5 weekly refresh"], None),
        (["git", "-C", str(REPO), "push", "origin", "main"], None),
        (["bash", "scripts/refresh_and_deploy.sh"], REPO),
    ]

    if not live and not _family_refresh_scripts():
        print("0 fv5 families to refresh (would still run the estate build + deploy on --live)")

    for cmd, cwd in steps:
        rc = _run(cmd, live=live, cwd=cwd)
        if live and rc != 0:
            print(f"STOPPED: `{' '.join(cmd)}` exited {rc}; nothing further run", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
