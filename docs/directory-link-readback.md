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
