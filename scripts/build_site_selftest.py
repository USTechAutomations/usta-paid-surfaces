#!/usr/bin/env python3
"""Prove the publisher obeys the build veto, both ways.

    python3 scripts/build_site_selftest.py

WHY THIS FILE EXISTS. scripts/build_slices.py asked the veto before it wrote a
page and scripts/build_site.py did not, and the two do different jobs: the first
decides what is written to families/ on disk, the second decides what is on the
site. A refused family keeps the pages it already had -- that is deliberate --
and the publisher then copied those pages into dist/ and shipped them, price and
pay button and all. air-permits went out that way on 2026-08-23: the veto said
"priced passes while lawful fails", the writer obeyed it, and a stranger could
still buy the page it had refused to write. The refusal reached the folder and
never reached the address.

WHAT IS UNDER TEST HERE, AND WHAT IS NOT. This file does not check whether the
veto is RIGHT about a family; scripts/pipeline_selftest.py does that, against
find_refusals(), which is the same function the real veto reads. What is under
test here is the wiring: that the publisher asks, that a refused family reaches
no address, that its old addresses keep answering as retired pages rather than
404ing, that it leaves the sitemap, and -- the half that is easy to forget --
that a family nobody refused is still published normally. So the veto is stood
in for on purpose, and each case decides the answer it wants back.

Nothing here writes to the real dist/, the real sitemap or the real
published-addresses.txt. All three are pointed at a temporary folder that is
thrown away, and the families/ folder is only ever read.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# An ordinary priced family with child pages, and a second one that must go on
# being published while the first is refused.
#
# BOTH ARE PICKED AT RUN TIME AND NEITHER IS NAMED HERE. They used to be typed in
# as `ttb` and `grid`, under a comment claiming they were read from the catalog --
# which they were not. The day grid came off sale this file went red and stayed
# red on "grid still sells", and the red said nothing about the publisher: the
# subject had simply stopped being the kind of page the case describes. A test
# that names its subject eventually reports on itself instead of on the rule.
FAILURES: list[str] = []


def subjects() -> tuple[str, str]:
    """The two families this run will use: one to refuse, one that must survive it.

    Both must be selling today by `sold()`'s own definition -- the same function
    the cases below assert with -- or the cases are about nothing. The one to be
    refused must also HAVE child pages, because "its child pages are published"
    over an empty list is a pass that proves nothing at all.
    """
    fams = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))["families"]
    able = []
    for f in sorted(fams, key=lambda x: x["id"]):
        page = ROOT / "families" / f["id"] / "index.html"
        # A price is a price only when it names an amount -- the rule build_hub.py
        # and render_slice.py both state in these words. "Not for sale yet" is a
        # sentence, and it is TRUTHY, so a plain `if not f.get("price")` counts a
        # withdrawn family as one on sale. That is how this very fix first went
        # green against a catalog with everything taken off sale.
        if "$" not in f.get("price", "") or not page.is_file() or not sold(page):
            continue
        kids = [d.name for d in sorted((ROOT / "families" / f["id"]).iterdir())
                if d.is_dir() and (d / "index.html").is_file()]
        able.append((f["id"], len(kids)))
    if len(able) < 2:
        raise SystemExit(
            f"CANNOT RUN: this test needs two families on sale today and it found "
            f"{len(able)}.\nIt refuses one and proves the other still ships, so with "
            "fewer than two there is\nno case here. Do not delete the cases: put a "
            "family back on sale, or record in the\ncatalog that the estate sells "
            "nothing.")
    # Refuse the one with the most children, so the child-page case has real work
    # to do; ties break on the id so two runs pick the same pages.
    refuse = max(able, key=lambda x: (x[1], x[0]))[0]
    if not [k for _id, k in able if _id == refuse][0]:
        raise SystemExit(
            "CANNOT RUN: no family on sale today has a child page, so the case that "
            "proves a\nrefused family's children stop selling would pass over an empty "
            "list. Do not keep\nthat pass: it is the shape of a check that has gone "
            "quiet.")
    healthy = next(i for i, _ in able if i != refuse)
    return refuse, healthy


def refusal_for(fid: str) -> dict:
    return {
        "id": fid,
        "higher": "priced",
        "lower": "lawful",
        "why": "a made-up refusal, so that this test can see what one does",
        "detail": "invented by scripts/build_site_selftest.py; no real source is implicated",
    }


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f'{"ok  " if ok else "FAIL"}  {name}')
    if not ok:
        FAILURES.append(f"{name}{': ' + detail if detail else ''}")


def run(veto: dict, estate_down: str | None) -> tuple[int, str, Path]:
    """One whole publish, with the veto standing in and dist/ in a temp folder."""
    tmp = Path(tempfile.mkdtemp(prefix="build-site-selftest-"))
    real_dist, real_pub, real_veto = build_site.DIST, build_site.PUBLISHED, build_site.build_veto
    published = tmp / "published-addresses.txt"
    shutil.copy2(real_pub, published)
    build_site.DIST = tmp / "dist"
    build_site.PUBLISHED = published
    build_site.build_veto = lambda *a, **k: (veto, estate_down)
    out, code = io.StringIO(), 0
    try:
        with redirect_stdout(out), redirect_stderr(out):
            build_site.main()
    except SystemExit as e:
        code = int(e.code or 0)
    finally:
        build_site.DIST, build_site.PUBLISHED = real_dist, real_pub
        build_site.build_veto = real_veto
    return code, out.getvalue(), tmp / "dist"


def sold(page: Path) -> bool:
    """Does this address still offer to take money?"""
    if not page.is_file():
        return False
    raw = page.read_text(encoding="utf-8")
    return 'class="price">$' in raw or "btn-buy" in raw or "buy.stripe.com" in raw


def main() -> None:
    REFUSE_ME, HEALTHY = subjects()
    REFUSAL = refusal_for(REFUSE_ME)
    # Say which pages this run actually covered. A derived subject that stays
    # silent is a test nobody can check, and "ok" would not say on what.
    print(f"picked from catalog.json at run time: refusing {REFUSE_ME}, "
          f"{HEALTHY} must survive it\n")

    # ---- 1. nobody is refused: the ordinary build, and the half that is easy
    # to forget. A gate that refuses everything is not a gate.
    code, log, dist = run({}, None)
    kids = [d.name for d in sorted((ROOT / "families" / REFUSE_ME).iterdir())
            if d.is_dir() and (d / "index.html").is_file()]
    check("no refusal: the build finishes", code == 0, log[-400:])
    check(f"no refusal: {REFUSE_ME} is published", (dist / REFUSE_ME / "index.html").is_file())
    check(f"no refusal: {REFUSE_ME} still sells", sold(dist / REFUSE_ME / "index.html"))
    check(f"no refusal: its {len(kids)} child pages are published",
          all((dist / REFUSE_ME / k / "index.html").is_file() for k in kids))
    check(f"no refusal: {REFUSE_ME} is in the sitemap",
          f"/{REFUSE_ME}<" in (dist / "sitemap.xml").read_text(encoding="utf-8"))
    check("no refusal: nothing says REFUSED", "REFUSED" not in log)
    shutil.rmtree(dist.parent, ignore_errors=True)

    # ---- 2. one family refused: it reaches no address, and everyone else does.
    code, log, dist = run({REFUSE_ME: [REFUSAL]}, None)
    page = dist / REFUSE_ME / "index.html"
    check("refused: the build still finishes, so the rest of the estate ships", code == 0,
          log[-400:])
    check("refused: the reason is printed", f"REFUSED  {REFUSE_ME}:" in log)
    check("refused: it is named again at the end", f"REFUSED and NOT published: {REFUSE_ME}" in log)
    check("refused: the address still answers", page.is_file())
    check("refused: and it sells nothing", not sold(page))
    check("refused: the address says it is retired",
          page.is_file() and "retired" in page.read_text(encoding="utf-8"))
    check("refused: no child page of it sells anything",
          not any(sold(dist / REFUSE_ME / k / "index.html") for k in kids))
    check("refused: it is out of the sitemap",
          f"/{REFUSE_ME}<" not in (dist / "sitemap.xml").read_text(encoding="utf-8"))
    check(f"refused: {HEALTHY} is published anyway", (dist / HEALTHY / "index.html").is_file())
    check(f"refused: {HEALTHY} still sells", sold(dist / HEALTHY / "index.html"))
    shutil.rmtree(dist.parent, ignore_errors=True)

    # ---- 3. the estate gate itself is down: nothing at all goes out.
    code, log, dist = run({}, "scripts/check_site.py is failing: a pretend reason")
    check("estate gate down: the build stops", code == 1, log[-400:])
    check("estate gate down: it names the gate, not twenty-seven families",
          "check_site.py is failing" in log)
    check("estate gate down: no page was written",
          not (dist / REFUSE_ME / "index.html").is_file())
    shutil.rmtree(dist.parent, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:", file=sys.stderr)
        for f in FAILURES:
            print(f"  {f}", file=sys.stderr)
        raise SystemExit(1)
    print("the publisher obeys the veto, and still publishes what nobody refused")


if __name__ == "__main__":
    main()
