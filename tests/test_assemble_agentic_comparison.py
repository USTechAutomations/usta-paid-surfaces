import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("agentic_install", HERE.parent / "scripts/assemble_agentic_comparison.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def make_db(path: Path, *, status_later=200, error_later=None):
    con = sqlite3.connect(path)
    con.executescript("""
      create table blobs(content_sha256 text primary key, content_gz blob not null, byte_len integer not null, truncated integer not null, first_seen_date text not null);
      create table page_snapshots(domain text,snapshot_date text,resource text,status_code integer,content_sha256 text,headers_json text,fetch_error text,row_sha256 text,collected_at text,primary key(domain,snapshot_date,resource));
      create table collection_runs(run_id text primary key,snapshot_date text,universe_version text,methodology text,started_at text,finished_at text,domains_seen integer,rows_inserted integer,rows_ignored integer,fetch_errors integer,batch_sha256 text);
    """)
    for day in ("2026-09-09", "2026-09-10"):
        hashes = []
        for resource in builder.AGENTIC_RESOURCES:
            body = b'{"ucp":{}}' if resource == "ucp" else (b"# shop" if resource == "llms" else b"{}")
            error = error_later if day == "2026-09-10" and resource == "mcp" else None
            status = status_later if day == "2026-09-10" and resource == "robots" and not error else (503 if error else 200)
            content_sha = None if error else builder.sha(body)
            projection = {"domain":"shop.example", "snapshot_date":day, "resource":resource,
                          "status_code":status, "content_sha256":content_sha,
                          "headers_json":"{}", "fetch_error":error}
            row_sha = builder.sha(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode())
            if content_sha:
                con.execute("insert or ignore into blobs values(?,?,?,?,?)", (content_sha, zlib.compress(body), len(body), 0, day))
            con.execute("insert into page_snapshots values(?,?,?,?,?,?,?,?,?)",
                        ("shop.example", day, resource, status, content_sha, "{}", error, row_sha, day))
            hashes.append(row_sha)
        con.execute("insert into collection_runs values(?,?,?,?,?,?,?,?,?,?,?)",
                    (day, day, "fixture", "fixture", day, day, 1, 7, 0,
                     int(day == "2026-09-10" and error_later is not None),
                     builder.sha(json.dumps(sorted(hashes)).encode())))
    con.commit(); con.close()


class AgenticInstall(unittest.TestCase):
    def test_status_changes_and_sealed_row_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db, status_later=204)
            with patch.object(builder, "canonical_scan", return_value=("CLEAN", "fixture clean")):
                meta = builder.build_agentic(db, ["shop.example"], root / "package", private_root=root)
            report = root / "package" / "report.csv"
            self.assertIn(",200,204,", report.read_text())
            self.assertEqual(meta["selected_row_count"], 14)
            self.assertEqual(meta["latest_observed_source_date"], "2026-09-10")
            self.assertRegex(meta["selected_rows_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(meta["source_runs"]["2026-09-10"]["seal_verification"], "recorded_not_recomputed_for_selected_scope")

    def test_fetch_error_is_unknown_and_writes_no_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db, error_later="timeout")
            with self.assertRaises(builder.UnknownArtifact):
                builder.build_agentic(db, ["shop.example"], root / "package", private_root=root)
            self.assertFalse((root / "package").exists())

    def test_guard_result_must_be_clean_before_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db)
            with patch.object(builder, "canonical_scan", return_value=("UNKNOWN", "fixture unavailable")) as scan:
                with self.assertRaises(builder.UnknownArtifact):
                    builder.build_agentic(db, ["shop.example"], root / "package", private_root=root)
            scan.assert_called_once()
            self.assertFalse((root / "package").exists())
            self.assertEqual(list(root.glob(".package-*")), [])

    def test_newer_partial_source_is_not_reported_as_current_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db)
            with sqlite3.connect(db) as con:
                con.execute("insert into page_snapshots select domain,'2026-09-11',resource,status_code,content_sha256,headers_json,fetch_error,row_sha256,collected_at from page_snapshots where snapshot_date='2026-09-10' and resource='robots'")
            with patch.object(builder, "canonical_scan", return_value=("CLEAN", "fixture clean")):
                meta = builder.build_agentic(db, ["shop.example"], root / "package", private_root=root)
            self.assertEqual(meta['latest_observed_source_date'], '2026-09-11')
            self.assertEqual(meta['later_copy'], '2026-09-10')
            self.assertTrue(meta['newer_incomplete_snapshot'])

    def test_existing_package_and_guard_failure_preserve_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db)
            with patch.object(builder, 'canonical_scan', return_value=('CLEAN', 'fixture clean')):
                first = builder.build_agentic(db, ['shop.example'], root/'package', private_root=root)
                before = {p.name:p.read_bytes() for p in (root/'package').iterdir()}
                with self.assertRaises(builder.UnknownArtifact):
                    builder.build_agentic(db, ['shop.example'], root/'package', private_root=root)
            self.assertEqual(before, {p.name:p.read_bytes() for p in (root/'package').iterdir()})
            with patch.object(builder, 'canonical_scan', side_effect=builder.UnknownArtifact('guard unavailable')):
                with self.assertRaises(builder.UnknownArtifact):
                    builder.build_agentic(db, ['shop.example'], root/'refused', private_root=root)
            self.assertFalse((root/'refused').exists())
            self.assertEqual(list(root.glob('.package-*')), [])

    def test_private_root_mode_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); db = root / "clock.db"; make_db(db)
            private = root / "private"; private.mkdir(mode=0o755)
            with self.assertRaises(builder.UnknownArtifact):
                builder.build_agentic(db, ["shop.example"], private / "package", private_root=private)


if __name__ == "__main__":
    unittest.main()
