"""Days missing from a run of dated copies, counted and named the same way twice.

Two pages had their own copy of this. new-entities collapsed a hole into "a
7-day stretch from X to Y"; crawler, written later and by hand, listed every
date flat, so the same six-day hole read as six unrelated days. Neither was
wrong about the days -- they disagreed about how a reader is told, and the
disagreement was invisible because the code was in two files.

Nothing here formats a date or writes a sentence about why a hole matters: the
caller passes its own date formatter in and keeps its own wording, because what
a missing day MEANS is different on a business register and a robots.txt panel.
What is shared is the arithmetic, which is the part that can be wrong.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence


def missing_days(dates: Sequence[str]) -> list[str]:
    """Days between the first and last date we hold that carry nothing.

    A date range cannot see a hole in itself: two dates at either end say
    nothing about the middle. Every day in the span is checked against what we
    actually hold, and the ones with nothing behind them come back named.
    """
    got = sorted(set(dates))
    if not got:
        return []
    first = dt.date.fromisoformat(got[0])
    last = dt.date.fromisoformat(got[-1])
    have = {dt.date.fromisoformat(d) for d in got}
    return [(first + dt.timedelta(days=i)).isoformat()
            for i in range((last - first).days + 1)
            if first + dt.timedelta(days=i) not in have]


def runs_of(days: Sequence[str]) -> list[list[str]]:
    """Consecutive days grouped, so a week-long hole reads as a week, not seven dates."""
    out: list[list[str]] = []
    for d in sorted(days):
        if out and (dt.date.fromisoformat(d)
                    - dt.date.fromisoformat(out[-1][-1])).days == 1:
            out[-1].append(d)
        else:
            out.append([d])
    return out


def span_days(dates: Sequence[str]) -> int:
    """Calendar days from the first date to the last, both ends counted."""
    got = sorted(set(dates))
    if not got:
        return 0
    return (dt.date.fromisoformat(got[-1]) - dt.date.fromisoformat(got[0])).days + 1


def name_gaps(
    days: Sequence[str],
    day: Callable[[str], str],
    short_day: Callable[[str], str] | None = None,
) -> str:
    """The missing days as one phrase, with runs of two or more said as a stretch.

    `day` writes a full date and `short_day`, when the caller has one, writes the
    same date without the year so a list does not repeat 2026 six times. The last
    date named always uses `day`, so the year is stated once and at the end.
    """
    runs = runs_of(days)
    if not runs:
        return ""
    brief = short_day or day
    bits: list[str] = []
    for i, run in enumerate(runs):
        last = i == len(runs) - 1
        if len(run) == 1:
            bits.append(day(run[0]) if last else brief(run[0]))
        else:
            bits.append(f"a {len(run)}-day stretch from {brief(run[0])} to "
                        f"{day(run[-1]) if last else brief(run[-1])}")
    if len(bits) == 1:
        return bits[0]
    return ", ".join(bits[:-1]) + " and " + bits[-1]
