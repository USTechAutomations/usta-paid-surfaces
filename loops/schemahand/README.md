# schemahand

Paste a PostgreSQL or MySQL `CREATE TABLE` script, get back a plain-data model
of the schema (tables, columns, primary keys, foreign keys, comments) as JSON
or as a [Mermaid](https://mermaid.js.org/) `erDiagram`. Useful for anyone
handing a database schema to someone else: a consultancy handing work to a
client's developers, a new hire reading an unfamiliar codebase, or a
changelog that wants to show what a migration actually did.

This repository holds the command-line reader. There is also a free,
in-browser diagram tool (no install, no account) at
**<https://ustechautomations.com/feeds/schemahand>** — paste a schema there
to get an interactive, pannable diagram with a search box and per-table
notes, and to download it as one self-contained HTML file you can hand off.

## Install

```bash
pip install git+https://github.com/USTechAutomations/schemahand
```

(This is a placeholder install command for the public package; if it does
not yet resolve, clone this repository and run the module directly — see
below.)

## Use

```bash
python3 -m loops.schemahand.cli schema.sql
python3 -m loops.schemahand.cli schema.sql --format mermaid
```

`schema.sql` is any file holding one or more `CREATE TABLE` statements
(PostgreSQL or MySQL). The default output is a JSON model:

```json
{
  "tables": [
    {"schema": "app", "name": "customers", "columns": [...], "pk": ["id"], "fks": [], "comment": null}
  ],
  "foreign_keys": [
    {"from_schema": "app", "from_table": "orders", "from_columns": ["customer_id"],
     "to_schema": "app", "to_table": "customers", "to_columns": ["id"]}
  ],
  "schemas": ["app"],
  "unknown_statements": 0
}
```

Anything that is not a `CREATE TABLE`, `ALTER TABLE ... ADD CONSTRAINT ...
FOREIGN KEY`, or (PostgreSQL) `COMMENT ON TABLE`/`COMMENT ON COLUMN`
statement is skipped and counted in `unknown_statements` — it is never
fatal. A file with no `CREATE TABLE` statements at all is refused with
`This does not look like SQL` and a non-zero exit code, so a bad paste never
produces a silent, empty result.

## What it understands

- Schema-qualified and quoted names (`"my_schema"."My Table"`, `` `my_table` ``).
- Column types with sizes: `VARCHAR(120)`, `NUMERIC(10,2)`, `DOUBLE PRECISION`,
  `TIMESTAMP WITH/WITHOUT TIME ZONE`.
- `NOT NULL`, `DEFAULT` (literals and function calls like `now()`).
- `PRIMARY KEY` and `UNIQUE`, inline or table-level, single or composite.
- `FOREIGN KEY ... REFERENCES ...`, inline or table-level.
- `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ...` (the common way
  `pg_dump` writes foreign keys after every table exists).
- `CHECK (...)` is read and safely ignored — it never breaks the parse.
- MySQL backtick identifiers, `AUTO_INCREMENT`, and a trailing
  `ENGINE=... DEFAULT CHARSET=...` clause are ignored.

It is not a general SQL engine and does not run your schema anywhere; it
only reads `CREATE TABLE` and the handful of statements above.

## Tests

```bash
python3 -m unittest loops.schemahand.tests.test_cli -v
node loops/schemahand/tests/test_tool.js
bash loops/schemahand/SMOKE.sh
```

The browser tool (`families/schemahand/tool.js`) implements the exact same
parsing algorithm in plain JavaScript, so both sides agree on every fixture.

## The paid handoff package

The command-line reader above is free and MIT-licensed. The in-browser tool
at <https://ustechautomations.com/feeds/schemahand> is also free to use. A
one-time payment of **$199 for 12 months** unlocks the "handoff package"
export from that page: an editable copy of the diagram with your notes kept,
a printable one-page-per-table view, and a CSV data dictionary — the parts a
consultancy actually hands to a client. Buy it at
<https://ustechautomations.com/feeds/schemahand>.

## License

MIT. See the rest of this repository for the license file.
