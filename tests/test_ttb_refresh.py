import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack, redirect_stdout
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slice_ttb

def refresh(dest, db):
    import build_slices, render_family
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.parent.parent
    (root / "catalog.json").write_text((Path(__file__).resolve().parents[1]/"catalog.json").read_text())
    slice_ttb.reset_data()
    with ExitStack() as stack:
        stack.enter_context(patch.object(slice_ttb, 'DB_PATH', db))
        stack.enter_context(patch.object(build_slices, 'ROOT', root))
        stack.enter_context(patch.object(build_slices, 'FAMILIES', root/'families'))
        stack.enter_context(patch.object(render_family, 'ROOT', root))
        stack.enter_context(patch.object(build_slices, 'load_modules', return_value=[slice_ttb]))
        stack.enter_context(patch.object(build_slices, 'build_veto', return_value=({}, None)))
        stack.enter_context(patch.object(slice_ttb, 'slices', return_value=[]))
        stack.enter_context(patch.object(sys, 'argv', ['build_slices.py','--only','ttb']))
        try:
            with redirect_stdout(io.StringIO()): build_slices.main()
        except (SystemExit, sqlite3.Error, OSError) as exc:
            print('UNKNOWN: '+str(exc), file=sys.stderr)
            return 2
    return 0


DDL = """
CREATE TABLE permit (
  snapshot_date TEXT NOT NULL,
  permit_number TEXT NOT NULL,
  operating_name TEXT,
  city TEXT,
  state_abbr TEXT,
  county TEXT,
  industry_type TEXT,
  new_permit_flag TEXT,
  state_prefix_mismatch TEXT,
  state_source TEXT
);
CREATE TABLE collection_runs (
  run_id TEXT PRIMARY KEY,
  snapshot_date TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  batch_sha256 TEXT NOT NULL,
  rows_inserted INTEGER NOT NULL,
  rows_total INTEGER NOT NULL,
  manifest_json TEXT NOT NULL
);
"""


def _put(con, day, permit, name, city="PASADENA", state="CA", trade="Wine Producer"):
    con.execute(
        "INSERT INTO permit VALUES (?,?,?,?,?,?,?,'0','0','ttb')",
        (day, permit, name, city, state, "COUNTY", trade),
    )


def _run(con, run_id, day, n):
    con.execute(
        "INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?)",
        (run_id, day, day + "T00:00:00", "x", n, n, "{}"),
    )


class RefreshContract(unittest.TestCase):
    def test_parent_refresh_hook_exists(self):
        self.assertTrue(
            callable(getattr(slice_ttb, "family_spec", None)),
            "TTB parent has no comparison refresh hook",
        )

    def tearDown(self):
        slice_ttb.reset_data()

    def _db(self, folder: Path) -> Path:
        db = folder / "ttb_permits.db"
        con = sqlite3.connect(db)
        con.executescript(DDL)
        # Window 1: 6 Jan 2026 vs 13 Jan 2026
        _put(con, "2026-01-06", "CA-P-1", "Alice Wines")
        _put(con, "2026-01-06", "CA-P-2", "Bob Cellars")
        _put(con, "2026-01-13", "CA-P-2", "Bob Cellars")
        _put(con, "2026-01-13", "CA-P-3", "Carol Vineyards")
        _run(con, "r1", "2026-01-06", 2)
        _run(con, "r2", "2026-01-13", 2)
        con.commit()
        con.close()
        return db

    def _add_window2(self, db: Path) -> None:
        con = sqlite3.connect(db)
        _put(con, "2026-01-20", "CA-P-3", "Carol Vineyards")
        _put(con, "2026-01-20", "CA-P-4", "Dana Imports")
        _run(con, "r3", "2026-01-20", 2)
        con.commit()
        con.close()

    def _stamps(self, csv_path: Path):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        body = rows[1:]
        earlier = {r[6] for r in body}
        later = {r[7] for r in body}
        permits = {r[0] for r in body}
        return earlier, later, permits, rows[0], body

    def test_two_windows_page_and_files_advance_together(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "families" / "ttb"
            dest.mkdir(parents=True)
            db = self._db(root)

            code1 = refresh(dest, db=db)
            self.assertEqual(code1, 0)
            page1 = (dest / "index.html").read_text(encoding="utf-8")
            earlier, later, permits, headers, body = self._stamps(dest / "sample.csv")
            js = json.loads((dest / "sample.json").read_text(encoding="utf-8"))
            self.assertEqual(headers[0], "Permit")
            self.assertEqual(js["rows"], body)
            self.assertEqual(earlier, {"6 Jan 2026"})
            self.assertEqual(later, {"13 Jan 2026"})
            self.assertIn("CA-P-3", permits)
            self.assertIn("CA-P-1", permits)
            self.assertIn("6 Jan 2026 → 13 Jan 2026", page1)
            self.assertIn("CA-P-3", page1)
            self.assertIn("CA-P-1", page1)
            self.assertIn("$99", page1)
            self.assertIn("one state or territory", page1)
            self.assertNotIn("20 Jan 2026", page1)

            snapshot = {
                "html": page1,
                "csv": (dest / "sample.csv").read_bytes(),
                "json": (dest / "sample.json").read_bytes(),
            }

            self._add_window2(db)
            slice_ttb.reset_data()
            code2 = refresh(dest, db=db)
            self.assertEqual(code2, 0)
            page2 = (dest / "index.html").read_text(encoding="utf-8")
            earlier, later, permits, _h, body = self._stamps(dest / "sample.csv")
            js = json.loads((dest / "sample.json").read_text(encoding="utf-8"))
            self.assertEqual(js["rows"], body)
            self.assertEqual(earlier, {"13 Jan 2026"})
            self.assertEqual(later, {"20 Jan 2026"})
            self.assertIn("CA-P-4", permits)
            self.assertIn("CA-P-2", permits)
            self.assertNotIn("CA-P-1", permits)
            self.assertIn("13 Jan 2026 → 20 Jan 2026", page2)
            self.assertIn("CA-P-4", page2)
            self.assertIn("CA-P-2", page2)
            self.assertNotIn("6 Jan 2026 → 13 Jan 2026", page2)
            self.assertNotIn("CA-P-1", page2)
            self.assertIn("$99", page2)
            self.assertNotEqual(page2, snapshot["html"])
            self.assertNotEqual((dest / "sample.csv").read_bytes(), snapshot["csv"])

    def test_changed_only_sample_uses_real_writers_and_truth_guard(self):
        import check_site
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self._db(root)
            con = sqlite3.connect(db)
            con.execute("DELETE FROM permit WHERE snapshot_date='2026-01-13'")
            _put(con, "2026-01-13", "CA-P-1", "Alice New Name")
            _put(con, "2026-01-13", "CA-P-2", "Bob Cellars")
            con.commit(); con.close()
            dest = root/'families/ttb'
            self.assertEqual(refresh(dest, db), 0)
            raw = (dest/'index.html').read_text()
            self.assertIn('Alice New Name', raw)
            self.assertIn('Changed fields in the sample', raw)
            with patch.object(check_site, 'ROOT', root):
                check_site.check_ttb_sample_contract()

    def test_missing_source_preserves_accepted_files(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "families" / "ttb"
            dest.mkdir(parents=True)
            html = "<html>accepted-parent</html>"
            csv_text = "Permit,Earlier sealed copy,Later sealed copy\nKEEP,1 Jan 2026,8 Jan 2026\n"
            json_text = '{"rows":[["KEEP"]],"headers":["Permit"]}\n'
            (dest / "index.html").write_text(html, encoding="utf-8")
            (dest / "sample.csv").write_text(csv_text, encoding="utf-8")
            (dest / "sample.json").write_text(json_text, encoding="utf-8")
            missing = Path(td) / "no-such.db"
            err = io.StringIO()
            with redirect_stderr(err):
                code = refresh(dest, db=missing)
            self.assertEqual(code, 2)
            self.assertIn("UNKNOWN", err.getvalue())
            self.assertEqual((dest / "index.html").read_text(encoding="utf-8"), html)
            self.assertEqual((dest / "sample.csv").read_text(encoding="utf-8"), csv_text)
            self.assertEqual((dest / "sample.json").read_text(encoding="utf-8"), json_text)

    def test_unreadable_source_preserves_accepted_files(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "families" / "ttb"
            dest.mkdir(parents=True)
            html = "<html>accepted-parent</html>"
            (dest / "index.html").write_text(html, encoding="utf-8")
            (dest / "sample.csv").write_text("KEEP\n", encoding="utf-8")
            (dest / "sample.json").write_text("{}\n", encoding="utf-8")
            bad = Path(td) / "bad.db"
            bad.write_text("not a sqlite database", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = refresh(dest, db=bad)
            self.assertEqual(code, 2)
            self.assertIn("UNKNOWN", err.getvalue())
            self.assertEqual((dest / "index.html").read_text(encoding="utf-8"), html)
            self.assertEqual((dest / "sample.csv").read_text(encoding="utf-8"), "KEEP\n")


if __name__ == "__main__":
    unittest.main()
