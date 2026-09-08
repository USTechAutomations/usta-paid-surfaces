#!/usr/bin/env node
/*
 * Offline tests for the casepack embed script's pure computation and markup
 * core. We deliberately test renderSheet(cfg) -> string and the calculation
 * helpers directly, rather than driving a full DOM, per the allowed
 * alternative in the brief ("or use a pure-function core renderSheet(cfg)
 * -> string that the script uses, and test that"). loops/embeds/casepack.js
 * exports these functions via module.exports when required from Node, and
 * only touches document/window when actually loaded as a browser <script>.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const cp = require('../embeds/casepack.js');

const FIXTURES = path.join(__dirname, 'fixtures');

function loadFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), 'utf8'));
}

let pass = 0;
let fail = 0;
const fails = [];

function test(name, fn) {
  try {
    fn();
    pass += 1;
  } catch (err) {
    fail += 1;
    fails.push(name + ': ' + err.message);
  }
}

// --- both currencies of quantity compute totals correctly -----------------
test('unitsFor: 2 cases of a 12-per-case row = 24 units', function () {
  const cfg = loadFixture('casepack_config_good.json');
  assert.strictEqual(cp.unitsFor(cfg.rows[0], 2, 'cases'), 24);
});

test('computeTotals: entering 2 cases of row 1 (fixture: per_case 12/24/6) = 24 units', function () {
  const cfg = loadFixture('casepack_config_good.json');
  const totals = cp.computeTotals(cfg.rows, [
    { mode: 'cases', qty: 2 },
    { mode: 'cases', qty: 0 },
    { mode: 'cases', qty: 0 }
  ]);
  assert.strictEqual(totals.rows[0].units, 24);
  assert.strictEqual(totals.totalUnits, 24);
});

test('computeTotals: entering units directly converts back to cases (48 units of a 24-per-case row = 2 cases)', function () {
  const cfg = loadFixture('casepack_config_good.json');
  const totals = cp.computeTotals(cfg.rows, [
    { mode: 'cases', qty: 0 },
    { mode: 'units', qty: 48 },
    { mode: 'cases', qty: 0 }
  ]);
  assert.strictEqual(totals.rows[1].units, 48);
  assert.strictEqual(totals.rows[1].cases, 2);
});

test('computeTotals: grand total sums every row correctly across both currencies', function () {
  const cfg = loadFixture('casepack_config_good.json');
  const totals = cp.computeTotals(cfg.rows, [
    { mode: 'cases', qty: 2 },   // 2 * 12 = 24
    { mode: 'units', qty: 48 },  // 48
    { mode: 'cases', qty: 3 }    // 3 * 6 = 18
  ]);
  assert.strictEqual(totals.totalUnits, 24 + 48 + 18);
});

// --- badge appears when pro=false, not when pro=true -----------------------
test('renderSheet: free config shows the make-your-own badge', function () {
  const cfg = loadFixture('casepack_config_good.json');
  const html = cp.renderSheet(cfg);
  assert.ok(html.includes('cp-badge'), 'expected cp-badge in free-config output');
  assert.ok(html.includes('make your own') || html.includes('haz la tuya'),
    'expected the badge copy to appear');
});

test('renderSheet: pro config shows no badge', function () {
  const cfg = loadFixture('casepack_config_pro.json');
  const html = cp.renderSheet(cfg);
  assert.ok(!html.includes('cp-badge'), 'pro config must not carry the badge');
});

// --- Spanish labels appear when lang="both" --------------------------------
test('renderSheet: lang=both carries Spanish labels alongside English ones', function () {
  const cfg = loadFixture('casepack_config_good.json'); // lang: "both"
  const html = cp.renderSheet(cfg);
  assert.ok(html.includes('Producto'), 'expected the Spanish header "Producto"');
  assert.ok(html.includes('Cantidad'), 'expected the Spanish header "Cantidad"');
  assert.ok(html.includes('Unidades por caja'), 'expected the Spanish header "Unidades por caja"');
  assert.ok(html.includes('SKU'), 'expected the English header "SKU" still present');
  assert.ok(html.includes('Quantity'), 'expected the English header "Quantity" still present');
});

test('renderSheet: lang=en carries no Spanish product header', function () {
  const cfg = loadFixture('casepack_config_pro.json'); // lang: "en"
  const html = cp.renderSheet(cfg);
  assert.ok(!html.includes('Producto'), 'lang=en must not render the Spanish header');
});

// --- known-bad: per_case 0 renders the honest row error, never NaN --------
test('renderSheet: a row with per_case 0 shows the honest message and no NaN anywhere', function () {
  const cfg = loadFixture('casepack_config_bad.json');
  const html = cp.renderSheet(cfg);
  assert.ok(html.includes('units per case must be at least 1'),
    'expected the honest per-row error message');
  assert.ok(!/NaN/.test(html), 'output must never contain the literal text NaN');
});

test('computeTotals: a bad per_case row yields a null unit total for the whole sheet, not NaN', function () {
  const cfg = loadFixture('casepack_config_bad.json');
  const totals = cp.computeTotals(cfg.rows, [
    { mode: 'cases', qty: 1 },
    { mode: 'cases', qty: 1 }
  ]);
  assert.strictEqual(totals.rows[0].error, 'units per case must be at least 1');
  assert.strictEqual(totals.rows[0].units, null);
  assert.strictEqual(totals.rows[1].units, 24); // the valid row still computes
  assert.ok(!Number.isNaN(totals.rows[1].units));
});

test('unitsFor/casesFor: invalid per_case never produces NaN, only null', function () {
  assert.strictEqual(cp.unitsFor({ per_case: 0 }, 5, 'cases'), null);
  assert.strictEqual(cp.unitsFor({ per_case: 'not-a-number' }, 5, 'cases'), null);
  assert.strictEqual(cp.casesFor({ per_case: 0 }, 10), null);
});

// --- must not throw if the config is missing; renders a one-line notice ---
test('renderSheet: null config does not throw and renders a one-line notice', function () {
  let html;
  assert.doesNotThrow(function () { html = cp.renderSheet(null); });
  assert.ok(html.includes('cp-empty'), 'expected the empty-state wrapper class');
  assert.ok(html.length > 0 && !html.includes('<table'), 'expected a one-line notice, not a table');
});

test('renderSheet: undefined and malformed configs do not throw', function () {
  assert.doesNotThrow(function () { cp.renderSheet(undefined); });
  assert.doesNotThrow(function () { cp.renderSheet({}); });
  assert.doesNotThrow(function () { cp.renderSheet({ rows: 'not-an-array' }); });
  assert.doesNotThrow(function () { cp.renderSheet('garbage'); });
  assert.doesNotThrow(function () { cp.renderSheet(42); });
});

// --- CSV / copy-text builders never crash and carry the right numbers -----
test('buildOrderText / buildCsv: reflect entered quantities without throwing', function () {
  const cfg = loadFixture('casepack_config_good.json');
  const entries = [{ mode: 'cases', qty: 2 }, { mode: 'cases', qty: 0 }, { mode: 'cases', qty: 0 }];
  const text = cp.buildOrderText(cfg, entries, 'en');
  assert.ok(text.includes('A100'));
  assert.ok(text.includes('24'));
  const csv = cp.buildCsv(cfg, entries, 'en');
  assert.ok(csv.split('\n')[0].includes('SKU'));
  assert.ok(csv.includes('A100'));
});

// --- summary ---------------------------------------------------------------
console.log('casepack embed tests: ' + pass + ' passed, ' + fail + ' failed');
if (fail > 0) {
  fails.forEach(function (m) { console.error('FAIL ' + m); });
  process.exit(1);
}
process.exit(0);
