#!/usr/bin/env python3
"""Offline self-test for the la-appeal-packet family. Exit 0 = pass.

Known-good: 5980 W 75th St 90045 (AIN 4104011015) must yield >= 3 support rows.
Known-bad: an address the county map does not hold, a subject with too few
neighbours, an outlier that must be dropped, and a page that must never print
a person's name or email.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fulfil as F  # noqa: E402

FIX = HERE / "fixtures" / "parcels-90045.json"
FAILS: list[str] = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
    return cond


def main() -> int:
    src = F.Source(str(FIX))
    check(src.offline, "fixture source must be offline")

    # module constants the delivery rail reads
    check(F.FAMILY == "la-appeal-packet", "FAMILY")
    check(F.LINK_ID_ENV_OR_CATALOG == "la-appeal-packet", "LINK_ID_ENV_OR_CATALOG")
    check(isinstance(F.ETA_MINUTES, int) and 1 <= F.ETA_MINUTES <= 1440, "ETA_MINUTES int in range")
    tree = ast.parse((HERE / "fulfil.py").read_text(encoding="utf-8"))
    eta_literal = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "ETA_MINUTES" for t in n.targets)]
    check(eta_literal and isinstance(eta_literal[0].value, ast.Constant), "ETA_MINUTES is a literal")

    # custom field shape (Stripe custom_fields)
    cf = json.loads((HERE / "custom_fields.json").read_text(encoding="utf-8"))
    check(isinstance(cf, list) and len(cf) == 1, "one custom field")
    f0 = cf[0] if cf else {}
    check(f0.get("key") == "address" and f0.get("type") == "text" and f0.get("optional") is False, "address field required text")
    check(len(f0.get("label", {}).get("custom", "")) <= 50, "label <= 50 chars")
    check(f0.get("text", {}).get("maximum_length", 0) >= 60, "max length >= 60")

    # address parsing
    p = F.parse_address("5980 W 75th St, Los Angeles, CA 90045")
    check(p["ok"] and p["house"] == "5980" and p["direction"] == "W" and p["street"] == "75TH"
          and p["suffix"] == "ST" and p["zip"] == "90045", "parse full address: %r" % p)
    p2 = F.parse_address("8017 Kentwood Avenue Los Angeles")
    check(p2["ok"] and p2["street"] == "KENTWOOD" and p2["suffix"] == "AVE" and p2["zip"] == "", "parse no zip: %r" % p2)
    p3 = F.parse_address("5980 W 75 St")
    check(p3["street"] == "75TH", "bare number street becomes ordinal: %r" % p3)
    p4 = F.parse_address("Kentwood Ave")
    check(not p4["ok"], "no house number -> not ok")
    p5 = F.parse_address("")
    check(not p5["ok"], "empty -> not ok")

    # session field reading, both shapes
    sess = json.loads((HERE / "fixtures" / "session_paid.json").read_text(encoding="utf-8"))
    check(F.typed_address(sess).startswith("5980 W 75th St"), "typed address from list shape")
    check(F.typed_address({"custom_fields": {"address": " 1 MAIN ST "}}) == "1 MAIN ST", "typed address from dict shape")
    check(F.fulfil({}) is None, "no session id -> None")

    # known-good: full packet
    html_out, packet = F.build_for_address(F.typed_address(sess), src, fetched="2026-09-09")
    check(packet is not None, "known-good packet built")
    if packet:
        s = packet["subject"]
        check(s["ain"] == "4104011015", "subject AIN")
        check(s["address"] == "5980 W 75TH ST" and s["zip"] == "90045", "subject street-only + zip")
        check(s["total"] == 649310, "subject roll total")
        rows = packet["support_rows"]
        check(len(rows) >= F.MIN_COMPS, "known-good >= %d rows (got %d)" % (F.MIN_COMPS, len(rows)))
        check(len(rows) <= F.MAX_COMPS, "<= max rows")
        check(packet["enough_support"], "enough_support true")
        check(all(r["ain"] != s["ain"] for r in rows), "subject never in support rows")
        check(all(r["base_year"] in F.BASE_YEARS for r in rows), "base years recent")
        check(all(r["recorded_in"] == str(int(r["base_year"]) - 1) for r in rows), "recorded_in = base year - 1")
        check(all(r["distance_m"] <= F.RADIUS_M for r in rows), "within radius")
        check(all(abs(r["sqft"] - s["sqft"]) <= F.SIZE_TOL * s["sqft"] for r in rows), "within size tolerance")
        check(all(r["enrolled_total"] == r["land"] + r["improvements"] for r in rows), "total = land + imp")
        by = [F.BASE_YEARS.index(r["base_year"]) for r in rows]
        check(by == sorted(by), "base year 2026 rows first")
        for i in range(1, len(rows)):
            if rows[i]["base_year"] == rows[i - 1]["base_year"]:
                check(rows[i]["distance_m"] >= rows[i - 1]["distance_m"], "nearest first within base year")
        check(all(re.match(r"^\d{5}$", r["zip"]) for r in rows), "zip is 5 digits")
        check(all(not re.search(r"\b(LOS ANGELES|CA)\b", r["address"]) for r in rows), "address column is street-only")
        # determinism
        html2, packet2 = F.build_for_address(F.typed_address(sess), src, fetched="2026-09-09")
        check(json.dumps(packet2, sort_keys=True) == json.dumps(packet, sort_keys=True), "deterministic")
        # rendering rules
        check(html_out.count("<h1") == 1, "one h1 in private page")
        check(all("not a confirmed sale price" in r["what_this_is"] for r in rows), "every row labelled not-a-confirmed-sale")
        check("confirmed sale" not in re.sub(r"not (a )?confirmed sale", "", html_out.lower()), "no row presented as a confirmed sale")
        check("assessor-enrolled value" in json.dumps(packet), "values labelled as enrolled")
        check("not a valuation" in html_out, "not-a-valuation line present")
        check("legal or tax advice" in html_out, "not-advice line present")
        check(F.CITATION in html_out, "citation present")
        check("@" not in re.sub(r"operations@ustechautomations\.com", "", html_out), "no email other than ours")
        for banned in ("Owner", "OWNER_NAME", "Taxpayer", "TaxpayerName", "MailAddress"):
            check(banned not in json.dumps(packet), "no %s field in packet" % banned)
        check("Get Started" not in html_out and "SOC 2" not in html_out, "no forbidden marketing phrases")
        check(re.search(r"style=\"[^\"]*(#[0-9a-fA-F]{3,8}|rgb\(|hsl\()", html_out) is None, "no colour literals inline")
        check("<script" not in html_out.lower(), "no scripts in private page")

    # known-bad 1: unknown address -> honest not-found page, no support rows
    html_nf, packet_nf = F.build_for_address("99999 Nowhere Blvd, Los Angeles, CA 90045", src)
    check(packet_nf is None, "unknown address -> no packet")
    check("could not match" in html_nf.lower(), "not-found page says so")
    check("operations@ustechautomations.com" in html_nf, "not-found page gives the mailbox")

    # known-bad 2: outlier must be dropped
    rows_all = src._fixture_rows()
    subj = next(r for r in rows_all if str(r["AIN"]) == "4104011015")
    fake = dict(subj, AIN="9999999999", Roll_LandBaseYear="2026", Roll_ImpBaseYear="2026",
                Roll_LandValue=10000, Roll_ImpValue=5000, SQFTmain1=subj["SQFTmain1"], UseCode="0100",
                CENTER_LAT=subj["CENTER_LAT"] + 0.0005, CENTER_LON=subj["CENTER_LON"], SitusUnit="", SitusDirection="W")
    sel = F.select_comps(subj, rows_all + [fake])
    check(all(str(c["AIN"]) != "9999999999" for c in sel["comps"]), "outlier (very low $/sqft) excluded")
    check(any("under half" in k for k in sel["dropped"]), "outlier drop reason recorded")

    # known-bad 3: condo / unit / mixed base years excluded
    for bad_key, bad_val, why in (("UseCode", "010C", "condo code excluded"), ("SitusUnit", "3", "unit excluded"),
                                  ("Roll_ImpBaseYear", "1999", "mixed base years excluded"), ("Units1", 2, "duplex excluded"),
                                  ("SQFTmain1", 0, "zero sqft excluded")):
        bad = dict(fake, Roll_LandValue=800000, Roll_ImpValue=700000)
        bad[bad_key] = bad_val
        sel_b = F.select_comps(subj, [bad])
        check(not sel_b["comps"], why)

    # known-bad 4: too few neighbours -> page says not enough support, no padding
    near = [r for r in rows_all if str(r["AIN"]) != "4104011015"][:0]
    sel_c = F.select_comps(subj, near)
    pk = F.build_packet(subj, sel_c, "5980 W 75TH ST", fetched="2026-09-09", offline=True)
    check(pk["enough_support"] is False and pk["support_rows"] == [], "zero neighbours -> not enough support")
    h = F.render_packet_html(pk)
    check("0 support rows" in h, "zero-row page says 0 support rows")
    check("Arithmetic reference" not in h, "no arithmetic reference without rows")

    # known-bad 5: a fixture row with a unit in the full address is normalised
    r = F.normalise_row({"SitusFullAddress": "123 W MAIN ST 4 LOS ANGELES CA 90045", "SitusHouseNo": "123",
                         "SitusStreet": "MAIN ST"})
    check(r["SitusDirection"] == "W" and r["SitusUnit"] == "4", "normalise picks direction and unit: %r" % r)

    if FAILS:
        print("FAIL %d" % len(FAILS))
        for f in FAILS:
            print(" -", f)
        return 1
    print("ok la-appeal-packet selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
