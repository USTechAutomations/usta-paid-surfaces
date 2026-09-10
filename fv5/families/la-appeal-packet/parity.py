#!/usr/bin/env python3
"""Prove the page's JavaScript picks the same rows, in the same order, with the
same numbers as fulfil.py, for a set of typed addresses. Exit 0 = identical."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fulfil as F  # noqa: E402

CASES = ["5980 W 75th St, Los Angeles, CA 90045", "5980 w 75 st 90045", "5221 Glasgow Way, Los Angeles, CA 90045",
         "7004 Ramsgate Ave 90045", "7143 S La Cienega Blvd, Los Angeles CA 90045", "7152 Knowlton Pl", "5205 Thornburn St 90045",
         "7100 Glasgow Ave Los Angeles", "6040 W 76TH ST", "5931 Abernathy Dr, 90045", "99999 Nowhere Blvd 90045", "Kentwood Ave"]


def py_case(typed: str, src: F.Source) -> dict:
    parsed = F.parse_address(typed)
    subject, _ = F.pick_subject(parsed, src.candidates(parsed))
    if subject is None:
        return {"parsed": parsed, "subject": None, "support_rows": []}
    sel = F.select_comps(subject, src.neighbours(subject))
    return {"parsed": parsed, "subject_ain": str(subject["AIN"]), "support_rows": [F.comp_record(k) for k in sel["comps"]],
            "candidates_in_radius": sel["candidates_in_radius"], "dropped": sel["dropped"]}


def main() -> int:
    live = "--live" in sys.argv
    src = F.Source() if live else F.Source(str(HERE / "fixtures" / "parcels-90045.json"))
    if live:
        assert not src.offline, "unset LA_PACKET_FIXTURE for --live"
    cases = CASES[:2] + CASES[-2:] if live else CASES
    env = dict(__import__("os").environ, LA_PARITY_LIVE="1" if live else "")
    bad = 0
    for typed in cases:
        py = py_case(typed, src)
        for r in py["support_rows"]:
            r.pop("what_this_is", None)
        js = json.loads(subprocess.run(["node", str(HERE / "parity.js"), typed], capture_output=True, text=True, check=True, env=env).stdout)
        same = json.dumps(py, sort_keys=True) == json.dumps(js, sort_keys=True)
        n = len(py["support_rows"])
        print("%s  %-45s py=%d js=%d" % ("same" if same else "DIFF", typed, n, len(js["support_rows"])))
        if not same:
            bad += 1
            for k in py:
                if json.dumps(py.get(k), sort_keys=True) != json.dumps(js.get(k), sort_keys=True):
                    print("   field %s differs" % k)
    print("parity %s (%s): %d/%d cases identical" % ("ok" if not bad else "FAIL", "live county map" if live else "fixture", len(cases) - bad, len(cases)))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
