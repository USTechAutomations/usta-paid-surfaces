'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const SRC = fs.readFileSync(path.join(__dirname, '../scripts/checkout_events.js'), 'utf8');
const EXACT_CLICK =
  'https://usta-loops-260481739341.us-central1.run.app/t?f=schemahand&e=checkout_click';
const EXACT_PROBE =
  'https://usta-loops-260481739341.us-central1.run.app/t?f=usta-diagnostic&e=checkout_probe';

let passed = 0;
let failed = 0;

function test(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(function () {
      passed += 1;
      console.log('PASS ' + name);
    })
    .catch(function (err) {
      failed += 1;
      console.log('FAIL ' + name + ': ' + err.message);
    });
}

function load(overrides) {
  overrides = overrides || {};
  const calls = [];
  let handler = null;
  const sandbox = {
    navigator: Object.assign({ webdriver: false }, overrides.navigator || {}),
    document: {
      addEventListener: function (type, fn) {
        if (type === 'click') handler = fn;
      }
    }
  };
  if (overrides.hasFetch !== false) {
    sandbox.fetch =
      overrides.fetch ||
      function (url, opts) {
        calls.push({ url: url, opts: opts });
        return Promise.resolve({});
      };
  }
  vm.runInNewContext(SRC, sandbox);
  return { calls: calls, handler: handler };
}

function labelled(family) {
  const link = {
    getAttribute: function (n) {
      return n === 'data-checkout' ? family : null;
    }
  };
  return {
    target: {
      closest: function (sel) {
        return sel === 'a[data-checkout]' ? link : null;
      }
    },
    preventDefault: function () {
      this._blocked = true;
    },
    stopPropagation: function () {
      this._blocked = true;
    },
    _blocked: false
  };
}

function nested(family) {
  const link = {
    getAttribute: function (n) {
      return n === 'data-checkout' ? family : null;
    }
  };
  return {
    target: {
      closest: function (sel) {
        return sel === 'a[data-checkout]' ? link : null;
      }
    }
  };
}

function main() {
  return test('real labelled click', function () {
    const ctx = load();
    assert.ok(ctx.handler, 'click handler required');
    assert.strictEqual(ctx.calls.length, 0);
    const ev = labelled('schemahand');
    ctx.handler(ev);
    assert.strictEqual(ctx.calls.length, 1);
    assert.strictEqual(ctx.calls[0].url, EXACT_CLICK);
    assert.strictEqual(ctx.calls[0].opts.keepalive, true);
    assert.strictEqual(ctx.calls[0].opts.mode, 'no-cors');
    assert.strictEqual(ev._blocked, false);
  })
    .then(function () {
      return test('nested element', function () {
        const ctx = load();
        ctx.handler(nested('schemahand'));
        assert.strictEqual(ctx.calls.length, 1);
        assert.strictEqual(ctx.calls[0].url, EXACT_CLICK);
      });
    })
    .then(function () {
      return test('malformed family', function () {
        const ctx = load();
        ctx.handler(labelled('SchemaHand'));
        ctx.handler(labelled(''));
        ctx.handler(labelled('-bad'));
        ctx.handler(labelled('has_under'));
        ctx.handler(labelled('a'.repeat(65)));
        ctx.handler({
          target: {
            closest: function () {
              return { getAttribute: function () { return null; } };
            }
          }
        });
        assert.strictEqual(ctx.calls.length, 0);
      });
    })
    .then(function () {
      return test('missing link', function () {
        const ctx = load();
        ctx.handler({ target: { closest: function () { return null; } } });
        ctx.handler({ target: {} });
        ctx.handler({});
        ctx.handler({ target: { closest: function () { return {}; } } });
        assert.strictEqual(ctx.calls.length, 0);
      });
    })
    .then(function () {
      return test('DNT', function () {
        const ctx = load({ navigator: { doNotTrack: '1' } });
        ctx.handler(labelled('schemahand'));
        assert.strictEqual(ctx.calls.length, 0);
      });
    })
    .then(function () {
      return test('globalPrivacyControl', function () {
        const ctx = load({ navigator: { globalPrivacyControl: true } });
        ctx.handler(labelled('schemahand'));
        assert.strictEqual(ctx.calls.length, 0);
      });
    })
    .then(function () {
      return test('webdriver diagnostic', function () {
        const ctx = load({ navigator: { webdriver: true } });
        ctx.handler(labelled('schemahand'));
        assert.strictEqual(ctx.calls.length, 1);
        assert.strictEqual(ctx.calls[0].url, EXACT_PROBE);
        assert.ok(ctx.calls[0].url.indexOf('schemahand') === -1);
        assert.ok(ctx.calls[0].url.indexOf('checkout_click') === -1);
      });
    })
    .then(function () {
      return test('fetch synchronous throw', function () {
        const ctx = load({
          fetch: function () {
            throw new Error('sync fetch fail');
          }
        });
        ctx.handler(labelled('schemahand'));
      });
    })
    .then(function () {
      return test('asynchronous rejection', function () {
        let unhandled = 0;
        function onUnhandled() {
          unhandled += 1;
        }
        process.on('unhandledRejection', onUnhandled);
        const ctx = load({
          fetch: function () {
            return Promise.reject(new Error('async fetch fail'));
          }
        });
        ctx.handler(labelled('schemahand'));
        return new Promise(function (resolve) {
          setImmediate(resolve);
        }).then(function () {
          return new Promise(function (resolve) {
            setImmediate(resolve);
          });
        }).then(function () {
          process.removeListener('unhandledRejection', onUnhandled);
          assert.strictEqual(unhandled, 0);
        }).catch(function (err) {
          process.removeListener('unhandledRejection', onUnhandled);
          throw err;
        });
      });
    })
    .then(function () {
      return test('no fetch API', function () {
        const ctx = load({ hasFetch: false });
        ctx.handler(labelled('schemahand'));
      });
    })
    .then(function () {
      console.log('passed=' + passed + ' failed=' + failed);
      if (failed) process.exit(1);
    });
}

main().catch(function (err) {
  console.error(err);
  process.exit(1);
});
