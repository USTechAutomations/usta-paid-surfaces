#!/usr/bin/env python3
"""Every "What is and is not in this feed" link has to land on a page.

WHY THIS TEST EXISTS
    scripts/render_slice.py puts a link to ../coverage/ on every slice page
    whose own slug is not "coverage". Nothing made a family produce that page:
    a family whose module never returned a slice with slug "coverage" shipped
    hundreds of child pages all pointing at an address that was never written.
    On 2026-09-10 six families were in that state -- 502 published pages, every
    one of them with a dead link in its "More from this feed" list.

    A link that 404s is not a cosmetic fault on this estate. These pages are
    sold on the promise that we name our sources and our gaps, and the link
    that promises exactly that was the broken one.

WHAT IT CHECKS
    Walks the built family pages under families/ -- which is what
    render_slice.write() writes and what build_site.py copies into dist/ -- and
    for every page that links to a family's coverage page, asserts that
    families/<family>/coverage/index.html exists on disk.

    It checks EVERY family, not a list of six, so the next family that grows a
    slice page cannot reintroduce the same fault quietly. The six are named in
    a second test only so that a build which silently stopped producing them
    fails loudly rather than passing on an empty walk.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "families"

# Both spellings the estate uses: the relative link render_slice.py writes, and
# the absolute one build_site.py rewrites it to when it copies a page to dist/.
REL = re.compile(r'href="\.\./coverage/?"')
ABS = re.compile(r'href="https://ustechautomations\.com/feeds/([a-z0-9-]+)/coverage/?"')

# The six that were broken. Named so an empty walk cannot pass as a green run.
WERE_BROKEN = (
    "hazmat-ship-pack",
    "patent-practitioner-directory",
    "enforcement-action-board",
    "nutrition-label-forge",
    "ai-disclosure-notice",
    "customs-broker-exam-bank",
)


def _pages() -> list[Path]:
    if not FAMILIES.is_dir():
        return []
    return sorted(FAMILIES.glob("*/*/index.html"))


def _links_to_coverage(html: str, page: Path) -> str | None:
    """The family id whose coverage page this page links to, or None."""
    if REL.search(html):
        return page.parent.parent.name
    m = ABS.search(html)
    return m.group(1) if m else None


class CoverageLinksResolve(unittest.TestCase):
    def test_every_coverage_link_lands_on_a_page(self):
        pages = _pages()
        self.assertTrue(pages, f"no built family pages under {FAMILIES}")
        checked = 0
        dead: list[str] = []
        for page in pages:
            fam = _links_to_coverage(page.read_text(encoding="utf-8"), page)
            if not fam:
                continue
            checked += 1
            if not (FAMILIES / fam / "coverage" / "index.html").is_file():
                dead.append(f"{page.relative_to(ROOT)} -> feeds/{fam}/coverage")
        self.assertEqual(
            [], dead[:20],
            f"{len(dead)} of {checked} pages link to a coverage page that was never "
            f"built. The family's scripts/slice_<family>.py has to return a slice with "
            f'slug "coverage", the way 31 other families already do.')
        self.assertGreater(checked, 0, "no page links to a coverage page at all")

    def test_the_six_that_were_broken_still_build_their_coverage_page(self):
        missing = [f for f in WERE_BROKEN
                   if not (FAMILIES / f / "coverage" / "index.html").is_file()]
        self.assertEqual([], missing,
                         "these families lost the coverage page they were given on "
                         "2026-09-10; rebuild with scripts/build_slices.py --only <family>")

    def test_a_coverage_page_does_not_link_to_itself(self):
        """render_slice.py drops the link on the coverage page. Prove it stays dropped."""
        selfish = []
        for fam in sorted(p.name for p in FAMILIES.iterdir() if p.is_dir()):
            page = FAMILIES / fam / "coverage" / "index.html"
            if not page.is_file():
                continue
            body = page.read_text(encoding="utf-8")
            if REL.search(body):
                selfish.append(fam)
        self.assertEqual([], selfish, "a coverage page links to itself")


if __name__ == "__main__":
    unittest.main()
