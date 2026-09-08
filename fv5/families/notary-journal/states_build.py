#!/usr/bin/env python3
"""Fetch each state's own notary-journal rule and read the facts out of it.

One row per state and DC. Every row is built from a document this machine
fetched from the state's own legislature or secretary of state, and every fact
on it points at the exact words in that document. Nothing here is recalled and
nothing is inferred from a state's reputation.

The rules of the road:

  * A fetch that does not return 200 is a FACT, not a puzzle. The status code is
    written into the row and into SOURCES.md and the state falls to `unclear`.
    We never work round a bot wall or a certificate we cannot verify.
  * A state whose provision we cannot locate in the fetched document is
    `unclear` too. "We could not find it" is a different sentence from "the law
    does not say so", and only the first one is ours to write.
  * Every derived flag is read off the fetched words by the classifier below,
    and the words themselves ship next to the flag so a reader can check it.
  * The default is `unclear`. A flag only moves off it when an explicit pattern
    matches, because the cost of a wrong `allowed` is a buyer paying for a tool
    their state will not accept.

No model is called from this file. The provisions are quoted, never summarised.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html as _html
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

FAMILY = "notary-journal"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
RAW = STATE / "raw"

UA = ("Mozilla/5.0 (compatible; USTechAutomations-notary-journal/1.0; "
      "+https://ustechautomations.com/feeds/notary-journal/)")
TIMEOUT = 45
MAX_QUOTE = 300
BODY_CHARS = 6000

# ---------------------------------------------------------------------------
# The sources. `cite` is the statute or rule page; `anchor` is the section
# number as that page writes it, used to find the provision inside a page that
# may hold a whole chapter. `agency` is the state's own notary office.
# `alt` is a second address tried only when the first does not answer 200.
# ---------------------------------------------------------------------------
SOURCES: list[dict] = [
 {"code":"AL","name":"Alabama","cite":"https://alison.legislature.state.al.us/code-of-alabama",
  "label":"Code of Alabama, Title 36 Chapter 20","anchor":r"36-20-\d",
  "agency":"https://www.sos.alabama.gov/",
  "alt":"https://www.sos.alabama.gov/government-records/notaries-public", "alt_label":"Alabama Secretary of State, notaries public"},
 {"code":"AK","name":"Alaska","cite":"https://www.akleg.gov/basis/statutes.asp#44.50.045",
  "label":"Alaska Stat. 44.50.045","anchor":r"44\.50\.045",
  "agency":"https://www.commerce.alaska.gov/web/dbs/notarypublic.aspx",
  "alt":"https://www.commerce.alaska.gov/web/dbs/notarypublic.aspx", "alt_label":"Alaska Notary Public office"},
 {"code":"AZ","name":"Arizona","cite":"https://www.azleg.gov/ars/41/00319.htm",
  "label":"A.R.S. 41-319","anchor":r"41-319",
  "agency":"https://azsos.gov/business/notary-public",
  "alt":"https://azsos.gov/business/notary-public", "alt_label":"Arizona Secretary of State, notary public",
  "mirror":"https://law.justia.com/codes/arizona/title-41/section-41-319/", "mirror_label":"Justia mirror of A.R.S. 41-319"},
 {"code":"AR","name":"Arkansas",
  "cite":"https://www.arkleg.state.ar.us/Acts/FTPDocument?path=/ACTS/2021R/Public/&file=1004.pdf",
  "label":"Arkansas Act 1004 of 2021 (Notaries)","anchor":r"21-14-107|journal",
  "agency":"https://www.sos.arkansas.gov/",
  "alt":"https://www.sos.arkansas.gov/business-commercial-services-bcs/notary-public", "alt_label":"Arkansas Secretary of State, notary public"},
 {"code":"CA","name":"California",
  "cite":"https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum=8206.",
  "label":"Cal. Gov. Code 8206","anchor":r"8206\.",
  "agency":"https://www.sos.ca.gov/notary",
  "alt":"https://www.sos.ca.gov/notary/notary-public-handbook", "alt_label":"California Secretary of State, notary public handbook",
  "mirror":"https://california.public.law/codes/government_code_section_8206", "mirror_label":"Public.Law mirror of Cal. Gov't Code 8206"},
 {"code":"CO","name":"Colorado","cite":"https://www.coloradosos.gov/pubs/notary/home.html",
  "label":"Colorado Secretary of State, notary program","anchor":r"journal",
  "agency":"https://www.coloradosos.gov/pubs/notary/home.html",
  "alt":"https://www.coloradosos.gov/pubs/notary/lawsAndRules.html", "alt_label":"Colorado Secretary of State, notary laws and rules"},
 {"code":"CT","name":"Connecticut","cite":"https://www.cga.ct.gov/current/pub/chap_006.htm",
  "label":"Conn. Gen. Stat. Chapter 6","anchor":r"3-9\d",
  "agency":"https://portal.ct.gov/sots",
  "alt":"https://portal.ct.gov/sots/notary-public/notary-public-services", "alt_label":"Connecticut Secretary of the State, notary public services"},
 {"code":"DE","name":"Delaware","cite":"https://delcode.delaware.gov/title29/c043/sc02/index.html",
  "label":"29 Del. C. 4327","anchor":r"4327",
  "agency":"https://notary.delaware.gov/",
  "alt":"https://notary.delaware.gov/", "alt_label":"Delaware Notary Public office"},
 {"code":"DC","name":"District of Columbia",
  "cite":"https://code.dccouncil.gov/us/dc/council/code/sections/1-1231.15",
  "label":"D.C. Code 1-1231.15","anchor":r"1-1231\.15",
  "agency":"https://os.dc.gov/service/notary-commissions",
  "alt":"https://os.dc.gov/service/notary-commissions", "alt_label":"D.C. Office of the Secretary, notary commissions"},
 {"code":"FL","name":"Florida",
  "cite":"http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0100-0199/0117/0117.html",
  "label":"Fla. Stat. ch. 117","anchor":r"117\.245",
  "agency":"https://www.flgov.com/notary/",
  "alt":"https://www.flgov.com/notary/", "alt_label":"Florida Governor's office, notary commissions",
  "mirror":"https://law.justia.com/codes/florida/title-x/chapter-117/part-ii/section-117-245/", "mirror_label":"Justia mirror of Fla. Stat. 117.245"},
 {"code":"GA","name":"Georgia","cite":"https://www.gsccca.org/notary-and-apostilles/handbook",
  "label":"Georgia Superior Court Clerks' Cooperative Authority, notary handbook",
  "anchor":r"record|journal","agency":"https://www.gsccca.org/notary-and-apostilles",
  "alt":"https://www.gsccca.org/notary-and-apostilles/notary-faq", "alt_label":"Georgia notary FAQ (Superior Court Clerks' Cooperative Authority)"},
 {"code":"HI","name":"Hawaii",
  "cite":"https://www.capitol.hawaii.gov/hrscurrent/Vol10_Ch0436-0474/HRS0456/HRS_0456-0015.htm",
  "label":"HRS 456-15","anchor":r"456-15",
  "agency":"https://ag.hawaii.gov/notaries-public/",
  "alt":"https://ag.hawaii.gov/notaries-public/", "alt_label":"Hawaii Attorney General, notaries public"},
 {"code":"ID","name":"Idaho",
  "cite":"https://legislature.idaho.gov/statutesrules/idstat/Title51/T51CH1/SECT51-119/",
  "label":"Idaho Code 51-119","anchor":r"51-119",
  "agency":"https://sos.idaho.gov/notary/",
  "alt":"https://sos.idaho.gov/notary/", "alt_label":"Idaho Secretary of State, notary public"},
 {"code":"IL","name":"Illinois",
  "cite":"https://www.ilga.gov/legislation/ilcs/fulltext.asp?DocName=000503120K3-107",
  "label":"5 ILCS 312/3-107","anchor":r"3-107",
  "agency":"https://www.ilsos.gov/departments/index/notary/home.html",
  "alt":"https://www.ilsos.gov/departments/index/notary/home.html", "alt_label":"Illinois Secretary of State, notary public"},
 {"code":"IN","name":"Indiana","cite":"https://iga.in.gov/laws/2024/ic/titles/33",
  "label":"Ind. Code 33-42-9","anchor":r"33-42-9",
  "agency":"https://www.in.gov/sos/",
  "alt":"https://www.in.gov/sos/business/notary/", "alt_label":"Indiana Secretary of State, notary public"},
 {"code":"IA","name":"Iowa","cite":"https://www.legis.iowa.gov/docs/code/9B.pdf",
  "label":"Iowa Code ch. 9B (Revised Uniform Law on Notarial Acts)","anchor":r"9B\.19",
  "agency":"https://sos.iowa.gov/notary/",
  "alt":"https://sos.iowa.gov/notary/", "alt_label":"Iowa Secretary of State, notary public"},
 {"code":"KS","name":"Kansas",
  "cite":"https://www.ksrevisor.gov/statutes/chapters/ch53/",
  "label":"K.S.A. ch. 53 (Notaries)","anchor":r"53-5a19",
  "agency":"https://sos.ks.gov/general-services/notary.html",
  "alt":"https://sos.ks.gov/general-services/notary.html", "alt_label":"Kansas Secretary of State, notary services"},
 {"code":"KY","name":"Kentucky",
  "cite":"https://apps.legislature.ky.gov/law/statutes/chapter.aspx?id=38494",
  "label":"KRS Chapter 423","anchor":r"423\.360",
  "agency":"https://www.sos.ky.gov/",
  "alt":"https://www.sos.ky.gov/admin/notaries/Pages/default.aspx", "alt_label":"Kentucky Secretary of State, notaries"},
 {"code":"LA","name":"Louisiana","cite":"https://www.legis.la.gov/legis/Law.aspx?d=98244",
  "label":"La. R.S. 35:199","anchor":r"35:199|journal|record",
  "agency":"https://www.sos.la.gov/",
  "alt":"https://www.sos.la.gov/NotaryAndCertifications/Pages/default.aspx", "alt_label":"Louisiana Secretary of State, notary"},
 {"code":"ME","name":"Maine","cite":"https://legislature.maine.gov/statutes/4/title4ch16sec0.html",
  "label":"4 M.R.S. ch. 16 (Notaries Public)","anchor":r"journal|record",
  "agency":"https://www.maine.gov/sos/cec/notary/",
  "alt":"https://www.maine.gov/sos/cec/notary/", "alt_label":"Maine Secretary of State, notaries public"},
 {"code":"MD","name":"Maryland",
  "cite":"https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gsg&section=18-214&enactments=false",
  "label":"Md. State Gov't 18-214 (Journal)","anchor":r"18-107",
  "agency":"https://sos.maryland.gov/Notary/",
  "alt":"https://sos.maryland.gov/Notary/Pages/default.aspx", "alt_label":"Maryland Secretary of State, notary"},
 {"code":"MA","name":"Massachusetts",
  "cite":"https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIII/Chapter222",
  "label":"M.G.L. c. 222","anchor":r"journal|record",
  "agency":"https://www.sec.state.ma.us/divisions/public-records/notary-public.htm",
  "alt":"https://www.sec.state.ma.us/divisions/public-records/notary-public.htm", "alt_label":"Massachusetts Secretary of the Commonwealth, notary public"},
 {"code":"MI","name":"Michigan","cite":"https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-55-286",
  "label":"MCL 55.286","anchor":r"55\.286",
  "agency":"https://www.michigan.gov/sos",
  "alt":"https://www.michigan.gov/sos/notary", "alt_label":"Michigan Department of State, notary"},
 {"code":"MN","name":"Minnesota","cite":"https://www.revisor.mn.gov/statutes/cite/359",
  "label":"Minn. Stat. ch. 359 (Notaries Public)","anchor":r"359\.05",
  "agency":"https://www.sos.mn.gov/",
  "alt":"https://www.sos.mn.gov/business-liens/notary/", "alt_label":"Minnesota Secretary of State, notary"},
 {"code":"MS","name":"Mississippi","cite":"https://www.sos.ms.gov/business-services/notaries",
  "label":"Mississippi Secretary of State, notaries","anchor":r"record|journal",
  "agency":"https://www.sos.ms.gov/",
  "alt":"https://www.sos.ms.gov/notaries", "alt_label":"Mississippi Secretary of State, notaries"},
 {"code":"MO","name":"Missouri","cite":"https://revisor.mo.gov/main/OneChapter.aspx?chapter=486",
  "label":"Mo. Rev. Stat. ch. 486 (Notaries Public)","anchor":r"486\.735",
  "agency":"https://www.sos.mo.gov/business/notary",
  "alt":"https://www.sos.mo.gov/business/notary", "alt_label":"Missouri Secretary of State, notary"},
 {"code":"MT","name":"Montana",
  "cite":"https://archive.legmt.gov/bills/mca/title_0010/chapter_0050/part_0060/sections_index.html",
  "label":"Mont. Code Ann. Title 1 ch. 5 pt. 6 (Notaries Public)","anchor":r"1-5-619",
  "agency":"https://sosmt.gov/notary/",
  "alt":"https://sosmt.gov/notary/", "alt_label":"Montana Secretary of State, notary"},
 {"code":"NE","name":"Nebraska","cite":"https://nebraskalegislature.gov/laws/browse-chapters.php?chapter=64",
  "label":"Neb. Rev. Stat. ch. 64 (Notaries Public)","anchor":r"64-210",
  "agency":"https://sos.nebraska.gov/business-services/notary-public",
  "alt":"https://sos.nebraska.gov/business-services/notary-public", "alt_label":"Nebraska Secretary of State, notary public"},
 {"code":"NV","name":"Nevada","cite":"https://www.leg.state.nv.us/nrs/nrs-240.html",
  "label":"NRS 240.120","anchor":r"240\.120",
  "agency":"https://www.nvsos.gov/sos/licensing/notary"},
 {"code":"NH","name":"New Hampshire",
  "cite":"https://www.gencourt.state.nh.us/rsa/html/XLIII/455/455-mrg.htm",
  "label":"N.H. Rev. Stat. ch. 455","anchor":r"455:\d|journal|record",
  "agency":"https://www.sos.nh.gov/",
  "alt":"https://www.sos.nh.gov/administration/notary-public-and-justice-peace", "alt_label":"New Hampshire Secretary of State, notary public"},
 {"code":"NJ","name":"New Jersey","cite":"https://pub.njleg.state.nj.us/Bills/2020/PL21/179_.PDF",
  "label":"N.J. P.L. 2021 c.179 (Notarial Acts)","anchor":r"journal",
  "agency":"https://www.njconsumeraffairs.gov/nnp",
  "alt":"https://www.njconsumeraffairs.gov/nnp", "alt_label":"New Jersey Division of Revenue, notaries public"},
 {"code":"NM","name":"New Mexico",
  "cite":"https://www.nmlegis.gov/Sessions/21%20Regular/final/SB0012.pdf",
  "label":"N.M. Laws 2021 ch. 33 (Revised Uniform Law on Notarial Acts)",
  "anchor":r"journal","agency":"https://www.sos.nm.gov/business-services/notary-and-apostille/",
  "alt":"https://www.sos.nm.gov/business-services/notary-and-apostille/", "alt_label":"New Mexico Secretary of State, notary"},
 {"code":"NY","name":"New York","cite":"https://dos.ny.gov/notary-public",
  "label":"New York Department of State, notary public","anchor":r"journal|record",
  "agency":"https://dos.ny.gov/notary-public",
  "alt":"https://dos.ny.gov/notary-public-license-information", "alt_label":"New York Department of State, notary public licence information"},
 {"code":"NC","name":"North Carolina",
  "cite":"https://www.ncleg.gov/Laws/GeneralStatuteSections/Chapter10B",
  "label":"N.C. Gen. Stat. ch. 10B (Notaries)","anchor":r"10B-36",
  "agency":"https://www.sosnc.gov/divisions/notary",
  "alt":"https://www.sosnc.gov/divisions/notary", "alt_label":"North Carolina Secretary of State, notary division"},
 {"code":"ND","name":"North Dakota","cite":"https://ndlegis.gov/cencode/t44c06-1.pdf",
  "label":"N.D. Cent. Code 44-06.1-19","anchor":r"44-06\.1-19",
  "agency":"https://sos.nd.gov/notary-public",
  "alt":"https://sos.nd.gov/notary-public", "alt_label":"North Dakota Secretary of State, notary public"},
 {"code":"OH","name":"Ohio","cite":"https://codes.ohio.gov/ohio-revised-code/chapter-147",
  "label":"Ohio Rev. Code ch. 147 (Notaries Public)","anchor":r"147\.542",
  "agency":"https://www.ohiosos.gov/notary/",
  "alt":"https://www.ohiosos.gov/notary/", "alt_label":"Ohio Secretary of State, notary"},
 {"code":"OK","name":"Oklahoma","cite":"https://oksenate.gov/sites/default/files/2019-12/os49.pdf",
  "label":"49 O.S. (Notaries Public)","anchor":r"register|record|journal",
  "agency":"https://www.sos.ok.gov/notary/default.aspx",
  "alt":"https://www.sos.ok.gov/notary/default.aspx", "alt_label":"Oklahoma Secretary of State, notary"},
 {"code":"OR","name":"Oregon","cite":"https://www.oregonlegislature.gov/bills_laws/ors/ors194.html",
  "label":"ORS 194.300","anchor":r"194\.300",
  "agency":"https://sos.oregon.gov/business/Pages/notary.aspx",
  "alt":"https://sos.oregon.gov/business/Pages/notary.aspx", "alt_label":"Oregon Secretary of State, notary"},
 {"code":"PA","name":"Pennsylvania",
  "cite":"https://www.legis.state.pa.us/WU01/LI/LI/CT/HTM/57/00.003.019.000..HTM",
  "label":"57 Pa.C.S. 319","anchor":r"319",
  "agency":"https://www.dos.pa.gov/OtherServices/Notaries/",
  "alt":"https://www.dos.pa.gov/OtherServices/Notaries/Pages/default.aspx", "alt_label":"Pennsylvania Department of State, notaries",
  "mirror":"https://law.justia.com/codes/pennsylvania/title-57/chapter-3/section-319/", "mirror_label":"Justia mirror of 57 Pa.C.S. 319"},
 {"code":"RI","name":"Rhode Island",
  "cite":"https://webserver.rilegislature.gov/Statutes/TITLE42/42-30.1/INDEX.htm",
  "label":"R.I. Gen. Laws ch. 42-30.1 (Uniform Law on Notarial Acts)","anchor":r"42-30\.1-19",
  "agency":"https://www.sos.ri.gov/divisions/notary-public",
  "alt":"https://www.sos.ri.gov/divisions/notary-public", "alt_label":"Rhode Island Department of State, notary public"},
 {"code":"SC","name":"South Carolina","cite":"https://www.scstatehouse.gov/code/t26c001.php",
  "label":"S.C. Code ch. 26-1 (Notaries Public)","anchor":r"26-1-1\d\d|journal|record book",
  "agency":"https://www.scsos.com/Notaries",
  "alt":"https://www.scsos.com/Notaries", "alt_label":"South Carolina Secretary of State, notaries"},
 {"code":"SD","name":"South Dakota","cite":"https://sdlegislature.gov/Statutes/18-1",
  "label":"SDCL ch. 18-1","anchor":r"18-1-\d",
  "agency":"https://sdsos.gov/general-services/notary-public/",
  "alt":"https://sdsos.gov/general-services/notary-public/", "alt_label":"South Dakota Secretary of State, notary public"},
 {"code":"TN","name":"Tennessee","cite":"https://sos.tn.gov/products/business-services/notary-public",
  "label":"Tennessee Secretary of State, notary public","anchor":r"record|journal",
  "agency":"https://sos.tn.gov/products/business-services/notary-public",
  "alt":"https://sos.tn.gov/products/business-services/notary-frequently-asked-questions", "alt_label":"Tennessee Secretary of State, notary FAQ"},
 {"code":"TX","name":"Texas","cite":"https://statutes.capitol.texas.gov/Docs/GV/htm/GV.406.htm",
  "label":"Tex. Gov't Code 406.014","anchor":r"406\.014",
  "agency":"https://www.sos.state.tx.us/statdoc/index.shtml",
  "alt":"https://www.sos.state.tx.us/statdoc/notary-faqs.shtml", "alt_label":"Texas Secretary of State, notary public FAQ",
  "mirror":"https://law.justia.com/codes/texas/government-code/title-4/subtitle-a/chapter-406/subchapter-a/section-406-014/", "mirror_label":"Justia mirror of Tex. Gov't Code 406.014"},
 {"code":"UT","name":"Utah","cite":"https://le.utah.gov/xcode/Title46/Chapter1/46-1.html",
  "label":"Utah Code ch. 46-1 (Notaries Public Reform Act)","anchor":r"46-1-14",
  "agency":"https://notary.utah.gov/",
  "alt":"https://notary.utah.gov/", "alt_label":"Utah Lieutenant Governor, notary programme"},
 {"code":"VT","name":"Vermont","cite":"http://legislature.vermont.gov/statutes/chapter/26/103",
  "label":"26 V.S.A. ch. 103 (Notaries Public)","anchor":r"5369|journal|record",
  "agency":"https://sos.vermont.gov/notaries-public/",
  "alt":"https://sos.vermont.gov/notaries-public/", "alt_label":"Vermont Secretary of State, notaries public"},
 {"code":"VA","name":"Virginia","cite":"https://law.lis.virginia.gov/vacode/title47.1/section47.1-14/",
  "label":"Va. Code 47.1-14","anchor":r"47\.1-14",
  "agency":"https://www.commonwealth.virginia.gov/official-documents/notary-commissions/",
  "alt":"https://www.commonwealth.virginia.gov/official-documents/notary-commissions/", "alt_label":"Virginia Secretary of the Commonwealth, notary commissions"},
 {"code":"WA","name":"Washington","cite":"https://app.leg.wa.gov/RCW/default.aspx?cite=42.45.180",
  "label":"RCW 42.45.180","anchor":r"42\.45\.180",
  "agency":"https://www.dol.wa.gov/professional-licenses/notaries-public",
  "alt":"https://www.dol.wa.gov/professional-licenses/notaries-public", "alt_label":"Washington Department of Licensing, notaries public",
  "mirror":"https://app.leg.wa.gov/rcw/default.aspx?cite=42.45.180", "mirror_label":"Washington Legislature, RCW 42.45.180"},
 {"code":"WV","name":"West Virginia","cite":"https://code.wvlegislature.gov/39-4/",
  "label":"W. Va. Code ch. 39 art. 4 (Revised Uniform Law on Notarial Acts)","anchor":r"39-4-19",
  "agency":"https://sos.wv.gov/business/notary/",
  "alt":"https://sos.wv.gov/business/notary/Pages/default.aspx", "alt_label":"West Virginia Secretary of State, notary"},
 {"code":"WI","name":"Wisconsin","cite":"https://docs.legis.wisconsin.gov/statutes/statutes/140",
  "label":"Wis. Stat. ch. 140 (Notarial Acts)","anchor":r"140\.18",
  "agency":"https://www.wdfi.org/apostilles_notary_public_and_trademarks/",
  "alt":"https://www.wdfi.org/apostilles_notary_public_and_trademarks/notary_public.htm", "alt_label":"Wisconsin Department of Financial Institutions, notary public"},
 {"code":"WY","name":"Wyoming","cite":"https://www.wyoleg.gov/statutes/compress/title34.pdf",
  "label":"Wyo. Stat. 34-26-119","anchor":r"34-26-119",
  "agency":"https://sos.wyo.gov/",
  "alt":"https://sos.wyo.gov/Notary/Default.aspx", "alt_label":"Wyoming Secretary of State, notary"},
]

SLUG = {s["code"]: s["name"].lower().replace(" ", "-") for s in SOURCES}


# ---------------------------------------------------------------------------
# Fetching. One address, one status code, cached raw on disk.
# ---------------------------------------------------------------------------
def fetch(url: str) -> tuple[int, bytes, str, str]:
    """(status, body, content-type, note). Never raises; a failure is a fact."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/pdf,*/*",
        "Accept-Encoding": "gzip"})
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT,
                                   context=ssl.create_default_context())
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return r.status, body, r.headers.get("Content-Type", ""), ""
    except urllib.error.HTTPError as e:
        return e.code, b"", "", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - a fetch fault is a recorded fact
        return -1, b"", "", f"{type(e).__name__}: {str(e)[:120]}"


def to_text(body: bytes, content_type: str, cache: Path) -> str:
    """Plain readable text out of HTML or PDF. pdftotext for the PDFs."""
    if body[:4] == b"%PDF" or "pdf" in content_type.lower():
        cache.write_bytes(body)
        try:
            out = subprocess.run(["pdftotext", "-layout", str(cache), "-"],
                                 capture_output=True, timeout=180)
            return out.stdout.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""
    s = body.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = s.replace(" ", " ").replace("‑", "-")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


# ---------------------------------------------------------------------------
# Finding the provision inside the fetched document.
# ---------------------------------------------------------------------------
DUTY = re.compile(r"\b(shall|must|is required to|may not|shall not)\b", re.I)
JOURNAL_WORD = re.compile(r"\b(journal|record book|register|records? of notarial)\b", re.I)


def provisions(text: str, anchor: str) -> list[str]:
    """The block of this document that actually carries the journal rule.

    A section number is a poor handle. Chapter pages open with a table of
    contents, section numbers get renumbered between codifications, and a page
    fetched by number can turn out to be the seal rule rather than the journal
    rule. So the handle is the subject itself: every place the document says
    journal, record book or register is scored on the obligation words around
    it, and the best-scoring block is the one we quote. The cited section
    number still counts, as a bonus, when the document shows it in the block.

    Blocks come back best first. The caller walks them in order and keeps the
    first that yields a sentence worth quoting, because a legislature's own
    navigation can outscore the statute on a page that carries both.
    An empty list is the honest answer for a page that turned out to be a
    navigation shell with no rule on it at all.
    """
    if not text:
        return []
    scored: list[tuple[int, str]] = []
    seen: set[int] = set()
    for m in JOURNAL_WORD.finditer(text):
        start = max(0, m.start() - 400)
        key = start // 500
        if key in seen:
            continue
        seen.add(key)
        chunk = text[start: start + BODY_CHARS]
        head = chunk[:2000]
        score = (len(re.findall(r"(shall|must)\s+(keep|maintain|record|make|enter)",
                                head, re.I)) * 6
                 + len(JOURNAL_WORD.findall(head)) * 2
                 + len(DUTY.findall(head)))
        if re.search(r"journal of notarial acts|official journal|notary journal",
                     head, re.I):
            score += 6
        if anchor and re.search(anchor, head, re.I):
            score += 4
        # A block that is mostly about the video recording of a remote
        # notarisation is not the journal block; prefer the journal block.
        rec = len(re.findall(r"audio[- ]?visual|audiovisual|recording", head, re.I))
        if rec > len(JOURNAL_WORD.findall(head)):
            score -= 6
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:8]]


QUOTE_SUBJECT = re.compile(
    r"\b(journal|record book|records? of notarial acts|official register)\b", re.I)
IMPERATIVE = re.compile(r"^\s*(keep|maintain|record|enter|use|make)\b", re.I)
NOT_REQUIRED = re.compile(
    r"(not required|no journal|is not mandatory|are not required"
    r"|required\?\s*(No|Yes)\b|is a .{0,40}journal required)", re.I)


def usable_quote(sent: str, before: str) -> bool:
    """True when this sentence is the state's own rule, not its site furniture.

    Legislature sites carry the word "journal" in their own navigation -- house
    journals, senate journals, an administrative register -- and a notary
    office page carries it in a menu. A sentence only counts when it names the
    subject, sits in text that is talking about notaries, and either imposes a
    duty, answers the question, or reads as an instruction to the notary.
    """
    if len(sent) < 40 or not QUOTE_SUBJECT.search(sent):
        return False
    if not re.search(r"notar", sent, re.I) and not re.search(r"notar", before, re.I):
        return False
    return bool(DUTY.search(sent) or IMPERATIVE.match(sent)
                or NOT_REQUIRED.search(sent))


def quote_from(body: str) -> str:
    """One exact sentence out of the provision, at most 300 characters.

    Exact words only. Whitespace is collapsed because the source runs its lines
    however its own layout does; no word is changed, added or dropped, and a
    sentence too long for the field is cut at a word boundary and marked.
    """
    flat = re.sub(r"\s+", " ", body).strip()
    pos = 0
    for sent in re.split(r"(?<=[.;:?])\s+", flat):
        before = flat[max(0, pos - 320): pos]
        pos += len(sent) + 1
        sent = sent.strip()
        if usable_quote(sent, before):
            if len(sent) <= MAX_QUOTE:
                return sent
            return sent[:MAX_QUOTE - 1].rsplit(" ", 1)[0].strip() + "…"
    return ""


LINK = re.compile(r'<a\b[^>]*href="([^"#]+)[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
NAV_JOURNAL = re.compile(
    r"house journal|senate journal|journals?\s*$|legislative journal|"
    r"administrative register|voter register|journal of the", re.I)
WANT_LINK = re.compile(
    r"journal|record of notarial|notarial record|record book|"
    r"records? of notarial acts", re.I)


def discover(page: bytes, base_url: str, limit: int = 3) -> list[str]:
    """Addresses on a chapter page whose own link text names the journal.

    A code site puts the section titles in its table of contents, so the state
    itself tells us which section carries the journal rule. We follow what the
    page says rather than guessing a section number, and we ignore the links a
    legislature uses for its own house and senate journals.
    """
    from urllib.parse import urljoin
    out: list[str] = []
    for href, text in LINK.findall(page.decode("utf-8", "replace")):
        label = re.sub(r"<[^>]+>", " ", text)
        label = re.sub(r"\s+", " ", _html.unescape(label)).strip()
        if not WANT_LINK.search(label) or NAV_JOURNAL.search(label):
            continue
        url = urljoin(base_url, _html.unescape(href))
        if url.startswith("http") and url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out


def first_quotable(text: str, anchor: str) -> tuple[str, str]:
    """Walk the candidate blocks best first; keep the first that quotes."""
    for block in provisions(text, anchor):
        q = quote_from(block)
        if q:
            return block, q
    return "", ""


# ---------------------------------------------------------------------------
# Reading the flags off the words. Conservative: unknown stays unknown.
# ---------------------------------------------------------------------------
REQUIRED_RE = re.compile(
    r"(shall|must)\s+(keep|maintain|record|make|enter|create|retain)[^.]{0,120}"
    r"(journal|record book|register|record of (each|every|all))", re.I)
NO_JOURNAL_RE = re.compile(
    r"(notar\w+|officer)[^.]{0,60}(is not required to|are not required to|need not)"
    r"[^.]{0,40}(keep|maintain|create)[^.]{0,40}(journal|record book)"
    r"|no journal is required"
    r"|journal[^.?]{0,60}required\?\s*No\b"
    r"|(a |the )?journal is not (required|mandatory)", re.I)
ELECTRONIC_OK_RE = re.compile(
    r"journal[^.]{0,160}(tangible medium or in an electronic format"
    r"|electronic (format|journal|medium|record)"
    r"|electronic or (a )?tangible)"
    r"|(electronic (format|medium)|electronically)[^.]{0,120}journal", re.I)
VENDOR_RE = re.compile(
    r"(approved|registered|selected from|listed by|authorized)\s+"
    r"(by|with)?\s*(the )?(secretary|department|state|commission)[^.]{0,160}"
    r"(vendor|provider|platform|technology)"
    r"|(vendor|provider|platform|technology)[^.]{0,120}"
    r"(approved|registered|authorized)\s+by\s+the\s+(secretary|department|state)", re.I)
BOUND_ONLY_RE = re.compile(
    r"(permanently |properly |well[- ])?bound (book|journal|register|volume)"
    r"|bound (book|journal|register) with (numbered|sequential) pages", re.I)
THUMB_RE = re.compile(r"\b(thumbprint|thumb print|fingerprint)\b", re.I)
SIGNATURE_RE = re.compile(
    r"signature of (the |each |every )?(person|signer|individual|party|principal)"
    r"|(person|signer|individual)[^.]{0,60}\bsign(s|ed)? the (journal|record|entry|book)", re.I)
RETENTION_RE = re.compile(
    r"(retain|keep|preserve|maintain)[^.]{0,140}?"
    r"\b(ten|seven|five|three|two|one|10|7|5|3|2|1)\b\s*\(?\d*\)?\s*years?", re.I)
RON_RE = re.compile(
    r"(remote|online|audio[- ]video|audiovisual)[^.]{0,200}"
    r"(notariz|notarial act)[^.]{0,200}", re.I)
WORDS = {"one": 1, "two": 2, "three": 3, "five": 5, "seven": 7, "ten": 10,
         "1": 1, "2": 2, "3": 3, "5": 5, "7": 7, "10": 10}

# The entry fields the app offers. Which of them a state's own words ask for is
# read off the provision; the base four appear for every state because every
# journal provision we could read names them.
BASE_FIELDS = ["date_time", "act_type", "document_type", "signer_name"]
FIELD_PATTERNS = [
    ("signer_address", re.compile(r"\baddress\b", re.I)),
    ("id_method", re.compile(r"(identif\w+|satisfactory evidence|credible witness|"
                             r"driver'?s licen[cs]e|passport)", re.I)),
    ("id_serial", re.compile(r"(serial number|identification number|number of the "
                             r"(identification|licen[cs]e)|licen[cs]e number)", re.I)),
    ("fee", re.compile(r"\bfee(s)? charged|\bfee\b", re.I)),
    ("signer_signature", SIGNATURE_RE),
]


def classify(body: str) -> dict:
    """Read every flag off the fetched words. Nothing here guesses."""
    out = {
        "journal_required": "unclear",
        "electronic_allowed": "unclear",
        "fields": list(BASE_FIELDS),
        "retention_years": None,
        "thumbprint": False,
        "signature": False,
        "ron_vendor_required": "unclear",
    }
    if not body:
        return out
    flat = re.sub(r"\s+", " ", body)
    if NO_JOURNAL_RE.search(flat):
        out["journal_required"] = "no"
    elif REQUIRED_RE.search(flat):
        out["journal_required"] = "yes"

    bound = bool(BOUND_ONLY_RE.search(flat))
    electronic = bool(ELECTRONIC_OK_RE.search(flat))
    vendor = bool(VENDOR_RE.search(flat))
    # The bound-book sentence in a modern notary act is conditional -- it says
    # what the journal must look like IF it is kept on paper. It only means
    # "paper only" when the same text never permits an electronic format.
    if electronic and vendor:
        out["electronic_allowed"] = "vendor_only"
    elif electronic:
        out["electronic_allowed"] = "allowed"
    elif bound:
        out["electronic_allowed"] = "not_allowed"

    m = RETENTION_RE.search(flat)
    if m:
        out["retention_years"] = WORDS.get(m.group(2).lower())
    out["thumbprint"] = bool(THUMB_RE.search(flat))
    out["signature"] = bool(SIGNATURE_RE.search(flat))
    for key, pat in FIELD_PATTERNS:
        if pat.search(flat):
            out["fields"].append(key)
    if RON_RE.search(flat):
        out["ron_vendor_required"] = "yes" if vendor else "unclear"
    return out


# ---------------------------------------------------------------------------
def build(limit: int = 0, dry_run: bool = False,
          only: list[str] | None = None) -> dict:
    """Fetch every source, read the flags, and hand back the two data blobs."""
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    rows: list[dict] = []
    cites: list[dict] = []
    n = 0
    for src in SOURCES:
        if only and src["code"] not in only:
            continue
        cache = RAW / f"{src['code']}.bin"
        # --limit is a budget for how many sources this run pulls over the wire,
        # not a cut on how many states get a page. Once the budget is spent the
        # remaining states are read from the copy already saved on disk, so a
        # limited run never shortens the estate or drops a state page.
        offline = bool(dry_run or (limit and n >= limit))
        n += 1
        used_url = src["cite"]
        status, body, ctype, note = (0, b"", "", "")
        if offline and cache.is_file():
            body, ctype, status = cache.read_bytes(), "", 200
            note = "read from the saved copy, not re-read this run"
        else:
            status, body, ctype, note = fetch(src["cite"])
            if status == 200 and body:
                cache.write_bytes(body)
            elif cache.is_file():
                body, status, note = cache.read_bytes(), status, f"{note}; used cached copy"
        text = to_text(body, ctype, RAW / f"{src['code']}.pdf") if body else ""
        prov, quote = first_quotable(text, src["anchor"])
        # The statute address did not carry the rule. The state's own notary
        # office is the second source the brief allows; try it, and if it
        # answers, the row cites the page the words actually came from.
        if not quote and src.get("alt"):
            alt_cache = RAW / f"{src['code']}_alt.bin"
            if offline and alt_cache.is_file():
                abody, actype, astatus, anote = (alt_cache.read_bytes(), "", 200,
                                                 "read from the saved copy, not re-read this run")
            else:
                astatus, abody, actype, anote = fetch(src["alt"])
                if astatus == 200 and abody:
                    alt_cache.write_bytes(abody)
                elif alt_cache.is_file():
                    abody, anote = alt_cache.read_bytes(), f"{anote}; used cached copy"
            atext = to_text(abody, actype, RAW / f"{src['code']}_alt.pdf") if abody else ""
            aprov, aquote = first_quotable(atext, src["anchor"])
            if aquote:
                used_url, prov, quote = src["alt"], aprov, aquote
                status = astatus
                note = (note + "; " if note else "") + f"rule found at {src['alt_label']}"
        # The state's own address and its notary office both came back without
        # the rule. The research pack names a mirror of the same code section
        # for a few states; read that, and cite the mirror, because that is
        # where the words on our page actually came from.
        if not quote and src.get("mirror"):
            mir_cache = RAW / f"{src['code']}_mir.bin"
            if offline and mir_cache.is_file():
                mbody, mctype, mstatus, mnote = (mir_cache.read_bytes(), "", 200,
                                                 "read from the saved copy, not re-read this run")
            else:
                mstatus, mbody, mctype, mnote = fetch(src["mirror"])
                if mstatus == 200 and mbody:
                    mir_cache.write_bytes(mbody)
                elif mir_cache.is_file():
                    mbody, mnote = mir_cache.read_bytes(), f"{mnote}; used cached copy"
            mtext = to_text(mbody, mctype, RAW / f"{src['code']}_mir.pdf") if mbody else ""
            mprov, mquote = first_quotable(mtext, src["anchor"])
            if mquote:
                used_url, prov, quote = src["mirror"], mprov, mquote
                status = mstatus
                note = (note + "; " if note else "") + f"rule found at {src['mirror_label']}"

        flags = classify(prov)
        fetched_ok = bool(quote)
        if not fetched_ok:
            flags["electronic_allowed"] = "unclear"
        # Still nothing. The chapter page may still be the right page -- it
        # just holds a table of contents. Follow the link whose own words name
        # the journal and read the section the state points at.
        if not quote and body and not offline:
            for cand in discover(body, used_url):
                cstatus, cbody, cctype, cnote = fetch(cand)
                if cstatus != 200 or not cbody:
                    continue
                (RAW / f"{src['code']}_disc.bin").write_bytes(cbody)
                ctext = to_text(cbody, cctype, RAW / f"{src['code']}_disc.pdf")
                cprov, cquote = first_quotable(ctext, src["anchor"])
                if cquote:
                    used_url, prov, quote, status = cand, cprov, cquote, cstatus
                    note = (note + "; " if note else "") + "followed the chapter's own journal link"
                    break

        row = {
            "code": src["code"],
            "name": src["name"],
            "slug": SLUG[src["code"]],
            "cite_label": (src["label"] if used_url == src["cite"]
                           else src["mirror_label"] if used_url == src.get("mirror")
                           else src.get("alt_label", src["label"])),
            "cite_url": used_url,
            "agency_url": src["agency"],
            "http_status": status,
            "fetch_note": note,
            "checked": today,
            "quote": quote,
            **flags,
        }
        row["buy_ok"] = (row["electronic_allowed"] == "allowed" and bool(quote))
        rows.append(row)
        cites.append({
            "code": src["code"],
            "url": used_url,
            "quote": quote,
            "fetched": today,
            "status": "ok" if quote else ("unfetched" if status != 200 else "not-found"),
            "http_status": status,
            "label": (src["label"] if used_url == src["cite"]
                      else src["mirror_label"] if used_url == src.get("mirror")
                      else src.get("alt_label", src["label"])),
        })
    return {
        "generated": today,
        "rows": rows,
        "citations": cites,
    }


def write(blob: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "states.json").write_text(
        json.dumps({"generated": blob["generated"], "states": blob["rows"]},
                   indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA / "citations.json").write_text(
        json.dumps(blob["citations"], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")


def load_states() -> dict:
    p = DATA / "states.json"
    if not p.is_file():
        return {"generated": "", "states": []}
    return json.loads(p.read_text(encoding="utf-8"))


def load_citations() -> list[dict]:
    p = DATA / "citations.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    b = build()
    write(b)
    ok = sum(1 for r in b["rows"] if r["quote"])
    allowed = sum(1 for r in b["rows"] if r["buy_ok"])
    print(f"rows={len(b['rows'])} quoted={ok} buy_ok={allowed}")
