# Preserving independent feeds components

The September8 full estate rebuild started from nginx plus this repository's dist tree. It discarded the registered PathLab and Workshop directories, runtime routes, hub links and sitemap entries that had been published by separate repositories. Revision81 served those twelve routes as404. This was a publication regression, not missing product commits.

Both scripts/deploy.sh and scripts/refresh_and_deploy.sh now use an isolated temporary build context from the pristine tracked nginx template. Before building, scripts/preserve_independent_overlays.py retrieves the actual single100%-traffic Cloud Run revision by immutable digest and retains registered component files, complete nginx locations (including explicit unavailable API responses), exact hub sections and existing unique sitemap admissions. It refuses missing components, collisions, symlinks, unknown registration mappings and split/unknown traffic. It does not restore removed pages from stale source copies or change checkout capabilities.

Both deploy paths cooperate through ~/.hermes/state/feeds/deploy.lock. Immediately before publication they compare the serving revision, generation and image with the preservation base. After deployment they fetch and compare every retained public component file plus hub sections and sitemap entries before stamping success. The refresh change hash includes the final site and nginx bytes. A no-change run still refreshes the preservation base before deciding there is nothing to publish.

The helper requires the existing local Docker installation and existing gcloud credentials; scheduled refresh passes its discovered absolute gcloud executable. It uses a temporary Docker credential directory that is removed after extraction. No account setting, service size or paid capability is changed.

Run tests with `python3 -m unittest discover -s tests -p test_preserve_independent_overlays.py -v` and `bash -n scripts/deploy.sh scripts/refresh_and_deploy.sh`.

New components require an explicit reviewed marker mapping in the helper and a registry declaration. Component releases remain owned by their separate repositories. Use a preserving overlay on a freshly fetched current image, pass published-byte quality and real href reachability, then add sitemap entries. Never roll back a shared service over newer families. Free publication requires no approval acknowledgment.

This prevents loss through these two canonical scripts. An unrelated tool that bypasses their helper and lock can still replace the service; current page/revision checks remain necessary. Restoration evidence: /home/gmullins/reports/restore-inaccessible-pages-20260908/.

The reviewed catalog-pilot-20260908 component uses browser workers exclusively. Its catalog-pilot-independent-20260908 hub marker and /feeds/catalog-migration/ prefix are explicitly mapped. It needs no invented API endpoint; the existing PathLab and Workshop API preservation requirements remain enforced. Test coverage exercises browser-only retention alongside the original components.
