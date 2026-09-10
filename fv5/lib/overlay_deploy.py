#!/usr/bin/env python3
"""Ship a handful of private buyer pages to the live feeds site WITHOUT
rebuilding or redeploying the rest of it.

How it works, in plain terms:

  * The live site is one container image. We read which image is serving 100%
    of traffic right now (by its immutable digest, never a tag).
  * We build a tiny new image that starts FROM that exact digest and adds only
    the new private pages on top. Everything else on the site is untouched by
    construction, including whatever other people have layered on.
  * Before switching traffic we re-read the serving digest. If someone else
    deployed in the meantime, we rebuild once on top of THEIR image so we never
    roll their work back.
  * Every page we shipped must answer 200 at its public URL, or we report failure.

Nothing here touches the repo's main checkout, runs the whole-site build, or
calls `scripts/refresh_and_deploy.sh`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = "usta-prod"
REGION = "us-central1"
SERVICE = "usta-feeds"
ACCOUNT = "admin@ustechautomations.com"
IMAGE_REPO = f"gcr.io/{PROJECT}/{SERVICE}"
HTML_ROOT = "/usr/share/nginx/html"          # where the nginx image serves /feeds from
PUBLIC_BASE = "https://ustechautomations.com/feeds"
DIGEST_RE = re.compile(r"^gcr\.io/usta-prod/usta-feeds@sha256:[0-9a-f]{64}$")
NOINDEX = 'name="robots" content="noindex'


class OverlayError(RuntimeError):
    pass


def gcloud_bin() -> str:
    for cand in (shutil.which("gcloud"),
                 str(Path.home() / "google-cloud-sdk/bin/gcloud")):
        if cand and Path(cand).is_file():
            return cand
    raise OverlayError("gcloud not found")


def _gcloud_json(*args: str) -> dict | list:
    out = subprocess.check_output([gcloud_bin(), *args, "--project", PROJECT,
                                   "--account", ACCOUNT, "--format=json"], text=True)
    return json.loads(out)


def current_head() -> dict:
    """The image digest serving 100% of traffic right now (refuses on splits)."""
    svc = _gcloud_json("run", "services", "describe", SERVICE, "--region", REGION)
    conds = svc["status"].get("conditions", [])
    if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in conds):
        raise OverlayError("feeds service is mid-rollout; try again after it settles")
    serving = [t for t in svc["status"].get("traffic", []) if t.get("percent", 0) > 0]
    if len(serving) != 1 or serving[0].get("percent") != 100:
        raise OverlayError("feeds traffic is split; refusing to pick a base image")
    rev = serving[0].get("revisionName")
    if not rev:
        raise OverlayError("serving revision has no name")
    detail = _gcloud_json("run", "revisions", "describe", rev, "--region", REGION)
    image = detail["status"]["imageDigest"]
    if not DIGEST_RE.match(image):
        raise OverlayError(f"serving image is not an owned immutable digest: {image}")
    return {"revision": rev, "image": image}


def page_url(rel: Path) -> str:
    """families/<fam>/p/<slug>/index.html -> public URL."""
    parts = rel.parts
    if len(parts) != 5 or parts[0] != "families" or parts[2] != "p" or parts[4] != "index.html":
        raise OverlayError(f"not a private page path: {rel}")
    return f"{PUBLIC_BASE}/{parts[1]}/p/{parts[3]}/"


def stage_context(repo: Path, pages: list[Path], base_image: str) -> Path:
    """Copy only the given pages into a scratch build folder + Dockerfile."""
    ctx = Path(tempfile.mkdtemp(prefix="fv5-overlay-"))
    site = ctx / "site"
    for rel in pages:
        src = repo / rel
        text = src.read_text(encoding="utf-8", errors="replace")
        if NOINDEX not in text:
            raise OverlayError(f"{rel} has no noindex line; a delivery page must never be indexed")
        page_url(rel)  # validates the shape
        dst = site / rel.parts[1] / "p" / rel.parts[3] / "index.html"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (ctx / "Dockerfile").write_text(
        f"FROM {base_image}\nCOPY site/ {HTML_ROOT}/\n", encoding="utf-8")
    return ctx


def build_image(ctx: Path, tag: str) -> str:
    """Build in Cloud Build; return the new image pinned by digest."""
    ref = f"{IMAGE_REPO}:{tag}"
    if os.environ.get("FV5_BUILD_LOCAL") == "1":
        # Same publication rail, using owned local compute. Never put registry
        # credentials in the build context, image, arguments or diagnostic log.
        with tempfile.TemporaryDirectory(prefix="usta-overlay-auth-") as auth_dir:
            env = dict(os.environ, DOCKER_CONFIG=auth_dir)
            token = subprocess.check_output(
                [gcloud_bin(), "auth", "print-access-token", "--account", ACCOUNT],
                text=True).strip()
            login = subprocess.run(
                ["docker", "login", "-u", "oauth2accesstoken", "--password-stdin", "https://gcr.io"],
                input=token, text=True, capture_output=True, env=env)
            del token
            if login.returncode:
                raise OverlayError("registry authentication unavailable")
            for command in (
                ["docker", "build", "--platform=linux/amd64", "-t", ref, str(ctx)],
                ["docker", "push", ref],
            ):
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                if result.returncode:
                    raise OverlayError(f"local image {command[1]} failed (exit {result.returncode})")
        digest = subprocess.check_output(
            [gcloud_bin(), "container", "images", "describe", ref, "--project", PROJECT,
             "--account", ACCOUNT, "--format=value(image_summary.digest)"], text=True).strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise OverlayError("built image digest is unavailable")
        return f"{IMAGE_REPO}@{digest}"
    rc = subprocess.run([gcloud_bin(), "builds", "submit", str(ctx), "--tag", ref,
                         "--project", PROJECT, "--account", ACCOUNT, "--quiet"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        raise OverlayError(f"cloud build exited {rc}")
    digest = subprocess.check_output(
        [gcloud_bin(), "container", "images", "describe", ref, "--project", PROJECT,
         "--account", ACCOUNT, "--format=value(image_summary.digest)"], text=True).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise OverlayError(f"could not read digest of built image {ref}")
    return f"{IMAGE_REPO}@{digest}"


def deploy_image(image: str) -> None:
    rc = subprocess.run([gcloud_bin(), "run", "deploy", SERVICE, "--image", image,
                         "--region", REGION, "--project", PROJECT, "--platform", "managed",
                         "--account", ACCOUNT, "--quiet"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        raise OverlayError(f"cloud run deploy exited {rc}")


def http_status(url: str, timeout: int = 30) -> int:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "fv5-overlay-verify"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def verify_live(pages: list[Path], *, tries: int = 6, wait: float = 5.0) -> list[str]:
    """Return the URLs that did NOT answer 200 after a few polite retries."""
    bad: list[str] = []
    for rel in pages:
        url = page_url(rel)
        ok = False
        for _ in range(tries):
            if http_status(url) == 200:
                ok = True
                break
            time.sleep(wait)
        if not ok:
            bad.append(url)
    return bad


def ship(repo: Path, pages: list[Path], *, live: bool, log=print) -> int:
    """Overlay `pages` onto the live site. Returns 0 on verified success."""
    if not pages:
        log("overlay: 0 pages to ship; nothing deployed")
        return 0
    if not live:
        log(f"overlay would: read serving digest; build FROM it + {len(pages)} page(s); "
            f"re-check digest; deploy; verify {len(pages)} URL(s) answer 200")
        return 0
    head = current_head()
    log(f"overlay: base = {head['revision']}")
    tag = f"fv5-delivery-{time.strftime('%Y%m%d-%H%M%S')}"
    for attempt in (1, 2):
        ctx = stage_context(repo, pages, head["image"])
        try:
            image = build_image(ctx, f"{tag}-{attempt}")
        finally:
            shutil.rmtree(ctx, ignore_errors=True)
        again = current_head()
        if again["image"] == head["image"]:
            break
        log(f"overlay: someone deployed {again['revision']} meanwhile; rebuilding on top of it")
        head = again
    else:
        raise OverlayError("serving image kept changing; gave up after 2 builds")
    deploy_image(image)
    bad = verify_live(pages)
    if bad:
        log(f"overlay: {len(bad)} of {len(pages)} page(s) did not answer 200: " + " ".join(bad))
        return 1
    log(f"overlay: {len(pages)} page(s) live and answering 200")
    return 0
