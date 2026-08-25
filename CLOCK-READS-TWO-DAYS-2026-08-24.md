# This machine answers "what day is it" two different ways

Found 2026-08-24 while landing the retirement-marker fix. **Not fixed here. Not to
be fixed by moving anything to UTC.** Recorded so the fix is done deliberately,
as its own job, by someone who has read the whole of this.

Append corrections with their own dated heading. Never edit a line above.

## The two answers, and the offset

Printed, not remembered. The offset is the whole finding, so it is printed:

    /etc/timezone      : Etc/UTC
    /etc/localtime  -> : /usr/share/zoneinfo/America/Phoenix
    TZ                 : unset
    date               : Mon Aug 24 07:23:15 PM MST 2026
    date -u            : Tue Aug 25 02:23:15 AM UTC 2026
    offset             : -0700
    python, local      : 2026-08-24
    python, UTC        : 2026-08-25

Two bookkeeping files disagree. `/etc/localtime` is the one the system actually
reads, so **MST wins and `-0700` is the real offset**; `/etc/timezone` is a stale
note that says otherwise. Every evening from 17:00 to midnight MST, the local
calendar date is **one day behind** the calendar date the data is sealed on.

## The finding: the error runs in the dangerous direction

Every freshness verdict in this shop is `age = today - newest_sealed_row`,
compared against a ceiling from `late_after(cadence)`.

Our sources seal in UTC. The gates ask the LOCAL clock what today is. During that
seven-hour window `today` is one day too small, so **`age` comes out one day
SMALLER than the true age.**

That is not a gate that cries wolf. It is a gate that can look at a feed which is
genuinely a day past its ceiling and call it **current** -- on pages that promise
a daily seal, to someone who paid for them. A page telling a buyer it is fresh
when it is late is a different and worse class of fault than a red on a board.

**Counted exposure today: 0 pages.** Not "probably none" -- counted. 200 dated
pages, and how much room each has before its own ceiling calls it late:

     51 pages  already past the ceiling, and every one of them says so on the page
    115 pages  2 days of room
      1 page   3 days of room
     20 pages  4 days of room
     12 pages  9 days of room
      1 page   29 days of room

Nothing sits at 0 or 1 day of room, and a one-day error can only tip a page that
sits at exactly 0. So the fault is **latent, not live**: it bites the first time a
daily page lands exactly 2 days behind during the evening window. Do not read
this table as "the estate is fine". Read it as "the estate got lucky today".

## The secondary symptom, which is how it was found

`check_built.py` reported:

    quakes: stamps 2026-08-25 as its read date, which has not happened yet

The page is honest. The quakes store really does hold **275 rows sealed under
`snapshot_date` 2026-08-25**, because USGS seals in UTC and it is already the 25th
there. The gate called a true date impossible because it was holding a clock seven
hours behind the one that wrote it.

Proof it is only the clock -- the same gate, the same built tree, twice:

    today = local (2026-08-24)  ->  2 faults: free-time, quakes
    today = UTC   (2026-08-25)  ->  1 fault:  free-time

## The four places that ask the local clock about a date

    scripts/check_built.py:233     today = today or dt.date.today()
    scripts/freshness.py:92        today = today or dt.date.today()
    scripts/family_status.py:429   today = today or dt.date.today()
    scripts/check_site.py:348      age = (dt.date.today() - ...).days

`check_site.py:348` is measuring the age of a checkout proof rather than a data
reading, so it is a different question wearing the same defect.

## What NOT to do

**Do not "fix" this by making everything UTC.** That is the move this shop has
already been bitten by: a clock that reports one answer confidently is how the
disagreement got hidden in the first place. Two clocks that disagree is a fact to
be printed, not smoothed over. Whatever the fix is, it should make the two answers
and the offset visible at the point of judgement, so a verdict says which clock it
used.

Also do not touch `/etc/timezone` or `/etc/localtime` to make this go away. That
is a change to the host, it silently moves every timer on the box, and it is not
this lane's to make.

## The rule this is an instance of

A date is only comparable to another date measured on the same clock. Ours are
sealed on one clock and judged on another, and nothing anywhere said so.
