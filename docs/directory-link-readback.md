# Check the directory customers actually receive

The public directory retained two `families/...` links returning 404 even though
the intended canonical pages and the local build were correct. Checking only
`urls.json` did not discover that defect. A third directory link returned 308.

Use the existing checker after a directory publication:

```sh
python3 scripts/check_urls.py --directory --pace 1 --quiet --out /absolute/report.json
```

This reads links from the published directory's main content. It checks only
owned HTTPS `/feeds/` destinations without queries or fragments. It never loads
checkout links, sends analytics, or writes customer/payment records. The normal
manifest mode remains available without `--directory`.

Exit 0 means the extracted destinations answered 200 under a stable observed
directory. Exit 1 means a stable non-200 response, 2 means unavailable evidence,
and 3 means observed version drift. Empty or unreadable directory HTML is UNKNOWN.
Observed HTTP statuses remain in the report when a missing witness prevents a
finding. A redirect is reported separately rather than silently followed.

The parser is `scripts/buyer_actions.py`; it classifies static anchors, not DOM
visibility, checkout validity, qualified demand, payment or fulfillment. Main-only
headings do not establish the page's total H1 count: this estate's hero can precede
`main`. Brand checks remain responsible for that.

No timer was added. This is a release check and a reusable operator readback.
The source build already rewrites `families/...` links; a hand-prepared image must
also pass this published-byte check. Preserve independent overlays and the shared
deployment lock. If another release changes the base image, rebase the small
patch and compare the complete image file set before publication.

Run the regression cases with:

```sh
python3 -m unittest discover -s tests -p 'test_directory_links_*.py' -v
```

Evidence and the exact release candidate are in
`/home/gmullins/advisor-plans/business-launch-closure-20260910/customer-journey-sep11/`.

## Recurring check — September 11, 2026

The existing `scripts/probe_live.py` now runs the directory checker before its sitemap freshness scan. It retains `~/.hermes/state/alerts/feeds-directory-latest.json`, keeps the existing freshness alert destination, and refuses to clear alerts on missing, malformed, inconsistent, stale or changing directory evidence. The directory subprocess gets 300 seconds; the remaining freshness scan stops with UNKNOWN before the existing 900-second service budget. A partial scan is not healthy. Network status zero is UNKNOWN, never a broken-page count.

Offline acceptance and precise installed hashes: `~/reports/customer-integration-20260911/current-refresh/`. Manager tests include invalid count types, count mismatches, stale report reuse, invalid dates and exhausted budgets. The existing timer remains subject to the fleet quiet window; `list-timers` is the current scheduling evidence. No new timer or collector was created.

## Recurring enforcement, September11

`refresh_and_deploy.sh` now calls the directory check before either success path:
when the build fingerprint is unchanged and after a publication attempt. Only
exit0 permits alert removal or a new published fingerprint. Bad destinations and
unavailable/changing evidence retain the previous fingerprint and write distinct
alert wording. A failed post-publication check no longer claims that nothing was
published. The existing build and publication commands were preserved.

The existing `feeds-live-probe.service` also has a manager-installed drop-in at
`~/.config/systemd/user/feeds-live-probe.service.d/30-directory-check.conf`.
Its ExecStopPost runs this same checker even when the preceding page probe fails,
writing `~/.hermes/state/feeds/directory-monitor.json`. There is no new timer.
The existing quiet-window condition remains in force; configuration/readback does
not prove that a scheduled invocation has occurred. The first interactive check
returned102/102 HTTP200 with a stable directory witness.

Tests: `python3 -m unittest discover -s tests -p 'test_refresh_directory.py' -v`.
Eight isolated fake workflows cover success, bad responses, unavailable evidence
and changing publication in both branches. No test invokes a real deployment.

Recovery: remove only `30-directory-check.conf` and reload the user service
manager to undo the monitor addition. Restore only the reviewed refresh-script
change to undo release enforcement; do not reset unrelated source files.
Current evidence: `continuation-sep11-1700/` in the September10 closure report.
