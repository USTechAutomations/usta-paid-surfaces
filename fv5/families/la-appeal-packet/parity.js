// Runs the page's selection logic (extracted from index.html between the markers)
// against the offline fixture and prints the result as JSON, in the same shape
// fulfil.py prints, so parity.py can diff them. Node only, no network.
const fs = require("fs"), path = require("path"), vm = require("vm");
const here = __dirname;
const page = fs.readFileSync(path.join(here, "..", "..", "..", "families", "la-appeal-packet", "index.html"), "utf8");
const a = page.indexOf("/* LA_PACKET_LOGIC_START"), b = page.indexOf("/* LA_PACKET_LOGIC_END */");
if (a < 0 || b < 0) { console.error("markers missing"); process.exit(2); }
const code = page.slice(a, b);
const sandbox = {module: {exports: {}}, console};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const L = sandbox.module.exports;
const typed = process.argv[2] || "5980 W 75th St, Los Angeles, CA 90045";
const p = L.parseAddress(typed);
const LIVE = process.env.LA_PARITY_LIVE === "1";

async function query(params) {
  const u = new URLSearchParams(params); u.set("f", "json"); u.set("returnGeometry", "false");
  const r = await fetch(L.SERVICE + "?" + u.toString(), {headers: {"User-Agent": "usta-la-appeal-packet/1"}});
  if (!r.ok) throw new Error("county map answered " + r.status);
  const d = await r.json();
  if (d.error) throw new Error("county map error: " + (d.error.message || ""));
  return (d.features || []).map(f => L.normaliseRow(f.attributes));
}

(async () => {
  let cands, nearFor;
  if (LIVE) {
    cands = p.ok ? await query(L.subjectQuery(p)) : [];
    nearFor = async subj => query(L.neighbourQuery(subj));
  } else {
    const fixture = JSON.parse(fs.readFileSync(path.join(here, "fixtures", "parcels-90045.json"), "utf8"));
    const rows = fixture.rows.map(L.normaliseRow);
    cands = p.ok ? rows.filter(r => String(r.SitusHouseNo || "").trim() === p.house && String(r.SitusStreet || "").toUpperCase().startsWith(p.street) && (!p.zip || String(r.SitusZIP || "").slice(0, 5) === p.zip)) : [];
    nearFor = async subj => rows.filter(r => String(r.Roll_LandBaseYear || "") >= L.BASE_YEARS[L.BASE_YEARS.length - 1] && L.haversine(L.num(subj.CENTER_LAT), L.num(subj.CENTER_LON), L.num(r.CENTER_LAT), L.num(r.CENTER_LON)) <= L.RADIUS_M);
  }
  const pick = L.pickSubject(p, cands);
  if (!pick.subject) { console.log(JSON.stringify({parsed: p, subject: null, support_rows: []})); return; }
  const subj = pick.subject;
  const sel = L.selectComps(subj, await nearFor(subj));
  console.log(JSON.stringify({parsed: p, subject_ain: String(subj.AIN), support_rows: sel.comps.map(L.compRecord), candidates_in_radius: sel.candidates_in_radius, dropped: sel.dropped}));
})().catch(e => { console.error(String(e)); process.exit(1); });
