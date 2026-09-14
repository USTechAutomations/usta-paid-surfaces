# OSHA source collector

This collector supplies the existing OSHA Apify actor with a validated, minimized copy of OSHA's published ZIP. The canonical private browser can read the official dashboard and download; the actor's direct hosted request returned HTTP 403. No paid proxy, personal browser, copied cookies or desktop automation is used.

Canonical source: /home/gmullins/code/usta-paid-surfaces/fv5/families/apify-public-records/collectors/osha/. A synchronized source copy is in the wt-fv5-apify-actors worktree. Runtime uses the existing harness/browser/venv Python and hand.Browser(headless=True) on private port 9334. Each run creates and closes only its own page.

The user service usta-osha-source-cache.service has the canonical company-network ExecCondition. Its timer runs at 03:40 America/Phoenix daily, with Persistent=false to avoid missed-run catchup in the quiet window. Units are also retained in systemd/ beside this file. Read actual scheduling with systemctl --user list-timers --all --no-pager.

State: /home/gmullins/.hermes/state/collectors/osha-source/. Read last_attempt.json, the attempt's source-evidence.json/manifest.json/summary.json/result.json, and the service journal. Successful oneshot completion normally leaves ActiveState=inactive and SubState=dead; require Result=success and ExecMainStatus=0. An ExecCondition refusal is not a successful collection. Check the latest attempt timestamp and the public manifest as well.

Publication is to existing owned Apify key-value store ElRfCpTirAfN8QY1l. LATEST.json points to an immutable checksum-named sanitized ZIP. The original official SHA and URL, actual coverage dates, HTTP evidence, collected_at and row count are preserved. Every public artifact is anonymously fetched and hash-checked before replacing the latest pointer. Source/parse/proof/readback errors report UNKNOWN and preserve the last accepted pointer when failure occurs before its replacement.

Before any write, owner identity, company-network PASS, enabled FREE plan, zero base price, hard monthly usage cap within the five-dollar included allowance, finite measured usage and a 0.40-dollar headroom are required. These are included credits, not authority for cash out. Failed guards refuse; never upgrade, switch accounts or loosen them automatically.

The public copy contains only the actor's REQUIRED columns. Raw source ZIPs remain local for the three most recent successful attempts; older generated source/sanitized bundles are pruned while receipts remain. Symlinks and non-generated directories are excluded. A per-state flock refuses concurrent runs. Changed source schema or report integrity requires review before publication. The actor refuses a collection older than 48 hours and validates size, row count, source URL and checksum independently.

To run a bounded read-only collection, use the existing browser Python with collector.py --actor-dir pointing to the installed actor and --state-dir pointing to a new report folder. No --publish means no public writes. To repeat the installed guarded publication, start usta-osha-source-cache.service and inspect its actual exit and public readback; a start request alone proves nothing.

Recovery: fix the concrete source/browser/network/free-plan failure on a copy, run SMOKE.sh with the existing SDK environment, then exercise the service and actor. Never reset collected_at without actually refetching the official bytes. To retire this route, disable --now only usta-osha-source-cache.timer and mark the actor deprecated through its existing API; do not delete pricing history or disturb other fleet timers. Disabling refresh alone eventually makes actor requests UNKNOWN after the 48-hour cutoff.

Acceptance on 12 September 2026: nine collector tests on copy and both sources/raw exit 0; actual installed service raw exit 0 at 22:22 UTC; anonymous manifest/artifact HTTP 200; final hosted actor raw exit 0 with source-matching output. First scheduled firing is still UNKNOWN. Evidence and full hashes: /home/gmullins/reports/marketplace-closure-20260912/osha-recovery/.
