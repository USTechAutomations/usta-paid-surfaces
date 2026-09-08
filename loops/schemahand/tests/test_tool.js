'use strict';
/*
 * Node test for the browser parser in families/schemahand/tool.js.
 *
 * tool.js is written to run in a browser with no build step. To load it
 * under Node we stub just enough of `document`/`window` that its top-level
 * setup code does not throw -- the parser itself, parseSQL(text), never
 * touches these and is exercised as a pure function.
 *
 * Run: node loops/schemahand/tests/test_tool.js
 */
const path = require('path');
const fs = require('fs');
const assert = require('assert');

global.window = global.window || {};
// Node 22 already defines a read-only `navigator` global; tool.js's pure
// parser never touches it, so we leave it alone rather than reassign it.
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

const toolPath = path.join(__dirname, '..', '..', '..', 'families', 'schemahand', 'tool.js');
const mod = require(toolPath);
const parseSQL = mod && mod.parseSQL;

let passed = 0, failed = 0;
function check(cond, msg) {
  if (cond) { passed++; } else { failed++; console.error('FAIL:', msg); }
}

check(typeof parseSQL === 'function', 'tool.js exports parseSQL as a pure function');

const FIXTURES = path.join(__dirname, '..', 'fixtures');

const pg = fs.readFileSync(path.join(FIXTURES, 'good_postgres.sql'), 'utf8');
const modelPg = parseSQL(pg);
check(modelPg.tables.length === 12, `postgres table count is ${modelPg.tables.length}, want 12`);
check(modelPg.foreign_keys.length === 15, `postgres foreign key count is ${modelPg.foreign_keys.length}, want 15`);
check(modelPg.schemas.slice().sort().join(',') === 'app,audit', `postgres schemas are ${modelPg.schemas.join(',')}, want app,audit`);
check(modelPg.unknown_statements === 3, `postgres unknown statements is ${modelPg.unknown_statements}, want 3`);
const withComment = modelPg.tables.filter(function (t) { return t.comment; });
check(withComment.length >= 1, 'at least one table comment captured');
const orderItems = modelPg.tables.filter(function (t) { return t.name === 'order_items'; })[0];
check(orderItems && orderItems.pk.slice().sort().join(',') === 'order_id,product_id',
      'order_items has the composite table-level primary key');

const my = fs.readFileSync(path.join(FIXTURES, 'good_mysql.sql'), 'utf8');
const modelMy = parseSQL(my);
check(modelMy.tables.length === 6, `mysql table count is ${modelMy.tables.length}, want 6`);
check(modelMy.foreign_keys.length === 7, `mysql foreign key count is ${modelMy.foreign_keys.length}, want 7`);

const bad = fs.readFileSync(path.join(FIXTURES, 'bad_input.txt'), 'utf8');
let threw = false;
try {
  parseSQL(bad);
} catch (e) {
  threw = true;
  check(/does not look like SQL/i.test(e.message), `bad input error message is ${e.message}`);
}
check(threw, 'bad input (JSON) must be refused, not silently accepted');

console.log(`NODE TEST: ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
