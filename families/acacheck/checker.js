/*
 * acacheck browser checker -- a light, free subset of the same idea as the
 * open-source `loops/aca` Python tool: paste a 1094-C/1095-C XML file and
 * see, in plain English, some of what is likely to trip up the IRS.
 *
 * Rules on purpose:
 *   - Everything runs in your browser. Nothing you paste is sent anywhere,
 *     ever -- there is no fetch(), no XMLHttpRequest, no network call at
 *     all in this file.
 *   - This is a smaller set of checks than the full open-source tool (15
 *     checks here vs. 46 in the Python package). It is meant to give you a
 *     fast first look, not to replace running the real thing before you
 *     transmit.
 *   - This is a pre-checker, not a filing agent: the IRS decides.
 */
(function () {
  "use strict";

  // ===========================================================================
  // small XML helpers -- namespace-tolerant, matches on local element name
  // ===========================================================================

  function findAll(root, name, out) {
    out = out || [];
    if (!root) return out;
    var kids = root.children || [];
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i];
      if (el.localName === name) out.push(el);
      findAll(el, name, out);
    }
    return out;
  }

  function findOne(root, name) {
    var all = findAll(root, name);
    return all.length ? all[0] : null;
  }

  function textOf(el) {
    return el && el.textContent != null ? el.textContent.trim() : "";
  }

  function childText(el, name) {
    return textOf(el ? findOne(el, name) : null);
  }

  function finding(id, severity, message, fix) {
    return { id: id, severity: severity, message: message, fix: fix };
  }

  // ===========================================================================
  // the 15 checks -- each pushes 0 or more findings onto `out`
  // ===========================================================================

  var EIN_RE = /^\d{9}$/;
  var SSN_RE = /^\d{9}$/;
  var ZIP_RE = /^\d{5}(\d{4})?$/;
  var YEAR_RE = /^\d{4}$/;
  var OFFER_CODE_RE = /^1[A-U]$/;
  var SAFE_HARBOR_RE = /^2[A-I]$/;

  function isAllSameDigit(s) {
    return /^(\d)\1+$/.test(s);
  }

  function checkManifest(doc, out) {
    if (!findOne(doc.documentElement, "Manifest")) {
      out.push(finding("AC03", "error",
        "There is no Manifest section.",
        "Add a Manifest element with the tax year and record count."));
    }
  }

  function checkForm1094C(doc, out) {
    var all = findAll(doc.documentElement, "Form1094C");
    if (all.length === 0) {
      out.push(finding("AC04", "error",
        "There is no Form1094C (the transmittal form) in this file.",
        "Every transmission needs exactly one Form1094C."));
    } else if (all.length > 1) {
      out.push(finding("AC05", "error",
        "There is more than one Form1094C in this file (" + all.length + " found).",
        "A single transmission should carry exactly one Form1094C."));
    }
    return all[0] || null;
  }

  function checkForm1095CPresent(doc, out) {
    var all = findAll(doc.documentElement, "Form1095C");
    if (all.length === 0) {
      out.push(finding("AC06", "error",
        "There are no Form1095C records (the per-employee forms) in this file.",
        "Add at least one Form1095C record."));
    }
    return all;
  }

  function checkEmployerEin(doc, out, form1094c) {
    if (!form1094c) return;
    var ein = childText(form1094c, "EmployerEIN");
    if (!ein) {
      out.push(finding("AC07", "error",
        "The employer's EIN is missing from Form1094C.",
        "Add EmployerEIN as a 9-digit number."));
    } else if (!EIN_RE.test(ein) || isAllSameDigit(ein)) {
      out.push(finding("AC08", "error",
        "The employer's EIN '" + ein + "' does not look right.",
        "Enter the EIN as exactly 9 digits, no dashes, and not all the same digit (like 00-0000000)."));
    }
  }

  function checkEmployerName(doc, out, form1094c) {
    if (!form1094c) return;
    if (!childText(form1094c, "EmployerName")) {
      out.push(finding("AC09", "error",
        "The employer's name is missing from Form1094C.",
        "Add EmployerName."));
    }
  }

  function checkTaxYear(doc, out, form1094c) {
    if (!form1094c) return;
    var year = childText(form1094c, "TaxYr");
    if (!year) {
      out.push(finding("AC10", "error",
        "The tax year is missing from Form1094C.",
        "Add a 4-digit TaxYr, like 2025."));
    } else if (!YEAR_RE.test(year)) {
      out.push(finding("AC10", "error",
        "The tax year '" + year + "' is not a plain 4-digit year.",
        "Use a 4-digit year, like 2025."));
    }
  }

  function checkFormCount(doc, out, form1094c, all1095c) {
    if (!form1094c) return;
    var claimed = childText(form1094c, "TotalNumberOf1095CFormsFiledCnt");
    if (!claimed) return;
    var claimedNum = parseInt(claimed, 10);
    if (!isNaN(claimedNum) && claimedNum !== all1095c.length) {
      out.push(finding("AC11", "error",
        "Form1094C says " + claimedNum + " Form1095C record(s) were filed, but this file has " + all1095c.length + ".",
        "Make TotalNumberOf1095CFormsFiledCnt match the number of Form1095C records actually in the file."));
    }
  }

  function checkEmployeeSsn(doc, out, form1094c, all1095c) {
    var bad = [];
    for (var i = 0; i < all1095c.length; i++) {
      var ssn = childText(all1095c[i], "EmployeeSSN");
      if (ssn && (!SSN_RE.test(ssn) || isAllSameDigit(ssn))) bad.push(ssn);
    }
    if (bad.length) {
      out.push(finding("AC12", "error",
        "One or more employee SSNs are not 9 plain digits (example: '" + bad[0] + "').",
        "Enter each employee's SSN as exactly 9 digits, no dashes."));
    }
  }

  function checkOfferCode(doc, out, form1094c, all1095c) {
    var bad = [];
    for (var i = 0; i < all1095c.length; i++) {
      var codes = findAll(all1095c[i], "OfferCode");
      for (var j = 0; j < codes.length; j++) {
        var v = textOf(codes[j]);
        if (v && !OFFER_CODE_RE.test(v)) bad.push(v);
      }
    }
    if (bad.length) {
      out.push(finding("AC13", "error",
        "One or more offer-of-coverage codes are not valid (example: '" + bad[0] + "').",
        "Offer codes must be 1A through 1U."));
    }
  }

  function checkSafeHarborCode(doc, out, form1094c, all1095c) {
    var bad = [];
    for (var i = 0; i < all1095c.length; i++) {
      var codes = findAll(all1095c[i], "SafeHarborCode");
      for (var j = 0; j < codes.length; j++) {
        var v = textOf(codes[j]);
        if (v && !SAFE_HARBOR_RE.test(v)) bad.push(v);
      }
    }
    if (bad.length) {
      out.push(finding("AC14", "error",
        "One or more safe-harbor codes are not valid (example: '" + bad[0] + "').",
        "Safe-harbor codes must be 2A through 2I, or left blank."));
    }
  }

  function checkZip(doc, out) {
    var bad = [];
    var zips = findAll(doc.documentElement, "ZipCd");
    for (var i = 0; i < zips.length; i++) {
      var v = textOf(zips[i]);
      if (v && !ZIP_RE.test(v)) bad.push(v);
    }
    if (bad.length) {
      out.push(finding("AC15", "error",
        "One or more ZIP codes are not 5 or 9 digits (example: '" + bad[0] + "').",
        "Use a 5-digit ZIP, or 9 digits with no dash."));
    }
  }

  /**
   * Run every check against XML text. Never throws. Returns
   * { ok, findings, wellFormed }.
   */
  function checkAcaXml(text) {
    var findings = [];
    if (!text || !text.trim()) {
      findings.push(finding("AC02", "error",
        "There is nothing to check -- the box is empty.",
        "Paste your 1094-C/1095-C XML file's contents into the box."));
      return { ok: false, findings: findings, wellFormed: false };
    }

    var doc;
    try {
      var parser = new DOMParser();
      doc = parser.parseFromString(text, "text/xml");
      var perr = doc.getElementsByTagName("parsererror");
      if (!doc.documentElement || (perr && perr.length)) {
        throw new Error("not well-formed");
      }
    } catch (e) {
      findings.push(finding("AC01", "error",
        "This file is not well-formed XML, so it cannot be read at all.",
        "Open the file in a text editor and look for an unclosed tag or a stray character near the start."));
      return { ok: false, findings: findings, wellFormed: false };
    }

    try {
      checkManifest(doc, findings);
      var form1094c = checkForm1094C(doc, findings);
      var all1095c = checkForm1095CPresent(doc, findings);
      checkEmployerEin(doc, findings, form1094c);
      checkEmployerName(doc, findings, form1094c);
      checkTaxYear(doc, findings, form1094c);
      checkFormCount(doc, findings, form1094c, all1095c);
      checkEmployeeSsn(doc, findings, form1094c, all1095c);
      checkOfferCode(doc, findings, form1094c, all1095c);
      checkSafeHarborCode(doc, findings, form1094c, all1095c);
      checkZip(doc, findings);
    } catch (e) {
      findings.push(finding("AC00", "error",
        "Something went wrong reading this file's structure.",
        "Double-check the file is a 1094-C/1095-C transmission and try again."));
    }

    return { ok: findings.length === 0, findings: findings, wellFormed: true };
  }

  // ===========================================================================
  // page wiring
  // ===========================================================================

  function renderResults(container, result) {
    container.innerHTML = "";
    if (result.findings.length === 0) {
      var ok = document.createElement("p");
      ok.className = "ac-ok";
      ok.textContent = "None of these 15 checks found a problem. The full open-source tool checks 46 things, so run that too before you transmit.";
      container.appendChild(ok);
      return;
    }
    var summary = document.createElement("p");
    summary.className = "ac-summary";
    summary.textContent = result.findings.length + " thing(s) this quick check did not like:";
    container.appendChild(summary);
    var list = document.createElement("ul");
    list.className = "ac-findings";
    result.findings.forEach(function (f) {
      var li = document.createElement("li");
      var msg = document.createElement("p");
      msg.className = "ac-msg";
      msg.textContent = "[" + f.id + "] " + f.message;
      var fix = document.createElement("p");
      fix.className = "ac-fix";
      fix.textContent = "Fix: " + f.fix;
      li.appendChild(msg);
      li.appendChild(fix);
      list.appendChild(li);
    });
    container.appendChild(list);
  }

  function init() {
    var input = document.getElementById("ac-input");
    var button = document.getElementById("ac-check");
    var demoButton = document.getElementById("ac-demo");
    var results = document.getElementById("ac-results");
    var demoScript = document.getElementById("ac-demo-xml");
    if (!input || !button || !results) return;

    button.addEventListener("click", function () {
      renderResults(results, checkAcaXml(input.value));
    });

    if (demoButton && demoScript) {
      demoButton.addEventListener("click", function () {
        input.value = demoScript.textContent.trim();
        renderResults(results, checkAcaXml(input.value));
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // exposed so this file's logic can be exercised outside a page too
  window.acacheckBrowserCheck = checkAcaXml;
})();
