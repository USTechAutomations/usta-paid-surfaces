#!/usr/bin/env python3
"""The journal itself: one HTML block with its script and its data inside it.

The same block is the free tool on the public page and the unlocked tool on the
page a buyer gets. Only two things change between them: the entry limit and the
licence line. Everything else is identical on purpose -- the buyer has already
used the free one, their entries are in the same browser store, and a tool that
behaved differently after payment would lose them.

Nothing here talks to a server. There is no upload, no account and no key
escrow: the passphrase never leaves the page, and neither do the entries. That
also means nobody can recover a forgotten passphrase, which the page says in
those words before anyone types one.
"""
from __future__ import annotations

import html
import json

FREE_LIMIT = 25

# Field labels. The list a state actually asks for is read from its own rule in
# data/states.json; these are the words the form puts on screen.
FIELD_LABELS = {
    "date_time": "Date and time of the notarial act",
    "act_type": "Type of notarial act",
    "document_type": "Type of document",
    "document_date": "Date on the document",
    "signer_name": "Name of the signer",
    "signer_address": "Address of the signer",
    "id_method": "How the signer was identified",
    "id_issuer": "Who issued the identification",
    "id_expiry": "Expiry date on the identification",
    "id_serial": "Identification number",
    "fee": "Fee charged",
    "notes": "Notes",
}
ALWAYS = ["date_time", "act_type", "document_type", "document_date",
          "signer_name", "id_method", "id_issuer", "id_expiry"]

CSS = """
<style>
#nj{border:1px solid #d8d8d8;border-radius:6px;padding:1rem;margin:1.5rem 0;background:#fff}
#nj h3{margin-top:0}
#nj .row{margin:.5rem 0}
#nj label{display:block;font-weight:600;margin-bottom:.15rem}
#nj input,#nj select,#nj textarea{width:100%;max-width:34rem;padding:.4rem;
 border:1px solid #bbb;border-radius:4px;font:inherit}
#nj .nj-note{background:#fff8e1;border-left:4px solid #e0a800;padding:.6rem .8rem;margin:.6rem 0}
#nj .nj-stop{background:#fdecea;border-left:4px solid #c0392b;padding:.6rem .8rem;margin:.6rem 0}
#nj .nj-ok{background:#eaf6ec;border-left:4px solid #2e7d32;padding:.6rem .8rem;margin:.6rem 0}
#nj button{font:inherit;padding:.45rem .9rem;margin:.2rem .3rem .2rem 0;
 border:1px solid #444;border-radius:4px;background:#f4f4f4;cursor:pointer}
#nj button:disabled{opacity:.5;cursor:not-allowed}
#nj table{border-collapse:collapse;width:100%;font-size:.92em}
#nj th,#nj td{border:1px solid #ddd;padding:.35rem .5rem;text-align:left;vertical-align:top}
#nj canvas{border:1px dashed #999;border-radius:4px;touch-action:none;background:#fff}
#nj .nj-hide{display:none}
#nj .nj-cite{font-size:.88em;color:#444}
@media print{body *{visibility:hidden}#nj-print,#nj-print *{visibility:visible}
 #nj-print{position:absolute;left:0;top:0;width:100%}}
</style>
"""


def _rule_sentence(st: dict) -> str:
    """What this state's own page says, in the state's own words, or nothing.

    There is no sentence here that tells a reader what their situation is. The
    page shows the fetched words and the address they came from, and stops.
    """
    if not st.get("quote"):
        return ("We could not read this state's rule from its own site on the "
                "date below, so nothing on this row is settled.")
    return html.escape(st["quote"])


def app_fragment(states: list[dict], stamp: str, unlocked: bool = False,
                 preselect: str = "") -> str:
    """The whole tool as one block of HTML: markup, style and script inline."""
    picker = "\n".join(
        '<option value="{c}"{sel}>{n}</option>'.format(
            c=html.escape(s["code"]), n=html.escape(s["name"]),
            sel=" selected" if s["code"] == preselect else "")
        for s in states)
    data = json.dumps({
        "states": [{
            "code": s["code"], "name": s["name"], "slug": s["slug"],
            "journal_required": s["journal_required"],
            "electronic_allowed": s["electronic_allowed"],
            "fields": s["fields"], "retention_years": s["retention_years"],
            "thumbprint": s["thumbprint"], "signature": s["signature"],
            "quote": s["quote"], "cite_url": s["cite_url"],
            "cite_label": s["cite_label"], "agency_url": s["agency_url"],
            "checked": s["checked"],
        } for s in states],
        "labels": FIELD_LABELS,
        "always": ALWAYS,
        "limit": 0 if unlocked else FREE_LIMIT,
        "unlocked": bool(unlocked),
        "stamp": stamp,
    }, ensure_ascii=False, separators=(",", ":"))

    licence = ("<p class=\"nj-ok\"><strong>This page is your copy. It does not "
               "expire.</strong> Keep the address, or save this page to your "
               "own machine. There is no renewal and nothing to cancel.</p>"
               if unlocked else
               "<p class=\"nj-note\">The free tool holds "
               f"{FREE_LIMIT} entries. Everything you enter stays in this "
               "browser either way.</p>")

    return CSS + f"""
<section id="nj" data-source-url="https://ustechautomations.com/feeds/notary-journal/">
  <h3>Notary journal (runs in your browser)</h3>
  {licence}
  <p class="nj-note"><strong>Read this before you type anything.</strong>
   Entries are locked with a passphrase you choose and are stored only in this
   browser. Nothing is sent anywhere, and nobody, including us, can read them or
   reset the passphrase. A browser can and does delete stored data on its own,
   so a saved backup file is the only copy that survives that. The tool asks you
   to save one.</p>

  <div id="nj-lock">
    <div class="row">
      <label for="nj-state">Which state's rule should the form follow?</label>
      <select id="nj-state">{picker}</select>
    </div>
    <div id="nj-rule" class="nj-cite"></div>
    <div class="row">
      <label for="nj-pass">Passphrase</label>
      <input id="nj-pass" type="password" autocomplete="new-password">
    </div>
    <div class="row" id="nj-pass2wrap">
      <label for="nj-pass2">Type the passphrase again (first time only)</label>
      <input id="nj-pass2" type="password" autocomplete="new-password">
    </div>
    <button id="nj-unlock" type="button">Open the journal</button>
    <p id="nj-msg"></p>
  </div>

  <div id="nj-app" class="nj-hide">
    <p id="nj-count"></p>
    <div id="nj-limit" class="nj-stop nj-hide"></div>
    <div id="nj-backup" class="nj-stop nj-hide"></div>
    <div id="nj-thumb" class="nj-note nj-hide"></div>
    <form id="nj-form" autocomplete="off">
      <div id="nj-fields"></div>
      <div class="row nj-hide" id="nj-sigwrap">
        <label for="nj-sig">Signature of the signer</label>
        <canvas id="nj-sig" width="360" height="110"></canvas>
        <button id="nj-sigclear" type="button">Clear the signature</button>
      </div>
      <div class="row">
        <label for="nj-corrects">Correcting an earlier entry? Its number
          (leave empty for a new entry)</label>
        <input id="nj-corrects" type="text" inputmode="numeric">
      </div>
      <button id="nj-save" type="submit">Save the entry</button>
      <button id="nj-download" type="button">Save an encrypted backup file</button>
      <button id="nj-folder" type="button" class="nj-hide">Choose a backup folder</button>
      <button id="nj-csv" type="button">Export a readable spreadsheet</button>
      <button id="nj-printbtn" type="button">Print</button>
      <label for="nj-import" style="margin-top:.6rem">Restore from a backup file</label>
      <input id="nj-import" type="file" accept="application/json">
    </form>
    <div id="nj-print">
      <h4>Entries in this browser</h4>
      <table id="nj-table"><thead><tr><th>No.</th><th>Saved</th><th>What it records</th></tr></thead>
      <tbody id="nj-rows"></tbody></table>
    </div>
    <p class="nj-cite">Entries cannot be edited or deleted here. A mistake is
      fixed by saving a correction that names the earlier number, so the record
      shows what was written and what changed. Numbers are never reused.</p>
  </div>
</section>
<script type="application/json" id="nj-data">{data}</script>
<script>
{SCRIPT}
</script>
"""


SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('nj-data').textContent);
  var NS = 'fv6.notary-journal.';
  var VKEY = NS + 'vault';
  var enc = new TextEncoder();
  var key = null, vault = null, dirHandle = null, sigDirty = false;

  function $(id){ return document.getElementById(id); }
  function show(el, on){ el.classList.toggle('nj-hide', !on); }
  function state(){ var c = $('nj-state').value;
    for (var i=0;i<D.states.length;i++){ if (D.states[i].code === c) return D.states[i]; }
    return D.states[0]; }

  /* ---------- storage: IndexedDB, with localStorage as the fallback ------- */
  function idb(){
    return new Promise(function(res, rej){
      if (!window.indexedDB) { rej(new Error('no indexeddb')); return; }
      var r = indexedDB.open('fv6.notary-journal', 1);
      r.onupgradeneeded = function(){ r.result.createObjectStore('vault'); };
      r.onsuccess = function(){ res(r.result); };
      r.onerror = function(){ rej(r.error); };
    });
  }
  function load(){
    return idb().then(function(db){
      return new Promise(function(res){
        var tx = db.transaction('vault', 'readonly').objectStore('vault').get(VKEY);
        tx.onsuccess = function(){ res(tx.result || null); };
        tx.onerror = function(){ res(null); };
      });
    }).catch(function(){
      try { var s = localStorage.getItem(VKEY); return s ? JSON.parse(s) : null; }
      catch (e) { return null; }
    });
  }
  function save(blob){
    return idb().then(function(db){
      return new Promise(function(res, rej){
        var tx = db.transaction('vault', 'readwrite').objectStore('vault').put(blob, VKEY);
        tx.onsuccess = function(){ res(true); };
        tx.onerror = function(){ rej(tx.error); };
      });
    }).catch(function(){
      try { localStorage.setItem(VKEY, JSON.stringify(blob)); return true; }
      catch (e) { return false; }
    });
  }

  /* ---------- the lock ---------------------------------------------------- */
  function b64(buf){ var b = new Uint8Array(buf), s = '';
    for (var i=0;i<b.length;i++) s += String.fromCharCode(b[i]);
    return btoa(s); }
  function unb64(str){ var s = atob(str), b = new Uint8Array(s.length);
    for (var i=0;i<s.length;i++) b[i] = s.charCodeAt(i); return b; }

  function derive(pass, salt){
    return crypto.subtle.importKey('raw', enc.encode(pass), 'PBKDF2', false, ['deriveKey'])
      .then(function(base){
        return crypto.subtle.deriveKey(
          {name:'PBKDF2', salt: salt, iterations: 200000, hash:'SHA-256'},
          base, {name:'AES-GCM', length:256}, false, ['encrypt','decrypt']);
      });
  }
  function seal(obj){
    var iv = crypto.getRandomValues(new Uint8Array(12));
    return crypto.subtle.encrypt({name:'AES-GCM', iv: iv}, key,
      enc.encode(JSON.stringify(obj))).then(function(ct){
        return {v:1, salt: vault.salt, iv: b64(iv), ct: b64(ct)};
      });
  }
  function open_(blob, pass){
    var salt = unb64(blob.salt);
    return derive(pass, salt).then(function(k){
      key = k;
      return crypto.subtle.decrypt({name:'AES-GCM', iv: unb64(blob.iv)}, k, unb64(blob.ct));
    }).then(function(pt){
      return JSON.parse(new TextDecoder().decode(pt));
    });
  }

  /* ---------- the form ---------------------------------------------------- */
  function fieldsFor(st){
    var want = D.always.slice();
    for (var i=0;i<st.fields.length;i++){
      if (want.indexOf(st.fields[i]) < 0) want.push(st.fields[i]);
    }
    if (want.indexOf('notes') < 0) want.push('notes');
    return want;
  }
  function drawForm(){
    var st = state(), want = fieldsFor(st), out = '';
    for (var i=0;i<want.length;i++){
      var f = want[i], lab = D.labels[f] || f;
      var tag = (f === 'notes')
        ? '<textarea id="nj-f-'+f+'" rows="2"></textarea>'
        : '<input id="nj-f-'+f+'" type="text">';
      out += '<div class="row"><label for="nj-f-'+f+'">'+lab+'</label>'+tag+'</div>';
    }
    $('nj-fields').innerHTML = out;
    show($('nj-sigwrap'), !!st.signature);
    var t = $('nj-thumb');
    show(t, !!st.thumbprint);
    if (st.thumbprint){
      t.textContent = 'This state’s rule mentions a thumbprint. This tool does '
        + 'not take one. A thumbprint has to be taken on paper and kept with a '
        + 'paper journal; a picture of one typed into a browser is not it.';
    }
    var d = $('nj-f-date_time');
    if (d && !d.value) d.value = new Date().toISOString().slice(0,16).replace('T',' ');
  }
  function ruleLine(){
    var st = state();
    var words = st.quote
      ? '“' + st.quote + '”'
      : 'We could not read this state’s own text from its site, so this row is unsettled.';
    var kind = {allowed:'This state’s text permits a journal in an electronic format.',
      not_allowed:'This state’s text describes a bound paper journal and we found no words permitting an electronic one.',
      vendor_only:'This state’s text ties an electronic journal to a provider the state approves.',
      unclear:'Unsettled: we could not read enough of this state’s text to say.'}[st.electronic_allowed];
    $('nj-rule').innerHTML = '<p>' + kind + '</p><p>' + words + '</p>'
      + '<p>Source: <a href="' + st.cite_url + '" rel="nofollow">' + st.cite_label
      + '</a>, read ' + st.checked + '. Notary office: <a href="' + st.agency_url
      + '" rel="nofollow">' + st.name + '</a>.</p>';
  }

  /* ---------- backups ----------------------------------------------------- */
  function backupName(){
    return 'notary-journal-backup-' + new Date().toISOString().slice(0,10) + '.json';
  }
  function backupDue(){
    if (!vault) return false;
    if (dirHandle) return false;
    var today = new Date().toISOString().slice(0,10);
    return (vault.entries.length > 0) && (vault.lastBackup !== today);
  }
  function paintBackup(){
    var due = backupDue();
    show($('nj-backup'), due);
    if (due){
      $('nj-backup').textContent = 'Save today’s encrypted backup before the '
        + 'next entry. A browser can clear this store without warning, and the '
        + 'backup file is the only copy that survives it.';
    }
    $('nj-save').disabled = due || overLimit();
  }
  function writeBackup(){
    return seal(vault).then(function(blob){
      var text = JSON.stringify(blob);
      if (dirHandle){
        return dirHandle.getFileHandle(backupName(), {create:true})
          .then(function(fh){ return fh.createWritable(); })
          .then(function(w){ return w.write(text).then(function(){ return w.close(); }); })
          .then(done);
      }
      var a = document.createElement('a');
      a.href = 'data:application/json;charset=utf-8,' + encodeURIComponent(text);
      a.download = backupName();
      document.body.appendChild(a); a.click(); a.remove();
      return done();
      function done(){
        vault.lastBackup = new Date().toISOString().slice(0,10);
        return persist().then(function(){ paintBackup(); return true; });
      }
    });
  }

  /* ---------- entries ----------------------------------------------------- */
  function overLimit(){
    return D.limit > 0 && vault && vault.entries.length >= D.limit;
  }
  function paintLimit(){
    var over = overLimit();
    show($('nj-limit'), over);
    if (over){
      $('nj-limit').textContent = 'The free tool holds ' + D.limit + ' entries and '
        + 'this browser now has ' + vault.entries.length + '. Your entries are '
        + 'still here and still readable, and a backup can still be saved. The '
        + 'copy sold on this page has no limit.';
    }
  }
  function persist(){
    return seal(vault).then(function(blob){ return save(blob); });
  }
  function paint(){
    var rows = '';
    for (var i=vault.entries.length-1; i>=0; i--){
      var e = vault.entries[i], bits = [];
      for (var k in e.fields){ if (e.fields[k]) bits.push((D.labels[k]||k) + ': ' + e.fields[k]); }
      var head = (e.kind === 'correction')
        ? 'Correction to entry ' + e.corrects + '. ' : '';
      rows += '<tr><td>' + e.n + '</td><td>' + e.at + '</td><td>'
        + esc(head + bits.join('; ')) + (e.sig ? ' (signature held)' : '') + '</td></tr>';
    }
    $('nj-rows').innerHTML = rows;
    $('nj-count').textContent = 'Entries in this browser: ' + vault.entries.length
      + (D.limit ? ' of ' + D.limit + ' in the free tool.' : '. No limit on this copy.');
    paintLimit(); paintBackup();
  }
  function esc(s){ return String(s).replace(/[&<>]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }

  /* ---------- signature --------------------------------------------------- */
  function wireSig(){
    var c = $('nj-sig'), ctx = c.getContext('2d'), drawing = false;
    ctx.lineWidth = 2; ctx.lineCap = 'round';
    function pos(ev){ var r = c.getBoundingClientRect();
      var p = ev.touches ? ev.touches[0] : ev;
      return [p.clientX - r.left, p.clientY - r.top]; }
    function down(ev){ drawing = true; sigDirty = true; ctx.beginPath();
      var p = pos(ev); ctx.moveTo(p[0], p[1]); ev.preventDefault(); }
    function move(ev){ if (!drawing) return; var p = pos(ev);
      ctx.lineTo(p[0], p[1]); ctx.stroke(); ev.preventDefault(); }
    function up(){ drawing = false; }
    c.addEventListener('mousedown', down); c.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    c.addEventListener('touchstart', down); c.addEventListener('touchmove', move);
    c.addEventListener('touchend', up);
    $('nj-sigclear').addEventListener('click', function(){
      ctx.clearRect(0,0,c.width,c.height); sigDirty = false; });
  }

  /* ---------- wiring ------------------------------------------------------ */
  $('nj-state').addEventListener('change', function(){ ruleLine(); drawForm(); });

  $('nj-unlock').addEventListener('click', function(){
    var pass = $('nj-pass').value, pass2 = $('nj-pass2').value;
    var msg = $('nj-msg');
    if (pass.length < 8){ msg.textContent = 'Use at least 8 characters. Nobody can reset this for you.'; return; }
    msg.textContent = 'Working…';
    load().then(function(blob){
      if (blob){
        return open_(blob, pass).then(function(v){
          vault = v; vault.salt = blob.salt;
        }).catch(function(){
          throw new Error('That passphrase does not open this journal. Nothing was changed.');
        });
      }
      if (pass !== pass2){ throw new Error('The two passphrases are different.'); }
      var salt = crypto.getRandomValues(new Uint8Array(16));
      return derive(pass, salt).then(function(k){
        key = k;
        vault = {v:1, salt: b64(salt), created: new Date().toISOString(),
                 next: 1, entries: [], lastBackup: null};
        return persist();
      });
    }).then(function(){
      msg.textContent = '';
      show($('nj-lock'), false); show($('nj-app'), true);
      drawForm(); paint();
    }).catch(function(e){ msg.textContent = e.message || String(e); });
  });

  $('nj-form').addEventListener('submit', function(ev){
    ev.preventDefault();
    if (overLimit() || backupDue()) return;
    var st = state(), want = fieldsFor(st), fields = {};
    for (var i=0;i<want.length;i++){
      var el = $('nj-f-' + want[i]);
      if (el) fields[want[i]] = el.value;
    }
    var corrects = ($('nj-corrects').value || '').trim();
    var e = {n: vault.next, at: new Date().toISOString(), state: st.code,
             kind: corrects ? 'correction' : 'entry',
             corrects: corrects ? Number(corrects) : null,
             fields: fields,
             sig: (st.signature && sigDirty) ? $('nj-sig').toDataURL('image/png') : null};
    vault.entries.push(e);
    vault.next += 1;
    persist().then(function(){
      $('nj-corrects').value = '';
      var s = $('nj-sig');
      if (s){ s.getContext('2d').clearRect(0,0,s.width,s.height); sigDirty = false; }
      paint();
      $('nj-msg').textContent = 'Entry ' + e.n + ' saved in this browser.';
    });
  });

  $('nj-download').addEventListener('click', function(){ writeBackup(); });

  if (window.showDirectoryPicker){
    show($('nj-folder'), true);
    $('nj-folder').addEventListener('click', function(){
      window.showDirectoryPicker({mode:'readwrite'}).then(function(h){
        dirHandle = h; return writeBackup();
      }).catch(function(){});
    });
  }

  $('nj-csv').addEventListener('click', function(){
    if (!vault) return;
    if (!window.confirm('This file is NOT encrypted. Anyone who opens it reads '
      + 'every entry. Save it only where you would keep the paper journal.')) return;
    var cols = ['n','at','kind','corrects','state'];
    var st = state(), want = fieldsFor(st);
    var head = cols.concat(want).join(',') + '\n', body = '';
    for (var i=0;i<vault.entries.length;i++){
      var e = vault.entries[i], row = [e.n, e.at, e.kind, e.corrects || '', e.state];
      for (var j=0;j<want.length;j++){ row.push(e.fields[want[j]] || ''); }
      body += row.map(function(v){ return '"' + String(v).replace(/"/g,'""') + '"'; }).join(',') + '\n';
    }
    var a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(head + body);
    a.download = 'notary-journal-' + new Date().toISOString().slice(0,10) + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  $('nj-printbtn').addEventListener('click', function(){ window.print(); });

  $('nj-import').addEventListener('change', function(ev){
    var f = ev.target.files && ev.target.files[0];
    if (!f) return;
    var pass = window.prompt('Passphrase for that backup file');
    if (!pass) return;
    f.text().then(function(t){
      var blob = JSON.parse(t);
      return open_(blob, pass).then(function(v){
        vault = v; vault.salt = blob.salt;
        return persist();
      });
    }).then(function(){
      show($('nj-lock'), false); show($('nj-app'), true);
      drawForm(); paint();
      $('nj-msg').textContent = 'Backup restored into this browser.';
    }).catch(function(){
      $('nj-msg').textContent = 'That file did not open with that passphrase. Nothing was changed.';
    });
  });

  wireSig(); ruleLine();
})();
"""
