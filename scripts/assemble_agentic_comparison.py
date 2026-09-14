#!/usr/bin/env python3
"""Private retained-snapshot Agentic Commerce artifact builder.

This candidate reads only the retained observation clock. It never crawls,
reads Stripe, infers a buyer or order, or sends a result.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import stat
import shutil
import tempfile
import zlib
from pathlib import Path
from typing import Any

AGENTIC_DB = Path("/home/gmullins/Claude CLI/clocks/agentic_commerce/data/agentic_commerce.db")
POLICY = Path("/home/gmullins/code/usta-paid-surfaces/paid_file_sources.json")
GUARD = Path("/home/gmullins/code/usta-paid-surfaces/scripts/outbound_guard.py")
EXPECTED_POLICY_SHA256 = "c72ac080854f3683c40900913c8a14a1e6915c87c9bc3df3e26b5b959c5c90e8"
EXPECTED_GUARD_SHA256 = "348676595840b6215d75fc8b5085259642c46c21aee7c3527d172ce4dfe1544f"
PRIVATE_ROOT = Path("~/.hermes/state/agentic-commerce/manual-artifacts").expanduser()
AGENTIC_METHODOLOGY = Path("/home/gmullins/Claude CLI/clocks/agentic_commerce/METHODOLOGY.md")
AGENTIC_REVIEW = Path("/home/gmullins/reports/feeds-18-unknown-review-2026-09-06.md")
EXPECTED_AGENTIC_METHODOLOGY_SHA256 = "4662474c83530660e10c3be946455d2cb52e6f8781aad3295f16d39bdd2fa3ad"
EXPECTED_AGENTIC_REVIEW_SHA256 = "5dc49355afd2d77fd105b490b556aceeee54fbe4d23860afabe2127fab98e130"
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
AGENTIC_RESOURCES = {
    "robots": "/robots.txt", "llms": "/llms.txt", "ucp": "/.well-known/ucp",
    "agent_card": "/.well-known/agent-card.json", "agent_json": "/.well-known/agent.json",
    "mcp": "/.well-known/mcp", "mcp_server_card": "/.well-known/mcp/server-card.json",
}


class UnknownArtifact(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise UnknownArtifact(f"source is absent or symlinked: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise UnknownArtifact(f"source cannot be opened: {path}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise UnknownArtifact(f"source is not regular: {path}")
        chunks = []
        while True:
            b = os.read(fd, 1024 * 1024)
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)
    finally:
        os.close(fd)


def agentic_authority() -> dict[str, str]:
    """Pin the existing internal source classification; no new permission is minted."""
    method = regular_bytes(AGENTIC_METHODOLOGY)
    review = regular_bytes(AGENTIC_REVIEW)
    if sha(method) != EXPECTED_AGENTIC_METHODOLOGY_SHA256 or sha(review) != EXPECTED_AGENTIC_REVIEW_SHA256:
        raise UnknownArtifact("agentic source authority documents changed after review")
    return {"methodology_sha256": sha(method), "review_sha256": sha(review), "basis": "existing review classifies this as our own observation of bot-facing files; no third-party payload is redistributed"}


def _confine(path: Path, private_root: Path) -> Path:
    """Return a path below a private root, rejecting symlinked ancestors."""
    private_root = Path(private_root).expanduser()
    if not private_root.exists():
        private_root.mkdir(parents=True, mode=0o700)
    root = private_root.resolve()
    if private_root.is_symlink() or not root.is_dir():
        raise UnknownArtifact("private artifact root is unavailable or symlinked")
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise UnknownArtifact("private artifact root must have mode 0700")
    # CLI paths are resolved from the caller's working directory; the root is
    # a confinement boundary, not an implicit second path prefix.
    target = Path(os.path.abspath(path))
    try:
        if os.path.commonpath((str(root), str(target))) != str(root):
            raise UnknownArtifact("artifact path escapes private root")
    except ValueError as exc:
        raise UnknownArtifact("artifact path is not below private root") from exc
    cur = target.parent
    while True:
        if cur.is_symlink():
            raise UnknownArtifact(f"symlinked artifact directory: {cur}")
        if cur == root:
            break
        if root not in cur.parents:
            raise UnknownArtifact("artifact path escapes private root")
        cur = cur.parent
    if target.is_symlink():
        raise UnknownArtifact(f"unsafe output path: {target}")
    return target


def atomic(path: Path, data: bytes) -> None:
    """Create one private file atomically without replacing a concurrent file."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise UnknownArtifact(f"unsafe output path: {path}")
    if path.exists():
        if regular_bytes(path) == data:
            return
        raise UnknownArtifact(f"refusing to replace existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data); fh.flush(); os.fsync(fh.fileno())
        # A hard link is the no-clobber commit: a concurrent creator wins or
        # loses the link operation, and is never overwritten by this writer.
        os.link(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    else:
        try: os.unlink(tmp)
        except OSError: pass


def _rename_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a complete package directory, refusing collisions."""
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise UnknownArtifact("atomic no-clobber directory commit is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    rc = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)  # RENAME_NOREPLACE
    if rc:
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise UnknownArtifact(f"refusing to replace existing package: {target}")
        raise OSError(err, os.strerror(err), str(target))


def _commit_package(output: Path, files: dict[str, bytes], report_name: str,
                    guard_store: str | None, guard_record: Path,
                    metadata: dict[str, Any], private_root: Path) -> dict[str, Any]:
    """Guard staged files, then expose report and metadata in one package rename."""
    package = _confine(output, private_root)
    if package.exists():
        raise UnknownArtifact(f"refusing to replace existing package: {package}")
    package.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=".package-", dir=package.parent))
    os.chmod(stage, 0o700)
    try:
        for name, content in files.items():
            atomic(stage / name, content)
        verdict, reason = canonical_scan(stage / report_name, guard_store, guard_record)
        if verdict != "CLEAN":
            raise UnknownArtifact(f"canonical outbound guard did not clear: {verdict}")
        # The staged pathname is intentionally short-lived; retain an honest
        # stable path in the receipt while the scan still covered exact bytes.
        reason = str(reason).replace(str(stage / report_name), str(package / report_name))
        metadata = dict(metadata)
        metadata.update({"guard_verdict": verdict, "guard_reason": reason,
                         "source_guard_cleared": verdict == "CLEAN"})
        meta_name = report_name + ".meta.json"
        atomic(stage / meta_name, (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
        _rename_noreplace(stage, package)
        return {**metadata, "package": str(package), "report": str(package / report_name),
                "metadata": str(package / meta_name)}
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def canonical_scan(path: Path, store: str | None, record: Path) -> tuple[str, str]:
    guard_bytes = regular_bytes(GUARD)
    if sha(guard_bytes) != EXPECTED_GUARD_SHA256:
        raise UnknownArtifact("canonical outbound guard changed after review")
    try:
        if record.resolve() == POLICY.resolve():
            if sha(regular_bytes(record)) != EXPECTED_POLICY_SHA256:
                raise UnknownArtifact("canonical permission record changed before guard scan")
    except FileNotFoundError as exc:
        raise UnknownArtifact("canonical permission record is unavailable") from exc
    if GUARD.is_symlink() or not GUARD.is_file():
        raise UnknownArtifact("canonical outbound guard is unavailable")
    spec = importlib.util.spec_from_file_location("candidate_outbound_guard", GUARD)
    if spec is None or spec.loader is None:
        raise UnknownArtifact("canonical outbound guard cannot load")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    verdict, reason = mod.scan(path, store=store or mod.STORE, record=str(record))
    return str(verdict), str(reason)


def _kind(resource: str, body: bytes | None) -> str:
    if body is None: return "unknown"
    b = body.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not b or b.startswith(b"<"): return "gone"
    if resource == "robots":
        return "there" if re.search(rb"(?im)^\s*user-agent\s*:", body) else "gone"
    if resource == "llms": return "there"
    if b[:1] not in (b"{", b"["): return "gone"
    try: obj = json.loads(b.decode("utf-8", "replace"))
    except ValueError: return "gone"
    if resource == "ucp": return "there" if isinstance(obj, dict) and "ucp" in obj else "gone"
    return "there" if isinstance(obj, dict) else "gone"


def _state(resource: str, status: int | None, body: bytes | None) -> str:
    if status is None: return "unknown"
    if status in (404, 410): return "gone"
    if 200 <= status < 300: return _kind(resource, body)
    return "unknown"


def _body(con: sqlite3.Connection, content_sha: str | None) -> bytes | None:
    if not content_sha: return None
    row = con.execute("select content_gz from blobs where content_sha256=?", (content_sha,)).fetchone()
    if not row: return None
    try: return zlib.decompress(row[0])
    except zlib.error: return None


def _agentic_days(con: sqlite3.Connection, shops: list[str]) -> tuple[str, str]:
    rows = con.execute("select snapshot_date, count(*) from page_snapshots where domain in (%s) group by snapshot_date" % ",".join("?" * len(shops)), shops).fetchall()
    complete = sorted(day for day, n in rows if n == 7 * len(shops))
    if len(complete) < 2: raise UnknownArtifact("fewer than two complete retained agentic snapshots")
    return complete[-2], complete[-1]


def build_agentic(db: Path, shops: list[str], output: Path, *, guard_record: Path = POLICY, guard_store: str | None = None,
                  expected_policy_sha256: str | None = EXPECTED_POLICY_SHA256,
                  private_root: Path = PRIVATE_ROOT) -> dict[str, Any]:
    shops = sorted(set(s.strip().lower().rstrip(".") for s in shops))
    if not shops or any(not DOMAIN.fullmatch(s) for s in shops):
        raise UnknownArtifact("shop scope must contain valid domain names")
    authority = agentic_authority()
    if db.is_symlink() or not db.is_file(): raise UnknownArtifact("agentic snapshot database unavailable")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True); con.execute("pragma query_only=on"); con.execute("BEGIN")
    except sqlite3.Error as exc:
        raise UnknownArtifact("agentic snapshot database cannot be opened read-only") from exc
    try:
        latest_observed = con.execute(
            "select max(snapshot_date) from page_snapshots where domain in (%s)" %
            ",".join("?" * len(shops)), shops).fetchone()[0]
        earlier, later = _agentic_days(con, shops)
        runs = {}
        for day in (earlier, later):
            row = con.execute("select batch_sha256,rows_inserted,fetch_errors from collection_runs where snapshot_date=? order by rowid desc limit 1", (day,)).fetchone()
            if not row or not re.fullmatch(r"[0-9a-f]{64}", str(row[0])): raise UnknownArtifact(f"missing run seal for {day}")
            # The run root covers every inserted row, while this report is a
            # selected shop scope. Preserve the recorded value and counts but
            # do not call it verified for the selected scope.
            runs[day] = {"batch_sha256": row[0], "rows_inserted": row[1],
                         "fetch_errors": row[2], "seal_verification": "recorded_not_recomputed_for_selected_scope"}
        q = "select domain,snapshot_date,resource,status_code,content_sha256,headers_json,fetch_error,row_sha256 from page_snapshots where domain in (%s) and snapshot_date in (?,?) order by domain,resource,snapshot_date" % ",".join("?" * len(shops))
        vals = shops + [earlier, later]
        data = {}
        selected_row_hashes = []
        for d, day, res, status, csha, headers, error, rsha in con.execute(q, vals):
            if str(error or "").strip():
                raise UnknownArtifact(f"fetch error retained for {d}/{res}/{day}")
            projection = {"domain": d, "snapshot_date": day, "resource": res, "status_code": status, "content_sha256": csha, "headers_json": headers, "fetch_error": error}
            if sha(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode()) != rsha:
                raise UnknownArtifact(f"sealed row hash mismatch for {d}/{res}/{day}")
            if csha:
                body = _body(con, csha)
                if body is None or sha(body) != csha:
                    raise UnknownArtifact(f"content hash mismatch for {d}/{res}/{day}")
            data[(d, res, day)] = (status, csha, rsha)
            selected_row_hashes.append(rsha)
        out_rows = []
        for shop in shops:
            shop_changed = False
            for resource, path in AGENTIC_RESOURCES.items():
                states = []
                for day in (earlier, later):
                    status, csha, rsha = data.get((shop, resource, day), (None, None, None))
                    if rsha is None: raise UnknownArtifact(f"missing {shop}/{resource} on {day}")
                    state = _state(resource, status, _body(con, csha))
                    if state == "unknown":
                        raise UnknownArtifact(f"unknown retained state for {shop}/{resource}/{day}")
                    states.append((state, status, csha, rsha))
                if (states[0][0] != states[1][0] or states[0][1] != states[1][1]
                        or states[0][2] != states[1][2]):
                    shop_changed = True
                    out_rows.append({"record_type":"change", "site":shop, "resource":resource, "path":path, "from_date":earlier, "to_date":later, "from_state":states[0][0], "to_state":states[1][0], "from_status":"" if states[0][1] is None else str(states[0][1]), "to_status":"" if states[1][1] is None else str(states[1][1]), "from_content_sha256":states[0][2] or "", "to_content_sha256":states[1][2] or ""})
            if not shop_changed:
                out_rows.append({"record_type":"coverage", "site":shop, "resource":"*", "path":"", "from_date":earlier, "to_date":later, "from_state":"unchanged", "to_state":"unchanged", "from_status":"", "to_status":"", "from_content_sha256":"", "to_content_sha256":""})
    finally: con.rollback(); con.close()
    cols = ("record_type","site","resource","path","from_date","to_date","from_state","to_state","from_status","to_status","from_content_sha256","to_content_sha256")
    buf = io.StringIO(newline=""); w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(out_rows)
    payload = buf.getvalue().encode()
    meta = {"family":"agentic-commerce", "artifact_role":"daily_comparison_component", "fulfillment_scope":"not the complete historical changes file; customer shop selection, agreed interval, saved-body request authority, and order/delivery join remain unresolved", "shops":shops, "earlier_copy":earlier, "later_copy":later, "latest_observed_source_date":latest_observed, "newer_incomplete_snapshot":latest_observed != later, "change_count":sum(r["record_type"] == "change" for r in out_rows), "csv_sha256":sha(payload), "selected_row_count":len(selected_row_hashes), "selected_rows_sha256":sha(json.dumps(sorted(selected_row_hashes), separators=(",", ":")).encode()), "source_runs":runs, "authority":authority}
    return _commit_package(output, {"report.csv": payload}, "report.csv", guard_store,
                           guard_record, meta, private_root)



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a guarded Agentic Commerce retained-snapshot artifact")
    ap.add_argument("--db", type=Path, default=AGENTIC_DB)
    ap.add_argument("--shop", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ns = ap.parse_args(argv)
    try:
        result = build_agentic(ns.db, ns.shop, ns.output)
    except (UnknownArtifact, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"status": "UNKNOWN", "error_type": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps({"status": "PASS" if result["source_guard_cleared"] else result["guard_verdict"], **result}, sort_keys=True))
    return 0 if result["source_guard_cleared"] else (1 if result["guard_verdict"] == "BLOCKED" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
