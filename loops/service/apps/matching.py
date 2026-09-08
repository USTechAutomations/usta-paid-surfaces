"""Compare two lists of invoices and say exactly which rows disagree.

Pure functions only. Nothing here touches the web, the store, or the network.

The two sides are called A and B. A is the person who started the compare, B is
the other business. This module never says which side is right; it only says
where the two lists differ.

No person data: a row holds an invoice reference, an optional date and an
amount. Nothing else is read or kept.
"""
from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from itertools import combinations

MAX_ROWS = 2000
MAX_COLUMNS = 3
MAX_REF_CHARS = 80

# how hard we look for a group of rows that adds up to one row on the other side
SPLIT_MAX_PARTS = 4
SPLIT_POOL = 16          # candidate rows considered per unmatched row
SPLIT_MAX_TARGETS = 300  # unmatched rows we run the search for

_HEADER_WORDS = {
    "ref", "reference", "invoice", "invoice no", "invoice number", "inv",
    "doc", "document", "number", "no", "date", "amount", "amt", "value",
    "total", "balance", "open", "due", "gross", "net",
}

_TWO_SPACES = re.compile(r"\s{2,}")
_DIGIT_RUN = re.compile(r"(?<!\d)0+(\d)")
_DATE_SLASH = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_MONEY_OK = re.compile(r"^-?\d+(\.\d+)?$")


# ---------------------------------------------------------------- amounts ---

def parse_amount(raw: str):
    """Turn a pasted amount into an exact number, or None if it is not one.

    Understands "$1,234.50", "(45.00)" for a negative, "45.00-", spaces and
    stray currency letters such as "USD".
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    # drop currency symbols and letters
    s = re.sub(r"[^0-9,.\-+ ]", "", s).strip()
    if s.endswith("-"):
        negative = True
        s = s[:-1].strip()
    if s.startswith("+"):
        s = s[1:].strip()
    if s.startswith("-"):
        negative = not negative
        s = s[1:].strip()
    s = s.replace(" ", "")
    if not s:
        return None
    # 1.234,56 (European) vs 1,234.56
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 2 and len(parts[0]) <= 3:
            s = parts[0] + "." + parts[1]     # 45,50 means 45.50
        else:
            s = s.replace(",", "")            # 1,234 means 1234
    if not _MONEY_OK.match(s):
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return value.quantize(Decimal("0.01"))


def money(value) -> str:
    """Show an amount as a plain number with two decimal places."""
    if value is None:
        return ""
    return f"{Decimal(value).quantize(Decimal('0.01')):,}"


# ------------------------------------------------------------------ dates ---

def _date_parts(raw: str):
    """(first, second, year) for a slash date, or None."""
    s = (raw or "").strip()
    m = _DATE_ISO.match(s)
    if m:
        return ("iso", int(m.group(2)), int(m.group(3)), int(m.group(1)))
    m = _DATE_SLASH.match(s)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        return ("slash", int(m.group(1)), int(m.group(2)), year)
    return None


def _looks_like_date(raw: str) -> bool:
    return _date_parts(raw) is not None


def decide_date_style(raws) -> str:
    """Say how we will read 03/04/2026: 'day/month', 'month/day' or 'none'.

    If any date has a first number above 12 it must be a day. If any has a
    second number above 12 the first must be the month. If we cannot tell, we
    read it the American way (month first) and say so on the report.
    """
    seen = False
    for raw in raws:
        p = _date_parts(raw or "")
        if not p or p[0] != "slash":
            continue
        seen = True
        if p[1] > 12:
            return "day/month"
        if p[2] > 12:
            return "month/day"
    return "month/day (we could not tell)" if seen else "none"


# ------------------------------------------------------------------ rows ----

_THOUSANDS = re.compile(r"^\d{3}(\.\d{1,4})?$")
_NUMBERISH = re.compile(r"^[($+-]*\d[\d,]*$")


def _merge_thousands(cols):
    """Put "1,250.00" back together after a split on commas.

    Only a column that is a bare number can join to the one after it, and only
    when that next one is a group of exactly three digits. A date never joins,
    because a date carries dashes or slashes.
    """
    out = []
    i = 0
    while i < len(cols):
        cur = cols[i]
        while (i + 1 < len(cols) and _NUMBERISH.match(cur.replace(" ", ""))
               and _THOUSANDS.match(cols[i + 1].replace(" ", "").rstrip(")-"))):
            nxt = cols[i + 1]
            cur = cur + "," + nxt
            i += 1
        out.append(cur)
        i += 1
    return out


def _split_line(line: str):
    for d in ("\t", "|", ";"):
        if d in line:
            return [c.strip().strip('"').strip() for c in line.split(d)]
    if "," in line:
        try:
            cols = next(csv.reader([line]))
        except Exception:  # noqa: BLE001
            cols = line.split(",")
        return _merge_thousands([c.strip() for c in cols])
    if _TWO_SPACES.search(line):
        return [c.strip() for c in _TWO_SPACES.split(line)]
    return [p.strip() for p in line.split()]


def _is_header(cols) -> bool:
    if not cols:
        return False
    low = [c.strip().lower() for c in cols]
    if parse_amount(low[-1]) is not None:
        return False
    return any(c in _HEADER_WORDS for c in low)


def parse_rows(text: str, max_rows: int = MAX_ROWS) -> dict:
    """Read pasted text or CSV into rows.

    Returns {"ok": True, "rows": [...], "date_style": str, "header_skipped": bool}
    or {"ok": False, "reason": "<plain English>"}.
    """
    if text is None:
        return {"ok": False, "reason": "Nothing was pasted. Paste your list of invoices and try again."}
    lines = [ln for ln in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    rows = []
    header_skipped = False
    date_raws = []
    counted = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cols = [c for c in _split_line(stripped)]
        cols = [c for c in cols if c != ""]
        if not cols:
            continue
        if not rows and not header_skipped and _is_header(cols):
            header_skipped = True
            continue
        if len(cols) > MAX_COLUMNS:
            return {"ok": False, "reason": (
                f"Line {i} has {len(cols)} columns. A row needs an invoice reference, "
                "an optional date, and an amount. Please remove the extra columns and try again.")}
        if len(cols) < 2:
            return {"ok": False, "reason": (
                f"Line {i} has only one column. A row needs an invoice reference and an "
                "amount, for example: INV-1001, 250.00")}
        counted += 1
        if counted > max_rows:
            return {"ok": False, "reason": (
                f"That list has more than {max_rows:,} rows. Please split it into smaller "
                "lists and compare them one at a time.")}
        ref = cols[0]
        if len(ref) > MAX_REF_CHARS:
            return {"ok": False, "reason": (
                f"Line {i}: the invoice reference is longer than {MAX_REF_CHARS} characters. "
                "Please shorten it.")}
        if "@" in ref:
            return {"ok": False, "reason": (
                f"Line {i} looks like it has an email address in it. Please give an invoice "
                "reference, not a person.")}
        date_raw = cols[1] if len(cols) == 3 else ""
        amount_raw = cols[-1]
        amount = parse_amount(amount_raw)
        if amount is None:
            return {"ok": False, "reason": (
                f"Line {i}: we could not read \"{amount_raw}\" as an amount. Amounts look "
                "like 1,250.00 or (45.00) for a credit.")}
        if len(cols) == 3 and date_raw and not _looks_like_date(date_raw):
            return {"ok": False, "reason": (
                f"Line {i}: we could not read \"{date_raw}\" as a date. Dates look like "
                "2026-03-04 or 03/04/2026.")}
        if date_raw:
            date_raws.append(date_raw)
        rows.append({"line": i, "ref": ref, "date": date_raw or None, "amount": amount})
    if not rows:
        return {"ok": False, "reason": (
            "We could not find any rows. Each line should be an invoice reference and an "
            "amount, for example: INV-1001, 250.00")}
    return {"ok": True, "rows": rows, "date_style": decide_date_style(date_raws),
            "header_skipped": header_skipped}


# -------------------------------------------------------------- matching ----

def normalise_ref(ref: str) -> str:
    """Same invoice written a different way: ignore case, spaces, leading zeros."""
    s = re.sub(r"\s+", "", (ref or "")).upper()
    return _DIGIT_RUN.sub(r"\1", s)


def _group(rows):
    out = {}
    for r in rows:
        out.setdefault(r["ref"].strip(), []).append(r)
    return out


def compare(rows_a, rows_b, label_a: str = "Side A", label_b: str = "Side B",
            date_style_a: str = "none", date_style_b: str = "none") -> dict:
    """Compare two lists of rows and describe every difference."""
    left = list(rows_a)
    right = list(rows_b)
    used_a, used_b = set(), set()
    findings = []

    def key_a(r):
        return ("a", r["line"], id(r))

    ida = {id(r): r for r in left}
    idb = {id(r): r for r in right}

    # 1) same reference, exactly as written
    ga, gb = _group(left), _group(right)
    for ref in sorted(set(ga) & set(gb)):
        pairs = zip(sorted(ga[ref], key=lambda r: r["line"]),
                    sorted(gb[ref], key=lambda r: r["line"]))
        for ra, rb in pairs:
            used_a.add(id(ra))
            used_b.add(id(rb))
            if ra["amount"] == rb["amount"]:
                findings.append({"kind": "matched", "ref_a": ra["ref"], "ref_b": rb["ref"],
                                 "amount_a": money(ra["amount"]), "amount_b": money(rb["amount"]),
                                 "difference": "", "note": "Both lists agree."})
            else:
                diff = ra["amount"] - rb["amount"]
                findings.append({"kind": "amount_differs", "ref_a": ra["ref"], "ref_b": rb["ref"],
                                 "amount_a": money(ra["amount"]), "amount_b": money(rb["amount"]),
                                 "difference": money(abs(diff)),
                                 "note": f"Amount differs by {money(abs(diff))}."})

    rest_a = [r for r in left if id(r) not in used_a]
    rest_b = [r for r in right if id(r) not in used_b]

    # 2) same amount, reference written a different way
    na = {}
    for r in rest_a:
        na.setdefault((normalise_ref(r["ref"]), r["amount"]), []).append(r)
    nb = {}
    for r in rest_b:
        nb.setdefault((normalise_ref(r["ref"]), r["amount"]), []).append(r)
    for k in sorted(set(na) & set(nb), key=lambda t: (t[0], str(t[1]))):
        for ra, rb in zip(sorted(na[k], key=lambda r: r["line"]),
                          sorted(nb[k], key=lambda r: r["line"])):
            used_a.add(id(ra))
            used_b.add(id(rb))
            findings.append({"kind": "ref_written_differently", "ref_a": ra["ref"],
                             "ref_b": rb["ref"], "amount_a": money(ra["amount"]),
                             "amount_b": money(rb["amount"]), "difference": "",
                             "note": "Same invoice, reference written differently."})

    rest_a = [r for r in left if id(r) not in used_a]
    rest_b = [r for r in right if id(r) not in used_b]

    # 3) a group of rows on one side that adds up to one row on the other
    for target, pool, side in ((rest_a, rest_b, "b"), (rest_b, rest_a, "a")):
        tried = 0
        for row in sorted(target, key=lambda r: r["line"]):
            if id(row) in used_a or id(row) in used_b:
                continue
            if tried >= SPLIT_MAX_TARGETS:
                break
            tried += 1
            free = [r for r in pool
                    if id(r) not in used_a and id(r) not in used_b
                    and r["amount"] > 0 and r["amount"] < row["amount"]]
            free.sort(key=lambda r: (-r["amount"], r["line"]))
            free = free[:SPLIT_POOL]
            found = None
            for size in range(2, SPLIT_MAX_PARTS + 1):
                for combo in combinations(free, size):
                    if sum((c["amount"] for c in combo), Decimal("0")) == row["amount"]:
                        found = combo
                        break
                if found:
                    break
            if not found:
                continue
            used = used_a if side == "b" else used_b
            used.add(id(row))
            other = used_b if side == "b" else used_a
            for c in found:
                other.add(id(c))
            parts = ", ".join(c["ref"] for c in found)
            if side == "b":
                ref_a, ref_b = row["ref"], parts
                amt_a, amt_b = money(row["amount"]), money(sum((c["amount"] for c in found), Decimal("0")))
            else:
                ref_a, ref_b = parts, row["ref"]
                amt_a, amt_b = money(sum((c["amount"] for c in found), Decimal("0"))), money(row["amount"])
            findings.append({"kind": "split_payment_candidate", "ref_a": ref_a, "ref_b": ref_b,
                             "amount_a": amt_a, "amount_b": amt_b, "difference": "",
                             "note": (f"{len(found)} rows on the other list add up to this one. "
                                      "It may have been paid or invoiced in parts.")})

    # 4) whatever is left is on one list only
    for r in sorted([r for r in left if id(r) not in used_a], key=lambda r: r["line"]):
        findings.append({"kind": "missing_on_b", "ref_a": r["ref"], "ref_b": "",
                         "amount_a": money(r["amount"]), "amount_b": "", "difference": "",
                         "note": f"Only on the list from {label_a}."})
    for r in sorted([r for r in right if id(r) not in used_b], key=lambda r: r["line"]):
        findings.append({"kind": "missing_on_a", "ref_a": "", "ref_b": r["ref"],
                         "amount_a": "", "amount_b": money(r["amount"]), "difference": "",
                         "note": f"Only on the list from {label_b}."})

    order = {"amount_differs": 0, "split_payment_candidate": 1, "missing_on_b": 2,
             "missing_on_a": 3, "ref_written_differently": 4, "matched": 5}
    findings.sort(key=lambda f: (order.get(f["kind"], 9), f["ref_a"], f["ref_b"]))

    counts = {"matched": 0, "amount_differs": 0, "missing_on_b": 0, "missing_on_a": 0,
              "ref_written_differently": 0, "split_payment_candidate": 0}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1

    total_a = sum((r["amount"] for r in left), Decimal("0"))
    total_b = sum((r["amount"] for r in right), Decimal("0"))
    report = {
        "counts": counts,
        "findings": findings,
        "totals": {"rows_a": len(left), "rows_b": len(right),
                   "total_a": money(total_a), "total_b": money(total_b),
                   "total_difference": money(total_a - total_b)},
        "labels": {"a": label_a, "b": label_b},
        "date_style": {"a": date_style_a, "b": date_style_b},
    }
    report["summary"] = summarise(report)
    return report


def summarise(report: dict) -> str:
    """One paragraph a bookkeeper can read out loud. Never says who is right."""
    c = report["counts"]
    t = report["totals"]
    a = report["labels"]["a"]
    b = report["labels"]["b"]
    def n_of(count, one, many):
        return f"{count} {one}" if count == 1 else f"{count} {many}"

    bits = [f"We compared {t['rows_a']} rows from {a} with {t['rows_b']} rows from {b}."]
    if c["matched"]:
        bits.append(n_of(c["matched"], "row agrees", "rows agree") + " exactly.")
    if c["amount_differs"]:
        bits.append(n_of(c["amount_differs"], "row uses", "rows use")
                    + " the same invoice reference but a different amount.")
    if c["ref_written_differently"]:
        bits.append(n_of(c["ref_written_differently"], "row looks", "rows look")
                    + " like the same invoice with the reference typed a different way.")
    if c["split_payment_candidate"]:
        bits.append(n_of(c["split_payment_candidate"], "row on one list adds",
                         "rows on one list add")
                    + " up to a single row on the other, which often means the invoice was "
                      "paid or raised in parts.")
    if c["missing_on_b"]:
        bits.append(n_of(c["missing_on_b"], "invoice is", "invoices are")
                    + f" only on the list from {a}.")
    if c["missing_on_a"]:
        bits.append(n_of(c["missing_on_a"], "invoice is", "invoices are")
                    + f" only on the list from {b}.")
    bits.append(f"The two lists add up to {t['total_a']} and {t['total_b']}, a gap of {t['total_difference']}.")
    for side, style in (("a", report["date_style"]["a"]), ("b", report["date_style"]["b"])):
        if style.startswith("month/day (we could not tell)"):
            who = a if side == "a" else b
            bits.append(f"We read the dates on the list from {who} as month first, then day, because the list did not make it clear.")
    bits.append("We do not say which side is right. Take the rows above to the other business and agree them together.")
    return " ".join(bits)
