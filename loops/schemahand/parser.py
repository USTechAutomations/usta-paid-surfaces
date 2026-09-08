"""A small, deliberately limited SQL DDL reader.

Reads PostgreSQL or MySQL ``CREATE TABLE`` scripts and builds a plain-data
model of the tables, columns and foreign keys. It is not a general SQL
parser: it understands enough of ``CREATE TABLE`` (schema-qualified and
quoted names, column types with sizes, ``NOT NULL``, ``DEFAULT``, inline and
table-level ``PRIMARY KEY``/``UNIQUE``/``FOREIGN KEY ... REFERENCES``, safely
ignored ``CHECK``), ``COMMENT ON TABLE``/``COMMENT ON COLUMN`` (PostgreSQL),
and ``ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY`` to read the schema
dumps a consultancy would paste in. Anything else is skipped and counted,
never fatal.

The browser tool (``families/schemahand/tool.js``) implements the exact same
algorithm in JavaScript so the two agree on a script.
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = ["SchemaParseError", "parse_sql", "to_mermaid"]


class SchemaParseError(ValueError):
    """Raised when the input holds no CREATE TABLE statements at all."""


# --- tiny character-level helpers, shared by every parse_* function -------

def _is_space(c: str) -> bool:
    return c in " \t\r\n\f\v"


def _is_alpha(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_alnum(c: str) -> bool:
    return c.isalnum() or c == "_"


def _skip_ws(s: str, i: int) -> int:
    n = len(s)
    while i < n and _is_space(s[i]):
        i += 1
    return i


def _peek_word(s: str, i: int):
    """Uppercased bareword at i (after whitespace), or (None, i)."""
    i = _skip_ws(s, i)
    n = len(s)
    j = i
    while j < n and _is_alnum(s[j]):
        j += 1
    if j == i:
        return None, i
    return s[i:j].upper(), j


def _expect_phrase(s: str, i: int, words: list[str]) -> Optional[int]:
    """If the next len(words) barewords match (case-insensitive), return the
    index just past them, else None (no partial consumption on failure)."""
    j = i
    for w in words:
        w2, j2 = _peek_word(s, j)
        if w2 != w:
            return None
        j = j2
    return j


def read_ident(s: str, i: int):
    """One identifier: "quoted", `quoted`, or a bare word. -> (name, next_i)."""
    i = _skip_ws(s, i)
    n = len(s)
    if i >= n:
        return None, i
    c = s[i]
    if c == '"':
        j = i + 1
        chars: list[str] = []
        while j < n:
            if s[j] == '"':
                if j + 1 < n and s[j + 1] == '"':
                    chars.append('"')
                    j += 2
                    continue
                return "".join(chars), j + 1
            chars.append(s[j])
            j += 1
        return "".join(chars), j
    if c == "`":
        j = i + 1
        chars = []
        while j < n and s[j] != "`":
            chars.append(s[j])
            j += 1
        return "".join(chars), min(j + 1, n)
    if _is_alpha(c):
        j = i
        while j < n and _is_alnum(s[j]):
            j += 1
        return s[i:j], j
    return None, i


def read_qualified(s: str, i: int):
    """ident(.ident)* -> (parts, next_i)."""
    parts: list[str] = []
    name, j = read_ident(s, i)
    if name is None:
        return parts, i
    parts.append(name)
    k = _skip_ws(s, j)
    while k < len(s) and s[k] == ".":
        name2, j2 = read_ident(s, k + 1)
        if name2 is None:
            break
        parts.append(name2)
        j = j2
        k = _skip_ws(s, j)
    return parts, j


def read_string(s: str, i: int):
    """A '...' literal (with '' as an escaped quote). -> (text, next_i) or (None, i)."""
    i = _skip_ws(s, i)
    n = len(s)
    if i >= n or s[i] != "'":
        return None, i
    j = i + 1
    chars: list[str] = []
    while j < n:
        if s[j] == "'":
            if j + 1 < n and s[j + 1] == "'":
                chars.append("'")
                j += 2
                continue
            return "".join(chars), j + 1
        chars.append(s[j])
        j += 1
    return "".join(chars), j


def find_matching_paren(s: str, open_i: int) -> int:
    """Index of the ')' matching s[open_i] == '(', or -1."""
    n = len(s)
    depth = 0
    i = open_i
    in_s = in_d = in_b = False
    while i < n:
        c = s[i]
        if in_s:
            if c == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            if c == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            if c == "`":
                in_b = False
            i += 1
            continue
        if c == "'":
            in_s = True
        elif c == '"':
            in_d = True
        elif c == "`":
            in_b = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split s on sep at paren-depth 0, outside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(s)
    in_s = in_d = in_b = False
    while i < n:
        c = s[i]
        if in_s:
            buf.append(c)
            if c == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            buf.append(c)
            if c == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            buf.append(c)
            if c == "`":
                in_b = False
            i += 1
            continue
        if c == "'":
            in_s = True
            buf.append(c)
        elif c == '"':
            in_d = True
            buf.append(c)
        elif c == "`":
            in_b = True
            buf.append(c)
        elif c == "(":
            depth += 1
            buf.append(c)
        elif c == ")":
            depth -= 1
            buf.append(c)
        elif c == sep and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        else:
            buf.append(c)
        i += 1
    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts


def strip_comments(sql: str) -> str:
    """Remove -- line comments and /* block */ comments, honoring quotes."""
    out: list[str] = []
    i, n = 0, len(sql)
    in_s = in_d = in_b = False
    while i < n:
        c = sql[i]
        if in_s:
            out.append(c)
            if c == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            out.append(c)
            if c == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            out.append(c)
            if c == "`":
                in_b = False
            i += 1
            continue
        if c == "'":
            in_s = True
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_d = True
            out.append(c)
            i += 1
            continue
        if c == "`":
            in_b = True
            out.append(c)
            i += 1
            continue
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append(" ")
            i = j
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(" ")
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def split_statements(sql: str) -> list[str]:
    """Split on ';' outside quotes. Assumes comments already stripped."""
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_s = in_d = in_b = False
    while i < n:
        c = sql[i]
        if in_s:
            buf.append(c)
            if c == "'":
                in_s = False
            i += 1
            continue
        if in_d:
            buf.append(c)
            if c == '"':
                in_d = False
            i += 1
            continue
        if in_b:
            buf.append(c)
            if c == "`":
                in_b = False
            i += 1
            continue
        if c == "'":
            in_s = True
            buf.append(c)
        elif c == '"':
            in_d = True
            buf.append(c)
        elif c == "`":
            in_b = True
            buf.append(c)
        elif c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
            i += 1
            continue
        else:
            buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


# --- column list / column-or-constraint parsing ----------------------------

def parse_paren_col_list(s: str, i: int):
    """'(' a, b, c ')' -> (['A','B','C'] as read, next_i). ([], i) if no '(' here."""
    i = _skip_ws(s, i)
    if i >= len(s) or s[i] != "(":
        return [], i
    close = find_matching_paren(s, i)
    if close == -1:
        return [], i
    body = s[i + 1 : close]
    cols = []
    for piece in split_top_level(body, ","):
        name, _ = read_ident(piece, 0)
        if name:
            cols.append(name)
    return cols, close + 1


_TYPE_CONTINUATIONS = {
    "DOUBLE": ["PRECISION"],
    "CHARACTER": ["VARYING"],
}


def _read_type(item: str, i: int):
    tname, i = _peek_word(item, i)
    words = [tname] if tname else []
    if tname == "TIMESTAMP" or tname == "TIME":
        for lead in ("WITH", "WITHOUT"):
            j2 = _expect_phrase(item, i, [lead, "TIME", "ZONE"])
            if j2 is not None:
                words += [lead, "TIME", "ZONE"]
                i = j2
                break
    elif tname in _TYPE_CONTINUATIONS:
        for cont in _TYPE_CONTINUATIONS[tname]:
            j2 = _expect_phrase(item, i, [cont])
            if j2 is not None:
                words.append(cont)
                i = j2
                break
    size = None
    ii = _skip_ws(item, i)
    if ii < len(item) and item[ii] == "(":
        close = find_matching_paren(item, ii)
        if close != -1:
            size = item[ii + 1 : close].strip()
            i = close + 1
    return " ".join(words), size, i


def _read_default_expr(item: str, i: int):
    i = _skip_ws(item, i)
    n = len(item)
    if i < n and item[i] == "'":
        return read_string(item, i)
    name, j = _peek_word(item, i)
    if name is not None:
        j_ws = _skip_ws(item, j)
        if j_ws < n and item[j_ws] == "(":
            close = find_matching_paren(item, j_ws)
            if close != -1:
                return item[i : close + 1], close + 1
        return item[i:j], j
    j2 = i
    while j2 < n and not _is_space(item[j2]) and item[j2] not in "(),":
        j2 += 1
    return item[i:j2], j2


def parse_column_def(item: str) -> Optional[dict]:
    name, i = read_ident(item, 0)
    if name is None:
        return None
    type_str, size, i = _read_type(item, i)
    col = {
        "name": name,
        "type": type_str,
        "size": size,
        "not_null": False,
        "default": None,
        "pk": False,
        "unique": False,
        "fk": None,
    }
    pos = i
    n = len(item)
    guard = 0
    while pos < n and guard < 64:
        guard += 1
        w, j = _peek_word(item, pos)
        if w is None:
            break
        if w == "NOT":
            j2 = _expect_phrase(item, pos, ["NOT", "NULL"])
            if j2 is not None:
                col["not_null"] = True
                pos = j2
                continue
            pos = j
            continue
        if w == "NULL":
            pos = j
            continue
        if w == "DEFAULT":
            expr, j2 = _read_default_expr(item, j)
            col["default"] = expr
            pos = j2
            continue
        if w == "PRIMARY":
            j2 = _expect_phrase(item, pos, ["PRIMARY", "KEY"])
            col["pk"] = True
            pos = j2 if j2 is not None else j
            continue
        if w == "UNIQUE":
            col["unique"] = True
            pos = j
            continue
        if w == "REFERENCES":
            parts, k2 = read_qualified(item, j)
            ref_schema, ref_table = (
                (parts[0], parts[1]) if len(parts) >= 2 else (None, parts[0] if parts else None)
            )
            ref_cols, k3 = parse_paren_col_list(item, k2)
            col["fk"] = {"ref_schema": ref_schema, "ref_table": ref_table, "ref_columns": ref_cols}
            pos = k3
            continue
        if w == "COMMENT":
            text, j2 = read_string(item, j)
            if text is None:
                break  # COMMENT without a string literal: stop scanning this column
            pos = j2
            continue
        if w in ("AUTO_INCREMENT", "AUTOINCREMENT", "SERIAL", "UNSIGNED", "ZEROFILL", "COLLATE"):
            pos = j
            if w == "COLLATE":
                _, pos = read_ident(item, j)
            continue
        if w == "GENERATED":
            pos = n
            continue
        break
    return col


def parse_column_or_constraint(item: str, table_pk: list, table_fks: list, table_uniques: list) -> None:
    w, j = _peek_word(item, 0)
    if w == "CONSTRAINT":
        _, j2 = read_ident(item, j)
        rest = item[j2:]
        parse_column_or_constraint(rest, table_pk, table_fks, table_uniques)
        return
    if w == "PRIMARY":
        j2 = _expect_phrase(item, 0, ["PRIMARY", "KEY"])
        if j2 is not None:
            cols, _ = parse_paren_col_list(item, j2)
            for c in cols:
                if c not in table_pk:
                    table_pk.append(c)
        return
    if w == "UNIQUE":
        cols, _ = parse_paren_col_list(item, j)
        if cols:
            table_uniques.append(cols)
        return
    if w == "FOREIGN":
        j2 = _expect_phrase(item, 0, ["FOREIGN", "KEY"])
        if j2 is not None:
            cols, after = parse_paren_col_list(item, j2)
            w2, k = _peek_word(item, after)
            if w2 == "REFERENCES":
                parts, k2 = read_qualified(item, k)
                ref_schema, ref_table = (
                    (parts[0], parts[1]) if len(parts) >= 2 else (None, parts[0] if parts else None)
                )
                ref_cols, _k3 = parse_paren_col_list(item, k2)
                table_fks.append(
                    {"columns": cols, "ref_schema": ref_schema, "ref_table": ref_table, "ref_columns": ref_cols}
                )
        return
    if w in ("CHECK", "KEY", "INDEX"):
        return  # ignored safely: not modelled, never fatal
    return


# --- statement-level parsing ------------------------------------------------

def parse_create_table(stmt: str) -> Optional[dict]:
    w, i = _peek_word(stmt, 0)
    if w != "CREATE":
        return None
    w, i = _peek_word(stmt, i)
    if w != "TABLE":
        return None
    j2 = _expect_phrase(stmt, i, ["IF", "NOT", "EXISTS"])
    if j2 is not None:
        i = j2
    parts, i = read_qualified(stmt, i)
    if not parts:
        return None
    schema, name = (parts[0], parts[1]) if len(parts) >= 2 else (None, parts[0])
    ii = _skip_ws(stmt, i)
    if ii >= len(stmt) or stmt[ii] != "(":
        return None  # e.g. CREATE TABLE ... AS SELECT: unsupported, treated as unknown
    close = find_matching_paren(stmt, ii)
    if close == -1:
        return None
    body = stmt[ii + 1 : close]
    items = split_top_level(body, ",")
    columns = []
    table_pk: list = []
    table_fks: list = []
    table_uniques: list = []
    for item in items:
        if not item.strip():
            continue
        w0, _ = _peek_word(item, 0)
        if w0 in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "KEY", "INDEX"):
            parse_column_or_constraint(item, table_pk, table_fks, table_uniques)
        else:
            col = parse_column_def(item)
            if col:
                columns.append(col)
    for c in columns:
        if c["pk"] and c["name"] not in table_pk:
            table_pk.append(c["name"])
    return {
        "schema": schema,
        "name": name,
        "columns": columns,
        "pk": table_pk,
        "unique": table_uniques,
        "fks": table_fks,
        "comment": None,
        "column_comments": {},
    }


def parse_alter_add_fk(stmt: str) -> Optional[dict]:
    w, i = _peek_word(stmt, 0)
    if w != "ALTER":
        return None
    w, i = _peek_word(stmt, i)
    if w != "TABLE":
        return None
    j2 = _expect_phrase(stmt, i, ["ONLY"])
    if j2 is not None:
        i = j2
    parts, i = read_qualified(stmt, i)
    if not parts:
        return None
    schema, name = (parts[0], parts[1]) if len(parts) >= 2 else (None, parts[0])
    w, i = _peek_word(stmt, i)
    if w != "ADD":
        return None
    w, i = _peek_word(stmt, i)
    if w == "CONSTRAINT":
        _, i = read_ident(stmt, i)
        w, i = _peek_word(stmt, i)
    if w != "FOREIGN":
        return None
    w, i = _peek_word(stmt, i)
    if w != "KEY":
        return None
    cols, i = parse_paren_col_list(stmt, i)
    w, i = _peek_word(stmt, i)
    if w != "REFERENCES":
        return None
    parts2, i = read_qualified(stmt, i)
    if not parts2:
        return None
    ref_schema, ref_table = (parts2[0], parts2[1]) if len(parts2) >= 2 else (None, parts2[0])
    ref_cols, i = parse_paren_col_list(stmt, i)
    return {
        "from_schema": schema,
        "from_table": name,
        "from_columns": cols,
        "to_schema": ref_schema,
        "to_table": ref_table,
        "to_columns": ref_cols,
    }


def parse_comment(stmt: str) -> Optional[dict]:
    w, i = _peek_word(stmt, 0)
    if w != "COMMENT":
        return None
    w, i = _peek_word(stmt, i)
    if w != "ON":
        return None
    w, i = _peek_word(stmt, i)
    if w == "TABLE":
        parts, i = read_qualified(stmt, i)
        if not parts:
            return None
        schema, table = (parts[0], parts[1]) if len(parts) >= 2 else (None, parts[0])
        w2, i2 = _peek_word(stmt, i)
        if w2 != "IS":
            return None
        text, _i3 = read_string(stmt, i2)
        return {"kind": "table", "schema": schema, "table": table, "text": text}
    if w == "COLUMN":
        parts, i = read_qualified(stmt, i)
        if len(parts) == 3:
            schema, table, column = parts
        elif len(parts) == 2:
            schema, table, column = None, parts[0], parts[1]
        else:
            return None
        w2, i2 = _peek_word(stmt, i)
        if w2 != "IS":
            return None
        text, _i3 = read_string(stmt, i2)
        return {"kind": "column", "schema": schema, "table": table, "column": column, "text": text}
    return None


def _resolve_table_key(tables: dict, schema: Optional[str], name: str):
    if (schema, name) in tables:
        return (schema, name)
    for key in tables:
        if key[1] == name:
            return key
    return None


def parse_sql(text: str) -> dict:
    """Parse a CREATE TABLE script into a plain-data model.

    Raises SchemaParseError if the input holds no CREATE TABLE statements.
    """
    cleaned = strip_comments(text)
    stmts = split_statements(cleaned)

    tables: dict = {}
    order: list = []
    fks: list = []
    unknown = 0
    comments_table = []
    comments_column = []

    for stmt in stmts:
        t = parse_create_table(stmt)
        if t is not None:
            key = (t["schema"], t["name"])
            tables[key] = t
            order.append(key)
            continue
        alt = parse_alter_add_fk(stmt)
        if alt is not None:
            fks.append(alt)
            continue
        c = parse_comment(stmt)
        if c is not None:
            (comments_table if c["kind"] == "table" else comments_column).append(c)
            continue
        unknown += 1

    for key in order:
        t = tables[key]
        for c in t["columns"]:
            if c["fk"]:
                fks.append(
                    {
                        "from_schema": t["schema"],
                        "from_table": t["name"],
                        "from_columns": [c["name"]],
                        "to_schema": c["fk"]["ref_schema"],
                        "to_table": c["fk"]["ref_table"],
                        "to_columns": c["fk"]["ref_columns"],
                    }
                )
        for f in t["fks"]:
            fks.append(
                {
                    "from_schema": t["schema"],
                    "from_table": t["name"],
                    "from_columns": f["columns"],
                    "to_schema": f.get("ref_schema"),
                    "to_table": f.get("ref_table"),
                    "to_columns": f.get("ref_columns"),
                }
            )

    for c in comments_table:
        key = _resolve_table_key(tables, c["schema"], c["table"])
        if key:
            tables[key]["comment"] = c["text"]
    for c in comments_column:
        key = _resolve_table_key(tables, c["schema"], c["table"])
        if key:
            tables[key]["column_comments"][c["column"]] = c["text"]

    if not tables:
        raise SchemaParseError("This does not look like SQL")

    schemas = sorted({t["schema"] for t in tables.values() if t["schema"]})
    return {
        "tables": [tables[k] for k in order],
        "foreign_keys": fks,
        "schemas": schemas,
        "unknown_statements": unknown,
    }


def _mermaid_label(schema: Optional[str], name: str) -> str:
    raw = f"{schema}_{name}" if schema else name
    return re.sub(r"[^A-Za-z0-9_]", "_", raw).upper()


def to_mermaid(model: dict) -> str:
    """Render the model as a Mermaid erDiagram string."""
    lines = ["erDiagram"]
    for t in model["tables"]:
        label = _mermaid_label(t["schema"], t["name"])
        lines.append(f"    {label} {{")
        for c in t["columns"]:
            base_type = (c["type"] or "text").split(" ")[0].lower() or "text"
            tags = []
            if c["pk"] or c["name"] in t["pk"]:
                tags.append("PK")
            if c["fk"]:
                tags.append("FK")
            tag_str = " " + ",".join(tags) if tags else ""
            lines.append(f"        {base_type} {c['name']}{tag_str}")
        lines.append("    }")
    for fk in model["foreign_keys"]:
        if not fk.get("to_table"):
            continue
        a = _mermaid_label(fk.get("to_schema"), fk["to_table"])
        b = _mermaid_label(fk.get("from_schema"), fk["from_table"])
        lines.append(f'    {a} ||--o{{ {b} : "fk"')
    return "\n".join(lines)
