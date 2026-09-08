#!/usr/bin/env python3
"""What search engines are allowed to list, and why we hold most of it back.

A domain that publishes hundreds of near-identical thin pages gets treated by
search engines as low quality, and that judgement lands on the WHOLE domain, not
just the thin pages. Our paid feeds live on the same domain as everything else,
so letting a flood of skimpy auto-built pages into the index would drag the
pages that actually earn down with them.

So the rule is deliberately stingy:

  * A page is worth indexing only if it carries real substance -- here, at least
    four distinct facts (rows, dated events, figures). Fewer than that and it is
    noise to a searcher.
  * Even among substantial pages we index only the best `cap` of them. Beyond
    that the marginal page adds little and the domain-level risk grows.
  * Everything not chosen is set to `noindex,follow`: kept OUT of the index, but
    its links are still followed so the pages it points to keep their standing.

Private buyer pages are never passed through here at all -- they get an outright
`noindex,nofollow` from ppp.py, because they must never be listed under any
circumstances.
"""
from __future__ import annotations


def robots_meta(substantive: bool) -> str:
    """The robots meta tag for a page.

    `substantive=True` -> list it (`index,follow`). `False` -> keep it out of the
    index but still follow its links (`noindex,follow`).
    """
    content = "index,follow" if substantive else "noindex,follow"
    return f'<meta name="robots" content="{content}">'


def index_budget(pages: list[tuple[str, int]], cap: int) -> set[str]:
    """Choose which pages may be indexed, and return their paths as a set.

    `pages` is a list of (path, fact_count). A page qualifies only with a
    fact_count of 4 or more; of those that qualify, the `cap` highest by
    fact_count are chosen. Ties are broken by path so the choice is stable from
    one build to the next. Every path NOT in the returned set should be rendered
    with `robots_meta(False)`.
    """
    if cap <= 0:
        return set()
    qualifying = [(path, n) for path, n in pages if n >= 4]
    # Highest fact_count first; path as a stable tie-breaker.
    qualifying.sort(key=lambda pn: (-pn[1], pn[0]))
    return {path for path, _ in qualifying[:cap]}
