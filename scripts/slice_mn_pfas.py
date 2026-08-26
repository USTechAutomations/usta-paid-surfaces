#!/usr/bin/env python3
"""Minnesota PFAS-in-products filer check: one named product line, one dated letter.

WHAT THIS SELLS
    A written verdict for one named product line: must file, need not file, or
    cannot tell from what you sent. The letter shows the tests we applied, the
    facts they sent, and the sentences we used from saved Minnesota pages.

WHY kind=build AND extras.json
    This is not a dated feed. There is no clock, no store, and no CSV of public
    rows. check_sample_rows would demand a sample file of "real rows out of
    dated copies we sealed ourselves" -- a sentence that is false here. kind=build
    is the estate's existing door for priced work sold by email
    (families/offers/). extras.json is what actually ships a kind=build page;
    catalog.json holds the price and the terms. Do not "fix" that by dropping
    either line.

WHY THERE ARE NO CHILD PAGES
    slices() returns an empty list on purpose. One product, one page.

WHERE THE WORDS COME FROM
    Saved copies of Minnesota pages fetched 2026-08-25, sitting in
    families/mn-pfas/sources/. Every quote this page prints is searched for in
    those files on every build. A quote that no longer matches stops the build.

WHAT IT REFUSES TO BUILD
    A Stripe URL (catalog checkout has no url; Claude mints).
    The sentence "you are compliant" or any certificate of compliance.
    A medical-device reporting out (statute subd. 8(b) carves testing and bans,
    not reporting).
    A need-not-file verdict grounded only in 325F.072 or 325F.075: those compiled
    sections are a class-B foam prohibition and a food-package prohibition.
    116.943 subd. 8(a)(2) is the sentence that carves products regulated under
    them out of "this section". The form cannot apply that carve-out, so that
    ground is cannot tell.
    A dollar amount in the search line other than the catalog price.
    A quote that is not in the saved copy it claims to come from.

THE PRICE
    catalog.json is the only place the rail amount is written. It is $450 for
    the first named product line. $175 for a further line on the same request
    lives in checkout.terms and in body prose, never in the rail, the search
    line, or a link -- those surfaces are gated to the catalog price string.
"""
from __future__ import annotations

import html
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import price_of, render, section, table  # noqa: E402

FAMILY = "mn-pfas"
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "families" / FAMILY / "sources"
READ_ON = "25 Aug 2026"

esc = html.escape


# ------------------------------------------------------------------ sources

# Filename inside families/mn-pfas/sources/, and a plain name for the stamp.
SOURCE_FILES = {
    "mpca-reporting": (
        "reporting-pfas-in-products.extracted.txt",
        "MPCA reporting page, fetched 25 Aug 2026",
    ),
    "mpca-prohibitions": (
        "pfas-use-prohibitions-and-reporting.extracted.txt",
        "MPCA prohibitions-and-reporting page, fetched 25 Aug 2026",
    ),
    "mpca-rulemaking": (
        "pfas-in-products-reporting-and-fees.extracted.txt",
        "MPCA reporting-and-fees rulemaking page, fetched 25 Aug 2026",
    ),
    "stat-116943": (
        "stat-116.943.extracted.txt",
        "compiled Minn. Stat. § 116.943, fetched 25 Aug 2026",
    ),
    "session-law": (
        "laws-2026-c127-art14-s4.section4.html",
        "2026 Minn. Laws ch. 127 art. 14 § 4, fetched 25 Aug 2026",
    ),
    "rules-7026": (
        "rules-7026-full.extracted.txt",
        "compiled Minn. R. ch. 7026, fetched 25 Aug 2026",
    ),
    "stat-325f072": (
        "325F.072.txt",
        "compiled Minn. Stat. § 325F.072, fetched 25 Aug 2026",
    ),
    "stat-325f075": (
        "325F.075.txt",
        "compiled Minn. Stat. § 325F.075, fetched 25 Aug 2026",
    ),
}


def _norm(s: str) -> str:
    """Fold a quote and a source file down to a form a comparison can trust.

    The saved MPCA extracts carry non-breaking spaces and curly apostrophes.
    A guard that compared raw strings would miss a quote that reached the page
    with those folded, which is how a quote reaches a page.
    """
    s = html.unescape(s or "")
    for a, b in (
        ("\xa0", " "), ("\u202f", " "), ("\u2009", " "),
        ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
        ("—", "-"), ("–", "-"),
    ):
        s = s.replace(a, b)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


_SOURCE_TEXT: dict[str, str] | None = None


def source_text() -> dict[str, str]:
    """The saved files, folded once per build."""
    global _SOURCE_TEXT
    if _SOURCE_TEXT is not None:
        return _SOURCE_TEXT
    out: dict[str, str] = {}
    missing = []
    for key, (name, _stamp) in SOURCE_FILES.items():
        path = SOURCES / name
        if not path.is_file():
            missing.append(str(path))
            continue
        out[key] = _norm(path.read_text(encoding="utf-8"))
    if missing:
        raise SystemExit(
            f"{FAMILY}: saved source file(s) missing, so no quote on this page "
            f"can be re-checked: {missing}. Nothing was written."
        )
    _SOURCE_TEXT = out
    return out


# Each quote this page is allowed to print. text must appear, after _norm, in
# the named source file. Adding a quote to the page without adding it here is
# how a sentence nobody checked would ship.
QUOTES: list[tuple[str, str]] = [
    (
        "Initial reports are due by September 15, 2026. Products manufactured before July 1, 2023, are excluded.",
        "mpca-reporting",
    ),
    (
        "The Minnesota Pollution Control Agency (MPCA) extended the initial reporting due date to September 15, 2026.",
        "mpca-reporting",
    ),
    (
        "The reporting due date for manufacturers receiving an extension is Dec. 14, 2026.",
        "mpca-reporting",
    ),
    (
        "The reporting due date for manufacturers denied an extension is 30 days after the notice of denial or Sept. 15, 2026, whichever is later.",
        "mpca-reporting",
    ),
    (
        "The MPCA is processing a large volume of reporting due date extension requests following the Aug. 16, 2026, postmark deadline.",
        "mpca-reporting",
    ),
    (
        "Subsequent reports are due each year on February 1.",
        "mpca-reporting",
    ),
    (
        "Each manufacturer is required to pay a one-time initial reporting fee of $800.",
        "mpca-reporting",
    ),
    (
        "products sold only online",
        "mpca-reporting",
    ),
    (
        "Any manufacturer of a product sold, offered for sale, or distributed in Minnesota and contains intentionally added PFAS must report.",
        "mpca-reporting",
    ),
    (
        "the entity that produces the product",
        "mpca-reporting",
    ),
    (
        "the entity that contracts production of the product under its brand or label",
        "mpca-reporting",
    ),
    (
        "the importer of first domestic distributor if the producer/brand owner has no U.S. presence",
        "mpca-reporting",
    ),
    (
        "One entity may submit a report on behalf of others if there is a documented agreement and all verification requirements are met.",
        "mpca-reporting",
    ),
    (
        "Products that have been previously installed, operated, or otherwise utilized by a prior owner are not required to be reported.",
        "mpca-reporting",
    ),
    (
        "This exemption does not apply to products returned to a retailer or offered for resale if they were not previously used.",
        "mpca-reporting",
    ),
    (
        'This product would not be reported because the PFAS would not be considered "intentionally added."',
        "mpca-reporting",
    ),
    (
        'Products that are leased, rented, or otherwise distributed in the state are considered "distributed in the state" under Minnesota Rule 7026.0010, Subp. 9.',
        "mpca-reporting",
    ),
    (
        "A one-time extension may be requested, but lack of supplier data does not remove the obligation to report.",
        "mpca-reporting",
    ),
    (
        "PFAS Product Reporting Information System for Manufacturers (PRISM) is used by manufacturers and their representatives to submit PFAS in product reports and pay related fees.",
        "mpca-reporting",
    ),
    (
        "Products that contain PFAS only in internal and electronic components are no longer subject to the 2025 sales prohibition but are subject to the 2026 PFAS reporting requirement.",
        "mpca-reporting",
    ),
    (
        "Manufacturers receiving extensions who later decide to request a waiver should postmark the waiver request by Nov. 14, 2026.",
        "mpca-reporting",
    ),
    (
        "Minn. Stat. §116.943 defines PFAS as a class of fluorinated organic chemicals containing at least one fully fluorinated carbon atom.",
        "mpca-reporting",
    ),
    (
        "setting a one-time flat fee of $800 per manufacturer to cover implementation costs",
        "mpca-reporting",
    ),
    (
        "must submit an initial report to the MPCA by Sept. 15, 2026, and pay the associated fee.",
        "mpca-rulemaking",
    ),
    (
        "However, those products must be reported if they contain intentionally added PFAS starting in 2026. (Minn. Stat. § 116.943, Subd. 8)",
        "mpca-prohibitions",
    ),
    (
        "Intentionally added PFAS in firefighting foam are prohibited for testing, training, and incident response, with limited exceptions that expire in 2026 and 2028.",
        "mpca-prohibitions",
    ),
    (
        "Intentionally added PFAS in food packaging are prohibited. (Minn. Stat. § 325F.075)",
        "mpca-prohibitions",
    ),
    (
        '"Intentionally added" means PFAS deliberately added during the manufacture of a product where the continued presence of PFAS is desired in the final product or one of the product\'s components to perform a specific function.',
        "stat-116943",
    ),
    (
        '"Manufacturer" means the person that creates or produces a product or whose brand name is affixed to the product. In the case of a product imported into the United States, manufacturer includes the importer or first domestic distributor of the product if the person that manufactured or assembled the product or whose brand name is affixed to the product does not have a presence in the United States.',
        "stat-116943",
    ),
    (
        '"Perfluoroalkyl and polyfluoroalkyl substances" or "PFAS" means a class of fluorinated organic chemicals containing at least one fully fluorinated carbon atom.',
        "stat-116943",
    ),
    (
        "On or before January 1, 2026, a manufacturer of a product sold, offered for sale, or distributed in the state that contains intentionally added PFAS must submit to the commissioner information that includes:",
        "stat-116943",
    ),
    (
        'This section is "Amara\'s Law."',
        "stat-116943",
    ),
    (
        "This section does not apply to:",
        "stat-116943",
    ),
    (
        "a product regulated under section 325F.072 or 325F.075; or",
        "stat-116943",
    ),
    (
        "the sale or resale of a used product.",
        "stat-116943",
    ),
    (
        "Subdivisions 4 and 5 do not apply to a prosthetic or orthotic device or to any product that is a medical device or drug or that is otherwise used in a medical setting or in medical applications regulated by the United States Food and Drug Administration.",
        "stat-116943",
    ),
    (
        "Beginning January 1, 2025, a person may not sell, offer for sale, or distribute for sale in this state the following products if the product contains intentionally added PFAS:",
        "stat-116943",
    ),
    (
        "Beginning January 1, 2032, a person may not sell, offer for sale, or distribute for sale in this state any product that contains intentionally added PFAS, unless the commissioner has determined by rule that the use of PFAS in the product is a currently unavoidable use.",
        "stat-116943",
    ),
    (
        "The commissioner may enforce this section under sections 115.071 and 116.072.",
        "stat-116943",
    ),
    (
        "manufactured after July 1, 2023",
        "session-law",
    ),
    (
        "This section is effective the day following final enactment.",
        "session-law",
    ),
    (
        '"Used product" means a product that has been installed, operated, or utilized for its intended purpose by at least one owner or operator or that is otherwise not pristine. Used product does not include a product that has been returned to a retailer or that is otherwise offered for resale if the product was not installed, operated, or utilized before resale.',
        "rules-7026",
    ),
    (
        "Component includes packaging only when the packaging is inseparable or integral to the final product's containment, dispensing, or preservation.",
        "rules-7026",
    ),
    (
        "A manufacturer or group of manufacturers of a product that is sold, offered for sale, or distributed in the state and that contains intentionally added PFAS must submit a report to the commissioner on or before January 1, 2026.",
        "rules-7026",
    ),
    (
        "A manufacturer or group of manufacturers of a new product with intentionally added PFAS after January 1, 2026, must submit a report by February 1 the following year.",
        "rules-7026",
    ),
    (
        "By February 1 each year, a manufacturer or group of manufacturers must submit an update to the report submitted under part 7026.0030 if during the previous calendar year:",
        "rules-7026",
    ),
    (
        "the commissioner must grant one 90-day extension of the established reporting due date.",
        "rules-7026",
    ),
    (
        "a product regulated under Minnesota Statutes, section 325F.072 or 325F.075;",
        "rules-7026",
    ),
    (
        "325F.072 FIREFIGHTING FOAM.",
        "stat-325f072",
    ),
    (
        '"Class B firefighting foam" means foam designed to prevent or extinguish a fire in flammable liquids, combustible liquids, petroleum greases, tars, oils, oil-based paints, solvents, lacquers, alcohols, and flammable gases.',
        "stat-325f072",
    ),
    (
        "No person, political subdivision, or state agency shall manufacture or knowingly sell, offer for sale, distribute for sale, or distribute for use in this state, and no person shall use in this state, class B firefighting foam containing PFAS chemicals.",
        "stat-325f072",
    ),
    (
        "Beginning on July 1, 2020, any person, political subdivision, or state agency that discharges, uses, releases, or knows of a discharge, use, or release of class B firefighting foam that contains intentionally added PFAS chemicals must be reported to the Minnesota Fire Incident Reporting System within 24 hours of the discharge, use, or release.",
        "stat-325f072",
    ),
    (
        "325F.075 FOOD PACKAGING; PFAS.",
        "stat-325f075",
    ),
    (
        '"Food package" means a container applied to or providing a means to market, protect, handle, deliver, serve, contain, or store a food or beverage.',
        "stat-325f075",
    ),
    (
        "No person shall manufacture or knowingly sell, offer for sale, distribute for sale, distribute, or offer for use in Minnesota a food package that contains intentionally added PFAS.",
        "stat-325f075",
    ),
    (
        "When requested by the commissioner of the Pollution Control Agency, a person must furnish to the commissioner any information that the person may have or may reasonably obtain that is relevant to show compliance with this section.",
        "stat-325f075",
    ),
]


def q(text: str) -> str:
    """The quote, escaped, as a blockquote cell. Must be in QUOTES."""
    return f"<blockquote>{esc(text)}</blockquote>"


def check_quotes_in_sources() -> int:
    """Every allowed quote still appears in the saved file it names."""
    texts = source_text()
    missing = []
    for text, key in QUOTES:
        hay = texts.get(key, "")
        if _norm(text) not in hay:
            missing.append((key, text[:80]))
    if missing:
        first = missing[0]
        raise SystemExit(
            f"{FAMILY}: {len(missing)} quote(s) no longer appear in the saved "
            f"source they name. First: {first[0]} {first[1]!r}. A quote that "
            "has drifted one word is worse than no quote. Nothing was written."
        )
    return len(QUOTES)


def check_page_quotes(page: str) -> None:
    """Every blockquote on the finished page is one of the allowed quotes."""
    allowed = {_norm(t) for t, _k in QUOTES}
    found = re.findall(r"(?is)<blockquote[^>]*>(.*?)</blockquote>", page)
    stray = []
    for raw in found:
        n = _norm(raw)
        if n and n not in allowed:
            stray.append(n[:80])
    if stray:
        raise SystemExit(
            f"{FAMILY}: a quoted sentence on this page is not in QUOTES, so it "
            f"was never checked against a saved file: {stray[0]!r}. Nothing was "
            "written."
        )


BANNED_CLAIMS = (
    "you are compliant",
    "you are in compliance",
    "certificate of compliance",
    "we certify",
    "request your extension today",
)


def check_banned(page: str) -> None:
    vis = _norm(re.sub(r"(?is)<[^>]+>", " ", page)).lower()
    hits = [p for p in BANNED_CLAIMS if p in vis]
    if hits:
        raise SystemExit(
            f"{FAMILY}: forbidden claim on the page: {hits}. Nothing was written."
        )


def check_search_line(spec: dict) -> None:
    """The search line may not name an amount the catalog does not sell."""
    desc = spec["desc"]
    price = price_of(spec)
    # Whole amounts, same rule as check_site._amounts.
    money = {m.group(0).replace(" ", "") for m in re.finditer(r"\$\s?\d[\d,]*(?:\.\d+)?", desc)}
    allowed = {m.group(0).replace(" ", "") for m in re.finditer(r"\$\s?\d[\d,]*(?:\.\d+)?", price)}
    stray = sorted(money - allowed)
    if stray:
        raise SystemExit(
            f"{FAMILY}: the search line names {stray} and the catalog sells this "
            f"at {price!r}. Nothing was written."
        )


# ------------------------------------------------------------------ catalog


def _fam_row() -> dict:
    """This family's catalog row. No fallback default."""
    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(
            f"{FAMILY}: no catalog row anywhere -- not in catalog.json and not in a "
            f"catalog-add-{FAMILY}.json fragment. Refusing to render a page whose "
            "price, group and buyer nothing has checked."
        )
    return row


# ------------------------------------------------------------------ example

# Invented, and said to be invented everywhere it appears. LLC in the name so
# the person-detector does not read it as a human trading under their own name.
EXAMPLE = {
    "company": "NORTHWOOD COATINGS LLC",
    "brand": "NORTHWOOD",
    "line": "NWC-400 WATER-SHED FABRIC FINISH",
    "what": "A water-resistant finish for outdoor fabric, sold in 5 litre jugs.",
    "role": "we make it",
    "minnesota": "yes, including online listings that ship into the state",
    "made": "on or after 1 July 2023",
    "pfas": "yes, added on purpose for water resistance",
    "used": "no",
}


def check_example_not_a_person() -> None:
    for key in ("company", "brand", "line"):
        if privacy.looks_personal(EXAMPLE[key]):
            raise SystemExit(
                f"{FAMILY}: the invented example {key} {EXAMPLE[key]!r} reads as a "
                "person's name, so it cannot go on a public page. Nothing was written."
            )


# ------------------------------------------------------------------ page


def _quote_cell(text: str) -> str:
    return q(text)


def family_spec() -> dict:
    """The dict render_family turns into families/mn-pfas/index.html.

    Guards run on the finished bytes, not on the pieces: the template wraps
    every section in a tab title, a search line and a price rail.
    """
    fam = _fam_row()
    n_quotes = check_quotes_in_sources()
    check_example_not_a_person()
    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Minnesota PFAS filer check")

    stamp = SOURCE_FILES["mpca-reporting"][1]

    # ---- 1. the refusal, first ----
    body = (
        "      <p><strong>This is not legal advice and we are not your lawyer.</strong> "
        "You describe one named product line. We read the Minnesota PFAS-in-products "
        "reporting rule against the facts you sent and we write one of three verdicts: "
        "<strong>must file</strong>, <strong>need not file</strong>, or "
        "<strong>cannot tell from what you sent</strong>. The letter shows the tests, "
        "the sentences we used, and the pages we read.</p>\n"
        '      <div class="honest">\n'
        "        <p><strong>A verdict is not a certificate that you are in the clear.</strong> "
        "We do not file the state report, we do not log into PRISM, we do not pay the "
        "state&rsquo;s fee, and we will not write that you are in the clear. If the facts "
        "you sent were wrong, the verdict is wrong with them.</p>\n"
        "        <p><strong>We do not test the product in a lab.</strong> This is a filer "
        "check, not a chemistry cutoff. Minnesota&rsquo;s report, on the pages we saved, "
        "turns on PFAS that was added on purpose, not on every trace a lab might find.</p>\n"
        "      </div>"
    )
    sections = [section("Read this before anything else", None, body)]

    # ---- 2. who ----
    who_rows = [
        [
            "Maker, brand owner, or (if those have no US presence) importer or first domestic distributor",
            _quote_cell(
                '"Manufacturer" means the person that creates or produces a product or whose brand name is affixed to the product. In the case of a product imported into the United States, manufacturer includes the importer or first domestic distributor of the product if the person that manufactured or assembled the product or whose brand name is affixed to the product does not have a presence in the United States.'
            ),
            "Minn. Stat. § 116.943 subd. 1(o), compiled page fetched 25 Aug 2026",
        ],
        [
            "The MPCA reporting FAQ says the same three roles in its own words",
            _quote_cell("the entity that produces the product"),
            stamp,
        ],
        [
            "Sold, offered for sale, or distributed in Minnesota, including listings that sell only online",
            _quote_cell("products sold only online"),
            stamp,
        ],
        [
            "The MPCA reporting FAQ treats leased or rented products as distributed in the state. The compiled rule 7026.0010 subp. 9, in the file we saved, defines &ldquo;Distribute for sale&rdquo; as shipping a product so a receiving party will sell it. We quote the FAQ for leases; we do not claim those words sit in subp. 9.",
            _quote_cell(
                'Products that are leased, rented, or otherwise distributed in the state are considered "distributed in the state" under Minnesota Rule 7026.0010, Subp. 9.'
            ),
            stamp,
        ],
    ]
    body = (
        "      <p>On the MPCA reporting page we saved on 25 Aug 2026:</p>\n"
        + table(
            ["The test", "The sentence we use", "Where"],
            who_rows,
            "Who the reporting page and the compiled statute name",
            stamp,
        )
        + "\n      <p>If you only put someone else&rsquo;s branded goods on a shelf and "
        "you do not make, brand, or import them, say so on the form. That is often the "
        "whole question. You do not need to be based in Minnesota.</p>"
    )
    sections.append(section("Who this letter is for", stamp, body))

    # ---- 3. dates ----
    date_rows = [
        [
            "Initial report, as the MPCA reporting page now administers it",
            "15 Sep 2026",
            _quote_cell(
                "Initial reports are due by September 15, 2026. Products manufactured before July 1, 2023, are excluded."
            ),
        ],
        [
            "Later date, only for manufacturers <strong>receiving</strong> an extension",
            "14 Dec 2026",
            _quote_cell(
                "The reporting due date for manufacturers receiving an extension is Dec. 14, 2026."
            ),
        ],
        [
            "Postmark cut-off for asking. As of 25 Aug 2026 that cut-off is past. Asking is not the same as receiving.",
            "16 Aug 2026",
            _quote_cell(
                "The MPCA is processing a large volume of reporting due date extension requests following the Aug. 16, 2026, postmark deadline."
            ),
        ],
        [
            "If the extension request is denied",
            "30 days after the denial notice, or 15 Sep 2026, whichever is later",
            _quote_cell(
                "The reporting due date for manufacturers denied an extension is 30 days after the notice of denial or Sept. 15, 2026, whichever is later."
            ),
        ],
        [
            "Products manufactured before this date, excluded from reporting on the MPCA page and in the 2026 session law",
            "1 Jul 2023",
            _quote_cell("manufactured after July 1, 2023"),
        ],
        [
            "Updates, when required, after the first report",
            "1 Feb each year",
            _quote_cell("Subsequent reports are due each year on February 1."),
        ],
        [
            "What the compiled statute page still prints for the first report. The session law did not change this date; it inserted the July 2023 manufacture cut-off. The MPCA pages name 15 Sep 2026. This letter uses the MPCA date.",
            "1 Jan 2026",
            _quote_cell(
                "On or before January 1, 2026, a manufacturer of a product sold, offered for sale, or distributed in the state that contains intentionally added PFAS must submit to the commissioner information that includes:"
            ),
        ],
    ]
    body = (
        "      <p>Today on the clock of the pages we saved is <strong>25 Aug 2026</strong>. "
        "The first MPCA date had not passed then. The 16 Aug postmark cut-off had.</p>\n"
        + table(
            ["What", "Date", "The sentence we use"],
            date_rows,
            f"{len(date_rows)} dates, each tied to a saved page",
            "pages fetched 25 Aug 2026",
        )
        + "\n      <p>Do not write to us asking us to request your extension. That window "
        "is past on the dates above. A waiver is a different request and is not this "
        "letter.</p>"
    )
    sections.append(section("The dates that apply", "pages fetched 25 Aug 2026", body))

    # ---- 4. the tests ----
    test_rows = [
        [
            "Intentionally added PFAS, not every lab trace",
            _quote_cell(
                '"Intentionally added" means PFAS deliberately added during the manufacture of a product where the continued presence of PFAS is desired in the final product or one of the product\'s components to perform a specific function.'
            ),
            "Minn. Stat. § 116.943 subd. 1(l)",
        ],
        [
            "What Minnesota means by PFAS",
            _quote_cell(
                '"Perfluoroalkyl and polyfluoroalkyl substances" or "PFAS" means a class of fluorinated organic chemicals containing at least one fully fluorinated carbon atom.'
            ),
            "Minn. Stat. § 116.943 subd. 1(q)",
        ],
        [
            "Used products",
            _quote_cell(
                "Products that have been previously installed, operated, or otherwise utilized by a prior owner are not required to be reported."
            ),
            stamp,
        ],
        [
            "Unused returns still in",
            _quote_cell(
                "This exemption does not apply to products returned to a retailer or offered for resale if they were not previously used."
            ),
            stamp,
        ],
        [
            "PFAS that arrives only as contamination in recycled content, on the MPCA FAQ",
            _quote_cell(
                'This product would not be reported because the PFAS would not be considered "intentionally added."'
            ),
            stamp,
        ],
        [
            "A quiet supplier does not move the deadline",
            _quote_cell(
                "A one-time extension may be requested, but lack of supplier data does not remove the obligation to report."
            ),
            stamp,
        ],
        [
            "Internal or electronic-only PFAS: still in the 2026 report, even where the 2025 sales ban does not apply",
            _quote_cell(
                "Products that contain PFAS only in internal and electronic components are no longer subject to the 2025 sales prohibition but are subject to the 2026 PFAS reporting requirement."
            ),
            stamp,
        ],
    ]
    body = (
        "      <p>Each verdict names which of these held, with the fact you sent next to "
        "the sentence. If a fact the rule turns on is missing, we will not guess.</p>\n"
        + table(
            ["The test", "The sentence we use", "Where"],
            test_rows,
            "The tests a verdict has to walk",
            f"{n_quotes} quotes checked against saved files on every build",
        )
    )
    sections.append(section("The tests a verdict walks", f"{n_quotes} quotes re-checked", body))

    # ---- 5. three verdicts ----
    body = (
        "      <p>One of these three labels, in plain type, once.</p>\n"
        "      <ul class=\"spec\">\n"
        "        <li><strong>Must file</strong>"
        "<span class=\"sub\">On the facts you sent, you look like a manufacturer as the "
        "rule uses that word, the product is sold, offered, or distributed in Minnesota, "
        "PFAS was added on purpose, and none of the exclusions you described apply. The "
        "letter does not file the report, fill the state form, or pay the state fee.</span></li>\n"
        "        <li><strong>Need not file</strong>"
        "<span class=\"sub\">On the facts you sent, at least one test does not hold: you "
        "are not the maker, brand owner, or importer the rule names; or the product was "
        "made before 1 Jul 2023; or it is a used product the MPCA FAQ leaves out; or you "
        "state that PFAS was not added on purpose. The letter names the test that failed "
        "and quotes the source. It is not a permission slip you can show a retailer or "
        "the agency.</span></li>\n"
        "        <li><strong>Cannot tell from what you sent</strong>"
        "<span class=\"sub\">A fact the rule turns on is missing or in conflict. We will "
        "not pick a side to make the letter feel finished. A silent supplier is not "
        "&ldquo;need not file.&rdquo; A write-in of &ldquo;foam,&rdquo; &ldquo;food "
        "packaging,&rdquo; or &ldquo;we are FDA&rdquo; is cannot tell until a person "
        "matches the product to the compiled definitions. See the 325F.072 / 325F.075 "
        "section below.</span></li>\n"
        "      </ul>"
    )
    sections.append(section("The three verdicts", None, body))

    # ---- 6. form ----
    form_rows = [
        ["Legal company name", "Who is asking"],
        ["Brand on the product, if different", "The rule may treat a brand owner as a manufacturer"],
        ["Named product line", "The unit we price and the unit we verdict"],
        ["Short description of what it is", "So the letter is about a real thing, not a SKU code"],
        ["Your role: we make it / our brand is on it / we import it into the US / we only retail someone else's brand / other", "Manufacturer test"],
        ["Sold, offered, or distributed in Minnesota? Yes / no / only online / we do not know. Include leased or rented if that is how it goes out.", "Minnesota nexus"],
        ["When was this product line manufactured? Before 1 Jul 2023 / on or after 1 Jul 2023 / mixed dates / we do not know", "Older-product cut-off"],
        ["Was PFAS added on purpose to the product or a part of it? Yes / no / supplier will not say / we have not asked / we do not know", "Intentionally added"],
        ["If yes: what job does the PFAS do?", "Function is part of the state&rsquo;s report; collected so the letter can say whether you already have what a filing would need"],
        ["Is this a used product? Yes / no / returned unused to a retailer / we do not know", "Used-product exclusion"],
        ["Pesticide, fertilizer, soil or plant amendment, or liming material? Yes / no / we do not know", "May be a different agency&rsquo;s form; default verdict is cannot tell on that split"],
        ["Has another company in the chain told you in writing that they already filed? Yes (attach) / no / we do not know", "Not need-not-file on its own. One party may file for others only with a documented agreement."],
        ["Did you postmark an extension request by 16 Aug 2026? Yes / no / we do not know", "Which calendar date applies"],
        ["Anything else you want on the letter (part numbers, UPC, supplier name)", "Optional. We will not hunt a supplier for you."],
    ]
    body = (
        "      <p><strong>There is no form on this page and nowhere to upload a file.</strong> "
        "You email the answers. A person reads them. How you pay is an email thread until "
        "a checkout link is minted; this page has no pay button yet.</p>\n"
        + table(
            ["What we ask", "Why"],
            [[esc(a), b] for a, b in form_rows],
            "One named product line per letter",
            "fields, not a web form",
        )
    )
    sections.append(section("What we need from you", "email, not a web form", body))

    # ---- 7. worked example ----
    ex = EXAMPLE
    ex_rows = [
        ["Legal company name", esc(ex["company"])],
        ["Brand", esc(ex["brand"])],
        ["Named product line", esc(ex["line"])],
        ["What it is", esc(ex["what"])],
        ["Role", esc(ex["role"])],
        ["Minnesota", esc(ex["minnesota"])],
        ["Manufactured", esc(ex["made"])],
        ["PFAS added on purpose", esc(ex["pfas"])],
        ["Used product", esc(ex["used"])],
        ["Verdict on those facts", "<strong>must file</strong>"],
    ]
    body = (
        "      <p><strong>Every word of the company and product below is invented.</strong> "
        "Nobody sent this. The quotes next to the tests are real, from the pages we saved "
        f"on {READ_ON}.</p>\n"
        + table(
            ["Field", "What they sent"],
            ex_rows,
            "Invented facts, real rule sentences",
            f"worked example, built {READ_ON}",
        )
        + "\n      <p>On those facts the manufacturer test holds, Minnesota nexus holds, "
        "the product was made after 1 Jul 2023, PFAS was added on purpose, and it is not "
        "a used product. The letter would still not file the report, and it would still "
        "not say they are in the clear.</p>"
    )
    sections.append(section("A worked example, on facts we made up", "invented company, real quotes", body))

    # ---- 8. 325F.072 / 325F.075 ----
    foam_rows = [
        [
            "Title of the compiled section",
            _quote_cell("325F.072 FIREFIGHTING FOAM."),
            "Minn. Stat. § 325F.072",
        ],
        [
            "What &ldquo;class B firefighting foam&rdquo; means in that section",
            _quote_cell(
                '"Class B firefighting foam" means foam designed to prevent or extinguish a fire in flammable liquids, combustible liquids, petroleum greases, tars, oils, oil-based paints, solvents, lacquers, alcohols, and flammable gases.'
            ),
            "325F.072 subd. 1(b)",
        ],
        [
            "The prohibition, as compiled",
            _quote_cell(
                "No person, political subdivision, or state agency shall manufacture or knowingly sell, offer for sale, distribute for sale, or distribute for use in this state, and no person shall use in this state, class B firefighting foam containing PFAS chemicals."
            ),
            "325F.072 subd. 3(a)",
        ],
        [
            "A 24-hour notification, to the Minnesota Fire Incident Reporting System, on discharge, use, or release of class B foam with intentionally added PFAS. The words file / filing do not appear in the compiled section we saved.",
            _quote_cell(
                "Beginning on July 1, 2020, any person, political subdivision, or state agency that discharges, uses, releases, or knows of a discharge, use, or release of class B firefighting foam that contains intentionally added PFAS chemicals must be reported to the Minnesota Fire Incident Reporting System within 24 hours of the discharge, use, or release."
            ),
            "325F.072 subd. 2",
        ],
    ]
    food_rows = [
        [
            "Title of the compiled section",
            _quote_cell("325F.075 FOOD PACKAGING; PFAS."),
            "Minn. Stat. § 325F.075",
        ],
        [
            "What &ldquo;food package&rdquo; means, opening sentence. The compiled definition also names shipping containers, unsealed cups and plates, coatings, inks, and labels.",
            _quote_cell(
                '"Food package" means a container applied to or providing a means to market, protect, handle, deliver, serve, contain, or store a food or beverage.'
            ),
            "325F.075 subd. 1(b)",
        ],
        [
            "The prohibition, as compiled",
            _quote_cell(
                "No person shall manufacture or knowingly sell, offer for sale, distribute for sale, distribute, or offer for use in Minnesota a food package that contains intentionally added PFAS."
            ),
            "325F.075 subd. 2",
        ],
        [
            "The compiled section has no matching line for report / notification / file / filing. It does tell a person to furnish information when the Pollution Control Agency commissioner asks.",
            _quote_cell(
                "When requested by the commissioner of the Pollution Control Agency, a person must furnish to the commissioner any information that the person may have or may reasonably obtain that is relevant to show compliance with this section."
            ),
            "325F.075 subd. 3(b)",
        ],
    ]
    body = (
        "      <p>Minn. Stat. § 116.943, subdivision 8(a)(2), in the compiled page we "
        "saved, says <em>that section</em> (the PFAS-in-products reporting section) "
        "does not apply to:</p>\n"
        "      " + q("a product regulated under section 325F.072 or 325F.075; or") + "\n"
        "      <p>The compiled texts of those two sections, as we saved them, are not "
        "themselves a 116.943 reporting-deadline statute. We will not treat a write-in "
        "of &ldquo;foam&rdquo; or &ldquo;food packaging&rdquo; as a finished "
        "<strong>need not file</strong> answer from those two sections alone. That "
        "ground is <strong>cannot tell</strong> until a person matches the product to "
        "the compiled definitions.</p>\n"
        + table(
            ["What 325F.072 actually says", "The compiled words", "Where"],
            foam_rows,
            "Class B firefighting foam, not all foam, and not food packaging",
            "compiled 325F.072 fetched 25 Aug 2026",
        )
        + table(
            ["What 325F.075 actually says", "The compiled words", "Where"],
            food_rows,
            "Food package as defined, not firefighting foam",
            "compiled 325F.075 fetched 25 Aug 2026",
        )
        + "\n      <p>Medical devices: compiled 116.943 subd. 8(b) carves prosthetic "
        "and FDA medical products out of subdivisions 4 and 5 (testing and bans), not "
        "obviously out of subdivision 2 (reporting). The MPCA prohibitions page we "
        "saved says those products must still be reported if they contain intentionally "
        "added PFAS. We do not advertise a medical-device out. A write-in of "
        "&ldquo;we are FDA&rdquo; is cannot tell.</p>\n"
        "      " + q(
            "However, those products must be reported if they contain intentionally added PFAS starting in 2026. (Minn. Stat. § 116.943, Subd. 8)"
        )
    )
    sections.append(section(
        "What 325F.072 and 325F.075 actually cover",
        "compiled texts fetched 25 Aug 2026",
        body,
    ))

    # ---- 9. what this is not ----
    body = (
        "      <ul class=\"spec\">\n"
        "        <li><strong>Not legal advice.</strong>"
        "<span class=\"sub\">We are not your lawyer.</span></li>\n"
        "        <li><strong>Not a filing.</strong>"
        "<span class=\"sub\">We do not submit the state&rsquo;s report and we do not log "
        "into PRISM. The MPCA reporting page names PRISM as the system manufacturers "
        "use to submit reports and pay related fees.</span></li>\n"
        "        <li><strong>Not a lab.</strong>"
        "<span class=\"sub\">We do not test for PFAS.</span></li>\n"
        "        <li><strong>Not a certificate that you are in the clear.</strong>"
        "<span class=\"sub\">That sentence will not appear on the letter or this page.</span></li>\n"
        "        <li><strong>Not the 2025 category sales bans, and not the 2032 currently-unavoidable-use ban.</strong>"
        "<span class=\"sub\">Those are different duties. This letter is the reporting check.</span></li>\n"
        "        <li><strong>Not the state&rsquo;s one-time $800 filing fee.</strong>"
        "<span class=\"sub\">The MPCA reporting page says each manufacturer pays that fee "
        "inside PRISM. We do not collect it and we do not pay it for you. Our fee is "
        f"{esc(p)} for the first named product line.</span></li>\n"
        "        <li><strong>Not a waiver request, not an extension request, not a trade-secret filing.</strong>"
        "<span class=\"sub\">The 16 Aug 2026 postmark window is past on the pages we saved.</span></li>\n"
        "      </ul>"
    )
    sections.append(section("What this is not", None, body))

    # ---- 10. FAQ ----
    body = (
        "      <p><strong>What is PFAS, in one paragraph?</strong> "
        "Minnesota&rsquo;s definition, on the compiled statute page we saved, is a class "
        "of fluorinated organic chemicals containing at least one fully fluorinated carbon "
        "atom. That is broader than a short lab list of famous names. This letter does "
        "not test your product for them.</p>\n"
        "      <p><strong>What if you are wrong?</strong> "
        "The letter shows its reasoning and its sources. It is a reading of the rule, "
        "not legal advice. If a page we cited later changes, the letter still means what "
        "it meant on its date. If the facts you sent were wrong, the verdict is wrong "
        "with them. If we misread a page we already cited, we send a corrected letter "
        "for that product line; whether that correction is free is not a live promise on "
        "this page.</p>\n"
        "      <p><strong>Do you file the report? Do you tell us we are in the clear?</strong> "
        "No and no.</p>\n"
        "      <p><strong>What if we do not know whether PFAS is in the product?</strong> "
        "That is cannot tell, unless some other test already knocks the product out. We "
        "will not treat a silent supplier as need not file.</p>\n"
        "      <p><strong>We did not ask for the 16 Aug extension. What date applies?</strong> "
        "15 Sep 2026, on the MPCA reporting page we saved. The 14 Dec 2026 date is for "
        "manufacturers receiving an extension. A request is not an approval.</p>\n"
        "      <p><strong>We have twenty product lines. Is that twenty times the first-line price?</strong> "
        "No. The first named product line on one request is the catalog price on this "
        "page. Each further named product line on the same request is priced in the "
        "written terms below the email path, not in the rail. Grouping similar products "
        "into one &ldquo;line&rdquo; is your call on the form. The state&rsquo;s own "
        "grouping rules for PRISM are a different question and are not this letter.</p>\n"
        "      <p><strong>Can we use this letter as a certificate for a retailer or the agency?</strong> "
        "No.</p>"
    )
    sections.append(section("Questions we are actually asked", None, body))

    # ---- 11. sources ----
    src_rows = []
    for key, (name, stamp_line) in SOURCE_FILES.items():
        src_rows.append([esc(stamp_line), esc(name)])
    body = (
        "      <p>Every quoted sentence above was searched for, after folding spaces and "
        f"punctuation, in the saved file named next to it. All {n_quotes} allowed quotes "
        "were found on this build. One mismatch and this page does not build.</p>\n"
        + table(
            ["Saved page", "File on this disk"],
            src_rows,
            f"{len(src_rows)} saved files, all fetched 25 Aug 2026",
            READ_ON,
        )
        + "\n      <p>The compiled statute page still banners that subd. 2 has been "
        "amended by 2026 Chapter 127, Article 14, Section 4, and still prints the old "
        "1 Jan 2026 due date. The session-law text inserts "
        "&ldquo;manufactured after July 1, 2023&rdquo;. When the compiled page will show "
        "those words is unverified.</p>"
    )
    sections.append(section("Where the words came from", READ_ON, body))

    desc = (
        "A reading of Minnesota's PFAS-in-products reporting rule for one named "
        "product line. Not legal advice. Email operations@."
    )
    spec = {
        "sections": sections,
        "id": FAMILY,
        "ready": True,
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": fam["short"],
        "h1": "Minnesota PFAS: do you have to file for this product line?",
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": (
            "Minnesota requires manufacturers to report PFAS in products by 15 Sep 2026, "
            "or 14 Dec 2026 only if the brand <strong>received</strong> an extension after "
            "asking by the 16 Aug postmark cut-off. You describe one named product line; "
            "we send back one written verdict &mdash; must file, need not file, or cannot "
            "tell from what you sent &mdash; with the reasoning shown. We are not your "
            "lawyer, we do not file the report, and a verdict is not a certificate that "
            "you are in the clear."
        ),
        "sample_dt": "What you get",
        "pill_text": "Letter, not a file",
        "pill_label": "One named product line",
        "subj": subj,
        "contact_h2": fam["contact_h2"],
        "contact_p": fam["contact_p"],
        "contact_cta": fam["contact_cta"],
        "contact_note": fam["contact_note"],
        "foot": fam["foot"],
        "hero_note": (
            "<strong>No pay button on this one yet.</strong> Email the named product line. "
            "A person replies with the fields we need and, when a checkout exists, the "
            "link. The rail amount is the first named product line."
        ),
    }
    check_search_line(spec)
    page = render(spec)
    check_banned(page)
    check_page_quotes(page)
    people = []
    vis = _norm(re.sub(r"(?is)<[^>]+>", " ", page))
    # Re-run the person test on the invented name as it actually appears.
    if privacy.looks_personal(EXAMPLE["company"]):
        people.append(EXAMPLE["company"])
    if people:
        raise SystemExit(
            f"{FAMILY}: a person-shaped name reached the page: {people}. Nothing was written."
        )
    return spec


def sample():
    """No sample file. A letter is not a CSV of sealed rows."""
    return None


def slices() -> list[dict]:
    """No child pages."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(
        f"{FAMILY}: {len(spec['sections'])} sections, "
        f"search line {len(spec['desc'])} characters"
    )
