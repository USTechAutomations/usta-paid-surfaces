'use strict';
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {execFileSync} = require('child_process');
const root = path.resolve(__dirname, '..', '..', '..');
const generator = path.join(root, 'loops/schemahand/generate_sample_handoff.js');
const fixture = fs.readFileSync(path.join(root, 'loops/schemahand/fixtures/good_postgres.sql'), 'utf8');
const tool = require(path.join(root, 'families/schemahand/tool.js'));
const wanted = ['README.txt', 'dictionary.csv', 'handoff.html', 'manifest.json', 'source.sql'];
function sha(v) { return crypto.createHash('sha256').update(v).digest('hex'); }
function unzipStore(buf) {
  const entries = new Map(); let p = 0;
  while (buf.readUInt32LE(p) === 0x04034b50) {
    const size = buf.readUInt32LE(p + 18), n = buf.readUInt16LE(p + 26), x = buf.readUInt16LE(p + 28);
    const name = buf.subarray(p + 30, p + 30 + n).toString('utf8'); const start = p + 30 + n + x;
    entries.set(name, buf.subarray(start, start + size)); p = start + size;
  }
  return entries;
}
const d = fs.mkdtempSync(path.join(os.tmpdir(), 'schemahand-sample-'));
const a = path.join(d, 'a.zip'), b = path.join(d, 'b.zip');
execFileSync('node', [generator, a]); execFileSync('node', [generator, b]);
assert.deepStrictEqual(fs.readFileSync(a), fs.readFileSync(b), 'two builds are byte-identical');
const entries = unzipStore(fs.readFileSync(a));
assert.deepStrictEqual([...entries.keys()], wanted, 'only allowlisted safe relative members');
assert.ok([...entries.keys()].every(n => !n.includes('/') && !n.includes('..')));
const manifest = JSON.parse(entries.get('manifest.json'));
const model = tool.parseSQL(fixture), csv = tool.toCsvDataDictionary(model), html = tool.exportHtml(model, {}, {editable:true});
assert.strictEqual(entries.get('source.sql').toString(), fixture);
assert.strictEqual(entries.get('dictionary.csv').toString(), csv);
assert.strictEqual(entries.get('handoff.html').toString(), html);
assert.strictEqual(manifest.source_sql_sha256, sha(fixture)); assert.strictEqual(manifest.tool_js_sha256, sha(fs.readFileSync(path.join(root, 'families/schemahand/tool.js'))));
assert.strictEqual(manifest.handoff_html_sha256, sha(html)); assert.strictEqual(manifest.dictionary_csv_sha256, sha(csv));
assert.deepStrictEqual(manifest.counts, {tables:12,foreign_keys:15,columns:54,schemas:2,unknown_statements:3});
assert.match(entries.get('README.txt').toString(), /synthetic/i); assert.match(entries.get('README.txt').toString(), /no customer data/i);
assert.ok(!entries.get('handoff.html').toString().match(/lp1\.schemahand|sk_(?:live|test)/));
const py = String.raw`import csv, datetime, io, json, sys, zipfile
p=sys.argv[1]
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 assert z.namelist()==['README.txt','dictionary.csv','handoff.html','manifest.json','source.sql']
 for info in z.infolist(): assert info.date_time==(1980,1,1,0,0,0), info.date_time
 m=json.loads(z.read('manifest.json'))
 rows=list(csv.DictReader(io.TextIOWrapper(z.open('dictionary.csv'), encoding='utf-8', newline='')))
 assert len(rows)==m['counts']['columns']
 assert any(r['schema']=='app' and r['table']=='customers' and r['column']=='id' for r in rows)
 assert any(r['schema']=='audit' and r['table']=='login_events' and r['column']=='happened_at' for r in rows)
`;
execFileSync('python3', ['-c', py, a]);
console.log('SAMPLE HANDOFF TEST: 1 passed; 0 failed');
