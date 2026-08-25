"""Proves the verifier's carve-out opens for stamp faults and NOTHING else."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_checkouts import _bootstrap_fault  # noqa: E402

PREFIX = "scripts/check_site.py is failing: "
ok = 0

# GREEN way 1: the never-verified fault opens (real text from check_site).
line = PREFIX + "FAIL: chicago checkout was never verified -- run scripts/verify_checkouts.py"
assert _bootstrap_fault(line) == "chicago", _bootstrap_fault(line)
ok += 1

# GREEN way 2: the aged-out twin opens.
line = PREFIX + "FAIL: los-angeles checkout was last proved working 31 days ago; re-verify before shipping"
assert _bootstrap_fault(line) == "los-angeles"
ok += 1

# RED way 1: a missing pay button is the BUILDER's fault, not the verifier's.
line = (PREFIX + "FAIL: chicago declares a checkout at https://buy.stripe.com/x "
        "and its own page shows no pay button at all")
assert _bootstrap_fault(line) is None
ok += 1

# RED way 2: a price lie does not open.
line = PREFIX + "FAIL: grid sells at $99/mo and is missing from the price list on families/coverage/"
assert _bootstrap_fault(line) is None
ok += 1

# RED way 3: the gate refusing to run at all does not open.
assert _bootstrap_fault("the honesty gate would not run: OSError(2)") is None
ok += 1

# RED way 4: a dead-status fault does not open -- that is a measured refusal.
line = PREFIX + "FAIL: chicago checkout is declared but its last check said 'dead'"
assert _bootstrap_fault(line) is None
ok += 1

# Cascade filter: byte-equal detail is dropped, anything else is kept.
estate_down = PREFIX + "FAIL: chicago checkout was never verified -- run scripts/verify_checkouts.py"
rows = [{"id": "chicago", "detail": estate_down},
        {"id": "grid", "detail": estate_down},
        {"id": "grid", "detail": "no permission note for its source"}]
kept = [r for r in rows if r.get("detail") != estate_down]
assert kept == [{"id": "grid", "detail": "no permission note for its source"}]
ok += 1

print(f"ok - {ok}/7 both ways")
