# BRAND.md — the look of every public feeds page

The operator's standard is `USTA_Website_UI_UX_Design_Rules.docx` (v1.3, 8 Sep 2026).
That document describes the React website in `usta-react/`. **These pages are not
that.** They are static HTML written by Python in this repo and served at
`ustechautomations.com/feeds/`. This file is that standard translated into what we
actually ship. Section numbers in brackets cite the operator's document.

The machine check is `scripts/check_brand.py`. A page that fails it strict is not
shippable. Nothing here is a matter of taste; if you want to change a rule, change
this file and the gate together, in one commit.

---

## 1. Colour tokens [doc §2 "Colors and themes"]

Every colour on a feeds page comes from a CSS variable in `styles.css`. The HSL
channels below are copied from the operator's table and already live in
`styles.css`; do not retype them into a page.

| Variable | Light | Dark |
| :-- | :-- | :-- |
| `--background` | `220 10% 99%` | `220 15% 8%` |
| `--foreground` | `220 20% 10%` | `220 15% 96%` |
| `--card` | `0 0% 100%` | `220 12% 10%` |
| `--card-foreground` | `220 20% 10%` | `220 15% 96%` |
| `--secondary` / `--muted` | `220 12% 97%` | `220 10% 16%` |
| `--muted-foreground` | `220 10% 42%` | `220 8% 62%` |
| `--border` | `220 13% 94%` | `220 10% 18%` |
| `--primary` | `207 100% 50%` | `207 100% 50%` |
| `--primary-foreground` | `0 0% 100%` | `0 0% 100%` |
| `--primary-hover` | `207 100% 44%` | `207 100% 44%` |

Use the resolved shorthands in page CSS, not raw channels: `var(--bg)`,
`var(--surface)`, `var(--surface-2)`, `var(--fg)`, `var(--muted-fg)`, `var(--line)`,
`var(--accent)`. Where you need alpha, write `hsl(var(--border) / .5)` — a token
reference, which the gate allows. A bare `hsl(220 13% 94%)` is a literal, and fails.

**Two colour literals are allowed, both outside page CSS** [doc §2: "Keep brand-logo
and meaningful error colors local"]:

- the brand mark's own `fill="#0391FE"` inside the inline logo SVG;
- `<meta name="theme-color">`, which paints browser chrome, not the page.

The gate only reads `style="…"` attributes and `<style>` blocks, so both are exempt
by construction. Anywhere else, a hex, `rgb()` or literal `hsl()` is a failure.

## 2. Fonts [doc §2 "Typography and spacing"]

Satoshi, loaded once in `styles.css` from
`https://ustechautomations.com/fonts/Satoshi-Variable.woff2` as a variable face
(`font-weight: 300 900`, `font-display: swap`). Do not add a second `@font-face`, do
not load Google Fonts, do not self-host a copy in this repo.

Body and headings are weight 500. Stacks are `--sans` (Satoshi), `--serif` (PT Serif
then Georgia) and `--mono`. PT Serif has **no** `@font-face` here and falls back to
Georgia; see §11.

## 3. Type scale [doc §2]

| Element | Base | ≥768px | ≥1024px |
| :-- | :-- | :-- | :-- |
| `h1` (`.hero h1`) | 48px | 60px | 72px, tracking −.03em |
| `h2` | 30px | 36px | — |
| `h3` | 24px | 30px | — |
| body | 16px, line-height 1.65 | | |
| `.lede` | clamp 17→20px | | |

Headings carry weight 500, tracking −.025em, line-height 1.15. Feed pages step one
rung down the site's ladder on purpose: an `h2` here is a subsection of a record, not
a marketing section header. Reading measure is `76ch` on `main section`; the fact
rail and evidence tables get the full 1280px container.

## 4. Spacing, radii, borders [doc §2, §3]

- Page gutter: `.wrap` is `max-width: 1280px`, padding 24px, 32px at ≥768px.
- Section rhythm: `main section` margin-bottom 2.75rem; hero 3.5rem top.
- Radius: one value, `--radius: .5rem`. Pill shapes (`999px`) are banned — see §7.
- Border: always `1px solid var(--line)`. There is no second border weight.
- Cards: `.card`, `.evidence`, `.contact` — surface fill, 1px line, `--radius`, at
  most `--shadow-sm`. Padding 1.25rem, 1.75rem on the contact block.

## 5. Buttons [doc §3 "Controls, cards and visuals"]

Two classes, both built on `.btn`. There is no third.

- `.btn .btn-buy` — the one primary action. Primary fill, primary-foreground text.
- `.btn .btn-ghost` — the secondary action. Transparent, primary text, thin border.
- `.btn-lg` bumps a hero or contact-block CTA. `.mail` is the same shape for mailto.

One primary action per page. Below 34rem they stack full-width rather than shrinking
their text [doc §3 "Mobile"]. Keep the focus ring; never remove outlines.

## 6. The page shell [doc §3 "Shared shell"]

Every public page is exactly this, in this order. `scripts/render_family.py` emits it;
copy from there, do not retype it.

1. `<html lang="en">`, `<meta charset>`, `<meta name="viewport">`, `<title>`,
   canonical link, `<link rel="stylesheet" href="…/styles.css">`.
2. `<body data-family="…">`
3. `<a class="skip" href="#main">Skip to content</a>`
4. `<header class="masthead">` — sticky, 64px, 1px bottom border, translucent +
   blur, wordmark left, crumbs beside it.
5. `<section class="hero">` — eyebrow, **exactly one `<h1>`**, lede, `dl.rail`,
   then the primary action.
6. `<main id="main">` with the content sections.
7. `<footer class="site">` — honesty line and the postal address.

There is one header and one footer. Do not fork them, do not add a mobile bottom nav,
do not add a theme toggle [doc §2, §3].

## 7. Banned

- **Decorative status badges** [doc §1, §3 "Status presentation", §5]. That means the
  `pill`, `pill-ready` and `pill-hold` classes that exist today. The doc is explicit
  that existing badge code is not the standard to copy. Replacement: muted text plus a
  muted icon, no container, readable in both themes, never colour alone.
- A new palette, or any hex / `rgb()` / literal `hsl()` in a `style=` attribute or a
  page `<style>` block [doc §2].
- A second header, footer, theme system or set of basic controls [doc §1].
- More than one `<h1>` [doc §1, §5].
- Claiming an integration or capability we do not run [doc §1, §3]. `check_site.py`
  already refuses the specific boast phrases; that gate stays authoritative.
- A `<style>` block that reaches outside its own page — no bare element or `:root`
  selectors, no overriding shared classes [doc §5 "Choose the scope"].

## 8. Light and dark [doc §1, §5]

`styles.css` defines the light tokens on bare `:root`, redefines them under
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`,
and again under `:root[data-theme="dark"]`. Any new token needs all three. A page that
looks right in one theme only is not finished.

## 9. Mobile and keyboard [doc §3, §5]

Content starts in one column and stays readable at 320, 375, 768, 1024, 1280 and
1440px. Wide things — evidence tables, code — scroll inside `.scroll`, never the body.
The skip link, `main id="main"`, visible focus and real link/button elements are
required. New touch targets aim for 44px. Images get dimensions and alt text;
decorative icons are hidden from assistive technology.

## 10. Baseline 2026-09-08

`python3 scripts/build_site.py && python3 scripts/check_brand.py --report` over
**3169** built pages, on commit-time `dist/`. Strict mode is **not** wired into
`check_site.py` yet; it becomes mandatory when every number below is zero.

| Check | Pages failing |
| :-- | --: |
| `one-h1` | 0 |
| `stylesheet` | 0 |
| `viewport` | 0 |
| `masthead` | 2 |
| `footer` | 0 |
| `skip-link` | 2 |
| `main-landmark` | 2 |
| `html-lang` | 0 |
| `no-status-badge` | 895 |
| `no-inline-colour` | 2 |
| `no-local-colour` | 11 |
| `themes` (repo-level) | pass |
| **total failing checks** | **914** |

The shell failures are the same two hand-written pages, `acacheck` and `schemahand`,
which still carry the old bare `<header>`. The colour failures are eleven pages with
their own `<style>` block and two with a colour in a `style=` attribute. The 895 is
the badge rule and is the only large number: it is one class pair used across the
generated family pages, so it is one edit in `render_family.py`, not 895 edits.

## 11. What did not translate

- **Everything React.** `WebsiteStyleProvider`, `Layout.tsx`, `Button`, `Input`,
  `Card`, `BentoGrid`, `FadeIn`, `ThemeProvider`, `AgentPageHero`,
  `IntegrationShowcase`, Lucide icons, React Router `Link`. We have no components and
  no JavaScript framework; the equivalents are the CSS classes named above.
- **Route registration, prerender paths, `routes.website.ts`, `WebsiteSEO`** [doc §4].
  There are no routes here. A page is a folder with an `index.html`; discovery is
  `sitemap.xml` and `catalog.json`, checked by `scripts/check_urls.py`.
- **The deployment chapters** [doc §6, §7]. Cloud Run, Cloud Build, the
  `deploy-pending` issue and the CDN invalidation belong to `usta-react`. This estate
  publishes by merging to `main`; that rail is unchanged and out of scope here.
- **`npm run type-check`, `lint:check`, the Playwright visual/accessibility suites**
  [doc §5]. No Node in this repo. `scripts/check_brand.py` plus the existing
  `scripts/run_all_checks.py` are the equivalent.
- **PT Serif.** The doc sets article body type in PT Serif [doc §4]. We declare the
  stack but ship no font file, so it renders as Georgia. Left as-is: no feeds page is
  long-form article prose, and adding a font file is a page-weight cost for nothing.
- **Motion, `FadeIn`, hero gradients** [doc §3]. Deliberately not translated. These
  pages are evidence, not marketing, and animation is not wanted here.
- **Contrast measurement, screenshot evidence, LCP/INP/CLS** [doc §5]. These are human
  review steps. A static gate cannot render a page, so it cannot measure them; they
  stay a reviewer's job and are not claimed as passing.
- **The `#abc` inside a page `<style>` block.** The gate reads only declaration bodies
  between braces, so an id selector is not mistaken for a colour. A selector that is
  itself three-to-eight hex characters (`#dead {`) would trip it. Use a class.
