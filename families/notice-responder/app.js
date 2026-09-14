import {
  DISCLAIMER,
  IRS_GENERAL_LOOKUP,
  NOTICES,
  NOT_COVERED_MESSAGE,
  resolve,
} from "./lookup.js";

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function paintNotCovered(query) {
  const out = $("result");
  const shown = query ? ` “${escapeHtml(query)}”` : "";
  out.innerHTML = `
    <div class="evidence">
      <div class="evidence-head">
        <span>Not covered yet</span>
      </div>
      <p>${escapeHtml(NOT_COVERED_MESSAGE)}</p>
      <p>There is no draft letter for${shown}. This tool does not invent a reply for a code it does not cover.</p>
      <p><a href="${escapeHtml(IRS_GENERAL_LOOKUP)}">IRS: Understanding your IRS notice or letter</a></p>
      <p class="demo">${escapeHtml(DISCLAIMER)}</p>
    </div>`;
}

function paintCovered(result) {
  const out = $("result");
  const e = result.explanation;
  const entry = result.entry;
  const options = (e.options || [])
    .map((o) => `<li>${escapeHtml(o)}</li>`)
    .join("");
  const docs = (e.documents || [])
    .map((d) => `<li>${escapeHtml(d)}</li>`)
    .join("");
  const source = e.source_url
    ? `<p><a href="${escapeHtml(e.source_url)}">IRS page used for this explanation</a></p>`
    : "";
  out.innerHTML = `
    <div class="evidence">
      <div class="evidence-head">
        <span>${escapeHtml(e.code)} — ${escapeHtml(entry.name)}</span>
      </div>
      <p><strong>${escapeHtml(entry.agency)}</strong></p>
      <p>${escapeHtml(e.meaning)}</p>
      <dl class="rail">
        <div><dt>Deadline the IRS page states</dt><dd>${escapeHtml(e.deadline_rule)}</dd></div>
      </dl>
      <p>Response options listed on the IRS page</p>
      <ul class="spec">${options}</ul>
      <p>Papers to gather</p>
      <ul class="spec">${docs}</ul>
      ${source}
      <p>Use the date printed on the notice you hold. This page does not calculate a deadline, prepare a letter, or submit anything to the IRS.</p>
      <p class="demo">${escapeHtml(DISCLAIMER)}</p>
    </div>`;
}

function fillPicker() {
  const sel = $("code-picker");
  if (!sel) return;
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Select a notice code";
  sel.appendChild(blank);
  for (const n of NOTICES) {
    const opt = document.createElement("option");
    opt.value = n.code;
    opt.textContent = `${n.code} — ${n.name}`;
    sel.appendChild(opt);
  }
  const params = new URLSearchParams(location.search);
  const preset = params.get("code");
  if (preset && NOTICES.some((n) => n.code === preset)) {
    sel.value = preset;
  }
}

function run() {
  const pasted = ($("paste") && $("paste").value.trim()) || "";
  const code = ($("code-picker") && $("code-picker").value) || "";
  const q = pasted || code;
  const out = $("result");
  if (!q) {
    if (out) out.innerHTML = "<p>Pick a code or paste the notice heading first.</p>";
    return;
  }
  const result = resolve(q);
  if (!result.covered) paintNotCovered(q);
  else paintCovered(result);
}

function main() {
  fillPicker();
  $("explain-btn") && $("explain-btn").addEventListener("click", run);
  $("notice-lookup-form") &&
    $("notice-lookup-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      run();
    });
  $("code-picker") && $("code-picker").addEventListener("change", run);
  if (new URLSearchParams(location.search).get("code")) run();
}

main();
