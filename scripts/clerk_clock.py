#!/usr/bin/env python3
"""Guarded Clerk Clock builder from raw, sealed permit observations.

It derives status-transition days from permit_prediction_snapshots rather than
filtering the dated aggregate sample. It requires a canonical ALLOW_PAID office,
verifies every selected snapshot with the existing snapshot_store helper, runs
the canonical outbound guard, and writes an immutable private pack only when a
requested office/quarter has at least 30 uncensored transitions.
"""
from __future__ import annotations
import csv,datetime as dt,hashlib,importlib,io,json,os,sqlite3,stat,tempfile,sys
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
import manual_artifacts as common
DB=common.DB; RECORD=common.RECORD; GUARD=common.GUARD
sys.path.insert(0, '/home/gmullins/Claude CLI/permits-engine')
EXPECTED_RECORD_SHA=common.EXPECTED_RECORD_SHA; EXPECTED_GUARD_SHA=common.EXPECTED_GUARD_SHA
EXPECTED_SNAPSHOT_STORE_SHA='f07cc5c91d84c5f8f62c646c06cdd222d1263f33ae83a9e54cba8f416e72ef4f'
OFFICES=('austin','montgomery-md','san-francisco')
FIELDS=['board','class','n','median_days','p25','p75','first_date','last_date']
MIN_CLERK_TRANSITIONS=30
class SourceUnknown(common.SourceUnknown):pass
class ScopeUnavailable(common.ScopeUnavailable):pass
class ImmutableArtifactError(common.ImmutableArtifactError):pass

def _percentile(values:list[int],p:float)->float:
 s=sorted(values); k=(len(s)-1)*p; lo=int(k);hi=min(lo+1,len(s)-1)
 return float(s[lo]) if lo==hi else s[lo]+(s[hi]-s[lo])*(k-lo)
def _fmt(v:float)->str:return str(int(round(v))) if abs(v-round(v))<1e-9 else f'{v:.1f}'
def _quarter(day:str)->str:
 try:d=dt.date.fromisoformat(day[:10])
 except ValueError:raise SourceUnknown(f'invalid snapshot date {day!r}')
 return f'{d.year}-Q{(d.month-1)//3+1}'
def _path(root:Path,office:str,quarter:str)->Path:
 return common._package_path(root,'clerk-clock',f'{office}\0{quarter}')
def _snapshot_verifier():
 path=Path('/home/gmullins/Claude CLI/permits-engine/permits_engine/issued_permits/snapshot_store.py')
 raw=common._regular(path);actual=hashlib.sha256(raw).hexdigest()
 if actual!=EXPECTED_SNAPSHOT_STORE_SHA:raise SourceUnknown(f'snapshot_store sha256 {actual} != reviewed {EXPECTED_SNAPSHOT_STORE_SHA}')
 mod=importlib.import_module('permits_engine.issued_permits.snapshot_store')
 return mod.verify_row,actual
def _collapse_daily(values:list[tuple[str,str,str]])->list[tuple[str,str]]:
 """Collapse model versions on one day; conflicting observed statuses are UNKNOWN."""
 days={}
 for day,status,model in values:
  key=day[:10];value=status.strip()
  if key in days and days[key][0]!=value:
   raise SourceUnknown(f'conflicting statuses for permit/date {key}')
  days[key]=(value,model)
 return sorted((day,value) for day,(value,model) in days.items())

def build_clerk_clock(*,office:str,quarter:str,output_root:Path,db:Path=DB,record:Path=RECORD,expected_db_size:int=3291238400,expected_db_mtime_ns:int=0,expected_record_sha256:str=EXPECTED_RECORD_SHA,expected_guard_sha256:str=EXPECTED_GUARD_SHA,min_observations:int=30,complete_fields:bool=False,office_details:dict|None=None)->dict[str,Any]:
 office=common._safe(office,'office').lower();quarter=common._safe(quarter,'quarter').upper()
 if office not in OFFICES:raise ScopeUnavailable('office has no reviewed ALLOW_PAID source')
 if not __import__('re').fullmatch(r'\d{4}-Q[1-4]',quarter):raise ScopeUnavailable('quarter must be YYYY-Q1..Q4')
 if db!=DB or record!=RECORD or expected_record_sha256!=EXPECTED_RECORD_SHA or expected_guard_sha256!=EXPECTED_GUARD_SHA:raise SourceUnknown('only pinned canonical DB, permission record, and guard are accepted')
 rec_sha,entries=common._record();before=db.stat()
 if expected_db_size and before.st_size!=expected_db_size:raise SourceUnknown(f'seller-signals size {before.st_size} != reviewed {expected_db_size}')
 if expected_db_mtime_ns and before.st_mtime_ns!=expected_db_mtime_ns:raise SourceUnknown('seller-signals mtime differs from reviewed snapshot')
 verify_row,verifier_sha=_snapshot_verifier();conn=sqlite3.connect(f'file:{db}?mode=ro',uri=True);conn.row_factory=sqlite3.Row;conn.execute('pragma query_only=on')
 try:
  conn.execute('begin')
  sig={r['permit_id']:str(r['permit_type'] or '') for r in conn.execute('select permit_id,permit_type from seller_signals where jurisdiction=?',(office,))}
  seq=defaultdict(list);snapshot_count=0
  for r in conn.execute('select * from permit_prediction_snapshots where jurisdiction=? order by permit_id,snapshot_date,model_version',(office,)):
   row=dict(r);snapshot_count+=1
   if not verify_row(row):raise SourceUnknown('snapshot content_sha256 verification failed')
   seq[row['permit_id']].append((str(row['snapshot_date']),str(row['status'] or ''),str(row['model_version'] or '')))
  conn.commit()
 finally:conn.close()
 after=db.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise SourceUnknown('seller-signals changed during read')
 if not seq:raise ScopeUnavailable('office has no retained snapshots')
 seq={pid:_collapse_daily(values) for pid,values in seq.items()}
 class_counts=Counter(sig.get(pid,'') for pid in seq);top=sorted(class_counts,key=lambda k:(-class_counts[k],k))[0]
 board_first=min(d[:10] for values in seq.values() for d,_ in values)
 byq=defaultdict(list)
 for pid,values in seq.items():
  if sig.get(pid,'')!=top:continue
  start=None
  if complete_fields:
   required_start={'austin':'active','montgomery-md':'open','san-francisco':'issued'}[office]
   for i,(day,status) in enumerate(values):
    if status.strip().lower()==required_start:start=(i,day,status);break
  elif office=='montgomery-md':
   for i,(day,status) in enumerate(values):
    if status.strip().lower()=='open':start=(i,day,status);break
  elif values and values[0][1].strip():start=(0,values[0][0],values[0][1])
  if not start:continue
  i0,first,status0=start
  if first[:10]==board_first:continue
  nxt=None
  for day,status in values[i0+1:]:
   if status.strip() and status!=status0:nxt=(day,status);break
  if not nxt:continue
  try:days=(dt.date.fromisoformat(nxt[0][:10])-dt.date.fromisoformat(first[:10])).days
  except ValueError as e:raise SourceUnknown('selected transition date malformed') from e
  if days<0:raise SourceUnknown('selected transition runs backwards')
  byq[_quarter(first)].append((first[:10],nxt[0][:10],days,status0,nxt[1]) if complete_fields else (first[:10],nxt[0][:10],days))
 selected=byq.get(quarter,[])
 if min_observations<MIN_CLERK_TRANSITIONS:raise ScopeUnavailable('minimum Clerk transition floor is 30 and cannot be lowered')
 if len(selected)<min_observations:raise ScopeUnavailable(f'{office}/{quarter} has {len(selected)} verified transitions; minimum {min_observations}')
 days=[x[2] for x in selected];row={'board':office,'class':top,'n':str(len(days)),'median_days':_fmt(float(__import__('statistics').median(days))),'p25':_fmt(_percentile(days,.25)),'p75':_fmt(_percentile(days,.75)),'first_date':min(x[0] for x in selected),'last_date':max(x[1] for x in selected)}
 extra_fields=[];counts=[]
 if complete_fields:
  from clerk_status_counts import status_counts
  counts=status_counts(selected)
  if office_details is not None:raise SourceUnknown('arbitrary office-hour assertions are not accepted')
  from clerk_office_details import office_details as read_office_details
  office_details=read_office_details(office)
  required_start={'austin':'active','montgomery-md':'open','san-francisco':'issued'}[office]
  row.update({'start_status':required_start,'next_status_counts':json.dumps(counts,sort_keys=True,separators=(',',':')),'window_hours':office_details['hours'],'window_hours_source_url':office_details.get('source_url') or 'UNKNOWN','window_hours_read_at':office_details.get('read_at') or 'UNKNOWN','window_hours_scope':office_details.get('scope') or 'UNKNOWN'})
  extra_fields=['start_status','next_status_counts','window_hours','window_hours_source_url','window_hours_read_at','window_hours_scope']
 prefix='';required=str(entries[office].get('required_text') or '')
 if required:prefix='# '+required+'\n'
 outbuf=io.StringIO(newline='');outbuf.write(prefix);w=csv.DictWriter(outbuf,fieldnames=FIELDS+extra_fields,lineterminator='\n');w.writeheader();w.writerow(row);artifact=outbuf.getvalue().encode()
 guard=common._guard_module();scope=f'{office}\0{quarter}'+('\0complete-fields-v1' if complete_fields else '')
 selected_digest=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 meta={'family':'clerk-clock','fulfillment_component':'timing summary only; office hours and per-status transition counts are not included','scope':{'office':office,'quarter':quarter,'minimum_observations':min_observations,'verified_transitions':len(selected),'top_permit_class':top,'transition_basis':'observed status transitions: first uncensored stored status to first later changed status','quarter_basis':'transition start date'},'source':{'path':str(db),'size':before.st_size,'mtime_ns':before.st_mtime_ns,'seller_signal_rows':len(sig),'snapshot_rows_for_office':snapshot_count,'schema_tables':['seller_signals','permit_prediction_snapshots'],'snapshot_verifier_path':'/home/gmullins/Claude CLI/permits-engine/permits_engine/issued_permits/snapshot_store.py','snapshot_verifier_sha256':verifier_sha},'selected_observations_sha256':selected_digest,'selected_observation_count':len(selected),'permission':{'path':str(record),'sha256':rec_sha,'source_id':office,'verdict':entries[office]['verdict']},'guard':{'path':str(GUARD),'sha256':EXPECTED_GUARD_SHA,'verdict':'CLEAN'},'artifact_sha256':hashlib.sha256(artifact).hexdigest(),'artifact_bytes':len(artifact),'internal_acceptance_fixture':True,'buyer_payment':False,'sent':False}
 if complete_fields:
  meta['fulfillment_component']='office/quarter/class timing, status counts and sourced office hours or explicit UNKNOWN; customer order and delivery separate'
  meta['status_transition_counts']=counts
  meta['office_details']=office_details
  meta['scope']['required_start_status']=required_start
 meta_bytes=(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode()
 out=common._commit_package(output_root,'clerk-clock',scope,artifact,meta_bytes,guard.scan,store=db,record=record)
 return {'output':str(out),'metadata':meta}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description='Build a guarded private Clerk Clock timing component.')
 p.add_argument('--office',required=True);p.add_argument('--quarter',required=True);p.add_argument('--output-root',type=Path,default=Path.home()/'.hermes/state/clerk-clock/manual-artifacts')
 p.add_argument('--complete-fields',action='store_true',help='Include status-pair counts and dated office-hour facts or UNKNOWN')
 a=p.parse_args();r=build_clerk_clock(office=a.office,quarter=a.quarter,output_root=a.output_root,complete_fields=a.complete_fields)
 print(json.dumps({'output':r['output'],'artifact_sha256':r['metadata']['artifact_sha256'],'verified_transitions':r['metadata']['scope']['verified_transitions']},sort_keys=True))
