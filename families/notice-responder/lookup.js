/** Pure notice lookup. No I/O. Document preparation, not tax advice. */

const STOP = new Set(
  "a an the of to for and or in on at by with from as is are was were be been being this that it its you your we our they their if then than not no yes".split(
    " ",
  ),
);

const PLACEHOLDER = /\{\{\s*([a-z0-9_]+)\s*\}\}/gi;

const DISCLAIMER = "This is document preparation, not tax advice.";

const IRS_GENERAL_LOOKUP =
  "https://www.irs.gov/individuals/understanding-your-irs-notice-or-letter";

const NOT_COVERED_MESSAGE =
  "This code is not covered yet — here is the IRS general notice lookup.";

/**
 * Sixteen common IRS notices. Each field is taken from the matching
 * irs.gov "Understanding your … notice" page fetched 2026-09-14.
 * letter_skeleton is empty on purpose: a generic letter is not a response.
 */
const NOTICES = [
  {
    code: "CP2000",
    agency: "IRS",
    name: "Underreporter proposed changes",
    urgency: "med",
    what_it_means:
      "The income or payment information the IRS received from third parties, such as employers or financial institutions, does not match what you reported. The difference may increase, decrease, or not change your tax. The notice explains proposed changes. It is not a bill. A response may be required.",
    deadline_rule:
      "Reply by the date listed on the notice. If you do not reply, or the IRS cannot resolve the discrepancy, it may send another notice and a bill.",
    options: [
      "Reply by the date listed, using the response form if the notice includes one: complete and sign it, state whether you agree or disagree, and include supporting documentation.",
      "If you agree and have no other income, credits, or expenses to report, follow the notice’s instructions. You do not need to amend your return.",
      "If the CP2000 is correct and you have other income, credits, or expenses to report, complete Form 1040-X, write “CP2000” on top, and submit it with your notice response.",
      "Request more time by sending an extension request with a reply option.",
      "If someone used your name and Social Security number, send your reply with a completed Form 14039, Identity Theft Affidavit.",
    ],
    documents_usually_needed: [
      "The CP2000 notice and its response form",
      "Forms W-2, 1098, 1099, and other payer statements named on the notice",
      "A signed statement and records if you disagree",
      "Form 1040-X if you have other items to report (write CP2000 at the top)",
      "Form 14039 if you are reporting identity theft",
    ],
    source_url:
      "https://www.irs.gov/individuals/understanding-your-cp2000-series-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP2501",
    agency: "IRS",
    name: "Underreporter inquiry",
    urgency: "med",
    what_it_means:
      "Third-party income or payment information does not match your return. The difference may increase, decrease, or not change your tax. The notice explains proposed changes. It is not a bill, but you must respond.",
    deadline_rule:
      "Reply on the letter’s response form by the date listed on the notice. You must respond.",
    options: [
      "If you agree: sign the response form (both spouses if you filed jointly) and choose a reply option.",
      "If you do not agree or the information is incorrect: return a signed response form with a signed statement explaining the disagreement, supporting documentation, and any expenses related to the unreported income that may reduce your tax.",
      "Include an amended return or the forms the notice requests. If you include Form 1040-X, write “CP2501” at the top.",
      "If the income is nontaxable under state relief, the Infrastructure Investment and Jobs Act, or a similar reason, include a signed statement with the response form.",
    ],
    documents_usually_needed: [
      "The CP2501 notice and its signed response form",
      "A signed statement if you disagree",
      "Documentation supporting your claim, including expenses tied to the unreported income",
      "Form 1040-X if the notice asks for an amended return (write CP2501 at the top)",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp2501-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP14",
    agency: "IRS",
    name: "Balance due",
    urgency: "med",
    what_it_means:
      "The IRS sent this notice because you owe money on unpaid taxes. It explains how much you owe and how to pay it.",
    deadline_rule:
      "Pay the amount you owe by the due date on the notice. The IRS does not charge extra interest if you pay in full by that date; interest accrues on any unpaid amount after it. Contact the IRS by that due date if you cannot pay in full.",
    options: [
      "Pay the amount you owe by the due date on the notice.",
      "Make a payment plan (including an installment agreement) if you cannot pay the full amount.",
      "Contact the IRS if you disagree with the notice.",
    ],
    documents_usually_needed: [
      "The CP14 notice (include the bottom part of the notice if you mail a payment)",
      "Proof of any payment already sent",
      "Your return and payment records if you disagree",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp14-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP501",
    agency: "IRS",
    name: "First reminder of balance due",
    urgency: "med",
    what_it_means:
      "This is a reminder that you owe a balance on a tax account. The IRS has not received your payment or a response to the previous notice asking you to pay.",
    deadline_rule:
      "Pay the amount you owe by the due date shown on the notice.",
    options: [
      "Pay the amount you owe by the due date shown on the notice (online or by mail in the envelope sent with the notice; include the bottom part of the notice).",
      "Apply online for a payment plan, or mail Form 9465, Installment Agreement Request, if you cannot pay in full.",
      "If you disagree, call the toll-free number on the notice immediately and have supporting paperwork ready (cancelled checks, amended return, and similar records).",
      "You may request an appeal under the Collection Appeals Program before collection action, following the instructions on the notice.",
    ],
    documents_usually_needed: [
      "The CP501 notice and the earlier bill it refers to",
      "Proof of payments already made (cancelled checks or similar)",
      "Form 9465 if you are asking for an installment agreement",
      "Form 1040-X if you need to correct the return",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp501-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP503",
    agency: "IRS",
    name: "Second reminder of balance due",
    urgency: "high",
    what_it_means:
      "This is the second reminder that you still have an unpaid balance. The IRS has not received your payment or a response to earlier notices. If you do not pay, arrange a plan, or call, the IRS may file a Notice of Federal Tax Lien.",
    deadline_rule:
      "Pay the entire balance by the due date shown on the notice to avoid additional penalties and interest.",
    options: [
      "Pay the amount you owe by the due date shown on the notice.",
      "Apply online for a payment plan, or mail an installment-agreement request, if you cannot pay in full.",
      "If you disagree, call the toll-free number on the notice immediately.",
      "If you already paid or arranged a plan, still call so the account is updated.",
    ],
    documents_usually_needed: [
      "The CP503 notice and prior balance-due notices",
      "Proof of payments or an installment-agreement request",
      "Records if you disagree with the balance",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp503-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP504",
    agency: "IRS",
    name: "Notice of intent to levy",
    urgency: "high",
    what_it_means:
      "The IRS has not received payment of your unpaid balance. This is a Notice of Intent to Levy under Internal Revenue Code section 6331(d). If you do not pay immediately, the IRS can levy income and bank accounts and seize property, including a state income-tax refund. The notice also explains passport denial or revocation for seriously delinquent tax debt.",
    deadline_rule:
      "Pay the amount shown on the notice immediately, or contact the IRS immediately to discuss a plan or a disagreement.",
    options: [
      "Pay the amount shown on the notice immediately (online or by mail; include the bottom part of the notice).",
      "If you cannot pay in full, pay what you can now and contact the IRS at the toll-free number on the notice, or apply online for an installment agreement.",
      "If you disagree, contact the IRS immediately at the toll-free number on the notice.",
      "If you already paid or have an installment agreement, still call so the account reflects it.",
    ],
    documents_usually_needed: [
      "The CP504 notice",
      "Proof of the balance and any payments already made",
      "Installment-agreement or financial information if you cannot pay in full",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp504-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP11",
    agency: "IRS",
    name: "Math or clerical error — you owe",
    urgency: "med",
    what_it_means:
      "The IRS corrected one or more mistakes on your tax return. As a result, the amount you owe has changed.",
    deadline_rule:
      "If you disagree, contact the IRS by the date shown on the notice. If you miss that date you lose formal rights to have the change reversed and to appeal to U.S. Tax Court. To avoid extra interest, pay in full by the due date on the notice.",
    options: [
      "If you agree: pay the amount owed by the date shown on the notice, or arrange to pay over time. Correct your copy of the return; do not send that copy in.",
      "If you disagree: contact the IRS by the date shown on the notice at the toll-free number in the “Where to find more information” section. The IRS says the fastest way to resolve many return errors is by telephone.",
      "Fax a missing or corrected form while on that call if the IRS asks for it.",
    ],
    documents_usually_needed: [
      "The CP11 notice",
      "Your original return and the workpapers for the figure you filed",
      "Any missing or corrected form the IRS asks for",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp11-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP12",
    agency: "IRS",
    name: "Math or clerical error — refund changed",
    urgency: "low",
    what_it_means:
      "The IRS corrected one or more mistakes on your tax return. You are now due a refund, or your original refund amount has changed.",
    deadline_rule:
      "If you agree, no response is required. If you disagree, contact the IRS by the date shown on the notice. If you miss that date you lose formal rights to have the change reversed and to appeal to U.S. Tax Court.",
    options: [
      "If you agree with the changes, no response is required. You should receive a refund check in 4–6 weeks unless you owe other tax or debts the IRS must collect.",
      "Correct the copy of your return that you kept; do not send that copy to the IRS.",
      "If you disagree, contact the IRS by the date indicated at the number shown on the notice. The IRS will reverse most changes that reduced the refund you requested; supporting documents can help, and if the IRS does not receive information that supports your original return it may forward the case for audit.",
    ],
    documents_usually_needed: [
      "The CP12 notice",
      "Your original return and workpapers for the refund figure you filed",
      "Any supporting documents if you ask the IRS to reverse the change",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp12-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP21A",
    agency: "IRS",
    name: "Data processing adjustment — you owe",
    urgency: "med",
    what_it_means:
      "The IRS made changes to your tax return. You owe because of those changes.",
    deadline_rule:
      "If you agree, pay the amount you owe by the date printed on the notice. Interest accrues if you do not pay in full by the date on the payment coupon.",
    options: [
      "If you agree, pay the amount you owe by the date printed on the notice.",
      "If you cannot pay in full, explore a payment plan, a temporary collection delay, or an offer in compromise. Correct your copy of the return for your records.",
      "If you disagree, contact the IRS at the number on the notice. Have a copy of the notice and your tax return when you call.",
      "If you need another correction to the account, file Form 1040-X.",
    ],
    documents_usually_needed: [
      "The CP21A notice",
      "Your tax return for the year on the notice",
      "Proof of the item the IRS adjusted",
      "Form 1040-X if you need a further correction",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp21a-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP22A",
    agency: "IRS",
    name: "Data processing adjustment — balance due",
    urgency: "med",
    what_it_means:
      "The IRS made changes to your tax return. You owe because of those changes.",
    deadline_rule:
      "If you agree, pay the amount you owe by the date printed on the notice. Interest accrues if you do not pay in full by the date on the payment coupon.",
    options: [
      "If you agree, pay the amount you owe by the date printed on the notice.",
      "If you cannot pay in full, explore a payment plan, a temporary collection delay, or an offer in compromise. Correct your copy of the return for your records.",
      "If you disagree, contact the IRS at the number on the notice.",
    ],
    documents_usually_needed: [
      "The CP22A notice",
      "Your tax return for the year on the notice",
      "Proof of the item the IRS adjusted",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp22a-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP161",
    agency: "IRS",
    name: "Unpaid balance due",
    urgency: "med",
    what_it_means:
      "You have an unpaid balance due. The notice explains how the IRS calculated the amount and lists payments it applied.",
    deadline_rule:
      "Contact the IRS within 10 days of the date of the notice if you think it made a mistake. Pay the amount due by the date on the notice.",
    options: [
      "Read the notice and compare the figures with your tax return.",
      "Check the list of payments applied; contact the IRS within 10 days of the notice date if you think it made a mistake.",
      "Pay the amount due by the date on the notice.",
      "Contact the IRS to make payment arrangements if you cannot pay in full.",
      "If you disagree, call the toll-free number on the notice with cancelled checks, an amended return, or similar records ready.",
    ],
    documents_usually_needed: [
      "The CP161 notice",
      "Your tax return for that year",
      "Proof of payments you made (cancelled checks or similar)",
      "Form 9465 if you are requesting an installment agreement",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp161-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP2100",
    agency: "IRS",
    name: "Missing or incorrect payee taxpayer identification numbers",
    urgency: "med",
    aliases: ["CP2100A"],
    what_it_means:
      "A payee’s name and taxpayer identification number on an information return you filed is missing or does not match IRS records. You may need to begin backup withholding. CP2100 is issued when 50 or more information returns have errors; CP2100A when fewer than 50. The instructions are the same.",
    deadline_rule:
      "For a missing or obviously incorrect TIN, begin backup withholding immediately. For a name/TIN mismatch that matches your records, send the appropriate B-notice immediately; if the payee does not respond, begin backup withholding no later than 30 business days after you received the CP2100 or CP2100A. Stop backup withholding no later than 30 calendar days after you receive the payee’s TIN.",
    options: [
      "For missing or obviously incorrect TINs: begin backup withholding immediately if you have not already, and make up to three TIN requests (initial, first annual, second annual) to avoid a penalty for omitting a TIN.",
      "For incorrect TINs that do not match IRS records: compare your payee records to the notice list. If they match, send the appropriate B-notice. If they do not match, correct or update your records only; do not call or write the IRS to say you corrected them.",
      "Report backup withholding on Form 945 using the same name and EIN you used on the information returns. The backup withholding rate stated on the IRS page is 24%.",
    ],
    documents_usually_needed: [
      "The CP2100 or CP2100A notice and the list of missing, incorrect, or not currently issued payee TINs",
      "Your payee records and the Forms 1099 as filed",
      "Publication 1281 (B-notice copies and backup-withholding instructions)",
      "Form 945 to report backup withholding collected",
      "Form 8822-B if you need to update the business mailing address",
    ],
    source_url:
      "https://www.irs.gov/individuals/understanding-your-cp2100-or-cp2100a-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "LT11",
    agency: "IRS",
    name: "Final notice of intent to levy (Letter 1058)",
    urgency: "high",
    aliases: ["Letter 1058", "LTR11", "LT 11"],
    what_it_means:
      "The IRS has not received payment for overdue taxes and intends to seize your property or rights to property. You must contact the IRS immediately. This is also issued as Letter 1058.",
    deadline_rule:
      "Contact the IRS immediately. Request a Collection Due Process hearing by following the instructions on the letter. The IRS page does not print a day count; use the hearing deadline stated on the LT11 / Letter 1058 you hold.",
    options: [
      "Pay the unpaid balance in full (online or as the letter directs).",
      "If you cannot pay in full, pay what you can now and, if you are current on filings, request an installment agreement (the IRS page says the Online Payment Agreement tool is the fastest route if you owe less than $50,000).",
      "If you already paid in full or think a payment was not credited, send proof of that payment to the address at the top of the notice.",
      "Request an appeal of the proposed levy by following the letter’s instructions. You may request a Collection Due Process hearing; see the letter for directions. Form 12153 is the CDP / equivalent-hearing request.",
    ],
    documents_usually_needed: [
      "The LT11 notice or Letter 1058",
      "Proof of any payment already made",
      "Form 12153 if you are requesting a Collection Due Process or equivalent hearing",
      "Publication 1660, Collection Appeal Rights, and financial information if you are asking for a plan or currently-not-collectible status",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-lt11-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "LT16",
    agency: "IRS",
    name: "Collection — unpaid tax and/or missing returns",
    urgency: "high",
    what_it_means:
      "The IRS is trying to collect unpaid taxes from you and/or its files show missing tax returns.",
    deadline_rule:
      "File any missing returns as soon as possible and pay the unpaid balance (interest and penalties stop being added when the balance is paid in full). If you paid in full within the last 21 days, disregard the LT16. If it has been over 10 weeks since you sent a missing return, send a signed copy again.",
    options: [
      "File any missing tax returns the notice lists.",
      "Pay the unpaid balance in full.",
      "If you cannot pay in full: pay as much as you can now and set up an installment agreement. You must be current on filings to apply.",
      "If you are facing financial hardship, contact the IRS about currently-not-collectible status (have income, expenses, and asset information ready) or check the Offer in Compromise pre-qualifier.",
      "If the tax is in doubt or you cannot resolve a disagreement, you are entitled to a hearing with the Office of Appeals (see Publication 1660).",
    ],
    documents_usually_needed: [
      "The LT16 notice",
      "Signed copies of any missing returns the notice lists",
      "Proof of payments made in the last 21 days if you already paid",
      "An installment-agreement request if you cannot pay in full",
      "Proof of income, expenses, and assets if you are claiming hardship",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-lt16-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP49",
    agency: "IRS",
    name: "Overpayment applied to other debts",
    urgency: "low",
    what_it_means:
      "The IRS used all or part of your refund to pay a tax debt.",
    deadline_rule:
      "The IRS page does not state a protest clock. If you still owe after the offset, pay or set a plan. If you already paid the full balance in the past 21 days, verify the account; a remaining credit is refunded if you owe nothing else the IRS must collect.",
    options: [
      "If you still owe money after the refund was applied, pay the remaining balance or apply for a payment plan. If you already have a payment plan for that tax year, continue making the payments.",
      "If you do not owe the tax (for example a spouse’s debt took part of a joint refund), you may claim your share by filing Form 8379, Injured Spouse Allocation.",
      "If you already have a payment arrangement for the unpaid balance, the IRS page says to disregard the notice.",
      "If you paid the full balance in the past 21 days and then received this notice, verify the account at the number on the notice.",
    ],
    documents_usually_needed: [
      "The CP49 notice",
      "Records of the debt the IRS says it paid",
      "Form 8379 if you are claiming injured-spouse relief",
      "Proof of a payment made in the past 21 days if you already paid",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp49-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
  {
    code: "CP59",
    agency: "IRS",
    name: "Return delinquency — no record of a prior-year return",
    urgency: "high",
    what_it_means:
      "The IRS has no record that you filed your prior-year personal tax return.",
    deadline_rule:
      "File the personal tax return immediately, or explain why you do not need to file. If you filed within the last eight weeks, you do not have to do anything. If you do not file, you may lose a refund or certain credits because of statutory time limits; if you owe, penalties and interest continue until you file and pay.",
    options: [
      "File your personal tax return immediately, and include any IRS-issued IP PIN. On a joint return include each spouse’s IP PIN.",
      "If you believe the IRS made a mistake, complete and mail, fax, or upload Form 15103, Form 1040 Return Delinquency.",
      "If you have not filed, or it has been more than eight weeks since you filed: check that the name, SSN or TIN, and tax year on the notice match the return, then mail a signed and dated copy. Confirm the original was not rejected.",
      "If you owe when you file and cannot pay in full, request a payment plan.",
      "Bona fide residents of certain U.S. territories who filed with a territory tax office should contact that office; they may need to send a territory tax transcript.",
    ],
    documents_usually_needed: [
      "The CP59 notice",
      "A signed and dated copy of the prior-year return, with any required IP PIN",
      "Form 15103 if you believe you did not have a filing requirement or the IRS made a mistake",
      "A territory tax transcript if you filed with a U.S. territory tax office",
    ],
    source_url: "https://www.irs.gov/individuals/understanding-your-cp59-notice",
    letter_skeleton: "",
    verified_against_source: true,
  },
];

export { DISCLAIMER, IRS_GENERAL_LOOKUP, NOT_COVERED_MESSAGE, NOTICES };

export function asList(notices) {
  if (notices == null) return NOTICES;
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

function allCodes(entry) {
  const extra = Array.isArray(entry.aliases) ? entry.aliases : [];
  return [entry.code, ...extra];
}

function looksLikeCode(raw) {
  return raw.length >= 3 && !/\s/.test(raw) && /^[A-Za-z]{1,10}[0-9A-Za-z]{1,10}$/.test(raw);
}

/**
 * Best entry for a pasted notice or a code.
 * Exact code match first (including aliases). An unknown bare code is not guessed.
 * Then a code pattern in pasted text, then keyword score.
 * Returns the entry or null.
 */
export function identify(textOrCode, notices) {
  const raw = String(textOrCode || "").trim();
  if (!raw) return null;
  const list = asList(notices);
  if (!list.length) return null;

  const whole = codeKey(raw);
  if (looksLikeCode(raw) || (whole.length >= 3 && !/\s/.test(raw))) {
    const exact = list.find((e) => allCodes(e).some((c) => codeKey(c) === whole));
    if (exact) return exact;
    if (!/\s/.test(raw)) return null;
  }

  const byLen = [...list].sort((a, b) => {
    const maxA = Math.max(...allCodes(a).map((c) => codeKey(c).length));
    const maxB = Math.max(...allCodes(b).map((c) => codeKey(c).length));
    return maxB - maxA;
  });
  for (const entry of byLen) {
    for (const code of allCodes(entry)) {
      const re = codePattern(code);
      if (re && re.test(raw)) return entry;
    }
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
    documents: [...(entry.documents_usually_needed || [])],
    source_url: entry.source_url || "",
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
    letter_skeleton: entry.letter_skeleton || "",
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
 * There is no generic skeleton in the builtin catalog, so this returns
 * an empty string unless a caller supplies a notice-specific skeleton.
 */
export function letter(entry, facts = {}) {
  if (!entry) return "";
  const skeleton = String(entry.letter_skeleton || "");
  if (!skeleton.trim()) return "";
  const data = {
    code: entry.code,
    agency: entry.agency,
    name: entry.name,
    deadline_rule: entry.deadline_rule,
    disclaimer: DISCLAIMER,
    ...facts,
  };
  return skeleton.replace(PLACEHOLDER, (_, key) => {
    const v = data[key] ?? data[key.toLowerCase()];
    return v == null ? "" : String(v);
  });
}

export function letterPack(entry, facts = {}) {
  if (!entry) return null;
  const text = letter(entry, facts);
  return {
    letter_text: text,
    checklist: [
      "Read the date printed on your notice. Use that date, not a guess.",
      "Match the tax year and the amount on the notice to your records.",
      "Use only the response options the IRS lists for this notice.",
      "Attach copies, not originals, of the papers listed for this notice.",
      "Keep a copy of what you send and the proof of mailing.",
      DISCLAIMER,
    ],
    enclosures: [...(entry.documents_usually_needed || [])],
  };
}

/**
 * Honest lookup. Unknown codes are not covered and never get a letter.
 */
export function resolve(textOrCode, notices) {
  const raw = String(textOrCode || "").trim();
  const entry = identify(raw, notices);
  if (!entry) {
    return {
      covered: false,
      query: raw,
      message: NOT_COVERED_MESSAGE,
      irs_lookup: IRS_GENERAL_LOOKUP,
      letter: "",
    };
  }
  return {
    covered: true,
    query: raw,
    entry,
    explanation: explain(entry),
    pack: letterPack(entry),
    letter: letter(entry),
  };
}
