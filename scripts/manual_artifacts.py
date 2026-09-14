#!/usr/bin/env python3
"""Guarded Address Record Packet builder for the six-city retained store.

Reads the canonical seller_signals.db read-only, checks its pinned permission
record and schema, accepts one explicit city/street scope with at least two
rows, maps the published seven-column packet schema, and runs the canonical
outbound guard on exact bytes before no-clobber private commit. No payment,
order, receipt, mail, or deployment integration exists here.
"""
from __future__ import annotations
import csv, ctypes, errno, hashlib, importlib.util, io, json, os, re, shutil, sqlite3, stat, tempfile
from pathlib import Path
from typing import Any
DB=Path('/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db')
RECORD=Path('/home/gmullins/code/usta-paid-surfaces/paid_file_sources.json')
GUARD=Path('/home/gmullins/code/usta-paid-surfaces/scripts/outbound_guard.py')
EXPECTED_RECORD_SHA='c72ac080854f3683c40900913c8a14a1e6915c87c9bc3df3e26b5b959c5c90e8'
EXPECTED_GUARD_SHA='348676595840b6215d75fc8b5085259642c46c21aee7c3527d172ce4dfe1544f'
ALLOWED_CITIES=('austin','cincinnati','montgomery-md','new-york','san-francisco','cambridge-ma')
PORTALS={'austin':'City of Austin Open Data Portal — Issued Construction Permits','cincinnati':'City of Cincinnati Open Data Portal — Cincinnati Building Permits','montgomery-md':'dataMontgomery — Residential Permit','new-york':'NYC Open Data — DOB NOW: Build – Approved Permits','san-francisco':'DataSF — Building Permits','cambridge-ma':'City of Cambridge Open Data — Building Permits'}
OUT_HEADERS=['city','address','permit_date','permit_type','work_class','status','source_portal']
CONTROL=re.compile(r'[\x00-\x1f\x7f]')
class ArtifactError(ValueError): pass
class SourceUnknown(ArtifactError): pass
class ScopeUnavailable(ArtifactError): pass
class ImmutableArtifactError(ArtifactError): pass
def sha256(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _regular(path:Path)->bytes:
 if path.is_symlink():raise SourceUnknown(f'symlink refused: {path}')
 try:fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 except OSError as e:raise SourceUnknown(f'cannot open {path}') from e
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise SourceUnknown(f'not regular: {path}')
  chunks=[]
  while True:
   b=os.read(fd,1024*1024)
   if not b:break
   chunks.append(b)
  return b''.join(chunks)
 finally:os.close(fd)
def _safe(value:str,field:str)->str:
 if not isinstance(value,str) or not value.strip() or CONTROL.search(value):raise ScopeUnavailable(f'invalid {field}')
 return ' '.join(value.split())
def _record()->tuple[str,dict[str,dict[str,Any]]]:
 raw=_regular(RECORD);actual=sha256(raw)
 if actual!=EXPECTED_RECORD_SHA:raise SourceUnknown(f'permission record sha256 {actual} != reviewed {EXPECTED_RECORD_SHA}')
 try:doc=json.loads(raw)
 except Exception as e:raise SourceUnknown('permission record is not JSON') from e
 src=doc.get('sources')
 if not isinstance(src,dict):raise SourceUnknown('permission sources missing')
 for city in ALLOWED_CITIES:
  e=src.get(city)
  if not isinstance(e,dict) or e.get('verdict')!='ALLOW_PAID':raise SourceUnknown(f'{city} is not currently ALLOW_PAID')
 return actual,{c:src[c] for c in ALLOWED_CITIES}
def _guard_module():
 raw=_regular(GUARD);actual=sha256(raw)
 if actual!=EXPECTED_GUARD_SHA:raise SourceUnknown(f'canonical outbound guard sha256 {actual} != reviewed {EXPECTED_GUARD_SHA}')
 spec=importlib.util.spec_from_file_location('canonical_outbound_guard',GUARD)
 if spec is None or spec.loader is None:raise SourceUnknown('canonical outbound guard unavailable')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def _db_schema(conn:sqlite3.Connection):
 fields=[r[1] for r in conn.execute('pragma table_info(seller_signals)')]
 expected=['permit_id','jurisdiction','permit_number','record_type','permit_type','permit_class','status','issue_date','address','zip_code','zone','subdivision','owner_name','contractor_name','valuation_usd','latitude','longitude','intent_score','is_seller_signal','signals_json','payload_json','sources_json','last_synced','apn','psir_prob','psir_ci_low','psir_ci_high','psir_model_version','psir_calibrated','psir_horizon_days','psir_scored_at']
 if fields!=expected:raise SourceUnknown('seller_signals schema differs from reviewed canonical schema')
def _work_class(payload:Any,city:str)->str:
 if not isinstance(payload,dict):raise SourceUnknown('payload_json is not an object')
 keys={'austin':'work_class','cincinnati':'workclassmapped','montgomery-md':'worktype','new-york':'work_type','san-francisco':'permit_type_definition','cambridge-ma':'permit_type'}
 v=payload.get(keys[city])
 if not isinstance(v,str) or not v.strip() or CONTROL.search(v):raise SourceUnknown(f'{city} work class unavailable')
 return v.strip()
def _cell(value:Any)->str:
 text='' if value is None else str(value).replace('\x00','').strip()
 if text.startswith(('=','+','-','@','\t','\r','\n')):return "'"+text
 return text
def _csv(rows:list[dict[str,str]],required_text:str)->bytes:
 out=io.StringIO(newline='')
 if required_text:out.write('# '+required_text+'\n')
 w=csv.DictWriter(out,fieldnames=OUT_HEADERS,lineterminator='\n');w.writeheader();w.writerows(rows)
 return out.getvalue().encode()
def _private_root(root:Path)->Path:
 root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
 if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode)&0o077:
  raise SourceUnknown('output root must be a private non-symlink directory')
 return root
def _write_exclusive(path:Path,data:bytes)->None:
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 except BaseException:
  try:path.unlink()
  except OSError:pass
  raise
def _package_path(root:Path,prefix:str,scope:str)->Path:
 return _private_root(root)/(f'{prefix}-{sha256(scope.encode())[:16]}')
def _same_package(path:Path,artifact:bytes,metadata:bytes)->bool:
 if path.is_symlink() or not path.is_dir():return False
 a=path/'artifact.csv';m=path/'metadata.json'
 try:return (not a.is_symlink() and not m.is_symlink() and _regular(a)==artifact and _regular(m)==metadata)
 except (OSError,SourceUnknown):return False
def _rename_noreplace(source:Path,target:Path)->None:
 libc=ctypes.CDLL(None,use_errno=True);fn=getattr(libc,'renameat2',None)
 if fn is None:raise SourceUnknown('atomic no-clobber directory primitive unavailable')
 fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
 if fn(-100,os.fsencode(source),-100,os.fsencode(target),1):
  e=ctypes.get_errno()
  if e==errno.EEXIST:raise FileExistsError(e,os.strerror(e),str(target))
  raise OSError(e,os.strerror(e),str(target))
def _commit_package(root:Path,prefix:str,scope:str,artifact:bytes,metadata:bytes,scan,*,store:Path,record:Path)->Path:
 """Guard and atomically install an immutable artifact+metadata directory."""
 root=_private_root(root);final=_package_path(root,prefix,scope)
 guard_stage=Path(tempfile.mkdtemp(prefix='.guard-',dir=root));guard_stage.chmod(0o700)
 package_stage=None
 try:
  guard_file=guard_stage/'artifact.csv';_write_exclusive(guard_file,artifact)
  verdict,reason=scan(guard_file,store=str(store),record=str(record))
  if verdict!='CLEAN':raise SourceUnknown(f'canonical outbound guard {verdict}: {reason}')
 finally:
  shutil.rmtree(guard_stage,ignore_errors=True)
 try:
  package_stage=Path(tempfile.mkdtemp(prefix='.package-',dir=root));package_stage.chmod(0o700)
  _write_exclusive(package_stage/'artifact.csv',artifact);_write_exclusive(package_stage/'metadata.json',metadata)
  _rename_noreplace(package_stage,final);package_stage=None
 except (FileExistsError,NotADirectoryError,OSError) as e:
  if final.exists() and _same_package(final,artifact,metadata):return final
  raise ImmutableArtifactError(f'output package already exists or is incomplete: {final}') from e
 finally:
  if package_stage is not None:shutil.rmtree(package_stage,ignore_errors=True)
 final.chmod(0o700)
 return final
def _private_path(root:Path,city:str,street:str)->Path:
 root=_private_root(root)
 digest=sha256(f'{city}\0{street}'.encode())[:16]
 return root/f'address-packet-{city}-{digest}'
def build_address_packet(*,city:str,street:str,output_root:Path,db:Path=DB,record:Path=RECORD,expected_db_size:int=3291238400,expected_db_mtime_ns:int=0,expected_record_sha256:str=EXPECTED_RECORD_SHA,expected_guard_sha256:str=EXPECTED_GUARD_SHA,min_rows:int=2)->dict[str,Any]:
 city=_safe(city,'city').lower();street=_safe(street,'street').upper()
 if city not in ALLOWED_CITIES:raise ScopeUnavailable('city is outside the six-city store')
 if record!=RECORD or expected_record_sha256!=EXPECTED_RECORD_SHA:raise SourceUnknown('only the pinned canonical permission record is accepted')
 if expected_guard_sha256!=EXPECTED_GUARD_SHA:raise SourceUnknown('only the pinned canonical outbound guard is accepted')
 record_sha,entries=_record();before=db.stat()
 if expected_db_size and before.st_size!=expected_db_size:raise SourceUnknown(f'seller-signals size {before.st_size} != reviewed {expected_db_size}')
 if expected_db_mtime_ns and before.st_mtime_ns!=expected_db_mtime_ns:raise SourceUnknown('seller-signals mtime differs from reviewed snapshot')
 conn=sqlite3.connect(f'file:{db}?mode=ro',uri=True);conn.execute('pragma query_only=on')
 try:
  conn.execute('begin');_db_schema(conn)
  rawrows=conn.execute('''select jurisdiction,address,issue_date,permit_type,status,payload_json,sources_json from seller_signals where lower(jurisdiction)=? and upper(trim(address))=? order by issue_date,permit_id''',(city,street)).fetchall()
  total=conn.execute('select count(*) from seller_signals').fetchone()[0];conn.commit()
 finally:conn.close()
 after=db.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise SourceUnknown('seller-signals changed during read')
 if min_rows<2:raise ScopeUnavailable('minimum address row floor is 2 and cannot be lowered')
 if len(rawrows)<min_rows:raise ScopeUnavailable(f'{city}/{street} has {len(rawrows)} rows; at least {min_rows} required')
 rows=[]
 for jurisdiction,address,issue_date,permit_type,status,payload,sources in rawrows:
  try:payload_obj=json.loads(payload)
  except Exception as e:raise SourceUnknown('payload_json is malformed') from e
  try:source_ids=json.loads(sources)
  except Exception as e:raise SourceUnknown('sources_json is malformed') from e
  if not isinstance(source_ids,list) or not any(isinstance(s,str) and s.startswith(city+':') for s in source_ids):raise SourceUnknown('row source does not match the permitted city source')
  rows.append({'city':city,'address':_cell(address),'permit_date':_cell(issue_date),'permit_type':_cell(permit_type),'work_class':_cell(_work_class(payload_obj,city)),'status':_cell(status),'source_portal':PORTALS[city]})
 required=str(entries[city].get('required_text') or '')
 artifact=_csv(rows,required);guard=_guard_module();scope=f'{city}\0{street}'
 selected_digest=sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())
 metadata={'family':'address-packet','scope':{'city':city,'street':street,'row_count':len(rows),'minimum_rows':min_rows},'source':{'path':str(db),'size':before.st_size,'mtime_ns':before.st_mtime_ns,'row_count':total,'schema':'seller_signals'},'selected_rows_sha256':selected_digest,'selected_row_count':len(rows),'permission':{'path':str(record),'sha256':record_sha,'source_id':city,'verdict':entries[city]['verdict']},'guard':{'path':str(GUARD),'sha256':EXPECTED_GUARD_SHA,'verdict':'CLEAN'},'artifact_sha256':sha256(artifact),'artifact_bytes':len(artifact),'internal_acceptance_fixture':True,'buyer_payment':False,'sent':False}
 metadata_bytes=(json.dumps(metadata,indent=2,sort_keys=True)+'\n').encode()
 root=_commit_package(output_root,'address-packet',scope,artifact,metadata_bytes,guard.scan,store=db,record=record)
 return {'output':str(root),'metadata':metadata}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description='Build a guarded private Address Record Packet.')
 p.add_argument('kind',choices=['address']);p.add_argument('--city',required=True);p.add_argument('--street',required=True);p.add_argument('--output-root',type=Path,default=Path.home()/'.hermes/state/address-packet/manual-artifacts')
 a=p.parse_args();r=build_address_packet(city=a.city,street=a.street,output_root=a.output_root)
 print(json.dumps({'output':r['output'],'artifact_sha256':r['metadata']['artifact_sha256'],'row_count':r['metadata']['scope']['row_count']},sort_keys=True))
