"""Where the pro-key signing secret comes from, on this machine and on Cloud Run.

On Cloud Run the secret arrives in the environment (Secret Manager mounts it as
LOOPS_SIGNING_SECRET). At home the delivery timer has no such variable, so this
asks Google Secret Manager through gcloud, once per process, and caches the
answer in memory only. It is never written to disk.
"""
from __future__ import annotations

import os
import subprocess

ENV = "LOOPS_SIGNING_SECRET"
SECRET_NAME = "loops-signing-secret"
PROJECT = "usta-prod"
ACCOUNT = "admin@ustechautomations.com"
_cache: str | None = None


class NoSecret(RuntimeError):
    pass


def get_secret() -> str:
    """The hex signing secret (>= 32 chars), or raise NoSecret with a plain reason."""
    global _cache
    if _cache:
        return _cache
    val = (os.environ.get(ENV) or "").strip()
    if len(val) >= 32:
        _cache = val
        return val
    try:
        out = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             f"--secret={SECRET_NAME}", f"--project={PROJECT}", f"--account={ACCOUNT}"],
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NoSecret(f"could not ask Secret Manager for the signing secret: {exc.__class__.__name__}")
    val = out.stdout.strip()
    if out.returncode != 0 or len(val) < 32:
        raise NoSecret("Secret Manager did not hand back a usable signing secret "
                       f"(gcloud exit {out.returncode})")
    _cache = val
    return val
