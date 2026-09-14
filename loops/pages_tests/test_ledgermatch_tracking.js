'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const SERVICE = 'https://usta-loops-260481739341.us-central1.run.app';
const CHECKOUT_HREF = 'https://buy.stripe.com/bJecMYeVEbSO3Rq3eW0sU2I';
const FORBIDDEN = /\b(url|query|records|key|domain|email|referrer)\b/i;

const html = fs.readFileSync(path.join(__dirname, '../../families/ledgermatch/index.html'), 'utf8');
const scripts = [];
const scriptRe = /<script(?![^>]*type="application\/ld\+json")[^>]*>([\s\S]*?)<\/script>/gi;
let match;
while ((match = scriptRe.exec(html))) scripts.push(match[1]);
const SOURCE = scripts.filter(function (s) {
  return s.indexOf('sendBeacon') !== -1 && s.indexOf('checkout_click') !== -1;
}).join('\n');

let assertions = 0;
let passed = 0;
let failed = 0;

function check(cond, msg) {
  assertions += 1;
  assert.ok(cond, msg);
}

function eq(actual, expected, msg) {
  assertions += 1;
  assert.strictEqual(actual, expected, msg);
}

function same(actual, expected, msg) {
  assertions += 1;
  assert.deepStrictEqual(actual, expected, msg);
}

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log('PASS ' + name);
  } catch (err) {
    failed += 1;
    console.error('FAIL ' + name + ': ' + (err && err.message ? err.message : err));
  }
}

function asParams(data) {
  if (typeof data === 'string') return new URLSearchParams(JSON.parse(data));
  if (data instanceof URLSearchParams) return data;
  throw new Error('expected JSON string or fallback query parameters, got ' + typeof data);
}

function paramObject(data) {
  return Object.fromEntries(asParams(data).entries());
}

function makeAnchor(checkout) {
  return {
    tagName: 'A',
    href: CHECKOUT_HREF,
    parentNode: null,
    getAttribute: function (name) {
      if (name === 'data-checkout') return checkout;
      if (name === 'href') return this.href;
      return null;
    },
    closest: function (sel) {
      var n = this;
      while (n) {
        if (sel === 'a[data-checkout="ledgermatch"]' &&
            n.tagName === 'A' && n.getAttribute('data-checkout') === 'ledgermatch') {
          return n;
        }
        n = n.parentNode;
      }
      return null;
    },
    addEventListener: function (type, fn, opts) {
      this._listeners = this._listeners || [];
      this._listeners.push({
        type: type,
        fn: fn,
        capture: opts === true || (opts && opts.capture === true),
      });
    },
    _listeners: [],
  };
}

function load(opts) {
  opts = opts || {};
  if (!SOURCE) throw new Error('tracking script not found in index.html');
  var sent = [];
  var docListeners = [];
  var checkout = makeAnchor('ledgermatch');
  var other = makeAnchor('other');
  var sendBeaconImpl = opts.sendBeacon;
  if (sendBeaconImpl === undefined) {
    sendBeaconImpl = function (url, data) {
      sent.push({ via: 'beacon', url: url, data: data });
      return true;
    };
  }
  var navigatorObj = {
    doNotTrack: opts.doNotTrack,
    globalPrivacyControl: opts.globalPrivacyControl,
  };
  if (sendBeaconImpl !== null) navigatorObj.sendBeacon = sendBeaconImpl;

  var ImageStub = opts.Image === null ? undefined : function () {
    Object.defineProperty(this, 'src', {
      set: function (url) { sent.push({ via: 'image', url: url }); },
    });
  };

  var documentObj = {
    readyState: 'complete',
    addEventListener: function (type, fn, captureOrOpts) {
      docListeners.push({
        type: type,
        fn: fn,
        capture: captureOrOpts === true || (captureOrOpts && captureOrOpts.capture === true),
      });
    },
    getElementById: function () { return null; },
    querySelector: function () { return null; },
    querySelectorAll: function (sel) {
      if (sel === 'a[data-checkout="ledgermatch"]') return [checkout];
      if (sel === 'a[data-checkout]') return [checkout, other];
      return [];
    },
    createElement: function () { return { style: {} }; },
  };

  var context = {
    document: documentObj,
    navigator: navigatorObj,
    URLSearchParams: URLSearchParams,
  };
  context.window = context;
  if (ImageStub) context.Image = ImageStub;
  vm.runInNewContext(SOURCE, context, { timeout: 2000 });
  return {
    sent: sent,
    docListeners: docListeners,
    checkout: checkout,
    other: other,
  };
}

function fire(env, node, extra) {
  var ev = {
    target: node,
    currentTarget: node,
    button: 0,
    detail: 1,
    preventDefault: function () { ev.prevented = true; },
    prevented: false,
  };
  if (extra) Object.keys(extra).forEach(function (k) { ev[k] = extra[k]; });
  env.docListeners.forEach(function (l) {
    if (l.type === 'click') l.fn(ev);
  });
  (node._listeners || []).forEach(function (l) {
    if (l.type === 'click') l.fn(ev);
  });
  return ev;
}

test('tracking script extracted from index.html', function () {
  check(SOURCE.length > 0, 'missing sendBeacon checkout_click script');
  check(SOURCE.indexOf('URLSearchParams') !== -1, 'script must use URLSearchParams');
  check(SOURCE.indexOf('preventDefault') === -1, 'script must not call preventDefault');
});

test('capture-phase listener is registered', function () {
  var env = load();
  var capture = env.docListeners.filter(function (l) {
    return l.type === 'click' && l.capture;
  });
  var linkCapture = (env.checkout._listeners || []).filter(function (l) {
    return l.type === 'click' && l.capture;
  });
  check(capture.length + linkCapture.length >= 1, 'expected a capture-phase click listener');
});

test('checkout click sends exactly family and event', function () {
  var env = load();
  var ev = fire(env, env.checkout);
  eq(env.sent.length, 1, 'one checkout click, one event');
  eq(env.sent[0].via, 'beacon', 'prefer sendBeacon');
  eq(typeof env.sent[0].data, 'string', 'receiver requires JSON text');
  eq(env.sent[0].url, SERVICE + '/t', 'beacon hits existing SERVICE_BASE /t');
  same(paramObject(env.sent[0].data), { f: 'ledgermatch', e: 'checkout_click' });
  eq([...asParams(env.sent[0].data).keys()].sort().join(','), 'e,f');
  check(!FORBIDDEN.test(asParams(env.sent[0].data).toString()), 'payload has no personal fields');
  eq(ev.prevented, false, 'must not prevent navigation');
  eq(env.checkout.href, CHECKOUT_HREF, 'checkout href unchanged');
});

test('unrelated link sends no event', function () {
  var env = load();
  fire(env, env.other);
  eq(env.sent.length, 0, 'other data-checkout values must not send');
});

test('privacy doNotTrack sends no event', function () {
  var env = load({ doNotTrack: '1' });
  var ev = fire(env, env.checkout);
  eq(env.sent.length, 0, 'doNotTrack must skip tracking');
  eq(ev.prevented, false);
});

test('privacy globalPrivacyControl sends no event', function () {
  var env = load({ globalPrivacyControl: true });
  var ev = fire(env, env.checkout);
  eq(env.sent.length, 0, 'globalPrivacyControl must skip tracking');
  eq(ev.prevented, false);
});

test('sendBeacon false falls back to image GET', function () {
  var beaconCalls = [];
  var env = load({
    sendBeacon: function (url, data) {
      beaconCalls.push({ url: url, data: data });
      return false;
    },
  });
  fire(env, env.checkout);
  eq(beaconCalls.length, 1, 'beacon attempted');
  eq(beaconCalls[0].url, SERVICE + '/t');
  same(paramObject(beaconCalls[0].data), { f: 'ledgermatch', e: 'checkout_click' });
  var images = env.sent.filter(function (x) { return x.via === 'image'; });
  eq(images.length, 1, 'image fallback after false');
  var u = new URL(images[0].url);
  eq(u.origin + u.pathname, SERVICE + '/t');
  same(Object.fromEntries(u.searchParams.entries()), { f: 'ledgermatch', e: 'checkout_click' });
});

test('sendBeacon throw falls back to image GET', function () {
  var env = load({
    sendBeacon: function () { throw new Error('blocked'); },
  });
  var ev = fire(env, env.checkout);
  eq(env.sent.length, 1);
  eq(env.sent[0].via, 'image');
  var u = new URL(env.sent[0].url);
  eq(u.origin + u.pathname, SERVICE + '/t');
  same(Object.fromEntries(u.searchParams.entries()), { f: 'ledgermatch', e: 'checkout_click' });
  eq(ev.prevented, false);
});

test('keyboard synthesized click sends once and does not preventDefault', function () {
  var env = load();
  var ev = fire(env, env.checkout, { detail: 0, button: 0 });
  eq(env.sent.length, 1, 'keyboard click counts once');
  eq(env.sent[0].via, 'beacon');
  same(paramObject(env.sent[0].data), { f: 'ledgermatch', e: 'checkout_click' });
  eq(ev.prevented, false, 'keyboard click must not preventDefault');
});

test('successful beacon does not also fire image', function () {
  var env = load();
  fire(env, env.checkout);
  eq(env.sent.filter(function (x) { return x.via === 'image'; }).length, 0);
  eq(env.sent.filter(function (x) { return x.via === 'beacon'; }).length, 1);
});

console.log('assertions ' + assertions);
console.log('passed ' + passed + ' failed ' + failed);
if (failed || assertions === 0) process.exit(1);
console.log('SMOKE OK');
