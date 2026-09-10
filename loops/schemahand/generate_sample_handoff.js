'use strict';
/* Generate the deterministic public SchemaHand worked example from the real browser exporter. */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const family = path.join(root, 'families', 'schemahand');
const fixture = path.join(__dirname, 'fixtures', 'good_postgres.sql');
const toolPath = path.join(family, 'tool.js');
const members = ['README.txt', 'dictionary.csv', 'handoff.html', 'manifest.json', 'source.sql'];

function sha256(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function crc32(data) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function u16(v) { const b = Buffer.alloc(2); b.writeUInt16LE(v); return b; }
function u32(v) { const b = Buffer.alloc(4); b.writeUInt32LE(v >>> 0); return b; }
// DOS date 1980-01-01: valid in ZIP readers and fixed for byte reproducibility.
const DOS_TIME = 0;
const DOS_DATE = 0x0021;
function deterministicZip(entries) {
  const local = [], central = [];
  let offset = 0;
  for (const entry of entries) {
    if (!members.includes(entry.name) || /[\\/]|\.\./.test(entry.name)) throw new Error(`unsafe sample member: ${entry.name}`);
    const name = Buffer.from(entry.name, 'utf8');
    const data = Buffer.isBuffer(entry.data) ? entry.data : Buffer.from(entry.data, 'utf8');
    const crc = crc32(data);
    const header = Buffer.concat([Buffer.from('504b0304', 'hex'), u16(20), u16(0), u16(0), u16(DOS_TIME), u16(DOS_DATE), u32(crc), u32(data.length), u32(data.length), u16(name.length), u16(0), name]);
    local.push(header, data);
    central.push(Buffer.concat([Buffer.from('504b0102', 'hex'), u16(20), u16(20), u16(0), u16(0), u16(DOS_TIME), u16(DOS_DATE), u32(crc), u32(data.length), u32(data.length), u16(name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset), name]));
    offset += header.length + data.length;
  }
  const directory = Buffer.concat(central);
  return Buffer.concat([...local, directory, Buffer.from('504b0506', 'hex'), u16(0), u16(0), u16(entries.length), u16(entries.length), u32(directory.length), u32(offset), u16(0)]);
}
function buildSample() {
  const sourceSql = fs.readFileSync(fixture, 'utf8');
  const toolBytes = fs.readFileSync(toolPath);
  const tool = require(toolPath);
  const model = tool.parseSQL(sourceSql);
  const handoffHtml = tool.exportHtml(model, {}, {editable: true});
  const dictionaryCsv = tool.toCsvDataDictionary(model);
  const columns = model.tables.reduce((total, table) => total + table.columns.length, 0);
  const manifest = {
    schema: 'schemahand-worked-example.v1', synthetic: true, customer_data: false,
    generator: 'loops/schemahand/generate_sample_handoff.js', source_sql_sha256: sha256(sourceSql),
    tool_js_sha256: sha256(toolBytes), handoff_html_sha256: sha256(handoffHtml), dictionary_csv_sha256: sha256(dictionaryCsv),
    counts: {tables: model.tables.length, foreign_keys: model.foreign_keys.length, columns, schemas: model.schemas.length, unknown_statements: model.unknown_statements}, members
  };
  const readme = [
    'SchemaHand worked example', '',
    'This archive is synthetic and contains no customer data. It is usable without a key.',
    'Start with source.sql if you want to check the input. It is parsed locally by the browser tool; SchemaHand does not connect to a database or execute DDL.',
    'Open handoff.html in a browser. Open a table under Editable notes, edit a note, then select Save edited copy. Open that saved HTML to confirm the note remains. Use the browser print command to print or save the printable table views as PDF.',
    'dictionary.csv describes schema metadata: tables, columns, keys and SQL comments. It is not a customer, order, or destination-import data export.',
    `manifest.json records deterministic input, tool and output hashes plus parsed counts. This fixture has ${manifest.counts.unknown_statements} unknown statements; unsupported statements are counted, not executed.`,
    '',
  ].join('\n');
  const entries = [
    {name: 'README.txt', data: readme}, {name: 'dictionary.csv', data: dictionaryCsv},
    {name: 'handoff.html', data: handoffHtml}, {name: 'manifest.json', data: JSON.stringify(manifest, null, 2) + '\n'},
    {name: 'source.sql', data: sourceSql}
  ];
  return {zip: deterministicZip(entries), manifest};
}
function generate(output = path.join(family, 'sample-handoff.zip')) {
  const {zip, manifest} = buildSample();
  fs.mkdirSync(path.dirname(output), {recursive: true});
  fs.writeFileSync(output, zip);
  return {output, sha256: sha256(zip), bytes: zip.length, counts: manifest.counts};
}
if (require.main === module) process.stdout.write(JSON.stringify(generate(process.argv[2])) + '\n');
module.exports = {deterministicZip, buildSample, generate};
