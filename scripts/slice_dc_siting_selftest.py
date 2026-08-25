#!/usr/bin/env python3
"""Does the dc-siting sample hold datacenters, and only datacenters?

The rows in the NEGATIVE cases below are not invented. They are the real text of
the rows that were in the sample when it was marked `fail`: concrete batch
plants, a cotton gin, a hospital, sewage works and mines. If this file goes
green, those rows cannot come back.

Every fixture host is a reserved test name (`.test`), so nothing here can be
mistaken for a real agency address and no fixture needs a permission record.

Run:  python3 slice_dc_siting_selftest.py     (no network, no live database)
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# privacy.py lives in the feeds repo's scripts/ directory next to the slice.
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/gmullins/code/usta-paid-surfaces/scripts")

_spec = importlib.util.spec_from_file_location("slice_dc_siting", HERE / "slice_dc_siting.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILS.append(name)


# --------------------------------------------------------------------------
# The rows that were actually in the failed sample. Applicant, facility.
# --------------------------------------------------------------------------
REAL_BAD_ROWS = [
    ("MICHELS ROAD & STONE INC", "CONCRETE BATCH PLANT 1"),
    ("SUMMIT MATERIALS LLC", "QK - PORTABLE 868"),
    ("GCC SUN CITY MATERIALS LLC", "PROJECT MDD150"),
    ("BIG BEND CONCRETE CO", "TX-18"),
    ("CROELL INC", "HEREFORD PORTABLE CONCRETE BATCH PLANTS"),
    ("TIC-THE INDUSTRIAL COMPANY", "PORTABLE CONCRETE BATCH PLANTS 1 & 2"),
    ("TEXAS MATERIALS GROUP INC", "CONCRETE BATCH PLANT SN 15760526-576"),
    ("BIG CITY CRUSHED CONCRETE LLC", "FOREST CRUSHING PLANT 3062"),
    ("D&D READY MIX CONCRETE LLC", "D & D READY MIX - CBP1 & CBP2"),
    ("STANLEY BLACK & DECKER INC", "STANLEY MECHANICS TOOLS"),
    ("COOPER POWER SYSTEMS LLC", "COOPER POWER SYSTEMS"),
    # the cotton gin
    ("TAFT GIN AND SEED COMPANY INC", "TAFT GIN AND SEED"),
    ("Glenbar Investment Group Inc.", "GLENBAR GIN"),
    # the hospitals
    ("Hrmc, Llc", "HAVASU REGIONAL MEDICAL CENTER"),
    ("Department Of Veterans Affairs", "NORTHERN ARIZONA VA HEALTHCARE SYSTEM"),
    # the sewage works
    ("Town Of Jerome", "TOWN OF JEROME - WWTP"),
    ("City Of Yuma", "CITY OF YUMA - FIGUEROA AVE WPCF"),
    ("Town Of Miami", "MIAMI WASTEWATER RECLAMATION FACILITY"),
    ("City Of Benson", "CITY OF BENSON - WWTF"),
    # the mines
    ("Asarco Llc- Hayden Operations", "ASARCO - HAYDEN OPERATIONS"),
    ("Freeport-Mcmoran Morenci, Inc.", "FREEPORT-MCMORAN - MORENCI"),
    ("South32 Hermosa Inc.", "JANUARY ADIT (NORTON MINE)"),
    ("Nucor Steel Kingman, Llc", "NUCOR STEEL KINGMAN"),
    ("Safety-Kleen Systems, Inc", "SAFETY-KLEEN"),
]

# Real datacenter rows out of the same store.
REAL_GOOD_ROWS = [
    ("ALIGNED DATA CENTERS REIT LLC", "ADC PLANO"),
    ("CRUSOE ENERGY SYSTEMS LLC", "LONGHORN DATA CENTER"),
    ("CRUSOE ENERGY SYSTEMS LLC", "GOODNIGHT DATA CENTER"),
    ("NEXUS HUBBARD POWER, LLC", "NEXUS DATA CENTER HUBBARD"),
]

# The trap. Both name a datacenter and both are permits for a concrete plant.
# A plain keyword rule accepts these, which is how batch plants got in.
REAL_TRAP_ROWS = [
    ("AMRIZE SOUTH CENTRAL INC", "DPR DATA CENTER TEMPORARY BATCH PLANT"),
    ("VAN EATON READY MIX INC", "CEMCO-403 & 365 CBP CLOCKTOWER DATA CENTER"),
]

# Real FAA text where the datacenter word is only in the description.
REAL_FAA_ROWS = [
    ("Substation-1-A", "The nature of the proposed development is a warehouse for data "
                       "centers and the associated electrical substation."),
    ("C1", "The proposed project is located in Prince William County and consists of one "
           "two-story data center building of approximately 230,370 SF."),
    ("Crane_B_Point_1", "275ft AGL Mobile Crane being used for Construction of (2) Data "
                        "Center Buildings located in Fairfax County, Virginia."),
]
FAA_NOT_DC = [
    ("Verizon Monopole", "Replace an existing monopole with a 155ft self-support tower."),
    ("Grain Elevator Leg", "New grain leg at an existing elevator."),
]


def test_the_rule() -> None:
    print("the rule, judged on the agency's own words")
    bad_kept = [r for r in REAL_BAD_ROWS if S.is_datacenter_siting(*r)]
    check(f"all {len(REAL_BAD_ROWS)} rows from the failed sample are rejected",
          not bad_kept, f"kept {bad_kept}")

    good_dropped = [r for r in REAL_GOOD_ROWS if not S.is_datacenter_siting(*r)]
    check(f"all {len(REAL_GOOD_ROWS)} real datacenter permits are accepted",
          not good_dropped, f"dropped {good_dropped}")

    trap_kept = [r for r in REAL_TRAP_ROWS if S.is_datacenter_siting(*r)]
    check("datacenter-named concrete batch plants are still rejected",
          not trap_kept, f"kept {trap_kept}")

    # and prove the trap rows really do beat the naive rule, so this test is
    # about the fix and not about nothing.
    check("the naive keyword rule would have accepted those batch plants",
          all(S.names_datacenter(*r) for r in REAL_TRAP_ROWS))

    faa_dropped = [r for r in REAL_FAA_ROWS if not S.is_datacenter_siting(*r)]
    check("FAA rows whose only datacenter word is in the description are accepted",
          not faa_dropped, f"dropped {faa_dropped}")

    faa_kept = [r for r in FAA_NOT_DC if S.is_datacenter_siting(*r)]
    check("FAA rows about a mast or a grain elevator are rejected",
          not faa_kept, f"kept {faa_kept}")

    check("the batch-plant short form only fires as a whole word",
          not S.is_supply_plant("CBPX HOLDINGS", "SUBCBPUNIT DATA CENTER"))
    check("'data centre' spelled the British way is accepted",
          S.is_datacenter_siting("ACME LTD", "NORTHERN DATA CENTRE"))
    check("an empty row is rejected", not S.is_datacenter_siting("", None))
    check("why_not names the supply plant reason",
          "supply plant" in S.why_not(*REAL_TRAP_ROWS[0]))
    check("why_not names the missing-datacenter reason",
          "names a datacenter" in S.why_not(*REAL_BAD_ROWS[0]))


# --------------------------------------------------------------------------
# A fixture store. Reserved `.test` hosts only.
# --------------------------------------------------------------------------
def build_fixture(db: Path, *, tx_rows, az_rows, faa_rows) -> None:
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE application (source_id TEXT, app_id TEXT, snapshot_date TEXT, "
              "applicant TEXT, facility TEXT, permit_number TEXT, received_date TEXT, "
              "stage TEXT, doc_url TEXT)")
    c.execute("CREATE TABLE faa_case (source_id TEXT, asn TEXT, snapshot_date TEXT, "
              "status TEXT, entered_date TEXT, structure_name TEXT, city TEXT, state TEXT, "
              "proposal_description TEXT, structure_type TEXT, sponsor_name TEXT)")
    for i, (applicant, facility) in enumerate(tx_rows):
        c.execute("INSERT INTO application VALUES (?,?,?,?,?,?,?,?,?)",
                  ("tceq_nsr_pending", f"tx{i}", "2026-08-24", applicant, facility,
                   f"P{i:04d}", "01/15/2026", "Technically Complete Application",
                   f"https://permits.agency.test/doc/{i}.pdf"))
    for i, (applicant, facility) in enumerate(az_rows):
        c.execute("INSERT INTO application VALUES (?,?,?,?,?,?,?,?,?)",
                  ("adeq_pip_all", f"az{i}", "2026-08-13", applicant, facility,
                   f"A{i:04d}", "2026-01-15", "In Progress",
                   f"https://pip.agency.test/doc/{i}.json"))
    for i, (name, desc, sponsor) in enumerate(faa_rows):
        c.execute("INSERT INTO faa_case VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  ("faa_part77_ASW_2026", f"faa_part77_ASW_2026:2026-ASW-{i}-OE",
                   "2026-08-21", "Studying", "2026-08-01", name, "Testville", "TX",
                   desc, "CRANE", sponsor))
    c.commit()
    c.close()


def with_fixture(fn, **kw):
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "fixture.db"
        build_fixture(db, **kw)
        real, S.DB = S.DB, db
        try:
            return fn()
        finally:
            S.DB = real


def test_the_sample() -> None:
    print("the sample the buyer downloads")

    good_faa = [(n, d, None) for n, d in REAL_FAA_ROWS] * 3
    kw = dict(tx_rows=REAL_GOOD_ROWS + REAL_BAD_ROWS + REAL_TRAP_ROWS,
              az_rows=[("ARIZONA DC HOLDINGS LLC", "PHOENIX DATA CENTER ONE"),
                       ("ARIZONA DC HOLDINGS LLC", "MESA DATA CENTER TWO")],
              faa_rows=good_faa + [(n, d, None) for n, d in FAA_NOT_DC])

    headers, rows = with_fixture(lambda: S.sample(), **kw)
    agency = lambda r: tuple(r[i] for i in S.AGENCY_TEXT_COLS)  # noqa: E731

    check("the sample has rows", len(rows) > 0)
    # Literal again, for the same reason.
    check("every row's agency text literally says data center or datacenter",
          all(any(w in " ".join(agency(r)).lower()
                  for w in ("data center", "datacenter", "data centre")) for r in rows),
          f"{[r[0] for r in rows if 'data cent' not in ' '.join(agency(r)).lower()]}")
    check("every row names a datacenter by the module's own rule",
          all(S.names_datacenter(*agency(r)) for r in rows))
    # Deliberately NOT S.is_supply_plant. A check that calls the function it is
    # testing goes green when that function is gutted. These are literal words.
    plant_words = ("BATCH PLANT", "READY MIX", "CRUSHING PLANT", " CBP")
    check("no row's agency text carries supply-plant words",
          not any(w in " ".join(agency(r)).upper() for r in rows for w in plant_words),
          f"{[r[0] for r in rows if any(w in ' '.join(agency(r)).upper() for w in plant_words)]}")
    check("no row is a supply plant by the module's own rule",
          not any(S.is_supply_plant(*agency(r)) for r in rows))
    check("no row is one of the rows that failed the sample",
          not any(r[0] in {f for _, f in REAL_BAD_ROWS} for r in rows))
    check("every row is the full width of the header", all(len(r) == len(headers) for r in rows))

    # The refused source. The fixture deliberately holds Arizona rows that ARE
    # datacenters, so this proves the source is excluded and not the classifier.
    az_names = {"PHOENIX DATA CENTER ONE", "MESA DATA CENTER TWO"}
    check("Arizona datacenter rows exist in the fixture store",
          all(S.is_datacenter_siting("ARIZONA DC HOLDINGS LLC", n) for n in az_names))
    check("no Arizona row reaches the sample even though it is a datacenter",
          not any(r[0] in az_names or r[3] in {"AZ", "Arizona"} for r in rows))

    proof = with_fixture(lambda: S.sample_proof(), **kw)
    check("the proof counts no non-datacenter rows", proof["rows_that_are_not"] == 0)
    check("the proof counts no refused-source rows", proof["rows_from_refused_source"] == 0)
    check("the proof counts the Arizona rows it is holding back",
          proof["arizona_rows_held_and_never_published"] == 2)
    check("the proof's datacenter count equals its row count",
          proof["rows_that_are_datacenters"] == proof["sample_rows"] == len(rows))


def test_the_guards_refuse() -> None:
    print("the guards, which have to refuse and not warn")

    def expect_raise(name, **kw):
        try:
            with_fixture(lambda: S.sample(), **kw)
        except RuntimeError:
            check(name, True)
        except Exception as e:  # noqa: BLE001
            check(name, False, f"raised {type(e).__name__}: {e}")
        else:
            check(name, False, "returned a sample instead of refusing")

    expect_raise("a store with no datacenter at all refuses, it does not pad",
                 tx_rows=REAL_BAD_ROWS, az_rows=[], faa_rows=[(n, d, None) for n, d in FAA_NOT_DC])
    expect_raise("a store holding only refused-source datacenters refuses",
                 tx_rows=REAL_BAD_ROWS, az_rows=[("X LLC", "PHOENIX DATA CENTER ONE")] * 40,
                 faa_rows=[])
    expect_raise("fewer rows than the floor refuses",
                 tx_rows=REAL_GOOD_ROWS[:1], az_rows=[], faa_rows=[])

    # A row that is not a datacenter, handed straight to the guard.
    try:
        S._guard([["CONCRETE BATCH PLANT 1", "MICHELS ROAD & STONE INC", "", "TX", "", "",
                   "Air permit for the site", "", "", "", "", ""]] * 10)
    except RuntimeError:
        check("the guard rejects a concrete batch plant handed to it directly", True)
    else:
        check("the guard rejects a concrete batch plant handed to it directly", False)

    # THE GUTTED-COPY TEST. The label in column 6 contains the word "datacenter".
    # If the guard read the whole row it would accept this hospital. It must not.
    hospital = [["HAVASU REGIONAL MEDICAL CENTER", "Hrmc, Llc", "Lake Havasu", "AZ", "", "",
                 "Air permit for the datacenter", "", "", "", "", ""]] * 10
    try:
        S._guard(hospital)
    except RuntimeError:
        check("a typed label saying 'datacenter' cannot pass a hospital through the guard", True)
    else:
        check("a typed label saying 'datacenter' cannot pass a hospital through the guard",
              False, "the guard read a column this script wrote")

    # And prove the guard would have accepted it if it read that column, so the
    # test above is testing something real.
    check("that same label does contain the datacenter word",
          S.names_datacenter("Air permit for the datacenter"))


def test_person_names_are_not_published() -> None:
    print("personal names")
    kw = dict(tx_rows=REAL_GOOD_ROWS, az_rows=[],
              faa_rows=[("Grant Node Data Center", "Mobile crane for hoisting.", "Kyle Hansen"),
                        ("Ironwood Building ARK2", "Two-Story Data Center.",
                         "BLACKCHAMBER GROUP LLC")] * 3)
    _, rows = with_fixture(lambda: S.sample(), **kw)
    companies = {r[1] for r in rows}
    check("a person's name in the sponsor field is not published",
          "Kyle Hansen" not in companies, f"companies={companies}")
    check("a company in the sponsor field is published",
          "BLACKCHAMBER GROUP LLC" in companies, f"companies={companies}")


if __name__ == "__main__":
    test_the_rule()
    test_the_sample()
    test_the_guards_refuse()
    test_person_names_are_not_published()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("all checks passed")
