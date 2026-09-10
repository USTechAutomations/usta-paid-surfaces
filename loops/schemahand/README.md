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
node loops/schemahand/tests/test_export.js
bash loops/schemahand/SMOKE.sh
```

The browser tool (`families/schemahand/tool.js`) implements the exact same
parsing algorithm in plain JavaScript, so both sides agree on every fixture.
`test_export.js` also keeps long ASCII and Unicode identities in free and paid
saved HTML, including their intrinsic diagram width. The visual geometry and
native-scroll check uses the canonical private browser and is kept with the
release acceptance evidence because it needs that browser runtime rather than
an extra package dependency. That browser check includes real mouse click,
normal drag, ordinary wheel, and releasing outside the SVG before a drag starts;
the last case must not resume a stale pan when the pointer returns.

## The paid handoff package

The command-line reader above is free and MIT-licensed. The in-browser tool
at <https://ustechautomations.com/feeds/schemahand> is also free to use. A
one-time payment of **$199 for 12 months** unlocks the "handoff package"
export from that page: an HTML diagram with editable notes,
printable table views, and a CSV data dictionary — the parts a
consultancy actually hands to a client. Buy it at
<https://ustechautomations.com/feeds/schemahand>. Before buying, download the page’s
synthetic worked example. It is a deterministic ZIP generated from the public
fixture, with `source.sql`, a paid-format `handoff.html`, `dictionary.csv`, and
`manifest.json`; it contains no customer, order, or destination-import data.
The tool parses SQL locally in the browser and does not connect to a database.

Regenerate and check that example with:

```bash
node loops/schemahand/generate_sample_handoff.js
node loops/schemahand/tests/test_sample_handoff.js
```

## License

MIT. See the rest of this repository for the license file.


## Export and current paid access (source acceptance, 2026-09-10)

The browser requires an affirmative SchemaHand annual response when unlocking and
checks current paid authority again for every paid export. Refused or unavailable
evidence preserves the pasted schema and hides the paid action. A downloaded file
is a local snapshot: it remains readable after key expiry or a later refund. This
client-side feature gate is not DRM; public JavaScript is not a tamper-proof license
boundary. Server recovery and verification enforce their own provider authority.

Paid HTML contains the diagram, editable table/column notes and printable table
views. Save edited copy serializes notes into the downloaded HTML; reopening it
restores the notes without changing schema identifiers or relationships. The free
HTML has no notes editor. Printable views escape identifiers, types, SQL comments
and edited notes. Large tables may span printed pages. CSV remains a dictionary
of the parsed SQL, including its SQL comments; later HTML note edits do not rewrite
the separately downloaded CSV. The paid document omits the promotional footer and
retains a quiet document footer.

Downloads reference the existing shared stylesheet/Satoshi. With no network,
browser-native Canvas colors and system-ui keep the document usable; no second
font or theme palette is embedded. SQL and notes are not submitted by the export.
Relationship diagrams retain their natural dimensions and scroll within the page;
notes use native keyboard-operable details/textarea controls.

Focused Node regression: `node loops/schemahand/tests/test_export.js`. The
reconciliation acceptance artifact records actual local HTTP/browser source hashes,
12 viewport/theme combinations, an independent Python parser/CSV comparison,
refund-after-unlock denial and inert malicious notes after save/reopen. It is
synthetic acceptance, not a production purchase or evidence of customer demand.

CSV export refuses a field starting with a spreadsheet formula marker or control
character. Quoting a CSV cell does not make it a typed text cell; no identifier is
prefixed or silently changed. The safe HTML remains available with exact original
data. A download request is reported only if Blob/URL/anchor initiation succeeds;
the browser/OS can still block saving without exposing completion to the page.
Edited notes update the printable view immediately as well as the saved copy.
