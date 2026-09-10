"""silent-refusal-kit has nothing to refresh on a schedule: the kit is static bytes and the
public sample is dated on the page. Re-run the kit's own tests instead."""
import subprocess, sys
from pathlib import Path

def main() -> int:
    kit = Path(__file__).resolve().parent / "kit"
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(kit), "-p", "test_*.py"],
                       capture_output=True, text=True)
    print("ok" if r.returncode == 0 else r.stdout[-800:] + r.stderr[-800:])
    return r.returncode

if __name__ == "__main__":
    raise SystemExit(main())
