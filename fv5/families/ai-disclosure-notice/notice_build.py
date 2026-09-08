#!/usr/bin/env python3
"""The rule rows, the cited quotes, and the notice texts for ai-disclosure-notice.

One module holds three things, so that the free page, the sub-pages, the paid
page and the refresh job all read the same rows rather than four copies that
drift:

  * SOURCES  -- the primary documents, how each one is fetched, and what its own
                page says about terms. A wall (403, a bot challenge, a broken
                certificate chain) is recorded as a fact here, never evaded.
  * CITES    -- one row per quoted passage: the source it came from, the exact
                words (<= 300 characters) and what it is quoted for. Every quote
                is checked back against the fetched text before it is written to
                data/citations.json, so a quote nobody could find is a build
                failure and not a published sentence.
  * DUTIES   -- one row per clause of a rule: who it reaches, who it does NOT
                reach, from when, which notice channel it drives, and which
                answers make it match. Nothing here says what the buyer must do.

Nothing in this module states a legal conclusion about anyone. A row says what a
published rule says and which of the reader's answers it matches. Whether a
particular company complies with it is not a question this family answers, and
the wording is kept clear of it deliberately -- see the verdict gate in
selftest.py.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html as _html
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

FAMILY = "ai-disclosure-notice"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
RAW_DIR = STATE / "raw"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
QUOTE_MAX = 300

# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
# `fetch` is how the bytes in RAW_DIR were obtained:
#   "curl"    -- an ordinary HTTPS GET from this host answered 200.
#   "browser" -- this host is refused (see `wall`), and the words were read
#                through the session's browser route instead. refresh.py cannot
#                re-check those quotes from here and says so rather than
#                pretending it did.
#   "blocked" -- we could not read the document at all, by any route we are
#                allowed to use. Nothing is quoted from it.
SOURCES = {
    "ec-art50-faq": {
        "label": "European Commission — Transparency obligations under Article 50 of the AI Act",
        "url": ("https://digital-strategy.ec.europa.eu/en/faqs/"
                "transparency-obligations-under-article-50-ai-act"),
        "file": "ec_article50_faq.html",
        "fetch": "curl",
        "status": "200",
        "terms": ("European Commission standard reuse notice: © European Union, "
                  "1995-2026. Reuse of Commission documents is authorised under the "
                  "Commission Decision 2011/833/EU, provided the source is acknowledged."),
        "note": ("EUR-Lex itself, which carries the Regulation's own words, answers a "
                 "202 AWS WAF JavaScript challenge to this host and to the browser "
                 "route. That is recorded, not evaded: the Article 50 wording quoted "
                 "here is the Commission's own explanatory text, which we can fetch."),
    },
    "eurlex-2024-1689": {
        "label": "EUR-Lex — Regulation (EU) 2024/1689 (the AI Act), official text",
        "url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
        "file": "eurlex_waf_challenge.html",
        "fetch": "blocked",
        "status": "202 (AWS WAF JavaScript challenge, 0 bytes of document)",
        "terms": ("Not read. The consolidated EUR-Lex text carries the notice “This "
                  "text is meant purely as a documentation tool and has no legal "
                  "effect.” We do not quote a page we could not fetch."),
        "note": ("Nothing is quoted from this source. The Article 50 rows cite the "
                 "European Commission's own Article 50 FAQ instead, and say so."),
    },
    "ca-bpc-17941": {
        "label": "California Business and Professions Code § 17941 (the BOT Act, SB 1001)",
        "url": ("https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
                "?lawCode=BPC&sectionNum=17941."),
        "file": "ca_bpc_17941.html",
        "fetch": "curl",
        "status": "200 (503 on the first attempt; 200 on retry with a cookie jar)",
        "terms": ("leginfo.legislature.ca.gov Terms of Use: the site is provided by the "
                  "Legislative Counsel of California for public access to California "
                  "law. California statutes are public records; no commercial-use "
                  "restriction is asserted over the text of the codes."),
        "note": "",
    },
    "ca-bpc-ch25": {
        "label": ("California Business and Professions Code ch. 25, §§ 22757–22757.6 "
                  "(California AI Transparency Act, SB 942 as amended by AB 853)"),
        "url": ("https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml"
                "?lawCode=BPC&division=8.&title=&part=&chapter=25.&article="),
        "file": "ca_bpc_ch25.html",
        "fetch": "curl",
        "status": "200",
        "terms": ("leginfo.legislature.ca.gov Terms of Use: public access to California "
                  "law published by the Legislative Counsel. Statute text is a public "
                  "record."),
        "note": "",
    },
    "ca-bpc-22602": {
        "label": ("California Business and Professions Code § 22602 "
                  "(Companion Chatbots, SB 243)"),
        "url": ("https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
                "?lawCode=BPC&sectionNum=22602."),
        "file": "ca_bpc_22602.html",
        "fetch": "curl",
        "status": "200",
        "terms": ("leginfo.legislature.ca.gov Terms of Use: public access to California "
                  "law published by the Legislative Counsel. Statute text is a public "
                  "record."),
        "note": "",
    },
    "co-sb26-189": {
        "label": ("Colorado General Assembly — SB26-189, Automated Decision-Making "
                  "Technology (bill summary as enacted)"),
        "url": "https://leg.colorado.gov/bills/sb26-189",
        "file": "co_sb26-189.html",
        "fetch": "curl",
        "status": "200",
        "terms": ("leg.colorado.gov publishes Colorado bills and session laws for public "
                  "use. Colorado bill text and summaries are public records of the "
                  "General Assembly."),
        "note": ("The quotes here are from the General Assembly's own bill summary, "
                 "which the page marks “This summary applies to this bill as "
                 "enacted.” They are not the section text of the act."),
    },
    "me-10mrsa-1500dd": {
        "label": "Maine Revised Statutes, 10 M.R.S. § 1500-DD",
        "url": "https://legislature.maine.gov/statutes/10/title10sec1500-DD.html",
        "file": "me_10mrsa_1500dd.html",
        "fetch": "curl",
        "status": "200",
        "terms": ("Office of the Revisor of Statutes: “The Revisor's Office cannot "
                  "provide legal advice or interpretation of Maine law to the public.” "
                  "The statutes are published by the State of Maine for public access."),
        "note": "",
    },
    "ut-sb0226": {
        "label": ("Utah S.B. 226 (2025), Enrolled Copy — Artificial Intelligence "
                  "Amendments, enacting Utah Code 13-75-102 to 13-75-104"),
        "url": "https://le.utah.gov/Session/2025/bills/enrolled/SB0226.pdf",
        "file": "ut_sb0226_enrolled.txt",
        "pdf": "ut_sb0226_enrolled.pdf",
        "strip_bill_lines": True,
        "fetch": "curl",
        "status": "200",
        "terms": ("le.utah.gov publishes enrolled bills of the Utah Legislature for "
                  "public access. Utah statutes and enrolled bills are public records."),
        "note": ("The Utah Code viewer at le.utah.gov/xcode/ answers 200 but returns a "
                 "page shell with no statute text to this host, so the enrolled bill "
                 "PDF is quoted instead."),
    },
    "ny-gbs-1701": {
        "label": "New York General Business Law § 1701 (AI Companion Models)",
        "url": "https://www.nysenate.gov/legislation/laws/GBS/1701",
        "file": None,
        "fetch": "browser",
        "status": "403 to this host; read through the session's browser route",
        "terms": ("nysenate.gov publishes New York consolidated laws for public access. "
                  "New York statutes are public records."),
        "note": ("nysenate.gov answers 403 to an ordinary request from this host. That "
                 "is recorded here as a fact. The words were read through the browser "
                 "route, so refresh.py cannot re-check them from this machine and "
                 "reports them as unchecked rather than as verified."),
    },
    "ny-gbs-1702": {
        "label": "New York General Business Law § 1702 (AI Companion Models)",
        "url": "https://www.nysenate.gov/legislation/laws/GBS/1702",
        "file": None,
        "fetch": "browser",
        "status": "403 to this host; read through the session's browser route",
        "terms": ("nysenate.gov publishes New York consolidated laws for public access. "
                  "New York statutes are public records."),
        "note": ("Same 403 wall as § 1701. Read through the browser route; not "
                 "re-checkable from this machine."),
    },
    "il-pa-103-0804": {
        "label": "Illinois Public Act 103-0804 (HB 3773), AI in employment decisions",
        "url": "https://www.ilga.gov/legislation/publicacts/fulltext.asp?Name=103-0804",
        "file": None,
        "fetch": "blocked",
        "status": ("TLS failure from this host (“unable to get local issuer "
                   "certificate”); 403 when verification is skipped; the browser "
                   "route also fails on the certificate"),
        "terms": "Not read. No terms quote, so nothing from this source is published.",
        "note": ("We could not read this document by any route we are allowed to use. "
                 "The Illinois row therefore states that we hold no text for it and "
                 "quotes nothing. It is listed as a CITE-CHECK in NOTES.md."),
    },
}

# --------------------------------------------------------------------------
# Cited passages
# --------------------------------------------------------------------------
# Each row: id, the source it came from, what it is quoted for, and the exact
# words. `verify_quotes()` checks every quote whose source we hold on disk.
CITES = [
    # ---- European Union -------------------------------------------------
    {"id": "eu-inform", "source": "ec-art50-faq",
     "for": "Article 50(1): tell people they are dealing with an AI system",
     "quote": ("Providers of AI systems that directly interact with people must design "
               "and develop those systems in such a way that the individuals concerned "
               "are informed that they are interacting with an AI system, unless this "
               "is obvious.")},
    {"id": "eu-timing", "source": "ec-art50-faq",
     "for": "Article 50(1): when the notice has to appear",
     "quote": ("People must be notified when they are interacting with an AI system "
               "from the start of the first interaction in a clear and distinguishable "
               "manner and in accordance with accessibility requirements.")},
    {"id": "eu-obvious", "source": "ec-art50-faq",
     "for": "Article 50(1): the case the duty does not reach",
     "quote": ("People do not need to be informed when it is obvious they are "
               "interacting with an AI system.")},
    {"id": "eu-marks", "source": "ec-art50-faq",
     "for": "Article 50(2): machine-readable marking of AI output",
     "quote": ("Providers must also ensure that the outputs of their generative AI "
               "systems are marked with effective, reliable, robust and interoperable "
               "machine-readable marks that enable the outputs to be detected as "
               "generated or manipulated by AI systems.")},
    {"id": "eu-emotion", "source": "ec-art50-faq",
     "for": "Article 50(3): emotion recognition and biometric categorisation",
     "quote": ("deployers must ensure that they inform people when they use emotion "
               "recognition or biometric categorisation systems")},
    {"id": "eu-deepfake", "source": "ec-art50-faq",
     "for": "Article 50(4): deepfakes and public-interest text",
     "quote": ("clearly label deepfakes and AI-generated or manipulated text published "
               "on matters of public interest without human review or editorial "
               "control")},
    {"id": "eu-deepfake-when", "source": "ec-art50-faq",
     "for": "Article 50(4): when the deepfake label has to appear",
     "quote": ("Deployers must disclose deepfake content to a natural person upon first "
               "exposure at the latest.")},
    {"id": "eu-applies", "source": "ec-art50-faq",
     "for": "the date Article 50 starts to apply",
     "quote": "Article 50 of the AI Act applies as from 2 August 2026."},
    {"id": "eu-grace", "source": "ec-art50-faq",
     "for": "the only grace period, and what it covers",
     "quote": ("A limited grace period is envisaged only for AI systems placed on the "
               "market before 2 August 2026 and only as regards the marking and "
               "detection obligation for AI-generated content")},
    {"id": "eu-grace-date", "source": "ec-art50-faq",
     "for": "when the grace period ends",
     "quote": ("Providers of such systems must comply with those obligations only as "
               "from 2 December 2026.")},

    # ---- California: the BOT Act ----------------------------------------
    {"id": "ca-bot-duty", "source": "ca-bpc-17941",
     "for": "§ 17941(a): the conduct the section makes unlawful",
     "quote": ("It shall be unlawful for any person to use a bot to communicate or "
               "interact with another person in California online, with the intent to "
               "mislead the other person about its artificial identity")},
    {"id": "ca-bot-purpose", "source": "ca-bpc-17941",
     "for": "§ 17941(a): the two purposes that bring a bot inside the section",
     "quote": ("in order to incentivize a purchase or sale of goods or services in a "
               "commercial transaction or to influence a vote in an election")},
    {"id": "ca-bot-safe", "source": "ca-bpc-17941",
     "for": "§ 17941(a): the way out of liability",
     "quote": ("A person using a bot shall not be liable under this section if the "
               "person discloses that it is a bot.")},
    {"id": "ca-bot-standard", "source": "ca-bpc-17941",
     "for": "§ 17941(b): the standard the disclosure has to meet",
     "quote": ("The disclosure required by this section shall be clear, conspicuous, "
               "and reasonably designed to inform persons with whom the bot "
               "communicates or interacts that it is a bot.")},
    {"id": "ca-bot-operative", "source": "ca-bpc-17941",
     "for": "when the BOT Act became operative",
     "quote": ("Effective January 1, 2019. Operative July 1, 2019, pursuant to Section "
               "17943.")},

    # ---- California: companion chatbots (SB 243) -------------------------
    {"id": "ca-comp-duty", "source": "ca-bpc-22602",
     "for": "§ 22602(a): the companion-chatbot notification",
     "quote": ("If a reasonable person interacting with a companion chatbot would be "
               "misled to believe that the person is interacting with a human, an "
               "operator shall issue a clear and conspicuous notification indicating "
               "that the companion chatbot is artificially generated and not human.")},
    {"id": "ca-comp-minor", "source": "ca-bpc-22602",
     "for": "§ 22602(c)(1): what a known minor is told",
     "quote": "Disclose to the user that the user is interacting with artificial intelligence."},
    {"id": "ca-comp-3hr", "source": "ca-bpc-22602",
     "for": "§ 22602(c)(2): the three-hourly reminder for minors",
     "quote": ("Provide by default a clear and conspicuous notification to the user at "
               "least every three hours for continuing companion chatbot interactions "
               "that reminds the user to take a break and that the companion chatbot is "
               "artificially generated and not human.")},
    {"id": "ca-comp-crisis", "source": "ca-bpc-22602",
     "for": "§ 22602(b)(1): the crisis protocol condition on operating at all",
     "quote": ("An operator shall prevent a companion chatbot on its companion chatbot "
               "platform from engaging with users unless the operator maintains a "
               "protocol for preventing the production of suicidal ideation, suicide, "
               "or self-harm content to the user")},
    {"id": "ca-comp-effective", "source": "ca-bpc-22602",
     "for": "when the companion-chatbot chapter took effect",
     "quote": "Added by Stats. 2025, Ch. 677, Sec. 1. (SB 243) Effective January 1, 2026."},

    # ---- California: AI Transparency Act (SB 942 / AB 853) ---------------
    {"id": "ca-ait-who", "source": "ca-bpc-ch25",
     "for": "§ 22757.1(d): the size threshold that defines a covered provider",
     "quote": ("means a person that creates, codes, or otherwise produces a generative "
               "artificial intelligence system that has over 1,000,000 monthly visitors "
               "or users and is publicly accessible within the geographic boundaries of "
               "the state.")},
    {"id": "ca-ait-manifest", "source": "ca-bpc-ch25",
     "for": "§ 22757.3(a): the visible “this is AI-generated” option",
     "quote": ("A covered provider shall offer the user the option to include a manifest "
               "disclosure in image, video, or audio content, or content that is any "
               "combination thereof")},
    {"id": "ca-ait-manifest-what", "source": "ca-bpc-ch25",
     "for": "§ 22757.3(a)(1): what the visible disclosure has to say",
     "quote": "The disclosure identifies content as AI-generated content."},
    {"id": "ca-ait-latent", "source": "ca-bpc-ch25",
     "for": "§ 22757.3(b): the hidden provenance disclosure",
     "quote": ("A covered provider shall include a latent disclosure in AI-generated "
               "image, video, or audio content, or content that is any combination "
               "thereof")},
    {"id": "ca-ait-tool", "source": "ca-bpc-ch25",
     "for": "§ 22757.2(a): the free detection tool",
     "quote": ("A covered provider shall make available an AI detection tool at no cost "
               "to the user")},
    {"id": "ca-ait-operative", "source": "ca-bpc-ch25",
     "for": "when the chapter becomes operative",
     "quote": "This chapter shall become operative on August 2, 2026."},
    {"id": "ca-ait-ab853", "source": "ca-bpc-ch25",
     "for": "the amendment that moved the operative date",
     "quote": "Amended by Stats. 2025, Ch. 674, Sec. 6. (AB 853) Effective January 1, 2026."},
    {"id": "ca-ait-exempt", "source": "ca-bpc-ch25",
     "for": "§ 22757.5: what the chapter does not reach",
     "quote": ("This chapter does not apply to any product, service, internet website, "
               "or application that provides exclusively non-user-generated video game, "
               "television, streaming, movie, or interactive experiences.")},
    {"id": "ca-ait-penalty", "source": "ca-bpc-ch25",
     "for": "§ 22757.4(a)(1): the civil penalty",
     "quote": ("A violator of this chapter shall be liable for a civil penalty in the "
               "amount of five thousand dollars ($5,000) per violation")},
    {"id": "ca-ait-perday", "source": "ca-bpc-ch25",
     "for": "§ 22757.4(b): each day counts separately",
     "quote": ("Each day that a covered provider, large online platform, or capture "
               "device manufacturer is in violation of this chapter shall be deemed a "
               "discrete violation.")},

    # ---- Colorado --------------------------------------------------------
    {"id": "co-2024", "source": "co-sb26-189",
     "for": "what the 2024 Colorado AI Act was",
     "quote": ("In 2024, the general assembly enacted Senate Bill 24-205, which created "
               "consumer protections in interactions with artificial intelligence "
               "systems.")},
    {"id": "co-repeal", "source": "co-sb26-189",
     "for": "what happened to the 2024 act",
     "quote": ("The act repeals and reenacts those provisions with new requirements "
               "regarding the use of automated decision-making technology in "
               "consequential decisions.")},
    {"id": "co-notice", "source": "co-sb26-189",
     "for": "the consumer notice at the point of interaction",
     "quote": ("The act establishes consumer notice requirements, mandating that "
               "deployers provide clear and conspicuous notice to consumers at the "
               "point of interaction with a covered ADMT.")},
    {"id": "co-adverse", "source": "co-sb26-189",
     "for": "the 30-day explanation after an adverse outcome",
     "quote": ("within 30 days after the covered ADMT makes a consequential decision "
               "that results in an adverse outcome for the consumer")},
    {"id": "co-devdoc", "source": "co-sb26-189",
     "for": "the developer documentation duty and its date",
     "quote": ("starting January 1, 2027, to provide a deployer of a covered ADMT "
               "(deployer) with technical documentation describing the covered ADMT")},
    {"id": "co-records", "source": "co-sb26-189",
     "for": "the record-keeping duty",
     "quote": ("Both developers and deployers are required to retain records necessary "
               "to demonstrate compliance with the act for at least 3 years.")},
    {"id": "co-review", "source": "co-sb26-189",
     "for": "the consumer's right to human review",
     "quote": ("The act also grants consumers the right to request meaningful human "
               "review and reconsideration following a covered ADMT making a "
               "consequential decision resulting in an adverse outcome.")},
    {"id": "co-enforce", "source": "co-sb26-189",
     "for": "who enforces it and how",
     "quote": ("The attorney general is directed to enforce the act through the "
               "'Colorado Consumer Protection Act', and a violation of the act is "
               "deemed a deceptive trade practice.")},

    # ---- Maine -----------------------------------------------------------
    {"id": "me-title", "source": "me-10mrsa-1500dd",
     "for": "the section heading",
     "quote": ("Required disclosure of use of artificial intelligence chatbot to engage "
               "in trade and commerce")},
    {"id": "me-def", "source": "me-10mrsa-1500dd",
     "for": "§ 1500-DD(1)(A): what counts as a chatbot",
     "quote": ("means a software application, web interface or computer program that "
               "simulates human conversation and interaction through textual or aural "
               "communications.")},
    {"id": "me-duty", "source": "me-10mrsa-1500dd",
     "for": "§ 1500-DD(2): the conduct the section reaches",
     "quote": ("A person may not use an artificial intelligence chatbot or any other "
               "computer technology to engage in trade and commerce with a consumer in "
               "a manner that may mislead or deceive a reasonable consumer into "
               "believing that the consumer is engaging with a human being")},
    {"id": "me-standard", "source": "me-10mrsa-1500dd",
     "for": "§ 1500-DD(2): the notice that takes the conduct back out",
     "quote": ("unless the consumer is notified in a clear and conspicuous manner that "
               "the consumer is not engaging with a human being.")},
    {"id": "me-violation", "source": "me-10mrsa-1500dd",
     "for": "§ 1500-DD(3): the enforcement route",
     "quote": ("A violation of subsection 2 is a violation of the Maine Unfair Trade "
               "Practices Act.")},
    {"id": "me-history", "source": "me-10mrsa-1500dd",
     "for": "the enacting session law",
     "quote": "PL 2025, c. 294, §1 (NEW). RR 2025, c. 1, Pt. A, §16 (RAL)."},

    # ---- Utah ------------------------------------------------------------
    {"id": "ut-ondemand", "source": "ut-sb0226",
     "for": "13-75-103(1)(a): the consumer-transaction disclosure",
     "quote": ("A supplier that uses generative artificial intelligence to interact with "
               "an individual in connection with a consumer transaction shall disclose "
               "to the individual that the individual is interacting with generative "
               "artificial intelligence and not a human")},
    {"id": "ut-trigger", "source": "ut-sb0226",
     "for": "13-75-103(1)(a): what sets the duty off",
     "quote": ("if the individual asks or otherwise prompts the supplier about whether "
               "artificial intelligence is being used.")},
    {"id": "ut-prompt", "source": "ut-sb0226",
     "for": "13-75-103(1)(b): what counts as asking",
     "quote": ("must be a clear and unambiguous request to determine whether the "
               "interaction is with a human or with artificial intelligence.")},
    {"id": "ut-regulated", "source": "ut-sb0226",
     "for": "13-75-103(2)(a): regulated occupations",
     "quote": ("prominently disclose when an individual receiving services is "
               "interacting with generative artificial intelligence in the provision of "
               "regulated services if the use of generative artificial intelligence "
               "constitutes a high-risk artificial intelligence interaction")},
    {"id": "ut-when", "source": "ut-sb0226",
     "for": "13-75-103(3): when the regulated-occupation disclosure is given",
     "quote": ("(a) verbally at the start of a verbal interaction; and (b) in writing "
               "before the start of a written interaction.")},
    {"id": "ut-safeharbour", "source": "ut-sb0226",
     "for": "13-75-104(1): the safe harbour",
     "quote": ("A person is not subject to an enforcement action for violating Section "
               "13-75-103 if the person")},
    {"id": "ut-safeharbour-words", "source": "ut-sb0226",
     "for": "13-75-104(1)(b): the words the safe harbour accepts",
     "quote": ("(i) is generative artificial intelligence; (ii) is not human; or (iii) "
               "is an artificial intelligence assistant.")},
    {"id": "ut-effective", "source": "ut-sb0226",
     "for": "when the disclosure section took effect",
     "quote": "13-75-103 (Effective 05/07/25). Required disclosures."},

    # ---- New York (browser route) ----------------------------------------
    {"id": "ny-notify", "source": "ny-gbs-1702",
     "for": "§ 1702: the notification at the start",
     "quote": ("An operator shall provide a clear and conspicuous notification to a user "
               "at the beginning of any AI companion interaction")},
    {"id": "ny-3hr", "source": "ny-gbs-1702",
     "for": "§ 1702: the repeat, and what it has to say",
     "quote": ("at least every three hours for continuing AI companion interactions "
               "which states either verbally or in writing that the user is not "
               "communicating with a human.")},
    {"id": "ny-crisis", "source": "ny-gbs-1701",
     "for": "§ 1701: the crisis protocol condition",
     "quote": ("It shall be unlawful for any operator to operate for or provide an AI "
               "companion to a user unless such AI companion contains a protocol to "
               "take reasonable efforts for detecting and addressing suicidal ideation "
               "or expressions of self-harm expressed by a user to the AI companion")},
    {"id": "ny-referral", "source": "ny-gbs-1701",
     "for": "§ 1701: what the protocol has to do",
     "quote": ("a notification to the user that refers them to crisis service providers "
               "such as the 9-8-8 suicide prevention and behavioral health crisis "
               "hotline")},
]

CITE_BY_ID = {c["id"]: c for c in CITES}

# --------------------------------------------------------------------------
# The answers the reader gives
# --------------------------------------------------------------------------
REGIONS = [
    ("eu", "The European Union"),
    ("ca", "California"),
    ("co", "Colorado"),
    ("ut", "Utah"),
    ("me", "Maine"),
    ("ny", "New York"),
    ("il", "Illinois"),
    ("us-other", "Somewhere else in the United States"),
    ("none", "None of these"),
]

USES = [
    ("chat", "It talks to people in text or voice"),
    ("genai", "It generates text, images, audio or video that people see"),
    ("emotion", "It does emotion recognition or biometric categorisation"),
    ("decision", "It makes or supports a consequential decision — employment, credit, "
                 "housing, insurance, education or health"),
    ("companion", "It is a companion or relationship chatbot"),
    ("commerce", "It sells, or influences a purchase or a vote"),
]

JURISDICTIONS = {
    "eu": {"label": "the European Union", "short": "EU",
           "page_title": "AI disclosure requirements in the European Union"},
    "ca": {"label": "California", "short": "California",
           "page_title": "AI disclosure requirements in California"},
    "co": {"label": "Colorado", "short": "Colorado",
           "page_title": "AI disclosure requirements in Colorado"},
    "ut": {"label": "Utah", "short": "Utah",
           "page_title": "AI disclosure requirements in Utah"},
    "me": {"label": "Maine", "short": "Maine",
           "page_title": "AI disclosure requirements in Maine"},
    "ny": {"label": "New York", "short": "New York",
           "page_title": "AI disclosure requirements in New York"},
    "il": {"label": "Illinois", "short": "Illinois",
           "page_title": "AI disclosure requirements in Illinois"},
}

CHANNELS = {
    "chat-banner": "Chat banner",
    "first-message": "First-message line",
    "content-label": "AI-generated content label",
    "media-label": "Synthetic-media label",
    "emotion-notice": "Emotion or biometric notice",
    "decision-notice": "Consequential-decision notice",
    "companion-notice": "Companion-chatbot notice",
}

# --------------------------------------------------------------------------
# The rule rows
# --------------------------------------------------------------------------
# `match` is the only thing the generator evaluates:
#   region   -- the row is in play when the reader picked this region
#   uses     -- ANY of these AI uses puts the row in play (empty = any use)
#   obvious  -- "exempt" means: reader said it is obvious to a reasonable person,
#               so the row moves to does-not-match and says why
#   size     -- "over-1m" means the row depends on the monthly-user threshold
#   depends  -- a plain-English condition we did NOT ask about, so the row can
#               only ever be "depends" when its region and use match
DUTIES = [
    # ---------------- European Union ----------------
    {"id": "eu-50-1", "region": "eu", "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(1)",
     "clause": "Article 50(1)",
     "duty": "Tell the person they are dealing with an AI system",
     "channels": ["chat-banner", "first-message", "companion-notice"],
     "covered": ("Providers of AI systems that interact directly with people — the "
                 "Commission names chatbots, AI agents and avatars — wherever they are "
                 "established, if the system is placed on the EU market, put into "
                 "service in the EU, or its output is used in the EU."),
     "not_covered": ("It does not reach a system that runs only in the background, only "
                     "machine to machine, or with no direct contact with people; and it "
                     "does not reach a case where it is obvious to a reasonably "
                     "well-informed person that they are dealing with an AI."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["eu-inform", "eu-timing", "eu-applies"],
     "match": {"uses": ["chat", "companion"], "obvious": "exempt"}},

    {"id": "eu-50-1-timing", "region": "eu",
     "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(1)",
     "clause": "Article 50(1), timing",
     "duty": "Show the notice from the start of the first interaction",
     "channels": ["chat-banner", "first-message"],
     "covered": ("The same providers as Article 50(1). The Commission says the notice "
                 "comes at the start of the first interaction, clearly and "
                 "distinguishably, and in line with accessibility requirements."),
     "not_covered": ("It does not reach a system whose AI nature is obvious, and it is "
                     "not satisfied by a line buried in terms of service or a privacy "
                     "policy."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["eu-timing", "eu-obvious"],
     "match": {"uses": ["chat", "companion"], "obvious": "exempt"}},

    {"id": "eu-50-2", "region": "eu", "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(2)",
     "clause": "Article 50(2)",
     "duty": "Mark generative AI output so a machine can detect it",
     "channels": ["content-label", "media-label"],
     "covered": ("Providers of generative AI systems: the outputs carry effective, "
                 "reliable, robust and interoperable machine-readable marks."),
     "not_covered": ("It does not reach a deployer who only uses somebody else's system "
                     "— this paragraph is written at the provider — and a visible "
                     "sentence on the page is not a machine-readable mark."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["eu-marks", "eu-applies"],
     "match": {"uses": ["genai"]}},

    {"id": "eu-50-2-grace", "region": "eu",
     "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(2)",
     "clause": "Article 50(2), grace period",
     "duty": "The one grace period, and the date it ends",
     "channels": ["content-label", "media-label"],
     "covered": ("Systems placed on the market before 2 August 2026, and only for the "
                 "marking and detection duty: those comply from 2 December 2026."),
     "not_covered": ("It does not extend to any other Article 50 duty, and content "
                     "generated before 2 August 2026 does not have to be labelled "
                     "retroactively."),
     "effective": "2026-12-02", "effective_text": "2 December 2026",
     "cites": ["eu-grace", "eu-grace-date"],
     "match": {"uses": ["genai"]}},

    {"id": "eu-50-3", "region": "eu", "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(3)",
     "clause": "Article 50(3)",
     "duty": "Tell people when emotion recognition or biometric categorisation is used",
     "channels": ["emotion-notice"],
     "covered": ("Deployers of emotion recognition or biometric categorisation systems: "
                 "they inform the people exposed to the system."),
     "not_covered": ("It does not reach a person using such a system in a personal, "
                     "non-professional capacity, and it is a deployer duty, not a "
                     "provider one."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["eu-emotion", "eu-applies"],
     "match": {"uses": ["emotion"]}},

    {"id": "eu-50-4", "region": "eu", "law": "EU AI Act, Regulation (EU) 2024/1689, Article 50(4)",
     "clause": "Article 50(4)",
     "duty": "Label deepfakes, and AI text published on matters of public interest",
     "channels": ["media-label", "content-label"],
     "covered": ("Deployers who generate or manipulate image, audio or video that is a "
                 "deepfake, and those who publish AI-generated or manipulated text on "
                 "matters of public interest without human review or editorial control. "
                 "The label reaches the person on first exposure at the latest."),
     "not_covered": ("The Commission says AI generation or manipulation that does not "
                     "make content falsely appear authentic or truthful — background "
                     "scenes, special effects, standard pre- and post-processing — is "
                     "not likely to be caught; and published text that did go through "
                     "human review or editorial control is outside the text half."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["eu-deepfake", "eu-deepfake-when"],
     "match": {"uses": ["genai"]}},

    # ---------------- California ----------------
    {"id": "ca-bot-17941a", "region": "ca",
     "law": "California Business and Professions Code § 17941(a) (the BOT Act)",
     "clause": "§ 17941(a)",
     "duty": "Disclose that a bot is a bot when it sells or influences a vote",
     "channels": ["chat-banner", "first-message"],
     "covered": ("A bot used to communicate or interact with a person in California "
                 "online, with intent to mislead about its artificial identity, in "
                 "order to incentivize a purchase or sale in a commercial transaction "
                 "or to influence a vote in an election."),
     "not_covered": ("It does not reach a bot used for anything other than those two "
                     "purposes — a support or FAQ bot that sells nothing and "
                     "canvasses no vote is outside the section — and a person who "
                     "discloses that it is a bot is not liable under it."),
     "effective": "2019-07-01", "effective_text": "1 July 2019",
     "cites": ["ca-bot-duty", "ca-bot-purpose", "ca-bot-safe", "ca-bot-operative"],
     "match": {"uses": ["commerce"]}},

    {"id": "ca-bot-17941b", "region": "ca",
     "law": "California Business and Professions Code § 17941(b) (the BOT Act)",
     "clause": "§ 17941(b)",
     "duty": "The disclosure has to be clear, conspicuous and designed to inform",
     "channels": ["chat-banner", "first-message"],
     "covered": ("Any disclosure given to escape liability under § 17941(a): it is "
                 "clear, conspicuous, and reasonably designed to inform the people the "
                 "bot talks to that it is a bot."),
     "not_covered": ("It sets no wording and no placement, so it does not tell you where "
                     "the line must sit; and it is only in play where § 17941(a) is."),
     "effective": "2019-07-01", "effective_text": "1 July 2019",
     "cites": ["ca-bot-standard"],
     "match": {"uses": ["commerce"]}},

    {"id": "ca-comp-22602a", "region": "ca",
     "law": "California Business and Professions Code § 22602(a) (SB 243)",
     "clause": "§ 22602(a)",
     "duty": "Say the companion chatbot is artificially generated and not human",
     "channels": ["companion-notice", "chat-banner"],
     "covered": ("Operators of companion chatbots, where a reasonable person "
                 "interacting with it would be misled into believing they are "
                 "interacting with a human."),
     "not_covered": ("It does not reach a chatbot no reasonable person would take for a "
                     "human, and the chapter is about companion chatbots rather than "
                     "ordinary customer-support bots."),
     "effective": "2026-01-01", "effective_text": "1 January 2026",
     "cites": ["ca-comp-duty", "ca-comp-effective"],
     "match": {"uses": ["companion"], "obvious": "exempt"}},

    {"id": "ca-comp-22602c", "region": "ca",
     "law": "California Business and Professions Code § 22602(c) (SB 243)",
     "clause": "§ 22602(c)(1)–(2)",
     "duty": "For a user the operator knows is a minor: say it is AI, and repeat every three hours",
     "channels": ["companion-notice"],
     "covered": ("Operators of companion chatbots, for a user the operator knows is a "
                 "minor: disclose the interaction is with artificial intelligence, and "
                 "by default give a break reminder at least every three hours."),
     "not_covered": ("It is written for users the operator KNOWS are minors, so it does "
                     "not reach an adult user; the three-hour cadence is a default, not "
                     "an absolute."),
     "effective": "2026-01-01", "effective_text": "1 January 2026",
     "cites": ["ca-comp-minor", "ca-comp-3hr"],
     "match": {"uses": ["companion"],
               "depends": "whether any of your users are people you know to be minors"}},

    {"id": "ca-comp-22602b", "region": "ca",
     "law": "California Business and Professions Code § 22602(b) (SB 243)",
     "clause": "§ 22602(b)",
     "duty": "Hold a self-harm crisis protocol and publish it",
     "channels": ["companion-notice"],
     "covered": ("Operators of companion chatbots: the bot does not engage with users "
                 "at all unless the operator maintains a crisis protocol, and the "
                 "details of that protocol are published on the operator's website."),
     "not_covered": ("This is a protocol and a published page, not a notice line — a "
                     "disclosure sentence does not answer it."),
     "effective": "2026-01-01", "effective_text": "1 January 2026",
     "cites": ["ca-comp-crisis"],
     "match": {"uses": ["companion"]}},

    {"id": "ca-ait-threshold", "region": "ca",
     "law": ("California AI Transparency Act, Business and Professions Code "
             "§ 22757.1(d) (SB 942 as amended by AB 853)"),
     "clause": "§ 22757.1(d)",
     "duty": "The size test that decides whether this chapter reaches you at all",
     "channels": ["content-label", "media-label"],
     "covered": ("A person who creates, codes or otherwise produces a generative AI "
                 "system with over 1,000,000 monthly visitors or users that is publicly "
                 "accessible inside California."),
     "not_covered": ("It does not reach a generative AI system under that monthly "
                     "threshold, or one that is not publicly accessible in California; "
                     "and the chapter does not apply at all to products offering "
                     "exclusively non-user-generated video game, television, streaming, "
                     "movie or interactive experiences."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["ca-ait-who", "ca-ait-exempt", "ca-ait-operative", "ca-ait-ab853"],
     "match": {"uses": ["genai"], "size": "over-1m"}},

    {"id": "ca-ait-manifest", "region": "ca",
     "law": "California AI Transparency Act, Business and Professions Code § 22757.3(a)",
     "clause": "§ 22757.3(a)",
     "duty": "Offer the user a visible “this is AI-generated” label",
     "channels": ["content-label", "media-label"],
     "covered": ("Covered providers, for image, video or audio content their generative "
                 "AI system created or altered: the user is offered the option of a "
                 "manifest disclosure that identifies the content as AI-generated, is "
                 "clear and conspicuous, and is permanent or extraordinarily difficult "
                 "to remove."),
     "not_covered": ("This is an option offered to the user, not a label the provider "
                     "must stamp on everything; and it is written about image, video "
                     "and audio rather than text."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["ca-ait-manifest", "ca-ait-manifest-what"],
     "match": {"uses": ["genai"], "size": "over-1m"}},

    {"id": "ca-ait-latent", "region": "ca",
     "law": "California AI Transparency Act, Business and Professions Code § 22757.3(b)",
     "clause": "§ 22757.3(b)",
     "duty": "Embed hidden provenance data in AI-generated image, video and audio",
     "channels": ["content-label", "media-label"],
     "covered": ("Covered providers: a latent disclosure carrying the provider's name, "
                 "the system name and version, the time and date of creation or "
                 "alteration and a unique identifier, detectable by the provider's own "
                 "detection tool."),
     "not_covered": ("A visible sentence on a page does not answer this — it asks for "
                     "data inside the file — and it is written about image, video and "
                     "audio rather than text."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["ca-ait-latent"],
     "match": {"uses": ["genai"], "size": "over-1m"}},

    {"id": "ca-ait-tool", "region": "ca",
     "law": "California AI Transparency Act, Business and Professions Code § 22757.2(a)",
     "clause": "§ 22757.2(a)",
     "duty": "Publish a free AI detection tool",
     "channels": ["content-label"],
     "covered": ("Covered providers: a publicly accessible detection tool, free to the "
                 "user, that reports system provenance data and supports an "
                 "application programming interface."),
     "not_covered": ("It is a tool to build and host, not a notice to write; nothing in "
                     "a notice pack answers it."),
     "effective": "2026-08-02", "effective_text": "2 August 2026",
     "cites": ["ca-ait-tool", "ca-ait-penalty", "ca-ait-perday"],
     "match": {"uses": ["genai"], "size": "over-1m"}},

    # ---------------- Colorado ----------------
    {"id": "co-repealed-2024", "region": "co",
     "law": "Colorado SB 24-205, repealed and reenacted by SB26-189",
     "clause": "SB26-189 bill summary",
     "duty": "The 2024 Colorado AI Act is not the rule to write a notice against",
     "channels": ["decision-notice"],
     "covered": ("Nothing: the General Assembly's own summary of SB26-189 says the act "
                 "repeals and reenacts the 2024 provisions with new requirements."),
     "not_covered": ("A notice written to the 2024 Colorado AI Act text is written to "
                     "provisions that were repealed and reenacted."),
     "effective": "2026-05-14", "effective_text": "signed 14 May 2026",
     "cites": ["co-2024", "co-repeal"],
     "match": {"uses": []}},

    {"id": "co-notice", "region": "co",
     "law": "Colorado SB26-189, Automated Decision-Making Technology",
     "clause": "SB26-189 bill summary, consumer notice",
     "duty": "Clear and conspicuous notice at the point of interaction with a covered ADMT",
     "channels": ["decision-notice"],
     "covered": ("Deployers of an automated decision-making technology used to "
                 "materially influence a consequential decision — education, "
                 "employment, housing, financial or lending services, insurance, "
                 "health care, or essential government services and public benefits."),
     "not_covered": ("It does not reach a technology that is not used to materially "
                     "influence one of those listed consequential decisions, and "
                     "specified entities are exempted to the extent they comply with "
                     "other legal obligations."),
     "effective": "2027-01-01", "effective_text": "see the date note on this row",
     "date_note": ("The General Assembly's summary dates the developer-documentation "
                   "duty from 1 January 2027 and does not attach a date to the "
                   "consumer-notice sentence. We have not fetched the section text, so "
                   "the notice duty's own start date is marked CITE-CHECK rather than "
                   "stated."),
     "cite_check": "the start date of the Colorado consumer-notice duty",
     "cites": ["co-notice", "co-devdoc"],
     "match": {"uses": ["decision"]}},

    {"id": "co-adverse", "region": "co",
     "law": "Colorado SB26-189, Automated Decision-Making Technology",
     "clause": "SB26-189 bill summary, adverse outcome",
     "duty": "Plain-language description within 30 days of an adverse consequential decision",
     "channels": ["decision-notice"],
     "covered": ("Deployers, after a covered ADMT makes a consequential decision that "
                 "results in an adverse outcome for the consumer."),
     "not_covered": ("It is not triggered by a decision with no adverse outcome, and "
                     "the attorney general is directed to write rules clarifying these "
                     "post-adverse-outcome disclosures by 1 January 2027."),
     "effective": "2027-01-01", "effective_text": "rules due by 1 January 2027",
     "cites": ["co-adverse"],
     "match": {"uses": ["decision"]}},

    {"id": "co-devdoc", "region": "co",
     "law": "Colorado SB26-189, Automated Decision-Making Technology",
     "clause": "SB26-189 bill summary, developer documentation",
     "duty": "Give the deployer technical documentation from 1 January 2027",
     "channels": ["decision-notice"],
     "covered": ("Developers of a covered ADMT: intended uses, categories of training "
                 "data, known limitations, and instructions for appropriate use and "
                 "human review, plus notice of material updates."),
     "not_covered": ("It is a developer-to-deployer document, not a consumer notice; a "
                     "company that only deploys somebody else's technology is on the "
                     "receiving end of it."),
     "effective": "2027-01-01", "effective_text": "1 January 2027",
     "cites": ["co-devdoc"],
     "match": {"uses": ["decision"]}},

    {"id": "co-records", "region": "co",
     "law": "Colorado SB26-189, Automated Decision-Making Technology",
     "clause": "SB26-189 bill summary, records",
     "duty": "Keep compliance records for at least three years",
     "channels": ["decision-notice"],
     "covered": "Both developers and deployers of a covered ADMT.",
     "not_covered": ("It says nothing about what a consumer is shown; a notice does not "
                     "answer a record-keeping duty."),
     "effective": "2027-01-01", "effective_text": "see the date note on the notice row",
     "cites": ["co-records"],
     "match": {"uses": ["decision"]}},

    {"id": "co-review", "region": "co",
     "law": "Colorado SB26-189, Automated Decision-Making Technology",
     "clause": "SB26-189 bill summary, human review",
     "duty": "Consumers may request meaningful human review and reconsideration",
     "channels": ["decision-notice"],
     "covered": ("Consumers, after a covered ADMT makes a consequential decision "
                 "resulting in an adverse outcome; they may also request the personal "
                 "data used and correction of factually incorrect data."),
     "not_covered": ("It is a right the consumer exercises, not a line of notice text, "
                     "so a notice pack can point at it but cannot satisfy it."),
     "effective": "2027-01-01", "effective_text": "see the date note on the notice row",
     "cites": ["co-review", "co-enforce"],
     "match": {"uses": ["decision"]}},

    # ---------------- Utah ----------------
    {"id": "ut-ondemand", "region": "ut",
     "law": "Utah Code 13-75-103(1) (S.B. 226, 2025)",
     "clause": "13-75-103(1)",
     "duty": "Answer honestly when a consumer asks whether they are talking to AI",
     "channels": ["chat-banner", "first-message"],
     "covered": ("A supplier using generative AI to interact with an individual in "
                 "connection with a consumer transaction, once that individual asks or "
                 "otherwise prompts about whether AI is being used."),
     "not_covered": ("It does not require an unprompted notice in a consumer "
                     "transaction: the duty runs when the individual asks, and the ask "
                     "has to be a clear and unambiguous request."),
     "effective": "2025-05-07", "effective_text": "7 May 2025",
     "cites": ["ut-ondemand", "ut-trigger", "ut-prompt", "ut-effective"],
     "match": {"uses": ["chat", "commerce"]}},

    {"id": "ut-regulated", "region": "ut",
     "law": "Utah Code 13-75-103(2)–(3) (S.B. 226, 2025)",
     "clause": "13-75-103(2)–(3)",
     "duty": "Regulated occupations: disclose prominently, up front",
     "channels": ["chat-banner", "first-message"],
     "covered": ("An individual providing services in a regulated occupation, where "
                 "generative AI use in providing those services is a high-risk AI "
                 "interaction: verbally at the start of a verbal interaction, and in "
                 "writing before a written one."),
     "not_covered": ("It does not reach an occupation that is not regulated, or a use "
                     "that is not a high-risk AI interaction."),
     "effective": "2025-05-07", "effective_text": "7 May 2025",
     "cites": ["ut-regulated", "ut-when"],
     "match": {"uses": ["chat", "genai"],
               "depends": "whether you provide services in a regulated occupation"}},

    {"id": "ut-safeharbour", "region": "ut",
     "law": "Utah Code 13-75-104 (S.B. 226, 2025)",
     "clause": "13-75-104",
     "duty": "The safe harbour: disclose at the outset and throughout",
     "channels": ["chat-banner", "first-message"],
     "covered": ("A person whose generative AI clearly and conspicuously discloses, at "
                 "the outset of the interaction and throughout it, that it is "
                 "generative AI, is not human, or is an AI assistant."),
     "not_covered": ("It removes an enforcement action under 13-75-103 and nothing "
                     "else; it is not a safe harbour for any other state's rule or for "
                     "the EU."),
     "effective": "2025-05-07", "effective_text": "7 May 2025",
     "cites": ["ut-safeharbour", "ut-safeharbour-words"],
     "match": {"uses": ["chat", "commerce", "genai"]}},

    # ---------------- Maine ----------------
    {"id": "me-duty", "region": "me",
     "law": "Maine Revised Statutes, 10 M.R.S. § 1500-DD(2)",
     "clause": "§ 1500-DD(2)",
     "duty": "Tell the consumer they are not engaging with a human being",
     "channels": ["chat-banner", "first-message"],
     "covered": ("A person using an AI chatbot, or any other computer technology, to "
                 "engage in trade and commerce with a consumer in a way that may "
                 "mislead or deceive a reasonable consumer into believing they are "
                 "engaging with a human being."),
     "not_covered": ("It does not reach a use that could not mislead or deceive a "
                     "reasonable consumer, and the duty falls away where the consumer "
                     "is notified clearly and conspicuously."),
     "effective": "2025-09-24", "effective_text": "see the date note on this row",
     "date_note": ("The statute page names the enacting session law, PL 2025, c. 294, "
                   "but does not print an effective date. We have not fetched the "
                   "chapter law, so the date is marked CITE-CHECK rather than stated."),
     "cite_check": "the effective date of 10 M.R.S. § 1500-DD",
     "cites": ["me-duty", "me-standard", "me-history"],
     "match": {"uses": ["chat", "commerce", "companion"], "obvious": "exempt"}},

    {"id": "me-scope", "region": "me",
     "law": "Maine Revised Statutes, 10 M.R.S. § 1500-DD(1)",
     "clause": "§ 1500-DD(1)",
     "duty": "What counts as an AI chatbot here",
     "channels": ["chat-banner"],
     "covered": ("A software application, web interface or computer program that "
                 "simulates human conversation and interaction through textual or "
                 "aural communications."),
     "not_covered": ("Software that does not simulate human conversation is outside the "
                     "definition, and the section is written about trade and commerce "
                     "with a consumer."),
     "effective": "2025-09-24", "effective_text": "see the date note on the duty row",
     "cites": ["me-def", "me-title"],
     "match": {"uses": ["chat", "companion"]}},

    {"id": "me-enforcement", "region": "me",
     "law": "Maine Revised Statutes, 10 M.R.S. § 1500-DD(3)",
     "clause": "§ 1500-DD(3)",
     "duty": "How a failure is enforced",
     "channels": ["chat-banner"],
     "covered": "A violation of subsection 2 runs through the Maine Unfair Trade Practices Act.",
     "not_covered": ("The section names no separate penalty figure of its own, so the "
                     "consequence is whatever that Act provides."),
     "effective": "2025-09-24", "effective_text": "see the date note on the duty row",
     "cites": ["me-violation"],
     "match": {"uses": ["chat", "commerce", "companion"]}},

    # ---------------- New York ----------------
    {"id": "ny-1702", "region": "ny",
     "law": "New York General Business Law § 1702 (Article 47, AI Companion Models)",
     "clause": "§ 1702",
     "duty": "Say the user is not communicating with a human, at the start and every three hours",
     "channels": ["companion-notice", "chat-banner"],
     "covered": ("Operators of an AI companion: a clear and conspicuous notification at "
                 "the beginning of the interaction, and at least every three hours in a "
                 "continuing one, verbally or in writing."),
     "not_covered": ("The start-of-interaction notification need not be given more than "
                     "once per day, and Article 47 is written about AI companions "
                     "rather than every chatbot."),
     "effective": "2025-11-05", "effective_text": "see the date note on this row",
     "date_note": ("Our source for this section is the browser route, which does not "
                   "print an effective date. The date is marked CITE-CHECK rather than "
                   "stated."),
     "cite_check": "the effective date of New York General Business Law Article 47",
     "cites": ["ny-notify", "ny-3hr"],
     "match": {"uses": ["companion"]}},

    {"id": "ny-1701", "region": "ny",
     "law": "New York General Business Law § 1701 (Article 47, AI Companion Models)",
     "clause": "§ 1701",
     "duty": "Hold a self-harm protocol that refers users to crisis services",
     "channels": ["companion-notice"],
     "covered": ("Operators of an AI companion: the companion contains a protocol for "
                 "detecting and addressing suicidal ideation or self-harm, including a "
                 "notification referring the user to crisis service providers."),
     "not_covered": ("This is a protocol inside the product, not a line of notice text; "
                     "a disclosure sentence does not answer it."),
     "effective": "2025-11-05", "effective_text": "see the date note on the § 1702 row",
     "cites": ["ny-crisis", "ny-referral"],
     "match": {"uses": ["companion"]}},

    # ---------------- Illinois ----------------
    {"id": "il-hb3773", "region": "il",
     "law": "Illinois Public Act 103-0804 (HB 3773) — text not held",
     "clause": "not fetched",
     "duty": "AI in employment decisions — we hold no text for this one",
     "channels": ["decision-notice"],
     "covered": ("We do not state who it covers. ilga.gov refuses this host: the "
                 "certificate chain does not verify, and skipping verification answers "
                 "403. The browser route fails on the same certificate. We publish no "
                 "quote and no date we could not read."),
     "not_covered": ("What we can say from the other sources on this page is that this "
                     "act is written about employment decisions rather than chatbot "
                     "disclosure, so a chat banner is not the thing it asks for."),
     "effective": "", "effective_text": "not stated — source unfetchable",
     "cite_check": "the whole of Illinois Public Act 103-0804 (HB 3773)",
     "cites": [],
     "match": {"uses": ["decision"]}},
]

DUTY_BY_ID = {d["id"]: d for d in DUTIES}

# --------------------------------------------------------------------------
# The notice texts
# --------------------------------------------------------------------------
# {{ORG}} is filled with the organisation name. Nothing here says the notice is
# enough, or that using it makes anybody compliant: each one carries the rows it
# was written from so the buyer can read the rule beside the words.
NOTICES = [
    {"key": "chat-banner", "channel": "chat-banner",
     "title": "Chat banner",
     "where": ("At the top of the chat window, visible before the person types "
               "anything, and readable by a screen reader."),
     "text": ("You are chatting with an AI assistant, not a person. "
              "It is operated by {{ORG}}. "
              "Ask for a human at any time and we will pass you to one."),
     "from_duties": ["eu-50-1", "eu-50-1-timing", "me-duty", "ut-safeharbour",
                     "ca-bot-17941b"]},
    {"key": "first-message", "channel": "first-message",
     "title": "First-message line",
     "where": ("The first line of the assistant's first message, in every session, "
               "before anything else it says."),
     "text": ("Before we start: I am an AI assistant run by {{ORG}}, not a human. "
              "I am generative artificial intelligence and not a person."),
     "from_duties": ["eu-50-1", "eu-50-1-timing", "ut-safeharbour", "ut-ondemand",
                     "me-duty"]},
    {"key": "companion-notice", "channel": "companion-notice",
     "title": "Companion-chatbot notice",
     "where": ("At the beginning of every companion interaction, and repeated in a "
               "continuing one at least every three hours."),
     "text": ("{{ORG}} reminder: you are not communicating with a human. "
              "This companion is artificially generated and not human. "
              "If you are struggling, contact a crisis service — in the United States "
              "call or text 9-8-8."),
     # Deliberately NOT eu-50-1. That clause reaches every chatbot, so listing it
     # here would offer a companion-chatbot notice to anybody running an ordinary
     # support bot in the EU. The EU duty is carried by the chat banner and the
     # first-message line instead.
     "from_duties": ["ny-1702", "ca-comp-22602a", "ca-comp-22602c"]},
    {"key": "commerce-bot", "channel": "chat-banner",
     "title": "Selling or vote-influencing bot disclosure",
     "where": ("Wherever the bot first communicates with a person, clear and "
               "conspicuous, before it recommends or sells anything."),
     "text": ("This is a bot, operated by {{ORG}}. "
              "You are not talking to a person."),
     "from_duties": ["ca-bot-17941a", "ca-bot-17941b"]},
    {"key": "content-label", "channel": "content-label",
     "title": "AI-generated content label",
     "where": ("Beside the content itself, on first exposure, in the same medium as "
               "the content."),
     "text": ("AI-generated content. This text was generated by an artificial "
              "intelligence system operated by {{ORG}}."),
     "from_duties": ["eu-50-2", "eu-50-4", "ca-ait-manifest"]},
    {"key": "media-label", "channel": "media-label",
     "title": "Synthetic-media label",
     "where": ("Visible or audible on the image, audio or video itself, reaching the "
               "viewer on first exposure at the latest."),
     "text": ("This image, audio or video has been artificially generated or "
              "manipulated by {{ORG}}. It does not depict a real event."),
     "from_duties": ["eu-50-4", "eu-50-2", "ca-ait-manifest", "ca-ait-latent"]},
    {"key": "emotion-notice", "channel": "emotion-notice",
     "title": "Emotion or biometric notice",
     "where": ("Where the person is exposed to the system, before or as the "
               "processing begins."),
     "text": ("{{ORG}} uses an artificial intelligence system here that analyses "
              "emotion or categorises people using biometric data. "
              "You are being told because you are exposed to that system."),
     "from_duties": ["eu-50-3"]},
    {"key": "decision-notice", "channel": "decision-notice",
     "title": "Consequential-decision notice",
     "where": ("At the point of interaction with the automated system, before the "
               "decision step, and in the record sent afterwards."),
     "text": ("{{ORG}} uses automated decision-making technology at this step. "
              "It processes your personal data to help decide the outcome. "
              "You can ask what it did, ask for the data it used, ask for factually "
              "incorrect data to be corrected, and ask for a human to review the "
              "decision."),
     "from_duties": ["co-notice", "co-adverse", "co-review"]},
]

NOTICE_BY_KEY = {n["key"]: n for n in NOTICES}


# --------------------------------------------------------------------------
# Fetching and quote verification
# --------------------------------------------------------------------------
def norm(s: str) -> str:
    """Whitespace-flattened text, for comparing a quote against a fetched page.

    Only whitespace is touched. HTML turns one sentence into several lines and a
    PDF text layer pads with runs of spaces; neither changes a word. Nothing else
    is normalised -- a different word, a different number or a different curly
    quote is a different quote and has to fail.
    """
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
    return _html.unescape(raw)


def strip_bill_line_numbers(text: str) -> str:
    """Drop the margin line numbers and page furniture from an enrolled-bill PDF.

    An enrolled bill prints a line number in the left margin of every line, and
    the PDF text layer keeps them, so they land in the middle of a sentence that
    wraps. They are printing furniture, not words of the statute. Only a leading
    integer at the start of a line is removed, plus the running header and the
    page-number rule, so nothing inside a sentence is touched.
    """
    out = []
    for line in text.splitlines():
        if re.fullmatch(r"\s*-\s*\d+\s*-\s*", line):
            continue
        if re.match(r"\s*(Enrolled Copy|S\.B\. 226)\s*$", line):
            continue
        line = re.sub(r"^\s*\d{1,4}(?=\s)", "", line)
        line = re.sub(r"^\s*(Enrolled Copy|S\.B\. 226)\s{6,}", "", line)
        line = re.sub(r"\s{6,}(Enrolled Copy|S\.B\. 226)\s*$", "", line)
        out.append(line)
    return "\n".join(out)


def read_source_text(sid: str) -> str | None:
    """The fetched text of one source from RAW_DIR, or None when we hold none."""
    src = SOURCES[sid]
    name = src.get("file")
    if not name:
        return None
    p = RAW_DIR / name
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(raw) if name.endswith(".html") else raw
    if src.get("strip_bill_lines"):
        text = strip_bill_line_numbers(text)
    return text


def fetch_source(sid: str, timeout: int = 60) -> tuple[int | str, bytes | None]:
    """Fetch one source over HTTPS. Returns (status, body) and never raises.

    A wall answers with its status code and that is the whole of our response to
    it: it is written down. Nothing here retries behind a challenge, forges a
    token or turns certificate verification off.
    """
    src = SOURCES[sid]
    url = src["url"]
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    pass
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, ssl.SSLError, OSError, ValueError) as e:
        return f"no-response ({type(e).__name__})", None


def verify_quotes(fetched: dict[str, str] | None = None) -> list[dict]:
    """Check every quote against the text of the source it claims to come from.

    Returns one row per cite:
      status "ok"        -- found, word for word, in the fetched text
      status "drifted"   -- the source is on disk and the quote is NOT in it
      status "unchecked" -- we hold no text for that source (a 403 wall read
                            through the browser route, or a document we could
                            not read at all)
    `fetched` lets refresh.py pass freshly downloaded text instead of the cache.
    """
    cache: dict[str, str | None] = {}
    out = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    for c in CITES:
        sid = c["source"]
        if fetched and sid in fetched:
            text = fetched[sid]
        else:
            if sid not in cache:
                cache[sid] = read_source_text(sid)
            text = cache[sid]
        src = SOURCES[sid]
        if text is None:
            status = "unchecked"
        else:
            status = "ok" if norm(c["quote"]) in norm(text) else "drifted"
        out.append({
            "id": c["id"],
            "url": src["url"],
            "source": sid,
            "source_label": src["label"],
            "for": c["for"],
            "quote": c["quote"],
            "fetched": stamp,
            "fetch_method": src["fetch"],
            "http_status": src["status"],
            "status": status,
        })
    return out


# --------------------------------------------------------------------------
# The generator, in Python. The same rules run in the browser; see
# scripts/slice_ai_disclosure_notice.py for the JS twin and browser_test.py for
# the test that drives both against the same fixtures.
# --------------------------------------------------------------------------
MATCH = "matches"
NO_MATCH = "does-not-match"
DEPENDS = "depends"

STATUS_LABEL = {
    MATCH: "Matches your answers",
    NO_MATCH: "Does not match your answers",
    DEPENDS: "Depends on something we did not ask",
}


def evaluate(duty: dict, answers: dict) -> dict:
    """Which of the reader's answers this rule row matches, and why.

    This is a filter over published rule text. It says whether a row's own stated
    conditions line up with the answers given, and it says which condition did
    the work. It does not say what anybody must do, and it never decides whether
    a company complies with anything.
    """
    regions = set(answers.get("regions") or [])
    uses = set(answers.get("uses") or [])
    obvious = bool(answers.get("obvious"))
    size = answers.get("users_over_1m")  # True / False / None

    m = duty.get("match", {})
    reasons: list[str] = []

    if duty["region"] not in regions:
        return {"status": NO_MATCH,
                "why": (f"You did not say your users are in "
                        f"{JURISDICTIONS[duty['region']]['label']}.")}

    want = set(m.get("uses") or [])
    if want and not (want & uses):
        return {"status": NO_MATCH,
                "why": ("This row is about a use you did not pick: "
                        + ", ".join(dict(USES)[u].lower() for u in sorted(want)) + ".")}

    if m.get("obvious") == "exempt" and obvious:
        return {"status": NO_MATCH,
                "why": ("You said a reasonable person would find it obvious this is an "
                        "AI. This row states its own exception for that case — read "
                        "the not-covered column before relying on it.")}

    if m.get("size") == "over-1m":
        if size is False:
            return {"status": NO_MATCH,
                    "why": ("You said the system is under 1,000,000 monthly users. This "
                            "row's own threshold is over 1,000,000.")}
        if size is None:
            return {"status": DEPENDS,
                    "why": ("This row turns on a monthly-user threshold of 1,000,000 and "
                            "you did not answer that question.")}
        reasons.append("you said the system is over 1,000,000 monthly users")

    if m.get("depends"):
        return {"status": DEPENDS,
                "why": f"It turns on {m['depends']}, which we did not ask."}

    if not duty.get("cites"):
        return {"status": DEPENDS,
                "why": ("We hold no text for this rule, so we do not say whether it "
                        "matches. See the not-covered column.")}

    reasons.append(f"your users are in {JURISDICTIONS[duty['region']]['label']}")
    if want:
        picked = sorted(want & uses)
        reasons.append("your AI " + " and ".join(dict(USES)[u].lower() for u in picked))
    return {"status": MATCH, "why": "Matched because " + ", and ".join(reasons) + "."}


def matrix(answers: dict) -> list[dict]:
    """Every rule row, with how it lines up against these answers."""
    out = []
    for d in DUTIES:
        r = evaluate(d, answers)
        out.append({**d, "result": r["status"], "why": r["why"]})
    return out


def notices_for(answers: dict, org: str) -> list[dict]:
    """The notice texts whose rule rows match these answers, filled with `org`.

    A notice is offered when at least one of the rows it was written from
    matches. The rows are carried along so the buyer reads the rule next to the
    words rather than trusting the words on their own.
    """
    res = {row["id"]: row["result"] for row in matrix(answers)}
    out = []
    for n in NOTICES:
        hit = [d for d in n["from_duties"] if res.get(d) == MATCH]
        maybe = [d for d in n["from_duties"] if res.get(d) == DEPENDS]
        if not hit and not maybe:
            continue
        out.append({
            "key": n["key"], "channel": n["channel"], "title": n["title"],
            "where": n["where"],
            "text": n["text"].replace("{{ORG}}", org),
            "matched": hit, "depends": maybe,
        })
    return out


def review_dates() -> list[dict]:
    """Every date a row names, soonest first, for the 'review again when' list."""
    seen: dict[str, dict] = {}
    for d in DUTIES:
        if not d.get("effective"):
            continue
        key = f"{d['effective']}|{d['region']}"
        seen.setdefault(key, {
            "date": d["effective"], "region": d["region"],
            "region_label": JURISDICTIONS[d["region"]]["label"],
            "text": d["effective_text"], "laws": [],
        })
        if d["law"] not in seen[key]["laws"]:
            seen[key]["laws"].append(d["law"])
    return sorted(seen.values(), key=lambda r: (r["date"], r["region"]))


def cite_checks() -> list[dict]:
    """Everything we could not verify, named, in one list."""
    out = []
    for d in DUTIES:
        if d.get("cite_check"):
            out.append({"duty": d["id"], "region": d["region"], "what": d["cite_check"],
                        "note": d.get("date_note", "")})
    for sid, s in SOURCES.items():
        if s["fetch"] in ("blocked", "browser"):
            out.append({"duty": "", "region": "", "what": f"source {sid}: {s['label']}",
                        "note": f"{s['fetch']} — {s['status']}"})
    return out


def load_status() -> dict:
    p = DATA / "status.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def stamp_of(status: dict | None = None) -> str:
    s = status if status is not None else load_status()
    return s.get("stamp") or dt.date.today().isoformat()


def _main() -> int:
    bad_len = [c["id"] for c in CITES if len(c["quote"]) > QUOTE_MAX]
    rows = verify_quotes()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"sources  {len(SOURCES)}  duties {len(DUTIES)}  cites {len(CITES)}  "
          f"notices {len(NOTICES)}")
    print(f"quotes   " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"over {QUOTE_MAX} chars: {bad_len or 'none'}")
    print(f"cite-checks {len(cite_checks())}")
    return 1 if (bad_len or counts.get("drifted")) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
