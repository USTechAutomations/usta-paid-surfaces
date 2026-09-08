#!/usr/bin/env python3
"""Fetch an official page, keep the raw bytes, and pull plain words out of it.

Nothing in this file decides what a rule means. It fetches, it caches the raw
answer under ~/.hermes/state/fv5/contractor-audit-file/raw/, and it turns markup
into readable text so the caller can look for the words a statute actually uses.
A page that answers anything but 200, or that comes back without the section
number we asked for, is reported as a fact and never guessed around.
"""
from __future__ import annotations

import gzip
import hashlib
import html as htmllib
import io
import json
import os
import re
import urllib.error
import urllib.request
import zlib
from pathlib import Path

FAMILY = "contractor-audit-file"
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
RAW = STATE / "raw"
UA = "USTechAutomations-fv6/1.0 (+https://ustechautomations.com; audit-evidence file)"
TIMEOUT = 40


def _raw_path(url: str) -> Path:
    return RAW / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".bin")


def fetch(url: str, *, use_cache: bool = True) -> tuple[int, bytes, str]:
    """(status, body, note). Never raises for a wall; a 403 is an answer."""
    p = _raw_path(url)
    if use_cache and p.is_file() and p.stat().st_size > 0:
        return 200, p.read_bytes(), "cache"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
            elif "deflate" in enc:
                body = zlib.decompress(body, -zlib.MAX_WBITS)
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, b"", f"HTTP {e.code}"
    except Exception as e:                      # DNS, TLS, timeout: all facts
        return 0, b"", f"{type(e).__name__}"
    if status == 200 and body:
        RAW.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return status, body, "network"


_TAGS = re.compile(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>")
_BR = re.compile(r"(?is)</(p|div|li|tr|h[1-6]|section|article)>")


def to_text(body: bytes) -> str:
    """Readable words out of HTML, XML or a PDF's text objects."""
    if body[:5] == b"%PDF-":
        return _pdf_text(body)
    s = body.decode("utf-8", "replace")
    s = _TAGS.sub(" ", s)
    s = _BR.sub("\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = s.replace(" ", " ").replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n\s*", "\n", s)
    return s.strip()


def _pdf_text(body: bytes) -> str:
    """Enough of a PDF to search it. Uncompressed text objects only."""
    out: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", body, re.S):
        chunk = m.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            pass
        for t in re.finditer(rb"\((?:\\.|[^()\\])*\)", chunk):
            piece = t.group(0)[1:-1]
            piece = re.sub(rb"\\([()\\])", rb"\1", piece)
            out.append(piece.decode("latin-1", "replace"))
    s = " ".join(out)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean(s: str) -> str:
    """A quote fit to print: no replacement characters, no control bytes.

    Two state sites answer in a legacy encoding, and the bytes that do not
    decode come back as U+FFFD. Left in, they end up inside a quotation mark on
    a page that says these are the statute's own words, which they are not.
    A run of them is cut to a single space and the quote is still exact
    everywhere else.
    """
    s = re.sub(r"[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;])\s+|\n", text)
    return [normalise(p) for p in parts if normalise(p)]


def passage(text, anchors, *, cap: int = 300, must_also=None, min_len: int = 60) -> str:
    """The shortest whole sentence in `text` that carries one of `anchors`.

    Whole sentences only. An earlier version cut a fixed window around the match
    and published quotes that began mid-word ("ncluding wages..."), which is not
    what the statute says. Newlines are flattened first because several state
    sites print their code with hard line wraps in the middle of sentences.
    """
    flat = normalise(text.replace("\n", " "))
    parts = re.split(r"(?<=[.;])\s+", flat)
    best = ""
    best_anchor = ""
    for a in anchors:
        al = a.lower()
        for s in parts:
            sl = s.lower()
            if al not in sl or len(s) < min_len:
                continue
            if must_also and not any(m in sl for m in must_also):
                continue
            if not best or len(s) < len(best):
                best = s
                best_anchor = al
        if best:
            break
    if not best:
        return ""
    best = clean(best)
    if len(best) > cap:
        # A long sentence is cut around the words we were looking for, not from
        # its start. Cutting from the start dropped the dollar amount out of
        # California's penalty section and left a quote that named no number.
        # The window is centred on the anchor that actually matched, not on the
        # earliest anchor in the list -- centring on the wrong one moved
        # Nebraska's quote onto a neighbouring prong's words. The result is
        # still one contiguous run of the source's own words.
        at = max(best.lower().find(best_anchor), 0)
        half = cap // 4   # anchor sits a quarter in, so its words read first
        start = max(0, at - half)
        end = min(len(best), start + cap - 2)
        start = max(0, end - (cap - 2))
        piece = best[start:end]
        if start:
            piece = piece.split(" ", 1)[-1]
        if end < len(best):
            piece = piece.rsplit(" ", 1)[0]
        best = ("\u2026" if start else "") + piece.strip() + ("\u2026" if end < len(best) else "")
    return best


def carries(text: str, must: list[str]) -> bool:
    low = re.sub(r"\s+", " ", text.lower())
    return all(m.lower() in low for m in must)


if __name__ == "__main__":
    import sys
    seeds = json.loads(Path(__file__).with_name("data").joinpath("sources_seed.json")
                       .read_text(encoding="utf-8"))
    rows = seeds["federal"] + seeds["states"]
    if "--only" in sys.argv:
        want = sys.argv[sys.argv.index("--only") + 1].split(",")
        rows = [r for r in rows if r["code"] in want]
    ok = 0
    for r in rows:
        url = r["url"].replace("{date}", "2026-01-01")
        st, body, note = fetch(url)
        txt = to_text(body) if body else ""
        good = st == 200 and carries(txt, r.get("must", []))
        ok += bool(good)
        print(f"{r['code']:8} {st:3} {len(body):8} match={int(good)} {note:8} {len(txt):7}")
    print(f"SEEDS ok={ok}/{len(rows)}")
