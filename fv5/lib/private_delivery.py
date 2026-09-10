"""Producer side of private delivery: spool a buyer's built file, then upload it
to the loops service with a signed, idempotent, retry-safe POST.

Buyer artifacts never belong in the repo or public image. The spool lives in an explicit state directory OUTSIDE the repository,
with tight permissions (0700 dirs, 0600 files) and atomic writes.

What is persisted, and what is not
----------------------------------
We persist only what a *retry with no live session* needs: the family, the HASH
of the buyer's checkout session id, the HTML, the HTML's hash, the purchase time
and a delivery state. We never persist the raw checkout session id: that value is
the buyer's capability. It is held only in memory, for the length of one run, so
that we can optionally confirm the upload by fetching it back the way the buyer's
browser will.

Read-after-write
----------------
An upload is only finalised ("delivered") when the signed admin receipt hands
back the exact hash we stored. A receipt that disagrees cannot finalise the
record, so a corrupted or truncated body never counts as delivered.

Logging
-------
Only aggregate counts and outcome *types* are ever logged here — never a URL, a
capability, a key, or a byte of HTML.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import stat
import tempfile
from pathlib import Path

# Match the server: the store id is derived from the family and the session
# hash, and the signed body is canonical (sorted keys, no whitespace).
COLL = "fv5_deliveries"
MAX_HTML_BYTES = 800_000
DEFAULT_TIMEOUT = 15
DEFAULT_SERVICE_BASE = "https://usta-loops-260481739341.us-central1.run.app"

PENDING = "pending"
DELIVERED = "delivered"
RETRYABLE = "retryable_error"
CONFLICT = "conflict"
REFUSED = "refused"


# --------------------------------------------------------------- id helpers
def session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def doc_id(family: str, sess_hash: str) -> str:
    return hashlib.sha256(f"{family}\x00{sess_hash}".encode("utf-8")).hexdigest()


def html_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def canonical_body(family: str, sess_hash: str, html: str, html_sha256: str, ts: int) -> bytes:
    """The exact bytes the server verifies its signature over."""
    payload = {
        "family": family,
        "session_hash": sess_hash,
        "html": html,
        "html_sha256": html_sha256,
        "ts": int(ts),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


# --------------------------------------------------------------- the spool
def secure_dir(path: Path) -> None:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('private state cannot follow a symlink')
        if (part / '.git').exists():
            raise ValueError('private state must be outside every Git working tree')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def atomic_bytes(path: Path, data: bytes) -> None:
    """Write private state atomically, syncing both file and directory."""
    secure_dir(path.parent)
    if path.is_symlink():
        raise ValueError('private state cannot overwrite a symlink')
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.replace(tmp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(parent_fd)
        finally: os.close(parent_fd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def atomic_json(path: Path, value) -> None:
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))


def read_private(path: Path) -> str:
    secure_dir(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf-8') as inp:
        if not stat.S_ISREG(os.fstat(inp.fileno()).st_mode):
            raise ValueError('private state must be a regular file')
        return inp.read()


class PrivateSpool:
    """Validated immutable artifacts outside Git, with recoverable local flags."""
    def __init__(self, state_dir: str | Path):
        self.root = Path(os.path.abspath(state_dir))
        secure_dir(self.root)
        self.spool_dir = self.root / 'spool'
        secure_dir(self.spool_dir)

    def _path_for(self, rec_id: str) -> Path:
        if not isinstance(rec_id, str) or not re.fullmatch(r'[0-9a-f]{64}', rec_id):
            raise ValueError('bad spool record id')
        path = self.spool_dir / (rec_id + '.json')
        if path.is_symlink(): raise ValueError('spool record is a symlink')
        return path

    @staticmethod
    def _validate(record: dict) -> dict:
        if not isinstance(record, dict): raise ValueError('invalid spool record')
        allowed = {'id','family','session_hash','html','html_sha256','ts','state','attempts','state_update','state_applied','finalized'}
        if set(record) - allowed: raise ValueError('unexpected spool fields')
        r = dict(record)
        if not isinstance(r.get('family'),str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,31}',r['family']): raise ValueError('invalid spool family')
        for key in ('id','session_hash','html_sha256'):
            if not isinstance(r.get(key),str) or not re.fullmatch(r'[0-9a-f]{64}',r[key]): raise ValueError('invalid spool hash')
        if r['id'] != doc_id(r['family'],r['session_hash']): raise ValueError('spool id mismatch')
        if not isinstance(r.get('html'),str) or len(r['html'].encode())>MAX_HTML_BYTES or html_hash(r['html']) != r['html_sha256']: raise ValueError('spool artifact mismatch')
        if type(r.get('ts')) is not int or r['ts']<0: raise ValueError('invalid spool timestamp')
        if r.get('state') not in {PENDING,DELIVERED,RETRYABLE,CONFLICT,REFUSED}: raise ValueError('invalid spool state')
        if type(r.get('attempts')) is not int or r['attempts']<0: raise ValueError('invalid spool attempts')
        r.setdefault('state_update',{});r.setdefault('state_applied',False);r.setdefault('finalized',False)
        if not isinstance(r['state_update'],dict) or any(type(r[k]) is not bool for k in ('state_applied','finalized')): raise ValueError('invalid recovery flags')
        return r

    def spool(self, family: str, session_id: str, html: str, ts: int, state_update=None) -> dict:
        sh=session_hash(session_id)
        record={'id':doc_id(family,sh),'family':family,'session_hash':sh,'html':html,'html_sha256':html_hash(html),'ts':int(ts),'state':PENDING,'attempts':0,'state_update':state_update or {},'state_applied':False,'finalized':False}
        record=self._validate(record)
        existing=self.load(record['id'])
        if existing:
            if existing['html_sha256'] != record['html_sha256'] or existing['state_update'] != record['state_update']: raise ValueError('immutable artifact conflict')
            record=existing
        else: self.save(record)
        return dict(record, _session_id=session_id)

    def save(self, record: dict) -> None:
        record=self._validate({k:v for k,v in record.items() if not k.startswith('_')})
        existing=self.load(record['id'])
        if existing:
            if any(existing[k]!=record[k] for k in ('family','session_hash','html','html_sha256','ts','state_update')): raise ValueError('immutable artifact conflict')
            if existing['state']==DELIVERED and record['state']!=DELIVERED: raise ValueError('delivery state cannot regress')
        atomic_json(self._path_for(record['id']),record)

    def load(self, rec_id: str) -> dict | None:
        path=self._path_for(rec_id)
        if not path.exists(): return None
        record=self._validate(json.loads(read_private(path)))
        if record['id']!=rec_id: raise ValueError('spool filename mismatch')
        return record

    def records(self) -> list[dict]:
        secure_dir(self.spool_dir)
        return [self.load(p.stem) for p in sorted(self.spool_dir.glob('*.json'))]

    def pending(self) -> list[dict]:
        return [r for r in self.records() if r['state'] != DELIVERED]

    def is_delivered(self, family: str, session_id: str) -> bool:
        rec=self.load(doc_id(family,session_hash(session_id)))
        return bool(rec and rec['state']==DELIVERED)


# --------------------------------------------------------------- uploader
def _real_poster(url: str, body: bytes, headers: dict, timeout: float):
    """A bounded urllib POST. Never runs when the self-test tripwire is set."""
    if os.environ.get("FV5_SELFTEST_NO_REAL"):
        raise RuntimeError("real network call blocked by FV5_SELFTEST_NO_REAL")
    if not url.startswith("https://"):
        raise ValueError("delivery upload must be https")
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as resp:
            return resp.status, resp.read(MAX_HTML_BYTES + 4096)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096)


class SignedUploader:
    """Signs a spooled record and POSTs it to the loops admin route.

    ``secret_provider`` is called with no arguments and returns the shared
    signing secret string; in production this is
    ``loops.lib.signing.get_secret``. Tests inject a fake that returns a known
    synthetic secret so no real secret source is touched.
    """

    def __init__(self, service_base: str | None = None, secret_provider=None,
                 poster=None, timeout: float = DEFAULT_TIMEOUT):
        self.service_base = (service_base or DEFAULT_SERVICE_BASE).rstrip("/")
        self._secret_provider = secret_provider or self._default_secret
        self._poster = poster or _real_poster
        self.timeout = timeout

    @staticmethod
    def _default_secret() -> str:
        from loops.lib.signing import get_secret

        return get_secret()

    def upload(self, record: dict) -> dict:
        """Attempt one signed upload. Returns an outcome dict; never raises for a
        transient failure (those become RETRYABLE)."""
        body = canonical_body(record["family"], record["session_hash"],
                              record["html"], record["html_sha256"], int(time.time()))
        try:
            secret = self._secret_provider()
        except Exception:  # noqa: BLE001 -- no secret is retryable, not a crash
            return {"outcome": RETRYABLE, "status": None, "reason": "no signing secret"}
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        url = f"{self.service_base}/admin/delivery"
        headers = {"content-type": "application/json", "x-loops-sig": sig}
        try:
            status, raw = self._poster(url, body, headers, self.timeout)
        except Exception:  # noqa: BLE001 -- network/timeout is transient
            return {"outcome": RETRYABLE, "status": None, "reason": "upload did not complete"}
        return self._interpret(status, raw, record["html_sha256"])

    @staticmethod
    def _interpret(status: int, raw: bytes, expect_sha: str) -> dict:
        if status == 200:
            try:
                receipt = json.loads(raw.decode("utf-8") or "{}")
            except Exception:  # noqa: BLE001
                receipt = {}
            # Only a receipt whose hash matches ours may finalise the record.
            if isinstance(receipt, dict) and receipt.get("ok") is True and receipt.get("stored") is True and receipt.get("html_sha256") == expect_sha:
                return {"outcome": DELIVERED, "status": 200, "receipt_sha": expect_sha}
            return {"outcome": RETRYABLE, "status": 200, "reason": "receipt hash did not match"}
        if status == 409:
            return {"outcome": CONFLICT, "status": 409}
        if status in (401, 403):
            return {"outcome": REFUSED, "status": status}
        # 400s (bad request) and 5xx / 503 alike: leave pending for another run.
        return {"outcome": RETRYABLE, "status": status}


# --------------------------------------------------------------- driver
def deliver(spool: PrivateSpool, record: dict, uploader: SignedUploader) -> dict:
    """Upload one record and persist the resulting state. Idempotent: a record
    already DELIVERED is left untouched and reported as such."""
    if record.get("state") == DELIVERED:
        return {"outcome": DELIVERED, "status": None, "already": True}
    result = uploader.upload(record)
    outcome = result["outcome"]
    persisted = {k: v for k, v in record.items() if not k.startswith("_")}
    persisted["attempts"] = int(persisted.get("attempts", 0)) + 1
    persisted["state"] = outcome
    spool.save(persisted)
    return result


def verify_via_buyer(uploader_service_base: str, family: str, session_id: str,
                     poster, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
    """Read-after-write the way the buyer's browser will: POST the live session
    id (held only in memory) and return the delivered {html, html_sha256}, or
    None. Used to confirm a delivery within the same run; never persisted."""
    base = uploader_service_base.rstrip("/")
    url = f"{base}/delivery/{family}"
    body = json.dumps({"session_id": session_id}).encode("utf-8")
    try:
        status, raw = poster(url, body, {"content-type": "application/json"}, timeout)
    except Exception:  # noqa: BLE001
        return None
    if status != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        return None


def summarize(records: list[dict]) -> dict:
    """Aggregate counts by outcome type — the ONLY thing safe to log."""
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec.get("state", "unknown")] = counts.get(rec.get("state", "unknown"), 0) + 1
    return counts
