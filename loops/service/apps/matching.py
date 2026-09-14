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
from collections import deque
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

# Amount text bounds. 100-digit strings and scientific forms must not reach
# Decimal.quantize (that path used to raise InvalidOperation).
_MAX_AMOUNT_CHARS = 64
_MAX_INT_DIGITS = 16
_MAX_FRAC_DIGITS = 6
_CENTS = Decimal("0.01")
_AMOUNT_CODES = ("USD", "EUR", "GBP")
_AMOUNT_SYMBOLS = "$€£"
_SPACE_CHARS = ("\u00a0", "\u202f", "\u2009")


# ---------------------------------------------------------------- amounts ---

def _unwrap_parens(s: str):
    """Return the inner text if s is a single wrapping '(...)', else None."""
    if len(s) < 2 or s[0] != "(" or s[-1] != ")":
        return None
    if s.count("(") != 1 or s.count(")") != 1:
        return None
    inner = s[1:-1].strip()
    if not inner:
        return None
    return inner


def _peel_code(s: str, trailing: bool):
    """Take one supported uppercase currency code, or None."""
    for code in _AMOUNT_CODES:
        if trailing:
            if not s.endswith(code):
                continue
            before = s[:-len(code)]
            if before and before[-1].isalpha():
                continue
            return before.rstrip(), code
        if not s.startswith(code):
            continue
        after = s[len(code):]
        if after and after[0].isalpha():
            continue
        return after.lstrip(), code
    return None


def _peel_wrappers(s: str):
    """Strip currency and a single sign. Return (number_text, negative) or None.

    Letters that are not a leading/trailing USD/EUR/GBP code are left in the
    number text so the caller can refuse them. Never strip internal letters.
    """
    paren = False
    unwrapped = _unwrap_parens(s)
    if unwrapped is not None:
        paren = True
        s = unwrapped

    leading_code = trailing_code = None
    leading_sym = trailing_sym = None
    leading_sign = None
    trailing_minus = False

    progressed = True
    while s and progressed:
        progressed = False
        taken = _peel_code(s, trailing=False)
        if taken is not None:
            if leading_code is not None:
                return None
            s, leading_code = taken
            progressed = True
            continue
        if s[0] in _AMOUNT_SYMBOLS:
            if leading_sym is not None:
                return None
            leading_sym = s[0]
            s = s[1:].lstrip()
            progressed = True
            continue
        if s[0] in "+-":
            if leading_sign is not None:
                return None
            leading_sign = s[0]
            s = s[1:].lstrip()
            progressed = True
            continue

    progressed = True
    while s and progressed:
        progressed = False
        taken = _peel_code(s, trailing=True)
        if taken is not None:
            if trailing_code is not None:
                return None
            s, trailing_code = taken
            progressed = True
            continue
        if s[-1] in _AMOUNT_SYMBOLS:
            if trailing_sym is not None:
                return None
            trailing_sym = s[-1]
            s = s[:-1].rstrip()
            progressed = True
            continue
        if s[-1] == "-":
            if trailing_minus or leading_sign is not None:
                return None
            trailing_minus = True
            s = s[:-1].rstrip()
            progressed = True
            continue
        if s[-1] == "+":
            return None

    inner = _unwrap_parens(s) if s else None
    if inner is not None:
        if paren or leading_sign is not None or trailing_minus:
            return None
        paren = True
        s = inner
        if s[0] in "+-" or s[-1] in "+-":
            return None

    if not s or "(" in s or ")" in s:
        return None
    if leading_code and trailing_code:
        return None
    if leading_sym and trailing_sym:
        return None
    code, symbol = leading_code or trailing_code, leading_sym or trailing_sym
    if code and symbol and {"USD": "$", "EUR": "€", "GBP": "£"}[code] != symbol:
        return None

    sign_count = 0
    negative = False
    if paren:
        sign_count += 1
        negative = True
    if leading_sign == "-":
        sign_count += 1
        negative = True
    elif leading_sign == "+":
        sign_count += 1
    if trailing_minus:
        sign_count += 1
        negative = True
    if sign_count > 1:
        return None
    return s, negative


def _groups_ok(int_part: str, sep: str) -> bool:
    """True when thousands groups are regular (first 1-3 digits, rest 3)."""
    if sep not in int_part:
        return bool(int_part) and int_part.isdigit()
    parts = int_part.split(sep)
    if len(parts) < 2 or any(p == "" for p in parts):
        return False
    if not parts[0].isdigit() or not 1 <= len(parts[0]) <= 3:
        return False
    return all(p.isdigit() and len(p) == 3 for p in parts[1:])


def _collapse_grouping_spaces(s: str):
    """Treat regular space groups as thousands. Refuse irregular spaces."""
    for sp in _SPACE_CHARS:
        s = s.replace(sp, " ")
    if "  " in s:
        return None
    s = s.strip()
    if " " not in s:
        return s
    parts = s.split(" ")
    last = parts[-1]
    dec_sep = None
    frac = None
    if "," in last and "." in last:
        return None
    if last.count(",") == 1 and "." not in last:
        dec_sep = ","
    elif last.count(".") == 1 and "," not in last:
        dec_sep = "."
    elif "," in last or "." in last:
        return None
    if dec_sep is not None:
        int_last, frac = last.rsplit(dec_sep, 1)
        if not frac.isdigit():
            return None
        int_parts = parts[:-1] + [int_last]
    else:
        int_parts = parts
    if any(not p.isdigit() for p in int_parts):
        return None
    if not 1 <= len(int_parts[0]) <= 3:
        return None
    if any(len(p) != 3 for p in int_parts[1:]):
        return None
    joined = "".join(int_parts)
    if dec_sep is None:
        return joined
    return joined + dec_sep + frac


def _canonical_number(body: str):
    """Return a Decimal-safe 'digits[.frac]' string, or None if malformed."""
    if not body or body[0] in ",." or body[-1] in ",.":
        return None
    if any(tok in body for tok in (",,", "..", ",.", ".,")):
        return None
    if any(ch not in "0123456789,." for ch in body):
        return None

    n_comma = body.count(",")
    n_dot = body.count(".")
    int_digits = None
    frac = ""

    if n_comma and n_dot:
        if body.rfind(",") > body.rfind("."):
            thousands, decimal = ".", ","
        else:
            thousands, decimal = ",", "."
        left, right = body.rsplit(decimal, 1)
        if thousands in right or not _groups_ok(left, thousands):
            return None
        int_digits = left.replace(thousands, "")
        frac = right
    elif n_comma:
        if _groups_ok(body, ","):
            int_digits = body.replace(",", "")
        elif n_comma == 1:
            left, right = body.split(",")
            if left.isdigit() and right.isdigit() and 1 <= len(right) <= _MAX_FRAC_DIGITS:
                int_digits, frac = left, right
            else:
                return None
        else:
            return None
    elif n_dot:
        if n_dot == 1:
            left, right = body.split(".")
            if left.isdigit() and right.isdigit() and 1 <= len(right) <= _MAX_FRAC_DIGITS:
                int_digits, frac = left, right
            else:
                return None
        elif _groups_ok(body, "."):
            int_digits = body.replace(".", "")
        else:
            return None
    else:
        if not body.isdigit():
            return None
        int_digits = body

    if not int_digits or not int_digits.isdigit():
        return None
    if frac and not frac.isdigit():
        return None
    if len(int_digits) > _MAX_INT_DIGITS or len(frac) > _MAX_FRAC_DIGITS:
        return None
    if frac:
        return int_digits + "." + frac
    return int_digits


def parse_amount(raw: str):
    """Turn pasted amount text into an exact Decimal cents value, or None.

    Only str is parsed. None, bool, float, int and other types return None.
    Strings longer than 64 characters return None. The function does not raise.

    Supported grammar (optional pieces in []):
      amount := [ws] ( '(' [ws] core [ws] ')' | core ) [ws]
      core   := [code] [ws] [symbol] [ws] [sign] [ws] [symbol] [ws] number
                [ws] [symbol] [ws] [code] [ws] [trailing-minus]
      code   := 'USD' | 'EUR' | 'GBP'   (uppercase; at most one; lead or trail)
      symbol := '$' | '€' | '£'         (at most one)
      sign   := '+' | '-'               (leading; not combined with parentheses)
      trailing-minus := '-'             (not combined with any other sign)
      number := us | european | plain | space-grouped
      plain  := digits [ '.' digits ]
      us     := digits{1,3} (',' digits{3})+ [ '.' digits ]
      european := digits{1,3} ('.' digits{3})+ [ ',' digits ]
                | digits ',' digits{1,6}     when not a US thousands group
      space-grouped := digits{1,3} (' ' digits{3})+ [ ('.'|',') digits ]

    A number has at most 16 integer digits and 6 fractional digits. The result
    is Decimal quantized to 0.01. Genuine zero (0, 0.00, 0,00) is 0.00.

    Refused (return None, never a different number): exponent forms (1e3,
    1E-2), internal letters (1O0), NaN/Inf, repeated or conflicting separators
    (1,,234 or 1.234,56.7), conflicting signs (+-45, (45.00)-, (-45.00)),
    unsupported letters, huge digit strings. Letters are not stripped.
    """
    try:
        return _parse_amount(raw)
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return None


def _parse_amount(raw):
    if not isinstance(raw, str):
        return None
    if len(raw) > _MAX_AMOUNT_CHARS:
        return None
    s = raw.strip()
    if not s:
        return None
    peeled = _peel_wrappers(s)
    if peeled is None:
        return None
    body, negative = peeled
    collapsed = _collapse_grouping_spaces(body)
    if collapsed is None:
        return None
    canon = _canonical_number(collapsed)
    if canon is None:
        return None
    value = Decimal(canon)
    if not value.is_finite():
        return None
    if negative:
        value = -value
    out = value.quantize(_CENTS)
    if not out.is_finite():
        return None
    return out


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
    # Check the original last cell too: lowercasing would hide uppercase USD/EUR/GBP.
    if parse_amount(low[-1]) is not None or parse_amount(cols[-1].strip()) is not None:
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
        # Repeated invoice references need exact amount matches before line-order
        # pairing; changing export order must not invent amount discrepancies.
        ordered_a = sorted(ga[ref], key=lambda r: r["line"])
        ordered_b = sorted(gb[ref], key=lambda r: r["line"])
        by_amount = {}
        for rb in ordered_b:
            by_amount.setdefault(rb["amount"], deque()).append(rb)
        pairs, remaining_a, matched_b = [], [], set()
        for ra in ordered_a:
            candidates = by_amount.get(ra["amount"])
            if candidates:
                rb = candidates.popleft()
                pairs.append((ra, rb)); matched_b.add(id(rb))
            else:
                remaining_a.append(ra)
        pairs.extend(zip(remaining_a, [rb for rb in ordered_b if id(rb) not in matched_b]))
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
