'use strict';
// Execute the actual exported document's script in a fresh JavaScript realm.
// Minimal DOM below is a test adapter, not an alternate renderer/parser.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const sh = require(process.env.SCHEMAHAND_TEST_TOOL || path.join(__dirname, '../../../families/schemahand/tool.js'));

class Element {
  constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; this.textContent = ''; }
  setAttribute(k, v) { this.attrs[k] = v; }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener() {}
  querySelectorAll() { return []; }
  set innerHTML(value) { assert.strictEqual(value, ''); this.children = []; }
}
function all(root) { return [root].concat(...root.children.map(all)); }
function exported(html) {
  // Raw-text script parsing stops at the HTML end tag, as a browser does.
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script\s*>/gi)];
  assert.strictEqual(scripts.length, 2, 'one inert data block and one runtime only');
  const data = scripts.find(s => s[1].includes('application/json'));
  const runtime = scripts.find(s => !s[1]);
  assert.ok(data && runtime);
  const root = new Element('div');
  const context = {
    document: { getElementById: id => id === 'schemahand-data' ? {textContent: data[2]} : id === 'sh-root' ? root : new Element('div'),
      createElementNS: (_ns, tag) => new Element(tag), createElement: tag => new Element(tag) },
    window: { addEventListener() {} },
  };
  vm.runInNewContext(runtime[2], context, {timeout: 1000});
  return {root, context, data: JSON.parse(data[2])};
}

let passed = 0;
function test(name, fn) { try { fn(); passed++; console.log('PASS ' + name); } catch (err) { console.error('FAIL ' + name + ': ' + err.message); process.exitCode = 1; } }

const sql = 'CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL); CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id));';
const model = sh.parseSQL(sql);

test('downloaded free and paid HTML execute standalone and render both tables and relation', () => {
  for (const editable of [false, true]) {
    const result = exported(sh.exportHtml(model, {}, {editable}));
    const nodes = all(result.root);
    assert.deepStrictEqual(nodes.filter(n => n.attrs.class === 'sh-table-title').map(n => n.textContent).sort(), ['customers', 'orders']);
    assert.strictEqual(nodes.filter(n => n.attrs.class === 'sh-edge').length, 1);
    assert.strictEqual(nodes.filter(n => n.attrs.class === 'sh-col').length, 4);
    assert.strictEqual(nodes.find(n => n.attrs.class === 'sh-pan-zoom').attrs.transform, undefined, 'export uses native scroll instead of mouse-only transforms');
    assert.ok(Number(nodes.find(n => n.attrs.class === 'sh-svg').attrs.height) < 400, 'small schema has intrinsic height');
    assert.deepStrictEqual(result.data.model.tables.map(t => t.name), ['customers', 'orders']);
  }
});

test('wide ASCII and Unicode identities retain intrinsic readable table widths in free and paid HTML', () => {
  const wide = 'W'.repeat(63);
  const sql = 'CREATE TABLE "顧客_very_long_table_identity" ("timestamp_without_timezone_列_identifier" TIMESTAMP WITHOUT TIME ZONE PRIMARY KEY);' +
    'CREATE TABLE "' + wide + '" ("customer_timestamp_reference_列" TIMESTAMP WITHOUT TIME ZONE, FOREIGN KEY ("customer_timestamp_reference_列") REFERENCES "顧客_very_long_table_identity"("timestamp_without_timezone_列_identifier"));';
  const model = sh.parseSQL(sql);
  for (const editable of [false, true]) {
    const result = exported(sh.exportHtml(model, {}, {editable}));
    const nodes = all(result.root);
    const titles = nodes.filter(n => n.attrs.class === 'sh-table-title').map(n => n.textContent);
    const boxes = nodes.filter(n => n.attrs.class === 'sh-table-bg');
    assert.ok(titles.includes(wide) && titles.includes('顧客_very_long_table_identity'));
    assert.ok(boxes.some(box => Number(box.attrs.width) >= wide.length * 15 + 24), 'wide Satoshi title gets an intrinsic box');
    assert.ok(Number(nodes.find(n => n.attrs.class === 'sh-svg').attrs.width) > 600, 'saved diagram keeps horizontal scroll dimensions');
  }
});

test('quoted identifier, comment and annotation script terminators remain inert data', () => {
  const payload = '</script><script>globalThis.injected=1</script>';
  const malicious = sh.parseSQL('CREATE TABLE "' + payload + '" ("<img src=x onerror=alert(1)>" TEXT); COMMENT ON TABLE "' + payload + '" IS \'' + payload + '\';');
  const result = exported(sh.exportHtml(malicious, {note: payload}, {editable: true}));
  assert.strictEqual(result.context.injected, undefined);
  assert.strictEqual(result.data.model.tables[0].name, payload);
  assert.strictEqual(result.data.model.tables[0].comment, payload);
  assert.strictEqual(result.data.annotations.note, payload);
  assert.strictEqual(all(result.root).find(n => n.attrs.class === 'sh-table-title').textContent, payload);
});

test('printable tables escape identifiers, types and all comment text', () => {
  const evil = '<img src=x onerror=alert(1)>';
  const hostile = {tables: [{schema: evil, name: evil, comment: evil, pk: [], column_comments: {[evil]: evil}, columns: [{name: evil, type: evil}]}]};
  const printed = sh.printablePages(hostile);
  assert.ok(!printed.includes('<img'));
  assert.strictEqual((printed.match(/&lt;img/g) || []).length, 6);
  assert.strictEqual((printed.match(/<section class="sh-print-page">/g) || []).length, 1);
});

test('CSV dictionary retains expected identifiers and inline foreign key', () => {
  const csv = sh.toCsvDataDictionary(model);
  const lines = csv.split('\r\n');
  assert.strictEqual(lines.length, 5);
  assert.ok(lines.includes(',orders,customer_id,INTEGER,,customers,,,') || lines.some(line => line.startsWith(',orders,customer_id,INTEGER,,customers,')));
  assert.ok(lines.some(line => line.startsWith(',customers,id,INTEGER,yes,')));
});

test('spreadsheet formula fields are rejected without changing canonical identifiers or HTML', () => {
  for (const name of ['=HYPERLINK("https://invalid.example")', '+SUM(1,1)', '-1+1', '@SUM(1,1)', ' \t=1+1']) {
    const dangerous = {tables:[{schema:'',name,pk:[],columns:[{name:'id',type:'INTEGER'}]}],foreign_keys:[]};
    assert.throws(() => sh.toCsvDataDictionary(dangerous), /CSV unavailable/);
    const result=exported(sh.exportHtml(dangerous,{}, {editable:true}));
    assert.strictEqual(result.data.model.tables[0].name,name);
  }
});

test('CSV comments with carriage returns round-trip through the independent Python csv reader', () => {
  const note='first line\rsecond line, with "quotes"\nthird line';
  const m={tables:[{schema:'',name:'records',pk:[],columns:[{name:'id',type:'INTEGER'}],column_comments:{id:note}}],foreign_keys:[]};
  const csv=sh.toCsvDataDictionary(m);
  const result=require('child_process').spawnSync('python3',['-c','import csv,io,json,sys;v=json.load(sys.stdin);r=list(csv.DictReader(io.StringIO(v["csv"],newline="")));assert len(r)==1;assert r[0]["notes"]==v["note"];assert r[0]["table"]=="records"'],{input:JSON.stringify({csv,note}),encoding:'utf8'});
  assert.strictEqual(result.status,0,result.stderr);
});

if (process.env.SCHEMAHAND_TEST_ARTIFACT_DIR && !process.exitCode) {
  const dir = process.env.SCHEMAHAND_TEST_ARTIFACT_DIR;
  fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(path.join(dir, 'schema-handoff-package.html'), sh.exportHtml(model, {}, {editable: true}));
  fs.writeFileSync(path.join(dir, 'schema-data-dictionary.csv'), sh.toCsvDataDictionary(model));
  const hostile = sh.parseSQL('CREATE TABLE "</script><script>globalThis.injected=1</script>" (id INTEGER);');
  fs.writeFileSync(path.join(dir, 'schema-hostile.html'), sh.exportHtml(hostile, {note: '</script><script>globalThis.injected=1</script>'}, {editable: true}));
}
console.log('EXPORT TEST: ' + passed + ' passed; ' + (process.exitCode ? 'failure present' : '0 failed'));
