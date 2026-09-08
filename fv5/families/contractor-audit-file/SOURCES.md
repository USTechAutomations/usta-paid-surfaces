# Sources

Every word quoted on a page of this family came out of one of the addresses
below, fetched over plain HTTPS from this host, cached under
`~/.hermes/state/fv5/contractor-audit-file/raw/`, and checked for the section
number we cite before anything was lifted from it. Nothing was paraphrased into
law and nothing was written from memory.

**Fetch method.** One HTTPS GET per address, no login, no cookies, no scraping
framework and no attempt to get past anything that said no. Cadence: monthly.
`refresh.py` re-reads every address and compares each quote it already holds;
a changed quote is marked `drifted` and the delivered page says so.

## Terms

| Source | What the source itself says about reuse | Status |
|---|---|---|
| California Legislative Information (`leginfo.legislature.ca.gov`) | "Code, the information described in subdivision (a) of Section 10248 of the Government Code and made available on this Web site is within the public domain and the State of California retains no copyright or other proprietary interest in the information." | quoted from the site's own home page, read 2026-09-08 |
| eCFR (`ecfr.gov`) | **CITE-CHECK** — the reader-aids page answered this host with an access-request interstitial, not the page, so we hold no terms quote for it. | `200` but the body was a bot wall |
| IRS (`irs.gov`) | **CITE-CHECK** — the privacy-and-reuse notice answered `404` on the address we tried. We hold no terms quote for the IRS pages. | `404` |
| Massachusetts Legislature (`malegislature.gov`) | **CITE-CHECK** — the privacy-policy address answered `404`. We hold no terms quote. | `404` |
| Other state legislature and labor-agency sites | **CITE-CHECK** — we did not fetch a terms page for each of the remaining jurisdictions. What we quote is the text of statutes and of agency guidance, which US law treats as edicts of government, but we have not quoted each site saying so. | not fetched |

The common contract says: refuse to ship a source with no terms quote. Four
source groups above carry a terms quote or a recorded reason there is none.
This is named in `NOTES.md` as the one place the contract is not fully met, and
it is named on the family page too, rather than papered over.

## What each address answered

`quoted` means the bytes came back, carried the section number we cite, and
yielded a whole-sentence passage. Every other status means no page was built
for that jurisdiction: we would rather name a gap than fill it.

| Jurisdiction | Section asked for | Status | What happened | Address |
|---|---|---|---|---|
| California | Cal. Lab. Code 2775 | `quoted` |  | https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=2775.&lawCode=LAB |
| Federal employment tax (common-law control) | IRS: Independent contractor (self-employed) or employee? | `quoted` |  | https://www.irs.gov/businesses/small-businesses-self-employed/independent-contractor-self-employed-or-employee |
| Federal wage law (economic reality) | 29 CFR part 795 | `quoted` |  | https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-29.xml?part=795 |
| Hawaii | HRS 383-6 | `quoted` |  | https://www.capitol.hawaii.gov/hrscurrent/Vol07_Ch0346-0398/HRS0383/HRS_0383-0006.htm |
| Idaho | Idaho Code 72-1316 | `quoted` |  | https://legislature.idaho.gov/statutesrules/idstat/Title72/T72CH13/SECT72-1316/ |
| Maine | 26 M.R.S. 1043 | `quoted` |  | https://legislature.maine.gov/statutes/26/title26sec1043.html |
| Massachusetts | Mass. Gen. Laws c.149 148B | `quoted` |  | https://malegislature.gov/laws/generallaws/parti/titlexxi/chapter149/section148B |
| Nebraska | Neb. Rev. Stat. 48-604 | `quoted` |  | https://nebraskalegislature.gov/laws/statutes.php?statute=48-604 |
| Nevada | NRS 612 | `quoted` |  | https://www.leg.state.nv.us/nrs/nrs-612.html |
| New Hampshire | RSA 282-A:9 | `quoted` |  | https://www.gencourt.state.nh.us/rsa/html/XXIII/282-A/282-A-9.htm |
| New Jersey | New Jersey Department of Labor, independent contractors (N.J.S.A. 43:21-19(i)(6)) | `quoted` |  | https://www.nj.gov/labor/myworkrights/worker-protections/independent_contractors/ |
| North Carolina | N.C.G.S. 96-1 | `quoted` |  | https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_96/GS_96-1.html |
| Ohio | Ohio Rev. Code 4141.01 | `quoted` |  | https://codes.ohio.gov/ohio-revised-code/section-4141.01 |
| Washington | RCW 51.08.195 | `quoted` |  | https://app.leg.wa.gov/RCW/default.aspx?cite=51.08.195 |
| Wisconsin | Wis. Stat. 108.02(12) | `quoted` |  | https://docs.legis.wisconsin.gov/statutes/statutes/108/02/12 |
| Alabama | Alabama Department of Labor, unemployment compensation for employers | `unreachable` | the address answered 404 from this host | https://labor.alabama.gov/uc/employer/ |
| Alaska | AS 23.20.525 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://www.akleg.gov/basis/statutes.asp#23.20.525 |
| Arizona | A.R.S. 23-902 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.azleg.gov/ars/23/00902.htm |
| Arkansas | Arkansas Division of Workforce Services, unemployment insurance for employers | `unreachable` | the address answered 404 from this host | https://www.dws.arkansas.gov/employers/unemployment-insurance/ |
| Colorado | Colorado Department of Labor and Employment, independent contractors | `unreachable` | the address answered 403 from this host | https://cdle.colorado.gov/employers/employer-services/independent-contractors |
| Connecticut | Conn. Gen. Stat. 31-222 | `unreachable` | the address answered 0 from this host | https://www.cga.ct.gov/current/pub/chap_567.htm |
| Delaware | 19 Del. C. 3302 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://delcode.delaware.gov/title19/c033/index.html |
| District of Columbia | D.C. Code 51-101 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://code.dccouncil.gov/us/dc/council/code/sections/51-101 |
| Federal wage law rulemaking | US Department of Labor news release, 26 February 2026 | `unreachable` | the address answered 403 from this host | https://www.dol.gov/newsroom/releases/whd/whd20260226 |
| Florida | Fla. Stat. 443.1216 | `no-passage` | the page answered, but none of the words these tests are written with are in it | http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0400-0499/0443/Sections/0443.1216.html |
| Form SS-8 determination | IRS: Completing Form SS-8 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.irs.gov/businesses/small-businesses-self-employed/completing-form-ss-8 |
| Georgia | Georgia Department of Labor, employer portal | `unreachable` | the address answered 404 from this host | https://dol.georgia.gov/employer-portal |
| Illinois | 820 ILCS 185 (Employee Classification Act) | `unreachable` | the address answered 0 from this host | https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=2789&ChapterID=68 |
| Indiana | Ind. Code 22-4-8-1 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://iga.in.gov/laws/2024/ic/titles/22 |
| Iowa | Iowa Code 96.19 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://www.legis.iowa.gov/docs/code/96.19.pdf |
| Kansas | K.S.A. 44-703 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.ksrevisor.gov/statutes/chapters/ch44/044_007_0003.html |
| Kentucky | KRS 341.050 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://apps.legislature.ky.gov/law/statutes/statute.aspx?id=48929 |
| Louisiana | La. R.S. 23:1472 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://www.legis.la.gov/legis/Law.aspx?d=85383 |
| Maryland | Md. Code, Lab. & Empl. 8-205 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gle&section=8-205 |
| Michigan | Michigan Unemployment Insurance Agency, employers | `unreachable` | the address answered 403 from this host | https://www.michigan.gov/leo/bureaus-agencies/uia/employers |
| Minnesota | Minn. Stat. 268.035 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.revisor.mn.gov/statutes/cite/268.035 |
| Mississippi | Mississippi Department of Employment Security, employers | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://mdes.ms.gov/employers/ |
| Missouri | Mo. Rev. Stat. 288.034 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://revisor.mo.gov/main/OneSection.aspx?section=288.034 |
| Montana | Montana Department of Labor and Industry, independent contractor central unit | `unreachable` | the address answered 404 from this host | https://erd.dli.mt.gov/work-comp-regulations/independent-contractor-central-unit/ |
| New Mexico | New Mexico Department of Workforce Solutions, unemployment insurance tax | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://www.dws.state.nm.us/Unemployment-Insurance-Tax |
| New York | New York State Department of Labor, independent contractors | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://dol.ny.gov/independent-contractors |
| North Dakota | Job Service North Dakota, employer liability | `unreachable` | the address answered 404 from this host | https://www.jobsnd.com/unemployment-individuals/employer-liability |
| Oklahoma | Oklahoma Employment Security Commission, businesses | `unreachable` | the address answered 404 from this host | https://oklahoma.gov/oesc/businesses.html |
| Oregon | Oregon Bureau of Labor and Industries, independent contractors | `unreachable` | the address answered 404 from this host | https://www.oregon.gov/boli/employers/pages/independent-contractors.aspx |
| Pennsylvania | Pennsylvania Department of Labor and Industry, unemployment benefits | `unreachable` | the address answered 404 from this host | https://www.pa.gov/agencies/dli/programs-services/unemployment-benefits.html |
| Rhode Island | R.I. Gen. Laws 28-42-8 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://webserver.rilegislature.gov/Statutes/TITLE28/28-42/28-42-8.HTM |
| South Carolina | S.C. Code 41-27-260 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.scstatehouse.gov/code/t41c027.php |
| South Dakota | SDCL 61-1-11 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://sdlegislature.gov/Statutes/61-1-11 |
| Tennessee | Tennessee Department of Labor and Workforce Development, unemployment insurance tax | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://www.tn.gov/workforce/employers/tax-and-insurance-redirect/unemployment-insurance-tax.html |
| Texas | Texas Workforce Commission, independent contractor test | `unreachable` | the address answered 404 from this host | https://www.twc.texas.gov/programs/unemployment-tax/independent-contractor-test |
| Utah | Utah Code 35A-4-204 | `wrong-page` | the page came back without the section number we asked for, so we do not treat it as that section | https://le.utah.gov/xcode/Title35A/Chapter4/35A-4-S204.html |
| Vermont | 21 V.S.A. 1301 | `unreachable` | the address answered 0 from this host | https://legislature.vermont.gov/statutes/section/21/017/01301 |
| Virginia | Va. Code 60.2-212 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://law.lis.virginia.gov/vacode/title60.2/chapter2/section60.2-212/ |
| West Virginia | W. Va. Code 21A-1-3 | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://code.wvlegislature.gov/21A-1-3/ |
| Wyoming | Wyoming Department of Workforce Services, unemployment insurance | `no-passage` | the page answered, but none of the words these tests are written with are in it | https://dws.wyo.gov/dws-division/unemployment-insurance/ |

## Tally

- `no-passage` — 14
- `quoted` — 15
- `unreachable` — 15
- `wrong-page` — 11

A `403` or a connection that never opens is a fact recorded here, not a puzzle
to solve. Nothing in this family tries a second address, a cache, a mirror or a
different user agent to get around a site that declined this host.
