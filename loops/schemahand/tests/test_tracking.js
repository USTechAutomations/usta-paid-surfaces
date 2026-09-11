'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const SOURCE = fs.readFileSync(require('path').resolve(__dirname, '../../../families/schemahand/tool.js'), 'utf8');
const SERVICE = 'https://usta-loops-260481739341.us-central1.run.app';
const CHECKOUT_HREF = 'https://buy.stripe.com/4gM8wI8xg5uqds0eXE0sU2J';

function makeAnchor(checkout) {
  return {
    dataset: { checkout: checkout },
    href: CHECKOUT_HREF,
    getAttribute(n) {
      if (n === 'data-checkout') return this.dataset.checkout;
      if (n === 'href') return this.href;
      return null;
    },
    addEventListener(n, f) { this._handlers[n] = (this._handlers[n] || []).concat([f]); },
    closest(sel) {
      if (sel === 'a[data-checkout="schemahand"]' && this.dataset.checkout === 'schemahand') return this;
      return null;
    },
    _handlers: {},
  };
}

function clickEvent(target, extra) {
  const ev = Object.assign({
    button: 0,
    currentTarget: target,
    target: target,
    preventDefault() { ev.prevented = true; },
    prevented: false,
  }, extra || {});
  return ev;
}

function loadTool(opts) {
  opts = opts || {};
  const sent = [];
  const net = [];
  const anchors = opts.anchors || [makeAnchor('schemahand')];
  const ready = [];
  let sendBeaconImpl = opts.sendBeacon;
  if (sendBeaconImpl === undefined) {
    sendBeaconImpl = function (url, data) { sent.push({ via: 'beacon', url, data }); return true; };
  }
  const navigator = {};
  if (sendBeaconImpl !== null) navigator.sendBeacon = sendBeaconImpl;
  const ImageStub = opts.Image === null ? undefined : function () {
    Object.defineProperty(this, 'src', {
      set(url) { sent.push({ via: 'image', url }); },
    });
  };
  const document = {
    readyState: opts.readyState || 'complete',
    addEventListener(n, f) { if (n === 'DOMContentLoaded') ready.push(f); },
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll(sel) {
      if (sel === 'a[data-checkout="schemahand"]') {
        return anchors.filter(a => a.dataset && a.dataset.checkout === 'schemahand');
      }
      return [];
    },
    body: { appendChild() {}, removeChild() {} },
    createElement() {
      return { style: {}, classList: { toggle() {} }, setAttribute() {}, appendChild() {}, addEventListener() {} };
    },
  };
  const context = {
    document,
    window: {},
    navigator,
    sent,
    net,
    fetch() { net.push({ kind: 'fetch', args: Array.prototype.slice.call(arguments) }); return Promise.resolve({}); },
    XMLHttpRequest: function () {
      net.push({ kind: 'xhr' });
      this.open = function () {};
      this.send = function () { net.push({ kind: 'xhr-send' }); };
    },
  };
  if (ImageStub) context.Image = ImageStub;
  vm.runInNewContext(SOURCE, context, { timeout: 2000 });
  if (opts.readyState === 'loading') {
    const times = opts.fireReady || 1;
    for (let i = 0; i < times; i++) ready.forEach(fn => fn());
  }
  return { sent, net, anchors, context, ready };
}

// ---------------------------------------------------------------------------
// Known-good / known-bad fixture kept from the manager's original script.
// ---------------------------------------------------------------------------
const sent = [];
const handlers = {};
const anchor = {
  dataset: { checkout: 'schemahand' },
  href: CHECKOUT_HREF,
  getAttribute(n) { return n === 'data-checkout' ? 'schemahand' : n === 'href' ? this.href : null; },
  addEventListener(n, f) { handlers[n] = f; },
  closest() { return this; },
};
const document = {
  readyState: 'complete',
  addEventListener() {},
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll() { return [anchor]; },
  body: { appendChild() {}, removeChild() {} },
  createElement() { return { style: {}, classList: { toggle() {} }, setAttribute() {}, appendChild() {}, addEventListener() {} }; },
};
const context = {
  document,
  window: {},
  navigator: { sendBeacon: (url, data) => { sent.push({ url, data }); return true; } },
  Image: function () { Object.defineProperty(this, 'src', { set(url) { sent.push({ url }); } }); },
};
vm.runInNewContext(SOURCE, context);
assert.strictEqual(context.window.parseSQL('CREATE TABLE t (id INTEGER PRIMARY KEY);').tables.length, 1, 'known-good parser preserved');
assert.strictEqual(sent.length, 0, 'initialization does not forge checkout');
assert.strictEqual(typeof handlers.click, 'function', 'missing checkout click tracking');
let prevented = false;
handlers.click({ button: 0, currentTarget: anchor, target: anchor, preventDefault() { prevented = true; } });
assert.strictEqual(sent.length, 1, 'one checkout action, one event');
assert.strictEqual(prevented, false, 'navigation must not be blocked');

let extraPassed = 0, extraFailed = 0;
function extra(name, fn) {
  try {
    fn();
    extraPassed++;
    console.log('PASS ' + name);
  } catch (err) {
    extraFailed++;
    console.error('FAIL ' + name + ': ' + err.message);
    process.exitCode = 1;
  }
}

extra('JSON POST body is only family and event', () => {
  assert.strictEqual(sent[0].url, SERVICE + '/t');
  assert.strictEqual(typeof sent[0].data, 'string');
  const payload = JSON.parse(sent[0].data);
  assert.deepStrictEqual(Object.keys(payload).sort(), ['e', 'f']);
  assert.strictEqual(payload.f, 'schemahand');
  assert.strictEqual(payload.e, 'checkout_click');
  const raw = sent[0].data;
  assert.ok(!/buy\.stripe|sk_|lp1\.|CREATE TABLE|@|href|schema\b/i.test(raw), 'payload must not carry buyer or schema content');
  assert.ok(!('credentials' in sent[0]) && !sent[0].headers, 'no special credential headers');
});

extra('href is unchanged after checkout click', () => {
  assert.strictEqual(anchor.href, CHECKOUT_HREF);
});

extra('sendBeacon absent uses Image GET fallback', () => {
  const env = loadTool({ sendBeacon: null });
  const a = env.anchors[0];
  const fn = a._handlers.click[0];
  fn(clickEvent(a));
  assert.strictEqual(env.sent.length, 1);
  assert.strictEqual(env.sent[0].via, 'image');
  assert.strictEqual(env.sent[0].url, SERVICE + '/t?f=schemahand&e=checkout_click');
  assert.strictEqual(env.net.length, 0);
});

extra('sendBeacon returning false uses Image GET fallback', () => {
  const beaconCalls = [];
  const env = loadTool({
    sendBeacon(url, data) { beaconCalls.push({ url, data }); return false; },
  });
  const a = env.anchors[0];
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(beaconCalls.length, 1);
  assert.strictEqual(beaconCalls[0].url, SERVICE + '/t');
  assert.strictEqual(JSON.parse(beaconCalls[0].data).e, 'checkout_click');
  assert.strictEqual(env.sent.filter(x => x.via === 'image').length, 1);
  assert.strictEqual(env.sent.filter(x => x.via === 'image')[0].url, SERVICE + '/t?f=schemahand&e=checkout_click');
});

extra('sendBeacon throwing uses Image GET fallback', () => {
  const env = loadTool({
    sendBeacon() { throw new Error('blocked'); },
  });
  const a = env.anchors[0];
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(env.sent.length, 1);
  assert.strictEqual(env.sent[0].via, 'image');
  assert.strictEqual(env.sent[0].url, SERVICE + '/t?f=schemahand&e=checkout_click');
});

extra('sendBeacon non-function uses Image GET fallback', () => {
  const env = loadTool({ sendBeacon: false });
  const a = env.anchors[0];
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(env.sent.length, 1);
  assert.strictEqual(env.sent[0].via, 'image');
});

extra('unrelated link is not counted', () => {
  const other = makeAnchor('other-family');
  other.dataset.checkout = 'other-family';
  const env = loadTool({ anchors: [makeAnchor('schemahand'), other] });
  assert.ok(!other._handlers.click);
  assert.strictEqual(env.anchors[0]._handlers.click.length, 1);
  if (other._handlers.click) other._handlers.click[0](clickEvent(other));
  env.anchors[0]._handlers.click[0](clickEvent(other));
  assert.strictEqual(env.sent.length, 0, 'handler ignores unrelated currentTarget');
  env.anchors[0]._handlers.click[0](clickEvent(env.anchors[0]));
  assert.strictEqual(env.sent.length, 1);
});

extra('right click is not counted', () => {
  const env = loadTool();
  const a = env.anchors[0];
  const ev = clickEvent(a, { button: 2 });
  a._handlers.click[0](ev);
  assert.strictEqual(env.sent.length, 0);
  assert.strictEqual(ev.prevented, false);
});

extra('keyboard-generated click is counted once', () => {
  const env = loadTool();
  const a = env.anchors[0];
  const ev = clickEvent(a, { button: 0, detail: 0 });
  a._handlers.click[0](ev);
  assert.strictEqual(env.sent.length, 1);
  assert.strictEqual(JSON.parse(env.sent[0].data).e, 'checkout_click');
  assert.strictEqual(ev.prevented, false);
});

extra('duplicate init registers one listener and one event', () => {
  const env = loadTool({ readyState: 'loading', fireReady: 2 });
  const a = env.anchors[0];
  assert.strictEqual(a._handlers.click.length, 1, 'initPage twice must not stack click listeners');
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(env.sent.length, 1);
});

extra('no fetch/XHR network; missing Image and sendBeacon is a no-op', () => {
  const env = loadTool({ sendBeacon: null, Image: null });
  const a = env.anchors[0];
  assert.strictEqual(typeof a._handlers.click[0], 'function');
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(env.sent.length, 0);
  assert.strictEqual(env.net.length, 0);
});

extra('preferred sendBeacon does not also fire Image', () => {
  const env = loadTool();
  const a = env.anchors[0];
  a._handlers.click[0](clickEvent(a));
  assert.strictEqual(env.sent.length, 1);
  assert.strictEqual(env.sent[0].via, 'beacon');
  assert.strictEqual(env.net.length, 0);
});

extra('export event names remain in source', () => {
  assert.ok(SOURCE.includes('beacon("export_free")'));
  assert.ok(SOURCE.includes('beacon("export_pro")'));
  assert.ok(SOURCE.includes('module.exports'));
});

console.log('TRACKING FIXTURE OK');
console.log('TRACKING EXTRA: ' + extraPassed + ' passed; ' + extraFailed + ' failed');
if (extraFailed) process.exit(1);
