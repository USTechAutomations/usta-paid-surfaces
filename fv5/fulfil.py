#!/usr/bin/env python3
"""Build the paid file for every buyer who has paid and not yet been served.

For each fv5 family this:
  1. finds its Stripe payment link;
  2. reads which of that link's paid checkouts it has already handled (a
     per-family log that carries a fingerprint, an amount and a date -- never an
     email);
  3. for each new paid checkout, asks the family's own `fulfil(session)` for the
     file's HTML and writes it to the buyer's private address;
  4. when run live and anything was written, hands off to fv5/publish.py to push
     the new pages out.

Two rules the batch never breaks:
  * One family's fulfil() blowing up must not stop the others. An exception is
    written down as an `error` outcome for that one checkout and the batch keeps
    going.
  * Two copies of this job must never run at once, or they would both try to
    write the same pages. A lock file stops the second one.

Default is a DRY RUN: it says what it would write and touches nothing. `--live`
does the writing and the publish. Run the live job with the python that has the
Stripe library:
  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" fv5/fulfil.py --live
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import ppp  # noqa: E402
import stripe_read  # noqa: E402
from mint_feed_links import _read_key, _redact  # noqa: E402

FAMILIES_DIR = FV5 / "families"
CATALOG = ROOT / "catalog.json"
STATE = Path.home() / ".hermes" / "state" / "fv5"
LOCK = STATE / "fulfil.lock"
LINKS_CACHE = STATE / "links.json"


# --------------------------------------------------------------- discovery
def discover_families(families_dir: Path) -> list[tuple[str, object]]:
    """(family id, imported module) for every fv5/families/<id>/fulfil.py."""
    out: list[tuple[str, object]] = []
    if not families_dir.is_dir():
        return out
    for child in sorted(families_dir.iterdir()):
        mod_path = child / "fulfil.py"
        if not mod_path.is_file():
            continue
        out.append((child.name, _import_module(child.name, mod_path)))
    return out


def _import_module(family_id: str, path: Path):
    name = "fv5_family_" + family_id.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    # Families built against the family contract (COMMON-FAMILY.md) may omit the
    # three module constants; fill sensible defaults so both shapes plug in.
    if not hasattr(module, "LINK_ID_ENV_OR_CATALOG"):
        module.LINK_ID_ENV_OR_CATALOG = family_id
    if not hasattr(module, "PRODUCT_NAME"):
        module.PRODUCT_NAME = family_id.replace("-", " ")
    if not hasattr(module, "ETA_MINUTES"):
        module.ETA_MINUTES = 15
    return module


# ------------------------------------------------------------ session view
class SessionView(dict):
    """A paid checkout in BOTH shapes a family may expect.

    The scaffold's own families read `session.custom_fields` as a dict of
    answers; families built to the family contract read a Stripe-shaped
    session (`session["custom_fields"]` list, `session["metadata"]["private_slug"]`).
    This object answers to both: attribute access and item access.
    """

    def __init__(self, s):
        answers = dict(getattr(s, "custom_fields", {}) or {})
        slug = ppp.private_slug(s.session_id)
        super().__init__(
            id=s.session_id, session_id=s.session_id, created=s.created,
            amount_total=s.amount_total, currency=s.currency,
            custom_fields=[{"key": k, "type": "text", "text": {"value": v},
                            "dropdown": {"value": v}} for k, v in answers.items()],
            answers=answers, customer_details={"email": None},
            email_hash=getattr(s, "email_hash", ""), link_id=getattr(s, "link_id", ""),
            metadata={"private_slug": slug, "fv5_family": ""},
        )

    def __getattr__(self, name):
        if name == "custom_fields":       # scaffold shape: dict of answers
            return self["answers"]
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _apply_state_update(state_dir: Path, family_id: str, update: dict, slug: str,
                        created: int) -> None:
    """Persist what a family asked to remember about this sale (live only).

    `{"watch": {...}}`   -> appended to <family>/watches.jsonl
    `{"featured": {...}}` -> appended to the list in <family>/featured.json
    anything else        -> appended to <family>/state_updates.jsonl
    """
    fam_dir = state_dir / family_id
    fam_dir.mkdir(parents=True, exist_ok=True)
    stamp = {"slug": slug, "created": created}
    for kind, payload in (update or {}).items():
        row = dict(payload or {})
        row.update(stamp)
        if kind == "watch":
            with (fam_dir / "watches.jsonl").open("a") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        elif kind == "featured":
            p = fam_dir / "featured.json"
            try:
                cur = json.loads(p.read_text()) if p.is_file() else []
            except Exception:  # noqa: BLE001
                cur = []
            if not isinstance(cur, list):
                cur = []
            cur.append(row)
            p.write_text(json.dumps(cur, indent=1, sort_keys=True))
        else:
            with (fam_dir / "state_updates.jsonl").open("a") as fh:
                fh.write(json.dumps({"kind": kind, **row}, sort_keys=True) + "\n")


def _normalise_result(result):
    """Family fulfil() may return HTML (str), None, or a dict with html/state_update."""
    if result is None:
        return None, None
    if isinstance(result, str):
        return result, None
    if isinstance(result, dict):
        html = result.get("html")
        if not isinstance(html, str) or not html.strip():
            return None, None
        return html, result.get("state_update")
    raise TypeError(f"fulfil() returned {type(result).__name__}, expected str, None or dict")


# ------------------------------------------------------------ link lookup
def _catalog_checkout_url(catalog: dict, family_id: str) -> str | None:
    for fam in catalog.get("families", []):
        if fam.get("id") == family_id:
            return ((fam.get("checkout") or {}).get("url"))
    return None


def _url_to_link_id(url: str, api_key: str, cache_path: Path) -> str:
    """Map a buy.stripe.com URL to its payment-link id, caching the whole map.

    The map is read from Stripe at most once and then kept on disk, so a family
    added later does not force a fresh listing every run.
    """
    cache = {}
    if cache_path.is_file():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    if url in cache:
        return cache[url]
    starting_after = None
    while True:
        status, links = stripe_read.list_payment_links(
            limit=100, api_key=api_key, starting_after=starting_after)
        for link in links:
            if link.get("url"):
                cache[link["url"]] = link["id"]
        if url in cache or not links:
            break
        starting_after = links[-1].get("id")
        if len(links) < 100:
            break
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    if url not in cache:
        raise RuntimeError(f"no Stripe payment link matches the catalog URL for this family")
    return cache[url]


def _held_reason(catalog: dict, family_id: str) -> str | None:
    """Why this family has nothing to deliver from our pages, or None.

    No catalog row means the family is parked off the site; a HOLD row is
    deliberately not on sale yet; EXTERNAL is billed elsewhere (Apify Store)."""
    row = next((f for f in catalog.get("families", []) if f.get("id") == family_id), None)
    if row is None:
        return "no catalog row (parked)"
    status = (row.get("checkout") or {}).get("status", "")
    if status in ("HOLD", "EXTERNAL"):
        return f"checkout status {status}"
    return None


def make_link_resolver(catalog: dict, cache_path: Path = LINKS_CACHE, api_key=None):
    """Turn a family's LINK_ID_ENV_OR_CATALOG into a real Stripe link id.

    If the value names an environment variable that is set, that variable holds
    the link id directly (handy for tests and one-offs). Otherwise the value is
    a catalog family id, and the id is resolved from that family's checkout URL.
    """
    def resolve(spec: str) -> str:
        if spec in os.environ:
            return os.environ[spec]
        url = _catalog_checkout_url(catalog, spec)
        if not url or not str(url).startswith("https://"):
            raise RuntimeError(f"{spec}: no armed checkout URL in the catalog to resolve")
        return _url_to_link_id(url, api_key or _read_key(), cache_path)
    return resolve


def default_session_source(link_id: str, since_ts: int):
    return stripe_read.paid_sessions(link_id, since_ts)


# --------------------------------------------------------------- state log
def load_state(sess_path: Path) -> tuple[set[str], int]:
    """(slugs already handled, newest created time seen) from a family's log."""
    handled: set[str] = set()
    watermark = 0
    if not sess_path.is_file():
        return handled, watermark
    for line in sess_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("slug"):
            handled.add(row["slug"])
        watermark = max(watermark, int(row.get("created", 0) or 0))
    return handled, watermark


def append_row(sess_path: Path, row: dict) -> None:
    sess_path.parent.mkdir(parents=True, exist_ok=True)
    with sess_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------- one family
def process_family(family_id: str, module, *, root: Path, state_dir: Path,
                   live: bool, session_source, link_resolver) -> dict:
    """Handle every new paid checkout for one family. Never raises for a buyer.

    Returns a summary: how many were written, skipped, errored or already done,
    plus a per-checkout list of (slug, outcome). Side effects (writing the page,
    appending to the log) happen only when `live` is True; a dry run computes the
    same outcomes and writes nothing.
    """
    summary = {"family": family_id, "written": 0, "skipped": 0, "errors": 0,
               "already": 0, "outcomes": []}
    sess_path = state_dir / family_id / "sessions.jsonl"
    handled, watermark = load_state(sess_path)

    try:
        link_id = link_resolver(module.LINK_ID_ENV_OR_CATALOG)
        sessions = session_source(link_id, watermark)
    except Exception as exc:  # noqa: BLE001 -- one family's link problem is not fatal
        summary["errors"] += 1
        summary["outcomes"].append(("-", f"error resolving link: {_redact(exc)}"))
        return summary

    for s in sessions:
        slug = ppp.private_slug(s.session_id)
        if slug in handled:
            summary["already"] += 1
            continue
        try:
            html, state_update = _normalise_result(module.fulfil(SessionView(s)))
        except Exception as exc:  # noqa: BLE001 -- never crash the batch on one buyer
            outcome = f"error: {_redact(exc)}"
            summary["errors"] += 1
            summary["outcomes"].append((slug, outcome))
            if live:
                append_row(sess_path, {"slug": slug, "created": s.created,
                                       "amount": s.amount_total, "outcome": outcome})
            continue
        if html is None:
            summary["skipped"] += 1
            summary["outcomes"].append((slug, "skipped (nothing to deliver)"))
            if live:
                append_row(sess_path, {"slug": slug, "created": s.created,
                                       "amount": s.amount_total, "outcome": "skipped"})
            continue
        summary["written"] += 1
        summary["outcomes"].append((slug, "written"))
        if live:
            ppp.write_private_page(root, family_id, s.session_id, html, s.created)
            if state_update:
                _apply_state_update(state_dir, family_id, state_update, slug, s.created)
            append_row(sess_path, {"slug": slug, "created": s.created,
                                   "amount": s.amount_total, "outcome": "written"})
    return summary


# --------------------------------------------------------------- publish hop
def _run_publish() -> int:
    import subprocess
    return subprocess.run([sys.executable, str(FV5 / "publish.py"), "--live"]).returncode


# ------------------------------------------------------------------- driver
def run(*, root: Path, state_dir: Path, families_dir: Path, live: bool,
        only: str | None = None, session_source=None, link_resolver=None,
        do_publish: bool = True) -> int:
    """Fulfil across families. Callable directly by the selftest with fakes."""
    fams = discover_families(families_dir)
    if only:
        fams = [(fid, m) for fid, m in fams if fid == only]
    if not fams:
        print("0 fv5 families to fulfil")
        return 0

    catalog = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.is_file() else {}
    if session_source is None:
        session_source = default_session_source
    if link_resolver is None:
        link_resolver = make_link_resolver(catalog)

    total_written = 0
    for family_id, module in fams:
        held = _held_reason(catalog, family_id)
        if held:
            print(f"{family_id}: held ({held}); nothing to deliver")
            continue
        summary = process_family(family_id, module, root=root, state_dir=state_dir,
                                 live=live, session_source=session_source,
                                 link_resolver=link_resolver)
        total_written += summary["written"]
        verb = "wrote" if live else "would write"
        print(f"{family_id}: {verb} {summary['written']}, skipped {summary['skipped']}, "
              f"errors {summary['errors']}, already done {summary['already']}")
        for slug, outcome in summary["outcomes"]:
            print(f"    {slug[:20]:20} {outcome}")

    if total_written and live and do_publish:
        print(f"\n{total_written} page(s) written; running fv5/publish.py --live")
        return _run_publish()
    if total_written and not live:
        print(f"\ndry run: {total_written} page(s) would be written. Re-run with --live.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--family", help="only this family id")
    ap.add_argument("--live", action="store_true", help="write pages and publish (default: dry run)")
    args = ap.parse_args()

    STATE.mkdir(parents=True, exist_ok=True)
    import fcntl
    with LOCK.open("w") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another fv5/fulfil.py run holds the lock; exiting without doing anything")
            return 0
        lock_fh.write(f"{os.getpid()} {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        lock_fh.flush()
        return run(root=ROOT, state_dir=STATE, families_dir=FAMILIES_DIR,
                   live=args.live, only=args.family)


if __name__ == "__main__":
    raise SystemExit(main())
