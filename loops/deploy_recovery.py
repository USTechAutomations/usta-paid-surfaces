"""Scoped mode of loops/deploy.sh: preserve the currently served image/config.

Builds locally, rechecks serving revision, and changes only key-recovery code.
The existing read credential passes through a mode-0600 temporary configuration,
never the image, command line, Git, or a printed service export.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "admin@ustechautomations.com"
PROJECT = "usta-prod"
REGION = "us-central1"
SERVICE = "usta-loops"
GC = ["gcloud"]
FLAGS = ["--account", ACCOUNT, "--project", PROJECT]
FILES = ["loops/service/app.py", "loops/service/payment_claim.py", "loops/service/paid_products.json"]


def gjson(*args):
    return json.loads(subprocess.check_output(GC+list(args)+FLAGS+["--format=json"], text=True))


def serving(service):
    rows = [r for r in service["status"]["traffic"] if r.get("percent", 0)]
    if len(rows) != 1 or rows[0].get("percent") != 100:
        raise RuntimeError("Serving traffic is split; no change made")
    return rows[0]["revisionName"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-app-sha256", required=True, help="SHA-256 of the freshly extracted serving app before this change")
    args = ap.parse_args()
    if len(args.expected_app_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.expected_app_sha256):
        raise RuntimeError("Expected app hash is invalid")
    svc = gjson("run", "services", "describe", SERVICE, "--region", REGION)
    revision = serving(svc)
    rev = gjson("run", "revisions", "describe", revision, "--region", REGION)
    image = rev["status"]["imageDigest"]
    if not image.startswith("gcr.io/usta-prod/usta-loops@sha256:"):
        raise RuntimeError("Unexpected base image; no change made")
    with tempfile.TemporaryDirectory(prefix="usta-recovery-deploy-") as td:
        scratch = Path(td)
        env = dict(os.environ, DOCKER_CONFIG=str(scratch/"docker-auth"))
        token = subprocess.check_output(GC+["auth", "print-access-token", "--account", ACCOUNT], text=True).strip()
        login = subprocess.run(["docker", "login", "-u", "oauth2accesstoken", "--password-stdin", "https://gcr.io"], input=token, text=True, env=env, capture_output=True)
        if login.returncode:
            raise RuntimeError("Registry authentication unavailable")
        del token
        subprocess.run(["docker", "pull", image], env=env, check=True)
        cid = subprocess.check_output(["docker", "create", "--platform=linux/amd64", image], env=env, text=True).strip()
        try:
            subprocess.run(["docker", "cp", cid+":/app/loops/service/app.py", str(scratch/"before.py")], env=env, check=True)
        finally:
            subprocess.run(["docker", "rm", cid], env=env, capture_output=True, check=True)
        if hashlib.sha256((scratch/"before.py").read_bytes()).hexdigest() != args.expected_app_sha256:
            raise RuntimeError("The serving app changed; reconcile before publishing")
        context = scratch/"context"
        for name in FILES:
            target = context/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/name, target)
        (context/"Dockerfile").write_text("FROM "+image+"\nCOPY loops/service/ /app/loops/service/\n")
        tag = "gcr.io/usta-prod/usta-loops:recovery-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime())
        subprocess.run(["docker", "build", "--platform=linux/amd64", "-t", tag, str(context)], env=env, check=True)
        subprocess.run(["docker", "push", tag], env=env, check=True)
        if serving(gjson("run", "services", "describe", SERVICE, "--region", REGION)) != revision:
            raise RuntimeError("Serving revision changed during build; traffic was not changed")
        sys.path.insert(0,str(Path.home()/"code/market-services/stripe-readback"))
        import common
        # Keep every current setting, including Secret Manager references.
        spec = svc["spec"]["template"]["spec"]
        container = spec["containers"][0]
        container["image"] = tag
        values = container.setdefault("env", [])
        values[:] = [v for v in values if v.get("name") != "LOOPS_STRIPE_READ_KEY"]
        values.append({"name":"LOOPS_STRIPE_READ_KEY","value":common.load_key()})
        template_meta = svc["spec"]["template"].setdefault("metadata",{})
        template_meta.pop("name",None)
        meta = svc["metadata"]
        for field in ["resourceVersion","uid","creationTimestamp","generation","selfLink"]:
            meta.pop(field,None)
        svc.pop("status",None)
        svc["spec"]["traffic"] = [{"latestRevision":True,"percent":100}]
        manifest=scratch/"service.json"
        manifest.touch(mode=0o600)
        manifest.write_text(json.dumps(svc))
        # Capture diagnostics because a provider could echo rejected config.
        deploy=subprocess.run(GC+["run","services","replace",str(manifest),"--region",REGION]+FLAGS+["--quiet"],capture_output=True,text=True)
        if deploy.returncode:
            raise RuntimeError("Cloud Run replacement failed; diagnostics withheld to protect configuration. Inspect revision conditions.")
        result=gjson("run","services","describe",SERVICE,"--region",REGION)
        print(json.dumps({"service":SERVICE,"previous_revision":revision,"revision":serving(result),"image":tag,"url":result["status"]["url"],"changed_code":FILES}))


if __name__ == "__main__":
    main()
