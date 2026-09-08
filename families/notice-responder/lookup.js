/** Pure notice lookup. No I/O. Document preparation, not tax advice. */

const STOP = new Set(
  "a an the of to for and or in on at by with from as is are was were be been being this that it its you your we our they their if then than not no yes".split(
    " ",
  ),
);

const PLACEHOLDER = /\{\{\s*([a-z0-9_]+)\s*\}\}/gi;

const DISCLAIMER = "This is document preparation, not tax advice.";

export { DISCLAIMER };

export function asList(notices) {
  if (Array.isArray(notices)) return notices;
  if (notices && Array.isArray(notices.notices)) return notices.notices;
  if (notices && Array.isArray(notices.rows)) return notices.rows;
  return [];
}

export function codeKey(code) {
  return String(code || "")
    .toUpperCase()
    .replace(/LETTER\s+/g, "")
    .replace(/[^A-Z0-9]/g, "");
}

export function codePattern(code) {
  const parts = String(code)
    .toUpperCase()
    .trim()
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!parts.length) return null;
  return new RegExp(`\\b${parts.join("[\\s-]*")}\\b`, "i");
}

function tokens(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !STOP.has(w));
}

/**
 * Best entry for a pasted notice or a code.
 * Code match first (longest code wins), then keyword score.
 * Returns the entry or null.
 */
export function identify(textOrCode, notices) {
  const raw = String(textOrCode || "").trim();
  if (!raw) return null;
  const list = asList(notices);
  if (!list.length) return null;

  const whole = codeKey(raw);
  if (whole.length >= 3 && !/\s/.test(raw)) {
    const exact = list.find((e) => codeKey(e.code) === whole);
    if (exact) return exact;
  }

  const byLen = [...list].sort(
    (a, b) => codeKey(b.code).length - codeKey(a.code).length,
  );
  for (const entry of byLen) {
    const re = codePattern(entry.code);
    if (re && re.test(raw)) return entry;
  }

  const hay = new Set(tokens(raw));
  if (!hay.size) return null;
  let best = null;
  let bestScore = 0;
  for (const entry of list) {
    const bag = tokens(`${entry.code} ${entry.name} ${entry.what_it_means}`);
    let score = 0;
    const seen = new Set();
    for (const w of bag) {
      if (seen.has(w)) continue;
      seen.add(w);
      if (hay.has(w)) score += w.length >= 6 ? 2 : 1;
    }
    if (score > bestScore) {
      bestScore = score;
      best = entry;
    }
  }
  if (bestScore < 6) return null;
  return best;
}

export function explain(entry) {
  if (!entry) return null;
  return {
    code: entry.code,
    meaning: entry.what_it_means,
    deadline_rule: entry.deadline_rule,
    options: [...(entry.options || [])],
    urgency: entry.urgency,
  };
}

export function outline(entry) {
  if (!entry) return null;
  return {
    code: entry.code,
    name: entry.name,
    agency: entry.agency,
    deadline_rule: entry.deadline_rule,
    documents_usually_needed: [...(entry.documents_usually_needed || [])],
    letter_skeleton: entry.letter_skeleton,
    disclaimer: DISCLAIMER,
  };
}

export function placeholdersIn(skeleton) {
  const found = [];
  const seen = new Set();
  String(skeleton || "").replace(PLACEHOLDER, (_, key) => {
    const k = key.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      found.push(k);
    }
    return _;
  });
  return found;
}

/**
 * Fill letter_skeleton with facts plus entry fields.
 * Unknown placeholders become empty strings so the paid letter has none left.
 */
export function letter(entry, facts = {}) {
  if (!entry) return "";
  const data = {
    code: entry.code,
    agency: entry.agency,
    name: entry.name,
    deadline_rule: entry.deadline_rule,
    disclaimer: DISCLAIMER,
    ...facts,
  };
  return String(entry.letter_skeleton || "").replace(PLACEHOLDER, (_, key) => {
    const v = data[key] ?? data[key.toLowerCase()];
    return v == null ? "" : String(v);
  });
}

export function letterPack(entry, facts = {}) {
  if (!entry) return null;
  return {
    letter_text: letter(entry, facts),
    checklist: [
      "Read the notice date and the deadline rule before you send anything.",
      "Match the tax year and the amount on the notice to your records.",
      "Attach copies, not originals, of the papers listed for this notice.",
      "Keep a copy of what you send and the proof of mailing.",
      DISCLAIMER,
    ],
    enclosures: [...(entry.documents_usually_needed || [])],
  };
}
