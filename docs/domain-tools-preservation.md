# Domain tools preservation

The independent source project is `/home/gmullins/code/usta-domain-tools-20260909-a`.
Its owned namespace is `/feeds/domain-tools/` and its feeds hub marker is
`domain-tools-independent-20260909-a`. The corresponding registry component is
`domain-tools-20260909-a`.

The preservation mapping retains this prefix, its five tool and five offline-edition
pages, and the exact current files and nginx routes. The buyer recovery page is
retained as a file but deliberately excluded from sitemap admission. The explicit
API location must remain present, including its unavailable response when hosted
commerce has not been connected. A static page does not establish a payment path.

This mapping changes no existing component. Namespace publication and registry
declaration remain separate steps. The owner stages from the freshly observed
immutable serving image while holding `~/.hermes/state/feeds/deploy.lock`, runs the
strict brand/truth/browser checks, then fetches every owned byte and persists the
canonical page-quality and crawl verdict before sitemap promotion. The owner
release code is `ops/release.py`; fetched receipts belong to
`/home/gmullins/reports/novel-five-20260909-codex-a/release/`.

Rollback must start from the then-current image and remove only this component's
files, marked hub/nginx additions and sitemap entries. Never switch shared traffic
to an older revision over another publisher's additions.
