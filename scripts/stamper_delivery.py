"""Prepare a private, unsent Stamper delivery from an existing accepted order.

The production entry point never accepts a payment-evidence file. It reads the
existing provider adapter after validating the canonical accepted proposal.
No mailbox, revenue ledger, order mutation, or sending transport is used.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
from email.message import EmailMessage
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

from delivery_binding import DeliveryRefusal, validate

HOME = Path.home()
PROPOSALS = HOME / '.hermes/state/revenue-readiness/outreach/accepted_order_proposals'
PACKAGES = HOME / '.hermes/state/stamper-appendix/private-artifacts'
OUTPUT = HOME / '.hermes/state/stamper-appendix/delivery-drafts'
MAX_BYTES = 8 * 1024 * 1024


def _install_directory(stage: Path, final: Path) -> None:
    """Linux atomic no-replace, including an existing empty directory."""
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, 'renameat2', None)
    if rename is None:
        raise DeliveryRefusal('Atomic private publication unavailable')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(final), 1):
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError('Private delivery already exists')
        raise DeliveryRefusal('Atomic private publication failed')


def private_read(path: Path, limit=MAX_BYTES) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise DeliveryRefusal('Input must be a private regular file')
            data = f.read(limit + 1)
        if len(data) > limit:
            raise DeliveryRefusal('Input exceeds bounded size')
        return data
    except OSError as exc:
        raise DeliveryRefusal('Input unavailable') from exc


def describe_package(package_dir: Path) -> dict:
    """Return machine-computed scope for an unaccepted offer; never alter an order."""
    from delivery_binding import _strict_json_object
    artifact = private_read(package_dir / 'artifact.csv')
    raw = private_read(package_dir / 'metadata.json')
    m = _strict_json_object(raw)
    fields = ['city', 'permit_type', 'work_class', 'filed_date', 'status', 'review_days', 'source_portal']
    if (m.get('family') != 'stamper-appendix'
            or m.get('state') != 'PRIVATE_PREPARED_SCOPE_REVIEW_REQUIRED'
            or m.get('fields') != fields or not isinstance(m.get('historical_work_class'), str)
            or not m['historical_work_class'].strip()
            or type(m.get('artifact_bytes')) is not int or m['artifact_bytes'] != len(artifact)
            or not artifact or m.get('artifact_sha256') != hashlib.sha256(artifact).hexdigest()
            or dt.date.fromisoformat(m.get('as_of')) > dt.datetime.now(dt.timezone.utc).date()):
        raise DeliveryRefusal('Prepared package scope is unavailable or mismatched')
    return {'family': 'stamper-appendix', 'as_of': m['as_of'],
            'artifact_sha256': hashlib.sha256(artifact).hexdigest(),
            'metadata_sha256': hashlib.sha256(raw).hexdigest(),
            'disclosures': {'historical_work_class': m['historical_work_class'], 'fields': fields}}


def observe_payment(reader, link: str, now: dt.datetime) -> dict:
    """Read one complete personal-link purchase and its current capture state."""
    try:
        listed = reader.get('/checkout/sessions', {'payment_link': link, 'status': 'complete', 'limit': 2})
        if listed.get('has_more') is not False or not isinstance(listed.get('data'), list) or len(listed['data']) != 1:
            raise DeliveryRefusal('One unambiguous completed purchase is required')
        s = listed['data'][0]
        sid = s.get('id')
        if not isinstance(sid, str) or not re.fullmatch(r'cs_live_[A-Za-z0-9]+', sid):
            raise DeliveryRefusal('Production checkout identity unavailable')
        # Read current session; list responses alone are not the access decision.
        s = reader.get('/checkout/sessions/' + sid)
        if s.get('id') != sid or s.get('mode') != 'payment' or s.get('payment_link') != link:
            raise DeliveryRefusal('Purchase does not match the one-off order')
        pi = s.get('payment_intent')
        if not isinstance(pi, str) or not re.fullmatch(r'pi_[A-Za-z0-9]+', pi):
            raise DeliveryRefusal('Payment intent unavailable')
        intent = reader.get('/payment_intents/' + pi)
        charge_id = intent.get('latest_charge')
        if intent.get('id') != pi or not isinstance(charge_id, str) or not re.fullmatch(r'ch_[A-Za-z0-9]+', charge_id):
            raise DeliveryRefusal('Capture identity unavailable')
        charge = reader.get('/charges/' + charge_id)
        if (charge.get('id') != charge_id or charge.get('payment_intent') != pi
                or intent.get('livemode') is not True or charge.get('livemode') is not True
                or intent.get('currency') != s.get('currency') or charge.get('currency') != s.get('currency')
                or type(s.get('amount_total')) is not int or s['amount_total'] <= 0
                or type(intent.get('amount_received')) is not int or intent['amount_received'] != s['amount_total']
                or type(charge.get('amount')) is not int or charge['amount'] != s['amount_total']
                or intent.get('customer') != s.get('customer') or charge.get('customer') != s.get('customer')
                or charge.get('captured') is not True):
            raise DeliveryRefusal('Capture does not match the checkout')
        return {'session_id': sid, 'payment_link_id': s.get('payment_link'),
                'buyer_email': (s.get('customer_details') or {}).get('email'),
                'amount_cents': s.get('amount_total'), 'currency': s.get('currency'),
                'livemode': s.get('livemode'), 'status': s.get('status'),
                'payment_status': s.get('payment_status'), 'intent_status': intent.get('status'),
                'charge_paid': charge.get('paid'), 'refunded': charge.get('refunded'),
                'disputed': charge.get('disputed'), 'amount_refunded': charge.get('amount_refunded'),
                'checked_at': now.isoformat()}
    except DeliveryRefusal:
        raise
    except Exception as exc:
        raise DeliveryRefusal('Current payment evidence unavailable') from exc


def compose(binding: dict, artifact: bytes, metadata: bytes) -> bytes:
    msg = EmailMessage()
    msg['From'] = 'operations@ustechautomations.com'
    msg['To'] = binding['buyer_email']
    msg['Subject'] = 'Your San Francisco OTC appendix'
    msg['X-USTA-Delivery-State'] = 'UNSENT-HUMAN-REVIEW-REQUIRED'
    msg.set_content('Your requested appendix is attached, together with its source metadata.\n\n'
                    f"Status observations through: {binding['as_of']}\n"
                    'The metadata describes the scope and limitations of the retained records.\n'
                    'This is a public-record extract, not a stamp or an opinion on safety or compliance.\n\n'
                    f"Order: {binding['proposal_id']}\nArtifact SHA-256: {binding['artifact_sha256']}\n")
    msg.add_attachment(artifact, maintype='text', subtype='csv', filename='stamper-appendix.csv')
    msg.add_attachment(metadata, maintype='application', subtype='json', filename='source-metadata.json')
    # Deterministic MIME bytes make an exact retry auditable.
    msg.set_boundary('usta-' + binding['artifact_sha256'][:40])
    return msg.as_bytes()


def prepare(proposal_path: Path, package_dir: Path, output_root: Path, reader,
            *, now=None, proposal_loader=None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    if proposal_loader is None:
        sys.path.insert(0, str(HOME / 'Claude CLI/lead-outreach'))
        from src.flows.ship_order_reconciliation import _read_minted_proposal
        proposal_loader = _read_minted_proposal
    # Loader is the existing accepted-order validator. No acceptance is created here.
    parsed = proposal_loader(proposal_path)
    if parsed is None:
        raise DeliveryRefusal('An existing accepted, minted order is required')
    proposal = parsed.payload
    artifact = private_read(package_dir / 'artifact.csv')
    metadata = private_read(package_dir / 'metadata.json')
    receipt = observe_payment(reader, parsed.payment_link_id, now)
    binding = validate(proposal, receipt, metadata, artifact, now)
    raw = compose(binding, artifact, metadata)
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_root.is_symlink() or output_root.stat().st_mode & 0o077:
        raise DeliveryRefusal('Output must be a private directory')
    identity = hashlib.sha256((binding['proposal_id'] + '\0' + binding['session_id']).encode()).hexdigest()
    final = output_root / identity
    manifest = {'state': 'UNSENT_HUMAN_REVIEW_REQUIRED', 'sent': False,
                'order': binding['proposal_id'], 'artifact_sha256': binding['artifact_sha256'],
                'draft_sha256': hashlib.sha256(raw).hexdigest(),
                'metadata_sha256': binding['metadata_sha256'],
                'next_action': 'Review the exact order and attachments; recheck payment immediately before human sending.'}
    encoded = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    if final.exists():
        if final.is_symlink() or private_read(final / 'draft.eml') != raw or private_read(final / 'manifest.json') != encoded:
            raise DeliveryRefusal('Existing delivery differs; do not overwrite')
        return {'state': manifest['state'], 'path': str(final), 'created': False, 'sent': False}
    stage = Path(tempfile.mkdtemp(prefix='.prepare-', dir=output_root))
    created = True
    try:
        for name, data in [('draft.eml', raw), ('manifest.json', encoded)]:
            fd = os.open(stage / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            _install_directory(stage, final)
        except FileExistsError:
            if final.is_symlink() or private_read(final / 'draft.eml') != raw or private_read(final / 'manifest.json') != encoded:
                raise DeliveryRefusal('Concurrent delivery differs')
            created = False
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {'state': manifest['state'], 'path': str(final), 'created': created, 'sent': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--describe-scope', action='store_true',
                        help='Print frozen offer.delivery fields for scope review; no order or payment action')
    args = parser.parse_args()
    try:
        # Do not let arbitrary JSON become a production accepted-order source.
        if args.package.is_symlink() or args.package.resolve().parent != PACKAGES.resolve():
            raise DeliveryRefusal('Use the existing private Stamper package directory')
        if args.describe_scope:
            if args.proposal is not None:
                raise DeliveryRefusal('Describe scope does not modify an existing order')
            print(json.dumps({'state': 'SCOPE_FOR_REVIEW_ONLY', 'accepted': False,
                              'offer_delivery': describe_package(args.package)}, indent=2))
            return 0
        if args.proposal is None or args.proposal.is_symlink() or args.proposal.resolve().parent != PROPOSALS.resolve():
            raise DeliveryRefusal('Use the existing canonical accepted-order directory')
        sys.path.insert(0, str(HOME / 'Claude CLI/lead-outreach'))
        from src.flows.ship_order_reconciliation import _read_minted_proposal
        parsed = _read_minted_proposal(args.proposal)
        if parsed is None or not isinstance(parsed.payload.get('offer', {}).get('delivery'), dict):
            raise DeliveryRefusal('Accepted order has no frozen delivery scope')
        sys.path.insert(0, str(HOME / 'code/market-services/stripe-readback'))
        sys.path.insert(0, str(HOME / 'code/usta-paid-surfaces'))
        from common import load_key
        from loops.service.payment_claim import StripeReader
        result = prepare(args.proposal, args.package, OUTPUT, StripeReader(load_key()),
                         proposal_loader=lambda path: parsed)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        # Provider diagnostics and private order data must not reach stdout.
        print(json.dumps({'state': 'REFUSED_OR_UNKNOWN', 'error_type': type(exc).__name__,
                          'sent': False, 'prepared': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
