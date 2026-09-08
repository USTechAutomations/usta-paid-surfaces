/*
 * schemahand -- paste a CREATE TABLE script, get an interactive diagram.
 *
 * This file is a plain script: no build step, no bundler, no third-party
 * library. It runs two things:
 *
 *   1. A pure parser, parseSQL(text), that reads PostgreSQL or MySQL
 *      CREATE TABLE scripts into a plain-data model. It is a deliberate
 *      port of loops/schemahand/parser.py -- same algorithm, same
 *      function names, so the two agree on a script. It never touches the
 *      page and never touches the network.
 *   2. A small browser UI (SVG renderer, pan/zoom, side panel, search,
 *      annotations, export) that only runs when a real document exists.
 *
 * The single network call this file ever makes is the pro-key check, and
 * only when the person on the page clicks "Unlock handoff package".
 */
(function () {
  "use strict";

  // ===========================================================================
  // 1. PURE PARSER -- must not read window/document/navigator/fetch/etc.
  // ===========================================================================

  function SchemaParseError(message) {
    this.name = "SchemaParseError";
    this.message = message;
  }
  SchemaParseError.prototype = Object.create(Error.prototype);

  function isSpace(c) {
    return c === " " || c === "\t" || c === "\r" || c === "\n" || c === "\f" || c === "\v";
  }
  function isAlpha(c) {
    return (c >= "a" && c <= "z") || (c >= "A" && c <= "Z") || c === "_";
  }
  function isAlnum(c) {
    return isAlpha(c) || (c >= "0" && c <= "9");
  }

  function skipWs(s, i) {
    const n = s.length;
    while (i < n && isSpace(s[i])) i++;
    return i;
  }

  function peekWord(s, i) {
    i = skipWs(s, i);
    const n = s.length;
    let j = i;
    while (j < n && isAlnum(s[j])) j++;
    if (j === i) return [null, i];
    return [s.slice(i, j).toUpperCase(), j];
  }

  function expectPhrase(s, i, words) {
    let j = i;
    for (let k = 0; k < words.length; k++) {
      const r = peekWord(s, j);
      if (r[0] !== words[k]) return null;
      j = r[1];
    }
    return j;
  }

  function readIdent(s, i) {
    i = skipWs(s, i);
    const n = s.length;
    if (i >= n) return [null, i];
    const c = s[i];
    if (c === '"') {
      let j = i + 1;
      const chars = [];
      while (j < n) {
        if (s[j] === '"') {
          if (j + 1 < n && s[j + 1] === '"') {
            chars.push('"');
            j += 2;
            continue;
          }
          return [chars.join(""), j + 1];
        }
        chars.push(s[j]);
        j++;
      }
      return [chars.join(""), j];
    }
    if (c === "`") {
      let j = i + 1;
      const chars = [];
      while (j < n && s[j] !== "`") {
        chars.push(s[j]);
        j++;
      }
      return [chars.join(""), Math.min(j + 1, n)];
    }
    if (isAlpha(c)) {
      let j = i;
      while (j < n && isAlnum(s[j])) j++;
      return [s.slice(i, j), j];
    }
    return [null, i];
  }

  function readQualified(s, i) {
    const parts = [];
    let r = readIdent(s, i);
    if (r[0] === null) return [parts, i];
    parts.push(r[0]);
    let j = r[1];
    let k = skipWs(s, j);
    while (k < s.length && s[k] === ".") {
      const r2 = readIdent(s, k + 1);
      if (r2[0] === null) break;
      parts.push(r2[0]);
      j = r2[1];
      k = skipWs(s, j);
    }
    return [parts, j];
  }

  function readString(s, i) {
    i = skipWs(s, i);
    const n = s.length;
    if (i >= n || s[i] !== "'") return [null, i];
    let j = i + 1;
    const chars = [];
    while (j < n) {
      if (s[j] === "'") {
        if (j + 1 < n && s[j + 1] === "'") {
          chars.push("'");
          j += 2;
          continue;
        }
        return [chars.join(""), j + 1];
      }
      chars.push(s[j]);
      j++;
    }
    return [chars.join(""), j];
  }

  function findMatchingParen(s, openI) {
    const n = s.length;
    let depth = 0;
    let i = openI;
    let inS = false, inD = false, inB = false;
    while (i < n) {
      const c = s[i];
      if (inS) {
        if (c === "'") inS = false;
        i++;
        continue;
      }
      if (inD) {
        if (c === '"') inD = false;
        i++;
        continue;
      }
      if (inB) {
        if (c === "`") inB = false;
        i++;
        continue;
      }
      if (c === "'") inS = true;
      else if (c === '"') inD = true;
      else if (c === "`") inB = true;
      else if (c === "(") depth++;
      else if (c === ")") {
        depth--;
        if (depth === 0) return i;
      }
      i++;
    }
    return -1;
  }

  function splitTopLevel(s, sep) {
    sep = sep || ",";
    const parts = [];
    let buf = [];
    let depth = 0;
    let i = 0;
    const n = s.length;
    let inS = false, inD = false, inB = false;
    while (i < n) {
      const c = s[i];
      if (inS) {
        buf.push(c);
        if (c === "'") inS = false;
        i++;
        continue;
      }
      if (inD) {
        buf.push(c);
        if (c === '"') inD = false;
        i++;
        continue;
      }
      if (inB) {
        buf.push(c);
        if (c === "`") inB = false;
        i++;
        continue;
      }
      if (c === "'") {
        inS = true;
        buf.push(c);
      } else if (c === '"') {
        inD = true;
        buf.push(c);
      } else if (c === "`") {
        inB = true;
        buf.push(c);
      } else if (c === "(") {
        depth++;
        buf.push(c);
      } else if (c === ")") {
        depth--;
        buf.push(c);
      } else if (c === sep && depth === 0) {
        parts.push(buf.join("").trim());
        buf = [];
        i++;
        continue;
      } else {
        buf.push(c);
      }
      i++;
    }
    const last = buf.join("").trim();
    if (last) parts.push(last);
    return parts;
  }

  function stripComments(sql) {
    const out = [];
    let i = 0;
    const n = sql.length;
    let inS = false, inD = false, inB = false;
    while (i < n) {
      const c = sql[i];
      if (inS) {
        out.push(c);
        if (c === "'") inS = false;
        i++;
        continue;
      }
      if (inD) {
        out.push(c);
        if (c === '"') inD = false;
        i++;
        continue;
      }
      if (inB) {
        out.push(c);
        if (c === "`") inB = false;
        i++;
        continue;
      }
      if (c === "'") {
        inS = true;
        out.push(c);
        i++;
        continue;
      }
      if (c === '"') {
        inD = true;
        out.push(c);
        i++;
        continue;
      }
      if (c === "`") {
        inB = true;
        out.push(c);
        i++;
        continue;
      }
      if (c === "-" && i + 1 < n && sql[i + 1] === "-") {
        let j = sql.indexOf("\n", i);
        j = j === -1 ? n : j;
        out.push(" ");
        i = j;
        continue;
      }
      if (c === "/" && i + 1 < n && sql[i + 1] === "*") {
        let j = sql.indexOf("*/", i + 2);
        j = j === -1 ? n : j + 2;
        out.push(" ");
        i = j;
        continue;
      }
      out.push(c);
      i++;
    }
    return out.join("");
  }

  function splitStatements(sql) {
    const stmts = [];
    let buf = [];
    let i = 0;
    const n = sql.length;
    let inS = false, inD = false, inB = false;
    while (i < n) {
      const c = sql[i];
      if (inS) {
        buf.push(c);
        if (c === "'") inS = false;
        i++;
        continue;
      }
      if (inD) {
        buf.push(c);
        if (c === '"') inD = false;
        i++;
        continue;
      }
      if (inB) {
        buf.push(c);
        if (c === "`") inB = false;
        i++;
        continue;
      }
      if (c === "'") {
        inS = true;
        buf.push(c);
      } else if (c === '"') {
        inD = true;
        buf.push(c);
      } else if (c === "`") {
        inB = true;
        buf.push(c);
      } else if (c === ";") {
        const stmt = buf.join("").trim();
        if (stmt) stmts.push(stmt);
        buf = [];
        i++;
        continue;
      } else {
        buf.push(c);
      }
      i++;
    }
    const tail = buf.join("").trim();
    if (tail) stmts.push(tail);
    return stmts;
  }

  function parseParenColList(s, i) {
    i = skipWs(s, i);
    if (i >= s.length || s[i] !== "(") return [[], i];
    const close = findMatchingParen(s, i);
    if (close === -1) return [[], i];
    const body = s.slice(i + 1, close);
    const cols = [];
    const pieces = splitTopLevel(body, ",");
    for (let k = 0; k < pieces.length; k++) {
      const r = readIdent(pieces[k], 0);
      if (r[0]) cols.push(r[0]);
    }
    return [cols, close + 1];
  }

  const TYPE_CONTINUATIONS = { DOUBLE: ["PRECISION"], CHARACTER: ["VARYING"] };

  function readType(item, i) {
    const r = peekWord(item, i);
    const tname = r[0];
    i = r[1];
    const words = tname ? [tname] : [];
    if (tname === "TIMESTAMP" || tname === "TIME") {
      const leads = ["WITH", "WITHOUT"];
      for (let k = 0; k < leads.length; k++) {
        const j2 = expectPhrase(item, i, [leads[k], "TIME", "ZONE"]);
        if (j2 !== null) {
          words.push(leads[k], "TIME", "ZONE");
          i = j2;
          break;
        }
      }
    } else if (Object.prototype.hasOwnProperty.call(TYPE_CONTINUATIONS, tname)) {
      const conts = TYPE_CONTINUATIONS[tname];
      for (let k = 0; k < conts.length; k++) {
        const j2 = expectPhrase(item, i, [conts[k]]);
        if (j2 !== null) {
          words.push(conts[k]);
          i = j2;
          break;
        }
      }
    }
    let size = null;
    const ii = skipWs(item, i);
    if (ii < item.length && item[ii] === "(") {
      const close = findMatchingParen(item, ii);
      if (close !== -1) {
        size = item.slice(ii + 1, close).trim();
        i = close + 1;
      }
    }
    return [words.join(" "), size, i];
  }

  function readDefaultExpr(item, i) {
    i = skipWs(item, i);
    const n = item.length;
    if (i < n && item[i] === "'") return readString(item, i);
    const r = peekWord(item, i);
    const name = r[0];
    let j = r[1];
    if (name !== null) {
      const jWs = skipWs(item, j);
      if (jWs < n && item[jWs] === "(") {
        const close = findMatchingParen(item, jWs);
        if (close !== -1) return [item.slice(i, close + 1), close + 1];
      }
      return [item.slice(i, j), j];
    }
    let j2 = i;
    while (j2 < n && !isSpace(item[j2]) && "(),".indexOf(item[j2]) === -1) j2++;
    return [item.slice(i, j2), j2];
  }

  function parseColumnDef(item) {
    const r0 = readIdent(item, 0);
    const name = r0[0];
    if (name === null) return null;
    let i = r0[1];
    const t = readType(item, i);
    const col = {
      name: name, type: t[0], size: t[1], not_null: false,
      default: null, pk: false, unique: false, fk: null,
    };
    i = t[2];
    let pos = i;
    const n = item.length;
    let guard = 0;
    while (pos < n && guard < 64) {
      guard++;
      const wr = peekWord(item, pos);
      const w = wr[0], j = wr[1];
      if (w === null) break;
      if (w === "NOT") {
        const j2 = expectPhrase(item, pos, ["NOT", "NULL"]);
        if (j2 !== null) {
          col.not_null = true;
          pos = j2;
          continue;
        }
        pos = j;
        continue;
      }
      if (w === "NULL") {
        pos = j;
        continue;
      }
      if (w === "DEFAULT") {
        const dr = readDefaultExpr(item, j);
        col.default = dr[0];
        pos = dr[1];
        continue;
      }
      if (w === "PRIMARY") {
        const j2 = expectPhrase(item, pos, ["PRIMARY", "KEY"]);
        col.pk = true;
        pos = j2 !== null ? j2 : j;
        continue;
      }
      if (w === "UNIQUE") {
        col.unique = true;
        pos = j;
        continue;
      }
      if (w === "REFERENCES") {
        const qr = readQualified(item, j);
        const parts = qr[0];
        const refSchema = parts.length >= 2 ? parts[0] : null;
        const refTable = parts.length >= 2 ? parts[1] : (parts.length ? parts[0] : null);
        const cr = parseParenColList(item, qr[1]);
        col.fk = { ref_schema: refSchema, ref_table: refTable, ref_columns: cr[0] };
        pos = cr[1];
        continue;
      }
      if (w === "COMMENT") {
        const sr = readString(item, j);
        if (sr[0] === null) break;
        pos = sr[1];
        continue;
      }
      if (w === "AUTO_INCREMENT" || w === "AUTOINCREMENT" || w === "SERIAL" ||
          w === "UNSIGNED" || w === "ZEROFILL" || w === "COLLATE") {
        if (w === "COLLATE") {
          const ir = readIdent(item, j);
          pos = ir[1];
        } else {
          pos = j;
        }
        continue;
      }
      if (w === "GENERATED") {
        pos = n;
        continue;
      }
      break;
    }
    return col;
  }

  function parseColumnOrConstraint(item, tablePk, tableFks, tableUniques) {
    const wr = peekWord(item, 0);
    const w = wr[0], j = wr[1];
    if (w === "CONSTRAINT") {
      const ir = readIdent(item, j);
      parseColumnOrConstraint(item.slice(ir[1]), tablePk, tableFks, tableUniques);
      return;
    }
    if (w === "PRIMARY") {
      const j2 = expectPhrase(item, 0, ["PRIMARY", "KEY"]);
      if (j2 !== null) {
        const cr = parseParenColList(item, j2);
        for (let k = 0; k < cr[0].length; k++) {
          if (tablePk.indexOf(cr[0][k]) === -1) tablePk.push(cr[0][k]);
        }
      }
      return;
    }
    if (w === "UNIQUE") {
      const cr = parseParenColList(item, j);
      if (cr[0].length) tableUniques.push(cr[0]);
      return;
    }
    if (w === "FOREIGN") {
      const j2 = expectPhrase(item, 0, ["FOREIGN", "KEY"]);
      if (j2 !== null) {
        const cr = parseParenColList(item, j2);
        const wr2 = peekWord(item, cr[1]);
        if (wr2[0] === "REFERENCES") {
          const qr = readQualified(item, wr2[1]);
          const parts = qr[0];
          const refSchema = parts.length >= 2 ? parts[0] : null;
          const refTable = parts.length >= 2 ? parts[1] : (parts.length ? parts[0] : null);
          const cr2 = parseParenColList(item, qr[1]);
          tableFks.push({ columns: cr[0], ref_schema: refSchema, ref_table: refTable, ref_columns: cr2[0] });
        }
      }
      return;
    }
    if (w === "CHECK" || w === "KEY" || w === "INDEX") return;
  }

  function parseCreateTable(stmt) {
    let wr = peekWord(stmt, 0);
    if (wr[0] !== "CREATE") return null;
    wr = peekWord(stmt, wr[1]);
    if (wr[0] !== "TABLE") return null;
    let i = wr[1];
    const j2 = expectPhrase(stmt, i, ["IF", "NOT", "EXISTS"]);
    if (j2 !== null) i = j2;
    const qr = readQualified(stmt, i);
    const parts = qr[0];
    if (!parts.length) return null;
    const schema = parts.length >= 2 ? parts[0] : null;
    const name = parts.length >= 2 ? parts[1] : parts[0];
    i = qr[1];
    const ii = skipWs(stmt, i);
    if (ii >= stmt.length || stmt[ii] !== "(") return null;
    const close = findMatchingParen(stmt, ii);
    if (close === -1) return null;
    const body = stmt.slice(ii + 1, close);
    const items = splitTopLevel(body, ",");
    const columns = [];
    const tablePk = [];
    const tableFks = [];
    const tableUniques = [];
    for (let k = 0; k < items.length; k++) {
      const item = items[k];
      if (!item.trim()) continue;
      const w0 = peekWord(item, 0)[0];
      if (["PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "KEY", "INDEX"].indexOf(w0) !== -1) {
        parseColumnOrConstraint(item, tablePk, tableFks, tableUniques);
      } else {
        const col = parseColumnDef(item);
        if (col) columns.push(col);
      }
    }
    for (let k = 0; k < columns.length; k++) {
      const c = columns[k];
      if (c.pk && tablePk.indexOf(c.name) === -1) tablePk.push(c.name);
    }
    return {
      schema: schema, name: name, columns: columns, pk: tablePk,
      unique: tableUniques, fks: tableFks, comment: null, column_comments: {},
    };
  }

  function parseAlterAddFk(stmt) {
    let wr = peekWord(stmt, 0);
    if (wr[0] !== "ALTER") return null;
    wr = peekWord(stmt, wr[1]);
    if (wr[0] !== "TABLE") return null;
    let i = wr[1];
    const jOnly = expectPhrase(stmt, i, ["ONLY"]);
    if (jOnly !== null) i = jOnly;
    const qr = readQualified(stmt, i);
    const parts = qr[0];
    if (!parts.length) return null;
    const schema = parts.length >= 2 ? parts[0] : null;
    const name = parts.length >= 2 ? parts[1] : parts[0];
    i = qr[1];
    wr = peekWord(stmt, i);
    if (wr[0] !== "ADD") return null;
    i = wr[1];
    wr = peekWord(stmt, i);
    if (wr[0] === "CONSTRAINT") {
      const ir = readIdent(stmt, wr[1]);
      i = ir[1];
      wr = peekWord(stmt, i);
    }
    if (wr[0] !== "FOREIGN") return null;
    i = wr[1];
    wr = peekWord(stmt, i);
    if (wr[0] !== "KEY") return null;
    i = wr[1];
    const cr = parseParenColList(stmt, i);
    i = cr[1];
    wr = peekWord(stmt, i);
    if (wr[0] !== "REFERENCES") return null;
    i = wr[1];
    const qr2 = readQualified(stmt, i);
    if (!qr2[0].length) return null;
    const refSchema = qr2[0].length >= 2 ? qr2[0][0] : null;
    const refTable = qr2[0].length >= 2 ? qr2[0][1] : qr2[0][0];
    const cr2 = parseParenColList(stmt, qr2[1]);
    return {
      from_schema: schema, from_table: name, from_columns: cr[0],
      to_schema: refSchema, to_table: refTable, to_columns: cr2[0],
    };
  }

  function parseComment(stmt) {
    let wr = peekWord(stmt, 0);
    if (wr[0] !== "COMMENT") return null;
    wr = peekWord(stmt, wr[1]);
    if (wr[0] !== "ON") return null;
    wr = peekWord(stmt, wr[1]);
    if (wr[0] === "TABLE") {
      const qr = readQualified(stmt, wr[1]);
      const parts = qr[0];
      if (!parts.length) return null;
      const schema = parts.length >= 2 ? parts[0] : null;
      const table = parts.length >= 2 ? parts[1] : parts[0];
      const wr2 = peekWord(stmt, qr[1]);
      if (wr2[0] !== "IS") return null;
      const sr = readString(stmt, wr2[1]);
      return { kind: "table", schema: schema, table: table, text: sr[0] };
    }
    if (wr[0] === "COLUMN") {
      const qr = readQualified(stmt, wr[1]);
      const parts = qr[0];
      let schema, table, column;
      if (parts.length === 3) {
        schema = parts[0]; table = parts[1]; column = parts[2];
      } else if (parts.length === 2) {
        schema = null; table = parts[0]; column = parts[1];
      } else {
        return null;
      }
      const wr2 = peekWord(stmt, qr[1]);
      if (wr2[0] !== "IS") return null;
      const sr = readString(stmt, wr2[1]);
      return { kind: "column", schema: schema, table: table, column: column, text: sr[0] };
    }
    return null;
  }

  function resolveTableKey(tables, order, schema, name) {
    const exact = schema + " " + name;
    if (Object.prototype.hasOwnProperty.call(tables, exact)) return exact;
    for (let k = 0; k < order.length; k++) {
      const key = order[k];
      if (tables[key].name === name) return key;
    }
    return null;
  }

  function parseSQL(text) {
    const cleaned = stripComments(text);
    const stmts = splitStatements(cleaned);

    const tables = {};
    const order = [];
    const fks = [];
    let unknown = 0;
    const commentsTable = [];
    const commentsColumn = [];

    for (let s = 0; s < stmts.length; s++) {
      const stmt = stmts[s];
      const t = parseCreateTable(stmt);
      if (t !== null) {
        const key = (t.schema || "") + " " + t.name;
        tables[key] = t;
        order.push(key);
        continue;
      }
      const alt = parseAlterAddFk(stmt);
      if (alt !== null) {
        fks.push(alt);
        continue;
      }
      const c = parseComment(stmt);
      if (c !== null) {
        (c.kind === "table" ? commentsTable : commentsColumn).push(c);
        continue;
      }
      unknown++;
    }

    for (let k = 0; k < order.length; k++) {
      const t = tables[order[k]];
      for (let ci = 0; ci < t.columns.length; ci++) {
        const c = t.columns[ci];
        if (c.fk) {
          fks.push({
            from_schema: t.schema, from_table: t.name, from_columns: [c.name],
            to_schema: c.fk.ref_schema, to_table: c.fk.ref_table, to_columns: c.fk.ref_columns,
          });
        }
      }
      for (let fi = 0; fi < t.fks.length; fi++) {
        const f = t.fks[fi];
        fks.push({
          from_schema: t.schema, from_table: t.name, from_columns: f.columns,
          to_schema: f.ref_schema, to_table: f.ref_table, to_columns: f.ref_columns,
        });
      }
    }

    for (let k = 0; k < commentsTable.length; k++) {
      const c = commentsTable[k];
      const key = resolveTableKey(tables, order, c.schema || "", c.table);
      if (key) tables[key].comment = c.text;
    }
    for (let k = 0; k < commentsColumn.length; k++) {
      const c = commentsColumn[k];
      const key = resolveTableKey(tables, order, c.schema || "", c.table);
      if (key) tables[key].column_comments[c.column] = c.text;
    }

    if (!order.length) {
      throw new SchemaParseError("This does not look like SQL");
    }

    const schemaSet = {};
    for (let k = 0; k < order.length; k++) {
      const sc = tables[order[k]].schema;
      if (sc) schemaSet[sc] = true;
    }
    const schemas = Object.keys(schemaSet).sort();

    return {
      tables: order.map(function (k) { return tables[k]; }),
      foreign_keys: fks,
      schemas: schemas,
      unknown_statements: unknown,
    };
  }

  // ===========================================================================
  // 2. BROWSER UI -- everything below only runs with a real document.
  // ===========================================================================

  var hasDom = typeof document !== "undefined" && typeof document.addEventListener === "function";

  var SERVICE = "https://usta-loops-260481739341.us-central1.run.app";
  var FOOTER_LINE = "Made with the schema handoff tool — ustechautomations.com/feeds/schemahand";

  function beacon(event) {
    try {
      var img = (typeof Image !== "undefined") ? new Image() : null;
      var url = SERVICE + "/t?f=schemahand&e=" + encodeURIComponent(event);
      if (img) {
        img.src = url;
      } else if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        navigator.sendBeacon(url);
      }
    } catch (e) { /* telemetry must never break the page */ }
  }

  // --- layered layout, no library ------------------------------------------

  function layoutTables(model) {
    var byKey = {};
    model.tables.forEach(function (t) { byKey[(t.schema || "") + " " + t.name] = t; });
    var outgoing = {}; // key -> [target keys]
    model.tables.forEach(function (t) { outgoing[(t.schema || "") + " " + t.name] = []; });
    model.foreign_keys.forEach(function (fk) {
      if (!fk.to_table) return;
      var fromKey = (fk.from_schema || "") + " " + fk.from_table;
      var toKey = (fk.to_schema || "") + " " + fk.to_table;
      if (outgoing[fromKey] && byKey[toKey] && toKey !== fromKey) outgoing[fromKey].push(toKey);
    });
    var layerOf = {};
    function layerFor(key, seen) {
      if (layerOf.hasOwnProperty(key)) return layerOf[key];
      if (seen.indexOf(key) !== -1) return 0; // cycle guard
      seen = seen.concat([key]);
      var deps = outgoing[key] || [];
      if (!deps.length) { layerOf[key] = 0; return 0; }
      var maxL = -1;
      deps.forEach(function (d) { maxL = Math.max(maxL, layerFor(d, seen)); });
      var lvl = Math.min(maxL + 1, 8);
      layerOf[key] = lvl;
      return lvl;
    }
    var keys = model.tables.map(function (t) { return (t.schema || "") + " " + t.name; });
    keys.forEach(function (k) { layerFor(k, []); });
    var byLayer = {};
    keys.forEach(function (k) {
      var l = layerOf[k];
      (byLayer[l] = byLayer[l] || []).push(k);
    });
    var COL_W = 260, ROW_GAP = 24, PAD = 24, HEADER_H = 26, ROW_H = 18;
    var pos = {};
    Object.keys(byLayer).sort(function (a, b) { return a - b; }).forEach(function (lStr) {
      var l = Number(lStr);
      var y = PAD;
      byLayer[l].forEach(function (k) {
        var t = byKey[k];
        var h = HEADER_H + Math.max(1, t.columns.length) * ROW_H + 10;
        pos[k] = { x: PAD + l * COL_W, y: y, w: COL_W - 40, h: h };
        y += h + ROW_GAP;
      });
    });
    return pos;
  }

  // --- SVG entity box rendering ---------------------------------------------

  var SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) if (attrs.hasOwnProperty(k)) el.setAttribute(k, attrs[k]);
    return el;
  }

  function tableLabel(t) {
    return (t.schema ? t.schema + "." : "") + t.name;
  }

  function keyOf(t) {
    return (t.schema || "") + " " + t.name;
  }

  function buildDiagram(root, model, annotations, opts) {
    opts = opts || {};
    var editable = !!opts.editable;
    root.innerHTML = "";
    var pos = layoutTables(model);

    var maxX = 0, maxY = 0;
    model.tables.forEach(function (t) {
      var p = pos[keyOf(t)];
      maxX = Math.max(maxX, p.x + p.w + 40);
      maxY = Math.max(maxY, p.y + p.h + 40);
    });

    var svg = svgEl("svg", {
      viewBox: "0 0 " + Math.max(maxX, 600) + " " + Math.max(maxY, 400),
      width: "100%", height: "100%",
      "font-family": "system-ui, sans-serif", "font-size": "12",
      class: "sh-svg",
    });
    var g = svgEl("g", { class: "sh-pan-zoom" });
    svg.appendChild(g);

    var edgesLayer = svgEl("g", { class: "sh-edges" });
    var boxesLayer = svgEl("g", { class: "sh-boxes" });
    g.appendChild(edgesLayer);
    g.appendChild(boxesLayer);

    var byKey = {};
    model.tables.forEach(function (t) { byKey[keyOf(t)] = t; });

    // edges
    model.foreign_keys.forEach(function (fk) {
      if (!fk.to_table) return;
      var fromKey = (fk.from_schema || "") + " " + fk.from_table;
      var toKey = (fk.to_schema || "") + " " + fk.to_table;
      var a = pos[fromKey], b = pos[toKey];
      if (!a || !b) return;
      var x1 = a.x + a.w, y1 = a.y + 16;
      var x2 = b.x, y2 = b.y + 16;
      if (a.x === b.x) { x1 = a.x; y1 = a.y; x2 = b.x; y2 = b.y + b.h; }
      var path = svgEl("path", {
        d: "M" + x1 + "," + y1 + " C" + (x1 + 40) + "," + y1 + " " + (x2 - 40) + "," + y2 + " " + x2 + "," + y2,
        class: "sh-edge", "data-from": fromKey, "data-to": toKey, fill: "none",
      });
      edgesLayer.appendChild(path);
    });

    model.tables.forEach(function (t) {
      var key = keyOf(t);
      var p = pos[key];
      var box = svgEl("g", { class: "sh-table", "data-table": key, transform: "translate(" + p.x + "," + p.y + ")" });
      box.appendChild(svgEl("rect", { class: "sh-table-bg", width: p.w, height: p.h, rx: 6 }));
      box.appendChild(svgEl("rect", { class: "sh-table-head", width: p.w, height: 24, rx: 6 }));
      var title = svgEl("text", { class: "sh-table-title", x: 8, y: 16 });
      title.textContent = tableLabel(t);
      box.appendChild(title);
      t.columns.forEach(function (c, idx) {
        var y = 24 + idx * 18 + 13;
        var marks = [];
        if (c.pk || t.pk.indexOf(c.name) !== -1) marks.push("PK");
        if (c.fk) marks.push("FK");
        var row = svgEl("text", { class: "sh-col", x: 10, y: y, "data-col": c.name });
        row.textContent = (marks.length ? marks.join("/") + " " : "") + c.name + " : " + (c.type || "");
        box.appendChild(row);
      });
      boxesLayer.appendChild(box);
      box.addEventListener("click", function (ev) {
        ev.stopPropagation();
        highlightTable(root, key);
        if (opts.onSelect) opts.onSelect(t);
      });
    });

    root.appendChild(svg);
    attachPanZoom(svg, g);
    return svg;
  }

  function highlightTable(root, key) {
    var boxes = root.querySelectorAll(".sh-table");
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].classList.toggle("sh-selected", boxes[i].getAttribute("data-table") === key);
    }
    var edges = root.querySelectorAll(".sh-edge");
    for (var j = 0; j < edges.length; j++) {
      var on = edges[j].getAttribute("data-from") === key || edges[j].getAttribute("data-to") === key;
      edges[j].classList.toggle("sh-edge-active", on);
    }
  }

  function attachPanZoom(svg, g) {
    var scale = 1, tx = 0, ty = 0;
    var dragging = false, lastX = 0, lastY = 0;
    function apply() {
      g.setAttribute("transform", "translate(" + tx + "," + ty + ") scale(" + scale + ")");
    }
    svg.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var delta = ev.deltaY > 0 ? 0.9 : 1.1;
      scale = Math.min(4, Math.max(0.2, scale * delta));
      apply();
    }, { passive: false });
    svg.addEventListener("mousedown", function (ev) {
      dragging = true; lastX = ev.clientX; lastY = ev.clientY;
    });
    window.addEventListener("mouseup", function () { dragging = false; });
    window.addEventListener("mousemove", function (ev) {
      if (!dragging) return;
      tx += ev.clientX - lastX; ty += ev.clientY - lastY;
      lastX = ev.clientX; lastY = ev.clientY;
      apply();
    });
    apply();
  }

  // --- HTML export (free + pro) ---------------------------------------------

  var VIEWER_RUNTIME = [
    "(" + buildDiagram.toString() + ")",
    "(" + layoutTables.toString() + ")",
    "(" + highlightTable.toString() + ")",
    "(" + attachPanZoom.toString() + ")",
    "(" + svgEl.toString() + ")",
    "(" + tableLabel.toString() + ")",
    "(" + keyOf.toString() + ")",
  ].join(";\n");

  function exportHtml(model, annotations, opts) {
    opts = opts || {};
    var editable = !!opts.editable;
    var footer = editable ? "" : ('<footer class="sh-footer">' + FOOTER_LINE + "</footer>");
    var dataBlock = JSON.stringify({ model: model, annotations: annotations || {} });
    var html = "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">" +
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
      "<title>Schema diagram</title>" +
      "<style>" + EXPORT_CSS + "</style></head><body>" +
      "<div id=\"sh-root\" class=\"sh-root\"></div>" +
      footer +
      "<script type=\"application/json\" id=\"schemahand-data\">" + dataBlock + "</" + "script>" +
      "<script>var SVG_NS=\"http://www.w3.org/2000/svg\";" + VIEWER_RUNTIME +
      ";var data=JSON.parse(document.getElementById('schemahand-data').textContent);" +
      "buildDiagram(document.getElementById('sh-root'), data.model, data.annotations, {editable:" + (editable ? "true" : "false") + "});" +
      "</" + "script></body></html>";
    return html;
  }

  var EXPORT_CSS = ".sh-root{width:100%;height:100vh;}" +
    ".sh-svg{width:100%;height:100%;background:#fafafa;}" +
    ".sh-table-bg{fill:#fff;stroke:#c9c9c9;}" +
    ".sh-table-head{fill:#eef2ff;stroke:#c9c9c9;}" +
    ".sh-table-title{font-weight:600;}" +
    ".sh-col{fill:#333;}" +
    ".sh-edge{stroke:#8a8fa3;stroke-width:1.5;}" +
    ".sh-edge-active{stroke:#2b6cb0;stroke-width:2.5;}" +
    ".sh-selected .sh-table-bg{stroke:#2b6cb0;stroke-width:2;}" +
    ".sh-footer{font:12px system-ui,sans-serif;color:#666;text-align:center;padding:8px;}";

  function toCsvDataDictionary(model) {
    var rows = [["schema", "table", "column", "type", "primary_key", "foreign_key", "not_null", "default", "notes"]];
    model.tables.forEach(function (t) {
      t.columns.forEach(function (c) {
        rows.push([
          t.schema || "", t.name, c.name, (c.type || "") + (c.size ? "(" + c.size + ")" : ""),
          (c.pk || t.pk.indexOf(c.name) !== -1) ? "yes" : "",
          c.fk ? (c.fk.ref_table || "") : "",
          c.not_null ? "yes" : "",
          c.default === null || c.default === undefined ? "" : String(c.default),
          (t.column_comments && t.column_comments[c.name]) || "",
        ]);
      });
    });
    return rows.map(function (r) {
      return r.map(function (v) {
        var s = String(v == null ? "" : v);
        if (/[",\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
        return s;
      }).join(",");
    }).join("\r\n");
  }

  function downloadFile(name, content, mime) {
    try {
      var blob = new Blob([content], { type: mime || "text/plain" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    } catch (e) { /* download is best-effort */ }
  }

  function printablePages(model) {
    var parts = [];
    model.tables.forEach(function (t) {
      parts.push('<section class="sh-print-page"><h2>' + tableLabel(t) + "</h2>");
      if (t.comment) parts.push("<p>" + t.comment + "</p>");
      parts.push("<table><thead><tr><th>Column</th><th>Type</th><th>Notes</th></tr></thead><tbody>");
      t.columns.forEach(function (c) {
        var tags = [];
        if (c.pk || t.pk.indexOf(c.name) !== -1) tags.push("primary key");
        if (c.fk) tags.push("links to " + (c.fk.ref_table || ""));
        var note = (t.column_comments && t.column_comments[c.name]) || tags.join(", ");
        parts.push("<tr><td>" + c.name + "</td><td>" + (c.type || "") + "</td><td>" + note + "</td></tr>");
      });
      parts.push("</tbody></table></section>");
    });
    return parts.join("\n");
  }

  // --- pro verify -------------------------------------------------------

  function verifyProKey(key) {
    return fetch(SERVICE + "/pro/verify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ family: "schemahand", key: key }),
    }).then(function (res) {
      if (!res.ok) throw new Error("verify failed");
      return res.json();
    });
  }

  // --- page wiring --------------------------------------------------------

  function initPage() {
    // The page-load beacon is a static <img> in index.html, per the
    // family contract; this JS only fires the export beacons below.
    var input = document.getElementById("sh-input");
    var parseBtn = document.getElementById("sh-parse");
    var demoBtn = document.getElementById("sh-demo");
    var canvas = document.getElementById("sh-canvas");
    var sidePanel = document.getElementById("sh-side");
    var search = document.getElementById("sh-search");
    var errorBox = document.getElementById("sh-error");
    var freeExportBtn = document.getElementById("sh-export-free");
    var proKeyInput = document.getElementById("sh-pro-key");
    var proUnlockBtn = document.getElementById("sh-pro-unlock");
    var proStatus = document.getElementById("sh-pro-status");
    var proExportBtn = document.getElementById("sh-export-pro");

    var currentModel = null;
    var annotations = {};
    var proKey = null;

    function renderSidePanel(model) {
      if (!sidePanel) return;
      sidePanel.innerHTML = "";
      model.tables.forEach(function (t) {
        var key = keyOf(t);
        var box = document.createElement("div");
        box.className = "sh-side-table";
        var h = document.createElement("h3");
        h.textContent = tableLabel(t);
        box.appendChild(h);

        var tNote = document.createElement("textarea");
        tNote.placeholder = "Notes about this table";
        tNote.value = (annotations[key] && annotations[key].note) || "";
        tNote.addEventListener("input", function () {
          annotations[key] = annotations[key] || {};
          annotations[key].note = tNote.value;
        });
        box.appendChild(tNote);

        var list = document.createElement("ul");
        t.columns.forEach(function (c) {
          var li = document.createElement("li");
          var label = document.createElement("span");
          label.textContent = c.name + " (" + (c.type || "") + ")";
          li.appendChild(label);
          var cNote = document.createElement("input");
          cNote.type = "text";
          cNote.placeholder = "note";
          var colKey = key + ":" + c.name;
          cNote.value = (annotations[colKey] && annotations[colKey].note) || "";
          cNote.addEventListener("input", function () {
            annotations[colKey] = annotations[colKey] || {};
            annotations[colKey].note = cNote.value;
          });
          li.appendChild(cNote);
          list.appendChild(li);
        });
        box.appendChild(list);
        box.addEventListener("click", function () { highlightTable(canvas, key); });
        sidePanel.appendChild(box);
      });
    }

    function showError(msg) {
      if (errorBox) { errorBox.textContent = msg; errorBox.hidden = !msg; }
    }

    function doParse() {
      var text = input ? input.value : "";
      try {
        currentModel = parseSQL(text);
        annotations = {};
        showError("");
        buildDiagram(canvas, currentModel, annotations, {});
        renderSidePanel(currentModel);
      } catch (e) {
        currentModel = null;
        showError(e && e.message ? e.message : "This does not look like SQL");
        if (canvas) canvas.innerHTML = "";
        if (sidePanel) sidePanel.innerHTML = "";
      }
    }

    if (parseBtn) parseBtn.addEventListener("click", doParse);
    if (demoBtn) {
      demoBtn.addEventListener("click", function () {
        var demo = document.getElementById("sh-demo-sql");
        if (input && demo) {
          input.value = demo.textContent;
          doParse();
        }
      });
    }
    if (search) {
      search.addEventListener("input", function () {
        var q = search.value.trim().toLowerCase();
        if (!canvas) return;
        var boxes = canvas.querySelectorAll(".sh-table");
        for (var i = 0; i < boxes.length; i++) {
          var name = (boxes[i].getAttribute("data-table") || "").toLowerCase();
          var cols = boxes[i].querySelectorAll(".sh-col");
          var colHit = false;
          for (var c = 0; c < cols.length; c++) {
            if ((cols[c].getAttribute("data-col") || "").toLowerCase().indexOf(q) !== -1) colHit = true;
          }
          var hit = !q || name.indexOf(q) !== -1 || colHit;
          boxes[i].classList.toggle("sh-dim", !hit);
        }
      });
    }

    if (freeExportBtn) {
      freeExportBtn.addEventListener("click", function () {
        if (!currentModel) { showError("Paste a schema and click Draw diagram first."); return; }
        var html = exportHtml(currentModel, annotations, { editable: false });
        downloadFile("schema-diagram.html", html, "text/html");
        beacon("export_free");
      });
    }

    if (proUnlockBtn) {
      proUnlockBtn.addEventListener("click", function () {
        var key = proKeyInput ? proKeyInput.value.trim() : "";
        if (!key) { if (proStatus) proStatus.textContent = "Paste your key first."; return; }
        if (proStatus) proStatus.textContent = "Checking your key…";
        verifyProKey(key).then(function () {
          proKey = key;
          if (proStatus) proStatus.textContent = "Key accepted. The handoff package is unlocked below.";
          if (proExportBtn) proExportBtn.hidden = false;
        }).catch(function () {
          if (proStatus) {
            proStatus.textContent = "We could not check that key just now. Here is the free version instead.";
          }
          if (currentModel) {
            var html = exportHtml(currentModel, annotations, { editable: false });
            downloadFile("schema-diagram.html", html, "text/html");
            beacon("export_free");
          }
        });
      });
    }

    if (proExportBtn) {
      proExportBtn.addEventListener("click", function () {
        if (!currentModel || !proKey) return;
        var html = exportHtml(currentModel, annotations, { editable: true });
        var printPages = printablePages(currentModel);
        html = html.replace("</body></html>",
          '<section class="sh-print">' + printPages + "</section></body></html>");
        downloadFile("schema-handoff-package.html", html, "text/html");
        var csv = toCsvDataDictionary(currentModel);
        downloadFile("schema-data-dictionary.csv", csv, "text/csv");
        beacon("export_pro");
      });
    }
  }

  if (hasDom) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initPage);
    } else {
      initPage();
    }
  }

  // ===========================================================================
  // 3. exports (CommonJS for the Node test; harmless in a browser)
  // ===========================================================================
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      parseSQL: parseSQL,
      SchemaParseError: SchemaParseError,
      layoutTables: layoutTables,
      exportHtml: exportHtml,
      toCsvDataDictionary: toCsvDataDictionary,
    };
  }
  if (typeof window !== "undefined") {
    window.parseSQL = parseSQL;
  }
})();
