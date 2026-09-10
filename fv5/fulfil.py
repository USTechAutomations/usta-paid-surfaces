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
sys.path.insert(0, str(ROOT))  # so the private-delivery signer can import loops.*

import ppp  # noqa: E402
import private_delivery as pd  # noqa: E402  (fv5/lib/private_delivery.py)
import stripe_read  # noqa: E402
from state_root import STATE_ROOT  # noqa: E402
from mint_feed_links import _read_key, _redact  # noqa: E402

FAMILIES_DIR = FV5 / "families"
CATALOG = ROOT / "catalog.json"
STATE = STATE_ROOT
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


def _read_rows(path: Path) -> list[dict]:
    if path.is_symlink(): raise ValueError('state symlink refused')
    if not path.exists(): return []
    rows=[json.loads(line) for line in pd.read_private(path).splitlines() if line.strip()]
    if any(not isinstance(row,dict) for row in rows): raise ValueError('invalid state row')
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    pd.atomic_bytes(path, ''.join(json.dumps(row,allow_nan=False)+'\n' for row in rows).encode())


def _apply_state_update(state_dir: Path, family_id: str, update: dict, slug: str,
                        created: int) -> None:
    """Atomic per-kind updates under the caller's process lock; retry is harmless."""
    if not isinstance(update,dict): raise ValueError('invalid state update')
    fam_dir=state_dir/family_id
    pd.secure_dir(fam_dir)
    for kind,payload in update.items():
        if not isinstance(payload,dict): raise ValueError('invalid update payload')
        row=dict(payload,slug=slug,created=created)
        if kind=='featured':
            path=fam_dir/'featured.json'
            cur=json.loads(pd.read_private(path)) if path.exists() or path.is_symlink() else []
            if not isinstance(cur,list) or any(not isinstance(r,dict) for r in cur): raise ValueError('invalid featured state')
            if any(r.get('slug')==slug for r in cur): continue
            pd.atomic_json(path,cur+[row])
        else:
            path=fam_dir/('watches.jsonl' if kind=='watch' else 'state_updates.jsonl')
            cur=_read_rows(path)
            if any(r.get('slug')==slug and (kind=='watch' or r.get('kind')==kind) for r in cur): continue
            if kind!='watch': row={'kind':kind,**row}
            _write_rows(path,cur+[row])


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
# Outcomes that mean a sale needs no more work. Everything else (an error, a
# retryable error, a bare 'pending', or a legacy 'written' that was never proved
# delivered) is UNRESOLVED and must be reprocessed on the next run.
TERMINAL_OUTCOMES = frozenset({"delivered", "skipped"})


def load_state(sess_path: Path) -> tuple[set[str], int]:
    """(slugs that need no more work, safe lower-bound created time).

    The last row wins per slug, so a sale that errored and later delivered is
    read as delivered. The watermark is a lower bound for the Stripe read: it is
    never advanced past the earliest UNRESOLVED sale, so a transient failure is
    always re-fetched and retried instead of being skipped forever.
    """
    latest: dict[str, tuple[int, str]] = {}
    if not sess_path.is_file():
        return set(), 0
    for row in _read_rows(sess_path):
        slug = row.get("slug")
        if not isinstance(slug,str) or not slug or type(row.get("created")) is not int or row["created"]<0:
            raise ValueError("invalid session state")
        latest[slug] = (row["created"], row.get("outcome", ""))

    handled = {slug for slug, (_c, outcome) in latest.items() if outcome in TERMINAL_OUTCOMES}
    terminal_created = [c for slug, (c, o) in latest.items() if o in TERMINAL_OUTCOMES]
    unresolved_created = [c for slug, (c, o) in latest.items() if o not in TERMINAL_OUTCOMES]
    if unresolved_created:
        # Hold the lower bound just below the oldest unresolved sale so it is
        # fetched again. Delivered sales past that point are filtered by `handled`.
        watermark = max(0, min(unresolved_created) - 1)
    else:
        watermark = max(terminal_created) if terminal_created else 0
    return handled, watermark


def append_row(sess_path: Path, row: dict) -> None:
    rows=_read_rows(sess_path)
    row=dict(row)
    if "amount" in row and any(r.get("slug")==row.get("slug") and "amount" in r for r in rows):
        row.pop("amount")
    if rows and rows[-1]==row: return
    _write_rows(sess_path,rows+[row])


# --------------------------------------------------------------- one family
def process_family(family_id: str, module, *, root: Path, state_dir: Path,
                   live: bool, session_source, link_resolver,
                   spool=None, uploader=None) -> dict:
    """Resume durable output before scanning Stripe; never rerender spooled bytes."""
    summary={'family':family_id,'delivered':0,'built':0,'pending':0,'skipped':0,'errors':0,'already':0,'outcomes':[]}
    sess_path=state_dir/family_id/'sessions.jsonl'
    def failure(exc):
        summary['errors']+=1
        summary['outcomes'].append(('-', 'error '+type(exc).__name__))
    def finish(record):
        if record['finalized']:
            summary['already']+=1;return
        if record['state']!=pd.DELIVERED:
            if uploader is None:
                summary['pending']+=1;return
            outcome=pd.deliver(spool,record,uploader)['outcome']
            if outcome!=pd.DELIVERED:
                summary['pending']+=1;return
            record=spool.load(record['id'])
        slug=record['session_hash'][:20]
        if not record['state_applied']:
            _apply_state_update(state_dir,family_id,record['state_update'],slug,record['ts'])
            record['state_applied']=True;spool.save(record)
        append_row(sess_path,{'slug':slug,'created':record['ts'],'outcome':'delivered'})
        record['finalized']=True;spool.save(record)
        summary['delivered']+=1
    try:
        if live:
            spool=spool or pd.PrivateSpool(state_dir)
            for record in spool.records():
                if record['family']==family_id and not record['finalized']:
                    try:finish(record)
                    except Exception as exc:failure(exc)
        handled,watermark=load_state(sess_path)
        sessions=list(session_source(link_resolver(module.LINK_ID_ENV_OR_CATALOG),watermark))
    except Exception as exc:
        failure(exc);return summary
    product_name=getattr(module,'PRODUCT_NAME',family_id.replace('-',' '))
    for session in sessions:
        slug=ppp.private_slug(session.session_id)
        if slug in handled:
            summary['already']+=1;continue
        try:
            rec_id=pd.doc_id(family_id,pd.session_hash(session.session_id))
            existing=spool.load(rec_id) if live else None
            if existing:
                # The recovery sweep already attempted this record once this run.
                continue
            if live:
                append_row(sess_path,{'slug':slug,'created':session.created,'amount':session.amount_total,'outcome':'pending'})
            body,update=_normalise_result(module.fulfil(SessionView(session)))
            if body is None:
                summary['skipped']+=1
                if live:append_row(sess_path,{'slug':slug,'created':session.created,'outcome':'skipped'})
                continue
            wrapped=ppp.wrap_private_page(family_id,product_name,body,session.created)
            if live:
                record=spool.spool(family_id,session.session_id,wrapped,session.created,state_update=update)
                summary['built']+=1
                finish(record)
            else:summary['built']+=1
        except Exception as exc:
            failure(exc)
            if live:
                try:append_row(sess_path,{'slug':slug,'created':session.created,'outcome':'retryable_error'})
                except Exception as state_exc:failure(state_exc)
    return summary


# ------------------------------------------------------------------- driver
def run(*, root: Path, state_dir: Path, families_dir: Path, live: bool,
        only: str | None = None, session_source=None, link_resolver=None,
        do_publish: bool = True, spool=None, uploader=None) -> int:
    """Fulfil across families. Callable directly by the selftest with fakes.

    Exit code:
      * a successful dry run returns 0; errors remain nonzero;
      * a live run that delivers everything returns 0;
      * a live run that leaves ANY sale unresolved (a failed delivery still in
        the spool) returns non-zero, and keeps returning non-zero on later runs
        until the sale is delivered — a failed publication is never reported as
        success;
      * `do_publish=False` builds and spools but does NOT deliver, and returns 0:
        a deliberate build step, told apart from a failed live publish by the
        fact that no delivery was attempted.
    """
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

    # A live run that means to deliver signs uploads with the shared loops secret.
    if live and spool is None:
        spool = pd.PrivateSpool(state_dir)
    if live and do_publish and uploader is None:
        uploader = pd.SignedUploader()

    total_built = total_delivered = total_pending = total_errors = 0
    for family_id, module in fams:
        held = _held_reason(catalog, family_id)
        if held:
            print(f"{family_id}: held ({held}); nothing to deliver")
            continue
        summary = process_family(family_id, module, root=root, state_dir=state_dir,
                                 live=live, session_source=session_source,
                                 link_resolver=link_resolver,
                                 spool=spool, uploader=uploader if do_publish else None)
        total_built += summary["built"]
        total_delivered += summary["delivered"]
        total_pending += summary["pending"]
        total_errors += summary["errors"]
        if live:
            print(f"{family_id}: delivered {summary['delivered']}, pending {summary['pending']}, "
                  f"skipped {summary['skipped']}, errors {summary['errors']}, "
                  f"already done {summary['already']}")
        else:
            print(f"{family_id}: would build {summary['built']}, skipped {summary['skipped']}, "
                  f"errors {summary['errors']}, already done {summary['already']}")
        for slug, outcome in summary["outcomes"]:
            print(f"    {slug[:20]:20} {outcome}")

    if not live:
        if total_built:
            print(f"\ndry run: {total_built} file(s) would be built. Re-run with --live.")
        return int(total_errors>0)

    if not do_publish:
        print(f"\nbuild-only live run: {total_built} file(s) spooled, none delivered.")
        return int(total_errors>0)

    # A failed publication is anything still sitting in the spool undelivered.
    remaining = len([r for r in spool.records() if not r["finalized"]]) if spool is not None else total_pending
    if total_errors:
        print(f"\n{total_errors} processing error(s); retry required.")
        return 1
    if remaining:
        print(f"\n{total_delivered} delivered; {remaining} delivery(ies) still pending — "
              f"returning non-zero so this is retried.")
        return 1
    print(f"\n{total_delivered} delivered; nothing pending.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--family", help="only this family id")
    ap.add_argument("--live", action="store_true", help="build and privately deliver (default: dry run)")
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
