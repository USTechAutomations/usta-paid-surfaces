/*!
 * casepack.js — bilingual wholesale reorder sheet embed.
 * A wholesaler pastes:
 *   <script src="https://usta-loops-260481739341.us-central1.run.app/embed/casepack.js" data-cfg="<cfg_id>"></script>
 * on their own site. This file fetches the config, draws a reorder table in
 * the host page, and never sends anything anywhere except the read fetch and
 * a couple of one-pixel count beacons. No third-party code is loaded.
 *
 * The maths (unitsFor / casesFor / computeTotals) and the markup builder
 * (renderSheet) are plain functions with no browser objects in them, so they
 * can be tested straight in Node. Everything that touches document/window
 * lives below the "browser only" line and only runs when a real page loads
 * this file as a <script> tag.
 */
(function () {
  'use strict';

  var SERVICE_BASE = 'https://usta-loops-260481739341.us-central1.run.app';
  var LANDING_URL = 'https://ustechautomations.com/feeds/casepack';

  var LABELS = {
    en: {
      sku: 'SKU',
      product: 'Product',
      unit: 'Unit',
      perCase: 'Units per case',
      qty: 'Quantity',
      modeCases: 'cases',
      modeUnits: 'units',
      totalUnits: 'Total units',
      totalCases: 'Total cases',
      copy: 'Copy order as text',
      download: 'Download CSV',
      grand: 'Order total, in units',
      switchLang: 'Ver en español',
      badge: 'Reorder sheet by ustechautomations.com/feeds/casepack — make your own',
      missing: 'This reorder sheet is not set up yet.',
      rowError: 'units per case must be at least 1'
    },
    es: {
      sku: 'SKU',
      product: 'Producto',
      unit: 'Unidad',
      perCase: 'Unidades por caja',
      qty: 'Cantidad',
      modeCases: 'cajas',
      modeUnits: 'unidades',
      totalUnits: 'Total en unidades',
      totalCases: 'Total en cajas',
      copy: 'Copiar pedido como texto',
      download: 'Descargar CSV',
      grand: 'Total del pedido, en unidades',
      switchLang: 'View in English',
      badge: 'Hoja de reorden de ustechautomations.com/feeds/casepack — haz la tuya',
      missing: 'Esta hoja de reorden todavía no está lista.',
      rowError: 'las unidades por caja deben ser al menos 1'
    }
  };

  // -------------------------------------------------------------------
  // pure functions — no document, no window, no fetch. Safe to test in Node.
  // -------------------------------------------------------------------

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function round2(n) {
    if (n === null || n === undefined || !isFinite(n)) return '0.00';
    return (Math.round(n * 100) / 100).toFixed(2);
  }

  function isValidPerCase(perCase) {
    var n = Number(perCase);
    return isFinite(n) && n >= 1;
  }

  // units in a row for a given entered quantity + mode ('cases' or 'units').
  // Returns null when the row's per_case is not a usable number.
  function unitsFor(row, qty, mode) {
    if (!row || !isValidPerCase(row.per_case)) return null;
    var perCase = Number(row.per_case);
    var q = Number(qty);
    if (!isFinite(q) || q < 0) q = 0;
    return mode === 'units' ? q : q * perCase;
  }

  // cases equivalent for a given unit count.
  function casesFor(row, units) {
    if (!row || !isValidPerCase(row.per_case) || units === null) return null;
    return units / Number(row.per_case);
  }

  // rows: array of {sku,name,unit,per_case,note}. entries: array of
  // {mode:'cases'|'units', qty:number}, same length as rows (missing/short
  // entries default to 0 cases). Returns {rows:[{error,units,cases}], totalUnits}.
  function computeTotals(rows, entries) {
    rows = Array.isArray(rows) ? rows : [];
    entries = Array.isArray(entries) ? entries : [];
    var perRow = [];
    var totalUnits = 0;
    var allValid = true;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var entry = entries[i] || { mode: 'cases', qty: 0 };
      if (!isValidPerCase(row.per_case)) {
        perRow.push({ error: 'units per case must be at least 1', units: null, cases: null });
        allValid = false;
        continue;
      }
      var units = unitsFor(row, entry.qty, entry.mode);
      var cases = casesFor(row, units);
      perRow.push({ error: null, units: units, cases: cases });
      totalUnits += units;
    }
    return { rows: perRow, totalUnits: allValid ? totalUnits : null };
  }

  function zeroEntries(rows) {
    return (rows || []).map(function () { return { mode: 'cases', qty: 0 }; });
  }

  function renderRow(row, i, L, calc) {
    row = row || {};
    if (calc && calc.error) {
      return (
        '<tr class="cp-row cp-row-bad" data-row="' + i + '">' +
        '<td>' + esc(row.sku) + '</td><td>' + esc(row.name) + '</td><td>' + esc(row.unit) + '</td>' +
        '<td class="cp-error" colspan="4">' + esc(L.rowError) + '</td>' +
        '</tr>'
      );
    }
    var units = calc ? calc.units : 0;
    var cases = calc ? calc.cases : 0;
    return (
      '<tr class="cp-row" data-row="' + i + '" data-per-case="' + Number(row.per_case) + '">' +
      '<td>' + esc(row.sku) + '</td>' +
      '<td>' + esc(row.name) + (row.note ? ' <span class="cp-note">(' + esc(row.note) + ')</span>' : '') + '</td>' +
      '<td>' + esc(row.unit) + '</td>' +
      '<td>' + Number(row.per_case) + '</td>' +
      '<td>' +
        '<input type="number" min="0" step="1" inputmode="numeric" class="cp-qty" data-row="' + i + '" value="0">' +
        '<select class="cp-mode" data-row="' + i + '">' +
          '<option value="cases">' + esc(L.modeCases) + '</option>' +
          '<option value="units">' + esc(L.modeUnits) + '</option>' +
        '</select>' +
      '</td>' +
      '<td class="cp-units" data-row="' + i + '">' + (units == null ? 0 : units) + '</td>' +
      '<td class="cp-cases" data-row="' + i + '">' + round2(cases) + '</td>' +
      '</tr>'
    );
  }

  function renderBlock(cfg, lg, hidden) {
    var L = LABELS[lg];
    var rows = cfg.rows;
    var totals = computeTotals(rows, zeroEntries(rows));
    var rowsHtml = rows.map(function (row, i) { return renderRow(row, i, L, totals.rows[i]); }).join('');
    var badge = cfg.pro ? '' :
      '<p class="cp-badge"><a href="' + LANDING_URL + '" target="_blank" rel="noopener">' + esc(L.badge) + '</a></p>';
    return (
      '<div class="cp-lang-block cp-lang-' + lg + (hidden ? ' cp-hidden' : '') + '" data-lang="' + lg + '">' +
      (cfg.title ? '<h3 class="cp-title">' + esc(cfg.title) + '</h3>' : '') +
      '<div class="cp-scroll"><table class="cp-table"><thead><tr>' +
        '<th>' + esc(L.sku) + '</th><th>' + esc(L.product) + '</th><th>' + esc(L.unit) + '</th>' +
        '<th>' + esc(L.perCase) + '</th><th>' + esc(L.qty) + '</th>' +
        '<th>' + esc(L.totalUnits) + '</th><th>' + esc(L.totalCases) + '</th>' +
      '</tr></thead><tbody>' + rowsHtml + '</tbody></table></div>' +
      '<p class="cp-grand">' + esc(L.grand) + ': <span class="cp-grand-total">' +
        (totals.totalUnits == null ? 0 : totals.totalUnits) + '</span></p>' +
      '<p class="cp-actions">' +
        '<button type="button" class="cp-copy">' + esc(L.copy) + '</button> ' +
        '<button type="button" class="cp-download">' + esc(L.download) + '</button>' +
      '</p>' +
      badge +
      '</div>'
    );
  }

  // cfg: {title, lang, rows, pro} from GET /cp/config/<cfg_id>, or null/bad
  // when the config could not be loaded. Always returns a string; never throws.
  function renderSheet(cfg) {
    try {
      if (!cfg || typeof cfg !== 'object' || !Array.isArray(cfg.rows)) {
        return '<div class="cp-embed cp-empty">' + esc(LABELS.en.missing) + '</div>';
      }
      var mode = cfg.lang === 'es' ? 'es' : (cfg.lang === 'both' ? 'both' : 'en');
      var langs = mode === 'both' ? ['en', 'es'] : [mode];
      var blocks = langs.map(function (lg, idx) { return renderBlock(cfg, lg, idx > 0); }).join('');
      var switchBtn = mode === 'both'
        ? '<p class="cp-switch-wrap"><button type="button" class="cp-lang-switch">' +
          esc(LABELS.en.switchLang) + ' / ' + esc(LABELS.es.switchLang) + '</button></p>'
        : '';
      return '<div class="cp-embed" data-lang="' + mode + '">' + switchBtn + blocks + '</div>';
    } catch (e) {
      return '<div class="cp-embed cp-empty">' + esc(LABELS.en.missing) + '</div>';
    }
  }

  function csvEscape(s) {
    s = String(s == null ? '' : s);
    if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function buildOrderText(cfg, entries, lg) {
    var L = LABELS[lg] || LABELS.en;
    var lines = [cfg.title || ''];
    (cfg.rows || []).forEach(function (row, i) {
      var e = (entries && entries[i]) || { mode: 'cases', qty: 0 };
      var qty = Number(e.qty) || 0;
      if (qty <= 0) return;
      var units = unitsFor(row, qty, e.mode);
      lines.push(
        row.sku + ' - ' + row.name + ': ' + qty + ' ' +
        (e.mode === 'units' ? L.modeUnits : L.modeCases) +
        (units == null ? '' : ' (' + units + ' ' + L.modeUnits + ')')
      );
    });
    var totals = computeTotals(cfg.rows, entries);
    lines.push(L.grand + ': ' + (totals.totalUnits == null ? 0 : totals.totalUnits));
    return lines.join('\n');
  }

  function buildCsv(cfg, entries, lg) {
    var L = LABELS[lg] || LABELS.en;
    var rows = [[L.sku, L.product, L.unit, L.perCase, L.qty, 'mode', L.totalUnits]];
    (cfg.rows || []).forEach(function (row, i) {
      var e = (entries && entries[i]) || { mode: 'cases', qty: 0 };
      var units = unitsFor(row, e.qty, e.mode);
      rows.push([row.sku, row.name, row.unit, row.per_case, e.qty || 0, e.mode, units == null ? '' : units]);
    });
    return rows.map(function (r) { return r.map(csvEscape).join(','); }).join('\n') + '\n';
  }

  // -------------------------------------------------------------------
  // browser only — everything below touches document/window/fetch and
  // only runs when this file is actually loaded as a <script> tag.
  // -------------------------------------------------------------------

  // The brand, carried as six of the embed's own custom properties.
  //
  // This embed runs inside somebody else's website. Loading the feeds
  // stylesheet here would restyle their whole page, so it is never loaded.
  // Instead the sheet's channels (BRAND.md section 1) are written once as
  // --cp-* properties on .cp-embed itself: they are set on our own element,
  // so they cannot leak out, and every rule below reads them rather than
  // naming a colour. Light and dark are both defined. Signal Blue appears
  // exactly once, on the link in the credit line; nothing else is coloured,
  // which is why the row error is muted text rather than red -- the words
  // already say what is wrong.
  var EMBED_CSS =
    '.cp-embed{' +
      '--cp-fg:hsl(220 20% 10%);--cp-muted:hsl(220 10% 42%);' +
      '--cp-line:hsl(220 13% 94%);--cp-surface:hsl(0 0% 100%);' +
      '--cp-surface-2:hsl(220 12% 97%);--cp-link:hsl(207 100% 50%);' +
      'font:500 14px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;' +
      'color:var(--cp-fg)}' +
    '@media (prefers-color-scheme:dark){.cp-embed{' +
      '--cp-fg:hsl(220 15% 96%);--cp-muted:hsl(220 8% 62%);' +
      '--cp-line:hsl(220 10% 18%);--cp-surface:hsl(220 12% 10%);' +
      '--cp-surface-2:hsl(220 10% 16%)}}' +
    '.cp-hidden{display:none}' +
    '.cp-scroll{overflow-x:auto}' +
    '.cp-title{font-size:18px;font-weight:650;margin:0 0 .625rem}' +
    '.cp-table{border-collapse:collapse;width:100%;min-width:520px;' +
      'background:var(--cp-surface);font-size:14px}' +
    '.cp-table th,.cp-table td{border:1px solid var(--cp-line);' +
      'padding:.5rem .625rem;text-align:left}' +
    '.cp-table th{background:var(--cp-surface-2);font-size:12px;font-weight:650;' +
      'letter-spacing:.05em;text-transform:uppercase;color:var(--cp-muted)}' +
    '.cp-qty,.cp-mode{min-height:44px;font:inherit;color:var(--cp-fg);' +
      'background:var(--cp-surface);border:1px solid var(--cp-line);border-radius:.5rem;' +
      'padding:.25rem .5rem}' +
    '.cp-qty{width:5em}' +
    '.cp-note,.cp-error,.cp-empty{color:var(--cp-muted)}' +
    '.cp-grand{font-weight:650}' +
    '.cp-actions,.cp-switch-wrap{display:flex;flex-wrap:wrap;gap:.5rem;margin:.75rem 0 0}' +
    '.cp-actions button,.cp-switch-wrap button{min-height:44px;font:inherit;' +
      'padding:.5rem .875rem;color:var(--cp-fg);background:var(--cp-surface);' +
      'border:1px solid var(--cp-line);border-radius:.5rem;cursor:pointer}' +
    '.cp-badge{font-size:12px;color:var(--cp-muted);margin:.75rem 0 0}' +
    '.cp-badge a{color:var(--cp-link)}';

  function injectStyles() {
    if (document.getElementById('cp-embed-style')) return;
    var style = document.createElement('style');
    style.id = 'cp-embed-style';
    style.textContent = EMBED_CSS;
    document.head.appendChild(style);
  }

  function beacon(event) {
    try {
      var img = new Image();
      img.src = SERVICE_BASE + '/t?f=casepack&e=' + encodeURIComponent(event);
    } catch (e) { /* counting must never break the page */ }
  }

  function activeBlock(container) {
    return container.querySelector('.cp-lang-block:not(.cp-hidden)') || container.querySelector('.cp-lang-block');
  }

  function readEntries(block, cfg) {
    var qtyInputs = block.querySelectorAll('.cp-qty');
    var modeSelects = block.querySelectorAll('.cp-mode');
    var entries = zeroEntries(cfg.rows);
    for (var i = 0; i < qtyInputs.length; i++) {
      var idx = Number(qtyInputs[i].getAttribute('data-row'));
      entries[idx] = { qty: qtyInputs[i].value, mode: modeSelects[i] ? modeSelects[i].value : 'cases' };
    }
    return entries;
  }

  function recalcBlock(block, cfg) {
    var entries = readEntries(block, cfg);
    var totals = computeTotals(cfg.rows, entries);
    totals.rows.forEach(function (calc, i) {
      var unitsCell = block.querySelector('.cp-units[data-row="' + i + '"]');
      var casesCell = block.querySelector('.cp-cases[data-row="' + i + '"]');
      if (unitsCell) unitsCell.textContent = calc.units == null ? 0 : calc.units;
      if (casesCell) casesCell.textContent = round2(calc.cases);
    });
    var grand = block.querySelector('.cp-grand-total');
    if (grand) grand.textContent = totals.totalUnits == null ? 0 : totals.totalUnits;
    return entries;
  }

  function downloadCsv(text) {
    try {
      var blob = new Blob([text], { type: 'text/csv' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'reorder.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (e) { /* ignore */ }
  }

  function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)['catch'](function () { fallbackCopy(text); });
        return;
      }
    } catch (e) { /* fall through */ }
    fallbackCopy(text);
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    } catch (e) { /* copy is best-effort only */ }
  }

  function wireEvents(container, cfg) {
    container.addEventListener('input', function (ev) {
      if (!ev.target.classList.contains('cp-qty')) return;
      var block = ev.target.closest ? ev.target.closest('.cp-lang-block') : activeBlock(container);
      recalcBlock(block || activeBlock(container), cfg);
    });
    container.addEventListener('change', function (ev) {
      if (!ev.target.classList.contains('cp-mode')) return;
      var block = ev.target.closest ? ev.target.closest('.cp-lang-block') : activeBlock(container);
      recalcBlock(block || activeBlock(container), cfg);
    });
    container.addEventListener('click', function (ev) {
      var el = ev.target;
      if (el.classList.contains('cp-lang-switch')) {
        var blocks = container.querySelectorAll('.cp-lang-block');
        blocks.forEach(function (b) { b.classList.toggle('cp-hidden'); });
        return;
      }
      if (el.classList.contains('cp-copy')) {
        var blockC = activeBlock(container);
        var lg = blockC.getAttribute('data-lang') || 'en';
        var entries = readEntries(blockC, cfg);
        copyText(buildOrderText(cfg, entries, lg));
        beacon('order_copied');
        return;
      }
      if (el.classList.contains('cp-download')) {
        var blockD = activeBlock(container);
        var lgD = blockD.getAttribute('data-lang') || 'en';
        var entriesD = readEntries(blockD, cfg);
        downloadCsv(buildCsv(cfg, entriesD, lgD));
      }
    });
  }

  function init() {
    // Primary contract: <script src="…/embed/casepack.js" data-cfg="ID"></script>
    var scriptEl = document.currentScript;
    if (!scriptEl) {
      // A page that inserts this script dynamically (e.g. a live preview),
      // or loads it with `async`, may lose currentScript. Fall back to the
      // last matching <script> tag.
      var all = document.querySelectorAll('script[src*="casepack.js"]');
      if (all.length) scriptEl = all[all.length - 1];
    }
    var cfgId = scriptEl ? (scriptEl.getAttribute('data-cfg') || '') : '';
    var container = null;
    if (!cfgId) {
      // Compatibility fallback: a host page may instead mark a container
      // with data-casepack="ID" (seen in loops/embeds/README.md's example
      // snippet). Fill that element directly rather than making a new one.
      var marker = document.querySelector('[data-casepack]');
      if (marker) {
        cfgId = marker.getAttribute('data-casepack') || '';
        container = marker;
      }
    }
    if (!container) {
      if (!scriptEl) return;
      container = document.createElement('div');
      container.className = 'cp-embed-mount';
      if (scriptEl.parentNode) scriptEl.parentNode.insertBefore(container, scriptEl.nextSibling);
    }
    injectStyles();
    container.innerHTML = renderSheet(null);
    beacon('embed_load');
    if (!cfgId) return;
    var url = SERVICE_BASE + '/cp/config/' + encodeURIComponent(cfgId);
    fetch(url).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (cfg) {
      container.innerHTML = renderSheet(cfg);
      if (cfg) wireEvents(container, cfg);
    })['catch'](function () {
      container.innerHTML = renderSheet(null);
    });
  }

  var API = {
    renderSheet: renderSheet,
    computeTotals: computeTotals,
    unitsFor: unitsFor,
    casesFor: casesFor,
    isValidPerCase: isValidPerCase,
    buildOrderText: buildOrderText,
    buildCsv: buildCsv,
    LABELS: LABELS
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = API;
  }
  if (typeof document !== 'undefined' && document.currentScript) {
    try { init(); } catch (err) { /* the embed must never throw on a host page */ }
  }
})();
