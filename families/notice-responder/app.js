import { identify, explain, DISCLAIMER } from "./lookup.js";

function $(id) {
  return document.getElementById(id);
}

function paint(entry, sourceLabel) {
  const out = $("result");
  if (!entry) {
    out.innerHTML =
      "<p>No matching notice in the 20-notice demo file. Try a code such as CP2000.</p>";
    return;
  }
  const e = explain(entry);
  const options = (e.options || [])
    .map((o) => `<li>${escapeHtml(o)}</li>`)
    .join("");
  out.innerHTML = `
    <div class="evidence">
      <div class="evidence-head">
        <span>Demo explanation of ${escapeHtml(e.code)}</span>
        <span class="stamp">demo output</span>
      </div>
      <p><strong>${escapeHtml(entry.name)}</strong> · ${escapeHtml(entry.agency)}</p>
      <p>${escapeHtml(e.meaning)}</p>
      <dl class="rail">
        <div><dt>Deadline rule</dt><dd>${escapeHtml(e.deadline_rule)}</dd></div>
        <div><dt>Urgency</dt><dd>${escapeHtml(e.urgency)}</dd></div>
      </dl>
      <p>Options</p>
      <ul class="spec">${options}</ul>
      <p class="demo">${escapeHtml(sourceLabel)}. ${escapeHtml(DISCLAIMER)}</p>
    </div>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadNotices() {
  const res = await fetch("./sample.json", { cache: "no-store" });
  if (!res.ok) throw new Error("sample.json missing");
  const blob = await res.json();
  return Array.isArray(blob) ? blob : blob.notices || blob.rows || [];
}

function fillPicker(notices) {
  const sel = $("code-picker");
  if (!sel) return;
  for (const n of notices) {
    const opt = document.createElement("option");
    opt.value = n.code;
    opt.textContent = `${n.code} — ${n.name}`;
    sel.appendChild(opt);
  }
  const params = new URLSearchParams(location.search);
  const preset = params.get("code");
  if (preset) {
    sel.value = notices.some((n) => n.code === preset) ? preset : sel.value;
  }
}

async function main() {
  const notices = await loadNotices();
  fillPicker(notices);
  const run = () => {
    const pasted = ($("paste") && $("paste").value.trim()) || "";
    const code = ($("code-picker") && $("code-picker").value) || "";
    const q = pasted || code;
    const entry = identify(q, notices);
    paint(entry, pasted ? "Demo from pasted text against the sample file" : "Demo from the code picker");
  };
  $("explain-btn") && $("explain-btn").addEventListener("click", run);
  $("code-picker") && $("code-picker").addEventListener("change", run);
  if (new URLSearchParams(location.search).get("code")) run();
}

main().catch((err) => {
  const out = $("result");
  if (out) out.textContent = String(err);
});
