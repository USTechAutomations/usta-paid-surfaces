"""Operator-only report preparation from the existing payment watcher's records.
No network, payment mutations, mailbox reading/sending, or raw-log deletion.
Reports cannot claim delivery or mailbox deletion. Not a public upload endpoint.
"""
import argparse
import ctypes
import tempfile
import shutil
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from datetime import datetime,timezone
from processor import analyze,render_csv,render_report

FAMILY='machine-visitor-ledger'
SOURCE='stripe-feeds-person-email'

def private_dir(path):
    path=Path(path)
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077:
        raise ValueError('report directory must be private and operator-owned')
    return path

def read_order(db,packets,session):
    if not re.fullmatch(r'cs_[A-Za-z0-9_]{1,180}',session):raise ValueError('invalid order reference')
    rootfd=os.open(packets,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        sessionfd=os.open(session,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=rootfd)
        try:
            fd=os.open('manifest.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=sessionfd)
            with os.fdopen(fd,'rb') as f:
                st=os.fstat(f.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_size>65536:raise ValueError('invalid packet file')
                raw=f.read(65537)
                if len(raw)>65536:raise ValueError('oversized packet')
                packet=json.loads(raw)
        finally:os.close(sessionfd)
    finally:os.close(rootfd)
    if not isinstance(packet,dict):raise ValueError('invalid packet')
    if packet.get('session_id')!=session or packet.get('family')!=FAMILY or packet.get('ledger_source')!=SOURCE:
        raise ValueError('order family or source mismatch')
    # Ledger remains read-only; a packet alone never authorizes report preparation.
    con=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        rows=con.execute('SELECT value_cents,metadata_json FROM revenue_events WHERE source=? AND source_ref=? AND business_id=? AND kind=? AND opportunity_id=?',
                         (SOURCE,packet.get('ledger_source_ref'),FAMILY,'revenue_received',session)).fetchall()
    finally:con.close()
    if len(rows)!=1:raise ValueError('matching recorded payment unavailable')
    amount,raw=rows[0];m=json.loads(raw)
    if m.get('checkout_session')!=session or m.get('family')!=FAMILY or m.get('currency')!='usd' or m.get('livemode') is not True:
        raise ValueError('payment evidence mismatch')
    if not isinstance(amount,int) or amount!=19900 or packet.get('amount_cents')!=amount or packet.get('currency')!='usd':
        raise ValueError('payment amount mismatch')
    return packet

def prepare(db,packets,session,log,output):
    packet=read_order(db,packets,session)
    root=private_dir(output)
    # Commit a complete staging directory; interruption cannot reserve an order.
    dest=root/hashlib.sha256(session.encode()).hexdigest()
    if dest.exists() or dest.is_symlink():raise FileExistsError('order report already exists')
    stage=Path(tempfile.mkdtemp(prefix='.prepare-',dir=root))
    os.chmod(stage,0o700)
    try:
        fd=os.open(log,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):raise ValueError('regular log required')
            result=analyze(stream)
            after=os.fstat(stream.fileno())
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('input changed during processing')
        contents={'report.md':render_report(result),'machines.csv':render_csv(result),'aggregate.json':json.dumps(result,indent=2)+'\n'}
        hashes={name:hashlib.sha256(body.encode()).hexdigest() for name,body in contents.items()}
        manifest={'schema_version':1,'family':FAMILY,'session_id':session,'state':'REPORT_PREPARED_INPUT_RETENTION_PENDING',
                  'created_at':datetime.now(timezone.utc).isoformat(),'artifacts':hashes,'input_sha256':result['input_sha256'],
                  'payment_evidence':'existing watcher packet and read-only revenue_events; no fresh refund/dispute check',
                  'source_log_deleted':False,'raw_processing_copies_created':0,'mailbox_attachment_deletion':'UNKNOWN',
                  'delivered':False,'payment_current':'UNKNOWN','next_action':'Confirm input/mailbox retention cleanup and current payment state; human reviews and sends report using existing draft workflow.'}
        contents['manifest.json']=json.dumps(manifest,indent=2)+'\n'
        for name,body in contents.items():
            fd=os.open(stage/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:f.write(body);f.flush();os.fsync(f.fileno())
        dirfd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        rename=getattr(ctypes.CDLL(None,use_errno=True),'renameat2',None)
        if rename is None:raise OSError('atomic directory commit unavailable')
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(stage),-100,os.fsencode(dest),1):
            err=ctypes.get_errno();raise OSError(err,os.strerror(err))
        dirfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        return dest
    finally:
        # A crash may retain a private aggregate-only stage; it never blocks retry.
        if stage.exists():shutil.rmtree(stage)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('db','packets','session','log','output'):p.add_argument('--'+field,required=True)
    a=p.parse_args()
    try:out=prepare(a.db,a.packets,a.session,a.log,a.output)
    except (OSError,ValueError,sqlite3.Error):print('Preparation refused; no delivery claimed.',file=sys.stderr);return 2
    print(out);return 0
if __name__=='__main__':sys.exit(main())
