"""Proves _bootstrap_fault opens for the two armed-but-dark shapes and NOTHING else.

Subjects are the real fail lines check_site prints, not invented ones: the
family shape and the board shape are copied from check_site.py's own fail()
calls, truncated at 200 characters the way pipeline.site_gate truncates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_slices import _bootstrap_fault  # noqa: E402

PREFIX = "scripts/check_site.py is failing: "
ok = 0

# GREEN way 1: the family shape opens, and names the family.
line = (PREFIX + "FAIL: chicago declares a checkout at https://buy.stripe.com/"
        "5kQbIU5l41eaafO5n40sU0Z and its own page shows no pay button at all, s")
assert _bootstrap_fault(line) == ("chicago", None), _bootstrap_fault(line)
ok += 1

# GREEN way 2: the board shape opens, and names family AND board.
line = (PREFIX + "FAIL: permit-files/austin has an armed board checkout at "
        "https://buy.stripe.com/aFafZa3cWg94gEcdTA0sU0T and its own page shows no")
assert _bootstrap_fault(line) == ("permit-files", "austin"), _bootstrap_fault(line)
ok += 1

# RED way 1: a price lie does NOT open. Real shape from the flips build log.
line = (PREFIX + "FAIL: grid sells at $99/mo and is missing from the price list "
        "on families/coverage/, which is the page a buyer reads to compare.")
assert _bootstrap_fault(line) is None
ok += 1

# RED way 2: a checkout fault that is NOT the missing-button one does not open.
line = (PREFIX + "FAIL: chicago says its checkout was verified on 2026-01-01, "
        "which is 236 days ago")
assert _bootstrap_fault(line) is None
ok += 1

# RED way 3: the gate refusing to run at all does not open.
line = "the honesty gate would not run: OSError(2, 'No such file')"
assert _bootstrap_fault(line) is None
ok += 1

# RED way 4: a fault on a family OUTSIDE the build set must stop the build.
# _bootstrap_fault only names the family; the in-set test lives at the call
# site, so prove the call-site condition with the matcher's own output.
fault = _bootstrap_fault(PREFIX + "FAIL: quakes declares a checkout at https://buy.stripe.com/x")
built_ids = {"chicago", "permit-files"}
assert fault == ("quakes", None) and fault[0] not in built_ids
ok += 1

# GREEN way 3 / RED way 5: the cascade filter drops ONLY the refusal whose
# detail names the identical fault on the identical family; anything else stands.
fault = ("chicago", None)
cascade = {"id": "chicago", "detail": PREFIX + "FAIL: chicago declares a checkout at https://buy.stripe.com/x and its own page shows no pay button"}
genuine = {"id": "chicago", "detail": "rows are 44 days stale"}
other = {"id": "grid", "detail": PREFIX + "FAIL: chicago declares a checkout at https://buy.stripe.com/x and its own page shows no pay button"}
kept = [r for r in (cascade, genuine, other)
        if not (r["id"] == fault[0] and _bootstrap_fault(r.get("detail") or "") == fault)]
assert kept == [genuine, other], kept
ok += 1

print(f"ok - {ok}/7 both ways")
