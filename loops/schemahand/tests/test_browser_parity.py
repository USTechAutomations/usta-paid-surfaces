"""Browser parser must match the three Python hardening contracts.

Runs the exported Node parseSQL and the Python parser against independent
expected values (not merely JS-equals-Python).
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from loops.schemahand import parser as sh

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "families" / "schemahand" / "tool.js"

NODE_RUNNER = r"""
'use strict';
const fs = require('fs');
global.window = global.window || {};
global.Image = global.Image || function Image() { this.src = ''; };
global.document = global.document || {
  readyState: 'complete',
  addEventListener: function () {},
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () {
    return { style: {}, classList: { toggle: function () {} }, setAttribute: function () {}, appendChild: function () {}, addEventListener: function () {} };
  },
  createElementNS: function () {
    return { setAttribute: function () {}, appendChild: function () {}, addEventListener: function () {} };
  },
  body: { appendChild: function () {}, removeChild: function () {} },
};
const toolPath = process.env.SCHEMAHAND_TOOL;
const sql = fs.readFileSync(0, 'utf8');
const mod = require(toolPath);
process.stdout.write(JSON.stringify(mod.parseSQL(sql)));
"""


def parse_browser(sql: str) -> dict:
    env = os.environ.copy()
    env["SCHEMAHAND_TOOL"] = str(TOOL)
    proc = subprocess.run(
        ["node", "-e", NODE_RUNNER],
        input=sql,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "browser parseSQL exited %s stderr=%r stdout=%r"
            % (proc.returncode, proc.stderr, proc.stdout)
        )
    return json.loads(proc.stdout)


UNIQUE_SQL = """
        CREATE TABLE users (
          id INT NOT NULL,
          email VARCHAR(190) NOT NULL,
          handle VARCHAR(60) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY `uq_users_email` (`email`),
          UNIQUE INDEX uq_users_handle (handle)
        );
        CREATE TABLE t2 (
          a INT,
          b INT,
          UNIQUE (a, b)
        );
        """

DECIMAL_SQL = """
        CREATE TABLE products (
          id INTEGER PRIMARY KEY,
          price NUMERIC(10,2) NOT NULL DEFAULT 9.99,
          tax NUMERIC(10,2) DEFAULT 0.00 NOT NULL,
          qty INTEGER NOT NULL DEFAULT 0
        );
        """

BACKTICK_SQL = """
        CREATE TABLE t (
          `we``ird` INT NOT NULL,
          b INT
        );
        """


class TestBrowserParityUnique(unittest.TestCase):
    def test_mysql_named_unique_key_and_index(self) -> None:
        py = sh.parse_sql(UNIQUE_SQL)
        js = parse_browser(UNIQUE_SQL)
        for model, label in ((py, "python"), (js, "browser")):
            users = next(t for t in model["tables"] if t["name"] == "users")
            t2 = next(t for t in model["tables"] if t["name"] == "t2")
            self.assertEqual(
                users["unique"],
                [["email"], ["handle"]],
                "%s users.unique" % label,
            )
            self.assertEqual(t2["unique"], [["a", "b"]], "%s t2.unique" % label)


class TestBrowserParityDecimal(unittest.TestCase):
    def test_decimal_default_literal_and_following_not_null(self) -> None:
        py = sh.parse_sql(DECIMAL_SQL)
        js = parse_browser(DECIMAL_SQL)
        for model, label in ((py, "python"), (js, "browser")):
            cols = {c["name"]: c for c in model["tables"][0]["columns"]}
            self.assertEqual(cols["price"]["default"], "9.99", "%s price.default" % label)
            self.assertTrue(cols["price"]["not_null"], "%s price.not_null" % label)
            self.assertEqual(cols["tax"]["default"], "0.00", "%s tax.default" % label)
            self.assertTrue(cols["tax"]["not_null"], "%s tax.not_null" % label)
            self.assertEqual(cols["qty"]["default"], "0", "%s qty.default" % label)
            self.assertTrue(cols["qty"]["not_null"], "%s qty.not_null" % label)


class TestBrowserParityBackticks(unittest.TestCase):
    def test_mysql_doubled_backtick_identifier(self) -> None:
        py = sh.parse_sql(BACKTICK_SQL)
        js = parse_browser(BACKTICK_SQL)
        for model, label in ((py, "python"), (js, "browser")):
            names = [c["name"] for c in model["tables"][0]["columns"]]
            self.assertEqual(names, ["we`ird", "b"], "%s column names" % label)
            weird = model["tables"][0]["columns"][0]
            self.assertEqual(weird["type"], "INT", "%s type" % label)
            self.assertTrue(weird["not_null"], "%s not_null" % label)


if __name__ == "__main__":
    unittest.main()
