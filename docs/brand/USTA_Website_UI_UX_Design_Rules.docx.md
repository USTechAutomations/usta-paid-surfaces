# **USTA Website** **Design & Build Reference**

## *Rules for consistent future pages, with code locations*

Version 1.3 • September 8, 2026 • Condensed reference

Use this guide for public pages at ustechautomations.com. The authenticated platform at app.ustechautomations.com is a separate application and deployment.

## **The design in one sentence**

Keep the site quiet and business-focused: Satoshi typography, neutral surfaces, restrained Signal Blue, generous whitespace, thin borders, and clear actions.

## **The rules every new page must follow**

* Reuse the closest existing page family and the shared website shell. Do not create another header, footer, theme system, or set of basic controls.  
* Use semantic color tokens and existing spacing utilities. Keep new CSS local unless the change should intentionally affect the whole website.  
* Give the page one clear H1, a useful content sequence, and a primary next action. State real capabilities and outcomes; do not imply unsupported integrations are live.  
* Keep mobile layouts readable, preserve keyboard access, and inspect both light and dark themes. Reuse working interactions as well as their appearance.  
* Avoid decorative status badges. Use muted text with a muted icon where helpful, on desktop and mobile. This is the requested direction for future work; existing badge code is not the standard to copy.  
* Register the route, metadata, and prerender path. A page component alone does not make a production URL.  
* Review the production website build and use the approved deployment workflow. Instructions are at the end.

## **How to use this reference**

Start with the code map on the next page, then use the visual rules and build checklist. “Must” is a future-work requirement; existing family-specific exceptions should be reused only within that family. Accessibility and release checks are review requirements, not claims that all current pages already pass.

Source of truth: the US-Tech-Automations/USTA GitHub repository is authoritative for website UI/UX. Start from the current main branch’s shared components, styling tokens, page patterns and maintained design guidance. This document is a reference, not an independent design system; if it differs from the repository, verify the intended behavior in the repo and update this guide. Explicitly requested changes, such as those recorded here, must be implemented and reviewed in the repository before they become the implemented standard.

The source review baseline is September 7, 2026\. This revision does not re-audit the live site or change website code. Current shared code and active route/build configuration take precedence over stale wiki guidance or DESIGN.md examples. Recheck the files before implementation.

[Repository baseline: 8273f3a7911a8a7dfd88ec10d6098fc34109cefe](https://github.com/US-Tech-Automations/USTA/tree/8273f3a7911a8a7dfd88ec10d6098fc34109cefe)

# **1\. Where the styling lives**

All paths in this table are relative to usta-react/. Click a path to open the reviewed revision on GitHub. Global rules live in CSS; many component sizes and layouts live directly in TSX className values.

| Location in usta-react/ | What it controls |
| :---- | :---- |
| [src/website/styles/index.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/styles/index.css) | Website light/dark tokens, global typography, container-padding, section-spacing, blog/FAQ and data-page styles. Start here for site-wide visual rules. |
| [src/index.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/index.css) | Shared Tailwind @theme mapping from semantic utilities to CSS variables; radius scale. Changes can affect more than the public website. |
| [src/styles/fonts.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/styles/fonts.css) | Satoshi and PT Serif font-face definitions; legacy Merriweather utility. |
| [src/website/styles/hero-animations.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/styles/hero-animations.css) | Ambient hero gradients and glow; imported by the website stylesheet. |
| [src/website/components/ui/button.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/ui/button.tsx) | Button variants, heights, padding, radii, hover and focus styles. |
| [src/website/components/ui/input.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/ui/input.tsx) | Input appearance and focus states. Textarea, Card and Dialog primitives are in this same ui directory. |
| [src/website/components/layout/Header.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/layout/Header.tsx) | Sticky header, responsive navigation, menus, actions and interaction behavior. |
| [src/website/components/layout/Footer.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/layout/Footer.tsx) | Shared footer layout, links, newsletter and legal/cookie controls. |
| [src/website/components/sections/BentoGrid.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/sections/BentoGrid.tsx) | Bento grid columns, item spans, card padding and geometry. |
| [src/website/components/ai-agents/ai-agents.module.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/ai-agents/ai-agents.module.css) | Scoped agent visuals, panels, chips, process and CTA effects. Keep these styles scoped. |
| [src/website/components/ai-agents/IntegrationShowcase.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/ai-agents/IntegrationShowcase.tsx) | “Connect Your Stack” cards, responsive grid, titles and status presentation. |
| [src/website/components/animations/FadeIn.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/animations/FadeIn.tsx) | Shared entry motion and stagger behavior. |
| [src/website/components/demo/styles/demoTheme.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/demo/styles/demoTheme.css) | Embedded demo styling; do not promote it into global marketing styles. |
| [src/website/pages/pricing/components/MobileWorkflowTimeline.module.css](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/pages/pricing/components/MobileWorkflowTimeline.module.css) | Specialized pricing mobile demo. ScrollDrivenWorkflow.module.css in the same folder handles the scroll-driven version. |

# **2\. Visual values to preserve**

## **Colors and themes**

Use bg-background, bg-card, text-foreground, text-muted-foreground and border-border. Use CSS variables for custom CSS. Do not hardcode a new palette. The values below are HSL channels, as stored in website/styles/index.css.

| Token | Light | Dark |
| :---- | :---- | :---- |
| background | 220 10% 99% | 220 15% 8% |
| foreground / card-foreground | 220 20% 10% | 220 15% 96% |
| card / popover | 0 0% 100% | 220 12% 10% |
| primary / ring | 207 100% 50% | 207 100% 50% |
| primary-surface | 207 100% 42% | 207 100% 42% |
| primary-surface-hover | 207 100% 36% | 207 100% 36% |
| primary-foreground | 0 0% 100% | 0 0% 100% |
| secondary / muted / accent | 220 12% 97% | 220 10% 16% |
| muted-foreground | 220 10% 42% | 220 8% 62% |
| border / input | 220 13% 94% | 220 10% 18% |
| destructive | 0 84.2% 60.2% | 0 62.8% 50% |

Primary filled buttons use primary-surface and primary-surface-hover through Button—not the brighter primary token described in older design notes. Keep brand-logo and meaningful error colors local. Reuse ThemeProvider and useTheme; do not add another theme toggle or persistence mechanism.

## **Typography and spacing**

| Element | Standard |
| :---- | :---- |
| Font and rhythm | Satoshi, body and global headings weight 500\. Paragraph line-height 1.625; global headings 1.15, tracking −0.025em. |
| Global headings | H1: 48 / 60 / 72px at base / 768 / 1024px (tracking −0.03em at lg). H2: 36 → 48px at 768px. H3: 30 → 36px; H4: 24 → 30px. |
| Agent hero exception | AgentPageHero: 36 / 48 / 60px; line-height 1.1. Reuse the component instead of normalizing it to the global H1. |
| Page gutters | container-padding: 24 / 32 / 48px at base / 768 / 1024px. |
| Major sections | section-spacing: 64 / 96 / 128px top and bottom at those same breakpoints. |
| Reading widths | max-w-2xl (672px) for copy; max-w-3xl (768px) for reading/FAQs; max-w-4xl (896px) for centered hero groups. |
| Internal spacing | Usually 16–24px gaps; 24px card padding, 32px for larger cards; 32px copy-to-CTA and 48px heading-to-grid. |

# **3\. Components and responsive behavior**

## **Shared shell**

Follow an existing route module: WebsiteStyleProvider wraps the page with @website/components/Layout. That Layout owns the header, main landmark, footer, scroll behavior and cookie consent. It is src/website/components/Layout.tsx; do not confuse it with similarly named files under components/layout/.

* Keep the 64px sticky header, z-40, thin border, translucent background and blur. Full navigation begins at xl (1280px); below that, use the existing expandable menu. Do not add a mobile bottom-navigation system.  
* Preserve the skip link, main id="main" and tabIndex={-1}. Menus must support click, keyboard, Escape with focus restoration, outside-click dismissal and closing after navigation.  
* Use React Router Link for website routes; use anchors for external URLs, downloads, mail/tel, /permits and /feeds. /offers is a website route. Login belongs on the platform subdomain.

## **Controls, cards and visuals**

| Element | Reuse rule |
| :---- | :---- |
| Buttons | Shared Button: default 40px high; small 36px; large CTA 44px. Rounded-md (6px). Primary for the main action, outline for a secondary action. Keep the focus ring. |
| Cards and grids | Default Card: 8px radius, border, bg-card, at most shadow-sm. BentoItem: 12px radius, 24px padding → 32px at md. BentoGrid: one column → six-column system at md. |
| Inputs and forms | Reuse Input, Textarea, labels and existing form flows. Preserve validation, loading, success and error states. Never rely on placeholder text as the label. |
| Icons and imagery | Use Lucide for UI actions. Integration logos must be official: reuse verified codebase assets first, otherwise obtain them from the official brand source. No generic substitutes or approximations. Label icon-only controls; hide decorative icons from assistive technology. Give images dimensions and appropriate alt text. |
| Motion | Reuse FadeIn (600ms / 20px; stagger 100ms) and scoped hero effects. Provide reduced-motion behavior; decorative layers must not block pointer events. |
| Status presentation | Use muted text plus a muted icon where useful, without a badge container. Do not rely on color alone. Muted styling must remain readable. |

## **Mobile and agent-page details**

* Start substantial content in one column. Use flexible widths, meaningful reading order and wrapping labels. Stack paired CTAs when needed; do not shrink their text to force a row.  
* AgentPageHero hides its visual below lg: essential information must also be in text. Reuse AgentPageHero, FeatureBento, ProcessFlow, IntegrationShowcase and GradientCTA rather than forking shared sections across agent pages.  
* IntegrationShowcase currently uses two featured columns on mobile and four at md. Long names must fit; its H3 can inherit oversized global heading styles. Adjust the shared component explicitly when implementing the compact status treatment.  
* GoHighLevel is live: display it as Live, not Coming soon or Roadmap. This is an explicit owner correction; reconcile stale website mappings and registry entries when implementing it. This guide does not establish that the code has already been updated.  
* “Popular” is not “live.” Use integrationStatus.ts and the backend registry for capability claims. Review featured-item selection when adding entries: the current first-four-popular logic can omit extra popular items.

# **4\. Build from the right page family**

| Page family | Starting point and content pattern |
| :---- | :---- |
| Marketing / solutions / platform | Copy the nearest page in src/website/pages/. Use an outcome-focused hero, relevant proof/features, restrained sections and a clear closing action. |
| AI agents | Shared ai-agents components: hero → capabilities → process → integrations → CTA. Keep page-specific content in typed props/data. |
| Blog / resources | Reuse listing, archive and article templates. Article title: Satoshi 700, 32/44/52px. Article body: PT Serif 400, 15/17px; scoped paragraph rules and max-w-3xl. Do not copy article wrapper line-height into ordinary pages. |
| Templates / recipes | Reuse catalog data and detail templates. Preserve search/filter/empty states and crawlable parent/detail links. |
| Pricing / partner / commercial | Reuse established offer data, comparison, FAQ and form flows. Keep specialized demo styling local. |
| Offers / legal | Use OffersFrame and data-page styles for dense evidence; use the legal template for /privacy and /terms. Avoid marketing-scale heroes on reference pages. |

## **Code locations for assembly and behavior**

Paths below are relative to usta-react/. Shared primitive files are in src/website/components/ui/; the FAQ accordion is in src/shared/components/ui/accordion.tsx.

| Location in usta-react/ | What it controls |
| :---- | :---- |
| [src/website/components/WebsiteStyleProvider.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/WebsiteStyleProvider.tsx) | Loads website styles and analytics. |
| [src/website/components/Layout.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/Layout.tsx) | Actual public-page shell. |
| [src/routes/home.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/routes/home.tsx) | Example route composition plus meta and canonical links. Agent route example: src/routes/ai-agents/customer-service.tsx. |
| [src/routes.website.ts](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/routes.website.ts) | Authoritative public website route registration. |
| [react-router.config.website.ts](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/react-router.config.website.ts) | MARKETING\_PATHS and dynamic prerender enumeration; new URLs need real prerender output. |
| [src/website/components/WebsiteSEO.tsx](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/components/WebsiteSEO.tsx) | Currently a no-op. Set metadata through route meta/links exports, not this component. |
| [src/website/lib/integrationStatus.ts](https://github.com/US-Tech-Automations/USTA/blob/8273f3a7911a8a7dfd88ec10d6098fc34109cefe/usta-react/src/website/lib/integrationStatus.ts) | Website status mapping; unknown entries fall back to roadmap. Registry source: repository-root backend/core/integrations/bootstrap.ts. |

The combined src/routes.ts may also need updating for local development. Editing it alone is insufficient: the website Docker build installs the website-specific route/config files. BUILD\_TARGET by itself does not reproduce that build.

# **5\. Before a new page is approved**

Treat this as the reusable acceptance checklist. Check the changed page and the shared surfaces it affects; do not claim an application-wide audit from a narrow check.

## **Choose the scope of a styling change**

* Edit global styles only for an intentional site-wide rule, such as a color token or typography scale. Check representative pages from every affected family, including both themes. Changes to src/index.css may also affect the authenticated platform.  
* Edit a shared component when the same appearance or interaction should change wherever it is reused. Review its consumers and check every affected page family; do not patch individual pages to compensate for a shared defect.  
* Use page-local styles for a requirement unique to one page or family. Keep selectors scoped, reuse semantic tokens, and avoid global overrides. Promote a repeated pattern into a shared component when reuse becomes appropriate.

## **Design and content**

* The page uses the existing shell, family template, semantic tokens and spacing. Any new global style has a deliberate cross-page purpose.  
* One clear H1, useful section hierarchy, accurate claims, working CTAs and no dead-end detail pages. Integration statuses reflect the registry; no decorative status badges.  
* Long titles, empty states, errors and loading states remain readable. Informational cards do not falsely imply clickability. Interactive cards have a real link or button.

## **Responsive and accessible behavior**

* Inspect 320, 375, 768, 1024, 1280 and 1440px widths, light/dark themes, keyboard navigation and reduced motion. Check header transitions, overflow, wrapping and focus visibility.  
* Use meaningful labels, alt text, heading order and form feedback. Keep focus out of closed menus/dialogs. Aim for 44px touch targets when adding controls; existing 36/40px heights are not a reason to make new targets cramped.  
* Verify contrast in rendered states: 4.5:1 for ordinary text, 3:1 for large text and essential control boundaries. Token names alone do not establish compliance.

## **Routing, metadata and runtime**

* Register the route and prerender path; export route meta/links for title, description and canonical URL. Check generated sitemap/discovery output and direct URL refresh—not only client-side navigation.  
* Verify actual image dimensions, lazy loading and stable placeholders. Keep essential content in the initial page. Preserve the home demo’s delayed mounting/hydration treatment when reusing it.  
* Check for console errors and layout shifts. Useful performance targets are LCP ≤2.5s, INP ≤200ms and CLS ≤0.1; these are targets, not measured results of this document.

## **Visual acceptance evidence**

* Include before/after screenshots of every affected page in the PR or review handoff, on desktop and mobile. For styling changes, capture light and dark modes. Use matching viewport sizes, content and UI states so differences can be compared. For new pages, provide after screenshots and identify the existing template used as the reference.  
* Label each screenshot with its route, viewport, theme and relevant state. Include changed menu, focus, form or error states where applicable; screenshots supplement keyboard and functional checks.

## **Existing checks to use**

From usta-react/, install with npm ci, then run npm run type-check and npm run lint:check. Use relevant existing tests under these paths:

src/website/components/\_\_tests\_\_/navLinkIntegrity.test.ts

src/website/components/\_\_tests\_\_/Header.navAccessibility.test.tsx

src/website/components/ai-agents/\_\_tests\_\_/IntegrationShowcase.test.tsx

The test:visual and test:accessibility scripts also exist. Their Playwright setup uses the local development server; confirm production behavior separately. Use the lockfile and repository scripts as the authority for dependencies. The local .nvmrc specifies Node 22; the website container uses Node 24\.

# **6\. Deployment instructions — prepare and release**

These instructions apply to the public usta-website service, not the authenticated platform. Repository-root paths are shown below. Recheck current workflow configuration before a release.

| File | Purpose |
| :---- | :---- |
| .github/workflows/deploy-production.yml | Service detection, production build/deploy and post-deploy gates. |
| .github/workflows/deploy-approve.yml | Admin approval through a deploy-pending issue. |
| usta-react/cloudbuild.website.yaml | Cloud Build, image publish, Cloud Run release and cache handling. |
| usta-react/Dockerfile.website | Production website build; full prerender into build-website/client. |
| usta-react/nginx-website.conf | Nginx routing, redirects and serving configuration; port 8080\. |
| deployment/validate-routes.shdeployment/validate-cloudbuild.sh | Preflight route and Cloud Build validation. |
| deployment/website-deploy-needed.sh | Website change detection. |
| deployment/deploy-website.sh | Manual fallback; it is not the normal release path. |

## **Prepare the release**

Complete the preceding checklist and run these from the repository root:

bash deployment/validate-routes.sh

bash deployment/validate-cloudbuild.sh usta-react/cloudbuild.website.yaml

To inspect a production-style build locally, run from usta-react/:

docker build \--platform linux/amd64 \-f Dockerfile.website \\

  \--build-arg GIT\_SHA="$(git rev-parse HEAD)" \\

  \-t usta-website:review .

docker run \--rm \-p 8080:8080 usta-website:review

Use the workflow’s build arguments when testing production-dependent behavior. Preserve the CAPTCHA configuration for forms. Expected public URLs: VITE\_APP\_URL=https://ustechautomations.com; VITE\_PLATFORM\_URL=https://app.ustechautomations.com; VITE\_API\_BASE\_URL=https://api.ustechautomations.com/api. Never place secrets in VITE\_\* variables.

## **Use the approved release path**

* Merge the reviewed change to main. A push detects affected services and updates a deploy-pending issue; it does not itself deploy production.  
* An authorized repository admin comments /deploy on that issue, not on the PR. Approval deploys the latest main at approval time, including accumulated changes—not necessarily the original issue’s commit.  
* When an authorized manual website release is appropriate, run deploy-production.yml on main with force\_website=true and other force flags false. An issue closing indicates dispatch, not successful deployment; monitor the workflow and Cloud Build.

Keep full website and incremental-blog releases coordinated through their shared deploy-website concurrency group. The manual \--cloud-build script bypasses that group and can refuse when incremental publishing is enabled; do not skip that protection as a routine workaround.

# **7\. Deployment instructions — verify and recover**

## **Know the release target**

Google Cloud project: usta-prod • Region: us-central1 • Cloud Run service: usta-website • Load balancer URL map: usta-frontend-lb.

The website Cloud Build creates the full prerendered image, publishes gcr.io/usta-prod/usta-website:latest and shifts traffic to the new revision. The base-commit pointer and CDN invalidation are best-effort steps. Record the known-good revision before releasing: the mutable latest tag is not a rollback identifier.

## **Verify the deployed revision**

gcloud run services describe usta-website \\

  \--project=usta-prod \--region=us-central1 \\

  \--format="yaml(status.latestReadyRevisionName,status.traffic)"

curl \-fsS https://ustechautomations.com/health

* Confirm the intended revision receives traffic and the workflow’s post-deploy checks pass, including machine-discovery and offer-graph checks where applicable. A healthy /health response alone is insufficient.  
* Open the actual new URL and refresh it directly. Inspect HTML metadata, canonical URL, assets, navigation, forms and CTAs on mobile and desktop. Verify that auth links go to the platform and legal links use /privacy and /terms.  
* If the CDN is stale or automatic invalidation did not complete, invalidate and verify again:

gcloud compute url-maps invalidate-cdn-cache usta-frontend-lb \\

  \--path="/\*" \--project=usta-prod

Cloud Build has a 3,000-second timeout; the GitHub job allows 55 minutes. A timeout can occur after some deployment steps have succeeded. Inspect the active revision and traffic before retrying.

## **Rollback when necessary**

Coordinate with anyone running a full or incremental release first so it cannot immediately overwrite the rollback. Identify the recorded known-good revision, then move traffic back:

gcloud run revisions list \--service=usta-website \\

  \--project=usta-prod \--region=us-central1

gcloud run services update-traffic usta-website \\

  \--project=usta-prod \--region=us-central1 \\

  \--to-revisions="KNOWN\_GOOD\_REVISION=100"

Replace KNOWN\_GOOD\_REVISION with the actual revision name. Invalidate the CDN and repeat the production checks. Do not trust the manual script’s backup tag as proof of the previous production image; it may tag the newly built image.

A traffic rollback does not reset the latest image tag or incremental-blog base pointer. Reconcile those before incremental publishing resumes, or perform a coordinated full release of the corrected source. Fix or revert the source through the normal reviewed PR process.