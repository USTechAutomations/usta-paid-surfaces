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


def _staged_html_path(ctx: Path, rel: Path) -> Path:
    """Where stage_context() writes a private page inside the build context.

    The single source of truth for "the bytes we baked into the image", so the
    live check compares against these, never against a source file that may have
    drifted after the build.
    """
    return ctx / "site" / rel.parts[1] / "p" / rel.parts[3] / "index.html"


def stage_context(repo: Path, pages: list[Path], base_image: str) -> Path:
    """Copy only the given pages into a scratch build folder + Dockerfile."""
    ctx = Path(tempfile.mkdtemp(prefix="fv5-overlay-"))
    for rel in pages:
        src = repo / rel
        text = src.read_text(encoding="utf-8", errors="replace")
        if NOINDEX not in text:
            raise OverlayError(f"{rel} has no noindex line; a delivery page must never be indexed")
        page_url(rel)  # validates the shape
        dst = _staged_html_path(ctx, rel)
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
    """Return the URLs that did NOT answer 200 after a few polite retries.

    Legacy HEAD-only liveness probe kept for other callers. It cannot tell the
    new bytes from an already-live old page, so ship() no longer trusts it as
    proof of publication (see confirm_serving_image / confirm_serving_bytes).
    """
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


def fetch_page(url: str, timeout: int = 30, *, max_bytes: int = 8_000_000) -> tuple[int | None, bytes | None]:
    """GET the URL and return (status, body_bytes).

    status is None (and body None) only when the page could not be reached at
    all -- an unreadable probe, never to be mistaken for a served page.
    """
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "fv5-overlay-verify"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(max_bytes + 1)
            return (r.status, body) if len(body) <= max_bytes else (r.status, None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def confirm_serving_image(built_image: str, *, tries: int = 6,
                          wait: float = 5.0) -> tuple[bool, str]:
    """Confirm the digest serving 100% of traffic equals the just-built image.

    Returns (ok, diagnostic). ok is True only when the serving digest is
    positively read AND equals `built_image`. A different (e.g. pinned/old)
    serving image is refused with an activation diagnostic -- we never force
    traffic; staged activation stays the manager's job. A provider we cannot
    read yields UNKNOWN, never a silent success.
    """
    serving: str | None = None
    for _ in range(tries):
        try:
            serving = current_head()["image"]
        except Exception:
            serving = None
        if serving is not None and serving == built_image:
            return True, ""
        time.sleep(wait)
    if serving is None:
        return False, ("UNKNOWN: could not read the serving image from the "
                       "provider; publication is unconfirmed")
    return False, (f"serving image {serving} is not the just-built overlay "
                   f"{built_image}: the overlay is staged but not receiving "
                   f"traffic; refusing blind activation (manager owns activation)")


def confirm_serving_bytes(expected: dict[Path, bytes], *, tries: int = 6,
                          wait: float = 5.0) -> tuple[int, int]:
    """Each page must answer GET 200 with bytes exactly equal to what we staged.

    Returns (mismatch_count, unreadable_count). `expected` maps each page to the
    bytes baked into the image. An unreadable page is counted as unreadable, not
    as a pass. Diagnostics stay page-count only -- no page URL or body content.
    """
    mismatch = 0
    unreadable = 0
    for rel, want in expected.items():
        url = page_url(rel)
        ok = False
        reached = False
        for _ in range(tries):
            status, body = fetch_page(url, max_bytes=len(want))
            if status is not None:
                reached = True
                if status == 200 and body == want:
                    ok = True
                    break
            time.sleep(wait)
        if ok:
            continue
        if reached:
            mismatch += 1
        else:
            unreadable += 1
    return mismatch, unreadable


def ship(repo: Path, pages: list[Path], *, live: bool, log=print) -> int:
    """Overlay `pages` onto the live site. Returns 0 ONLY on verified success.

    Verified success means: every staged page is what the site actually serves.
    Concretely, after deploy the digest serving 100% of traffic must equal the
    just-built image, and every page must answer GET 200 with bytes identical to
    what we baked in (not a fresh read of a possibly-drifted source). Anything
    unconfirmed -- unreadable provider, unactivated image, byte mismatch, empty
    live set -- returns non-zero. No traffic is forced and nothing is rolled back.
    """
    if not live:
        # Rehearsal: pure description, never touches provider or network.
        if not pages:
            log("overlay rehearsal: 0 pages; nothing to preview")
            return 0
        log(f"overlay would: read serving digest; build FROM it + {len(pages)} page(s); "
            f"re-check digest; deploy; confirm the serving image is ours and each "
            f"page serves its exact bytes")
        return 0
    if not pages:
        # An empty live set is no work, not a publish. Do not credit it as success.
        log("overlay: refusing empty live publish; no pages to confirm serving")
        return 1
    head = current_head()
    log(f"overlay: base = {head['revision']}")
    tag = f"fv5-delivery-{time.strftime('%Y%m%d-%H%M%S')}"
    expected: dict[Path, bytes] = {}
    for attempt in (1, 2):
        ctx = stage_context(repo, pages, head["image"])
        try:
            # Freeze the exact bytes we baked in, before build or cleanup, so a
            # later source edit can never redefine what "correct" means.
            expected = {rel: _staged_html_path(ctx, rel).read_bytes() for rel in pages}
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
    ok_image, diag = confirm_serving_image(image)
    if not ok_image:
        log(f"overlay: {diag}")
        return 1
    mismatch, unreadable = confirm_serving_bytes(expected)
    if mismatch or unreadable:
        log(f"overlay: publication unconfirmed -- {mismatch} page(s) served wrong "
            f"bytes and {unreadable} unreadable of {len(expected)}")
        return 1
    ok_image, diag = confirm_serving_image(image, tries=1, wait=0)
    if not ok_image:
        log(f"overlay: {diag}")
        return 1
    log(f"overlay: {len(expected)} page(s) confirmed -- serving image is ours and "
        f"bytes match")
    return 0
