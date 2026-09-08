#!/usr/bin/env python3
"""Seal openFDA device establishment exports (offline folder or --fetch download); public business registrations only."""
from __future__ import annotations
import argparse, csv, fcntl, hashlib, io, json, os, re, shutil, sys, tempfile, urllib.request, zipfile
from datetime import date
from pathlib import Path
BET_ID = 'fda-device-establishment-week'
KILL_DATE = '2026-10-08'
STATE = Path.home() / '.hermes/state' / BET_ID
COLUMNS = ('week_ending','fei_number','registration_number','owner_operator_number','name','city','state_code','iso_country_code','establishment_types','status_code','reg_expiry_date_year','product_code_count')
DELTA_COLUMNS = COLUMNS + ('change','changed_fields')
COMPARE = tuple(c for c in COLUMNS if c not in ('week_ending','fei_number','registration_number'))
EXPORT = re.compile(r'^export_([0-9]{4}-[0-9]{2}-[0-9]{2})$')
PART = re.compile(r'(?:part[-_]?|[-_])([0-9]+)[-_]of[-_]([0-9]+)',re.I)
SOURCE = 'https://api.fda.gov/download.json'
DATASET = ('device','registrationlisting')
MAX_PART_BYTES = 400*1024*1024

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def scalar(value):
    if value is None: return ''
    if not isinstance(value,(str,int)): raise ValueError('invalid scalar type')
    result=str(value).strip()
    if any(ord(c)<32 for c in result): raise ValueError('control character in source scalar')
    return result

def key(row):
    return row['registration_number'],row['fei_number']

def csv_bytes(columns, rows):
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=columns,lineterminator=chr(10),extrasaction='raise')
    writer.writeheader(); writer.writerows(rows)
    return buf.getvalue().encode('utf-8')

def read_export(folder):
    match=EXPORT.fullmatch(folder.name)
    if not match: raise ValueError('export directory must be export_YYYY-MM-DD')
    day=match.group(1); date.fromisoformat(day)
    files=sorted(folder.glob('*.zip'))
    if not files: raise ValueError('export has no ZIP parts')
    mf=folder/'manifest.json'
    manifest=json.loads(mf.read_text()) if mf.exists() else None
    matches=[PART.search(p.name) for p in files]
    if any(matches):
        if not all(matches): raise ValueError('mixed named and unnamed ZIP parts')
        totals={int(m.group(2)) for m in matches}
        if len(totals)!=1: raise ValueError('inconsistent ZIP part total')
        total=next(iter(totals))
        if len(files)!=total or {int(m.group(1)) for m in matches}!=set(range(1,total+1)):
            raise ValueError('incomplete ZIP parts')
    elif manifest is None:
        raise ValueError('ZIP completeness UNKNOWN: supply part-X-of-Y filenames or manifest.json')
    if manifest is not None and manifest.get('parts')!=len(files): raise ValueError('manifest part count mismatch')
    records=0; missing_identity=0; unsafe=0; conflicts=set(); by_key={}; suppressed=set(); inputs=[]
    for file in files:
        blob=file.read_bytes(); inputs.append({'file':file.name,'sha256':sha(blob)})
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            members=[n for n in archive.namelist() if n.endswith('.json')]
            if len(members)!=1: raise ValueError('each ZIP must contain one JSON')
            doc=json.loads(archive.read(members[0]))
        del blob
        if not isinstance(doc,dict) or not isinstance(doc.get('results'),list): raise ValueError('missing results list')
        meta=doc.get('meta',{})
        if not isinstance(meta,dict): raise ValueError('invalid metadata')
        if meta.get('export_date') and meta['export_date']!=day: raise ValueError('export date mismatch')
        for record in doc['results']:
            records+=1
            if not isinstance(record,dict) or not isinstance(record.get('registration'),dict): raise ValueError('invalid registration object')
            reg=record['registration']; name=scalar(reg.get('name'))
            identity=(scalar(reg.get('registration_number')),scalar(reg.get('fei_number')))
            if not all(identity):
                missing_identity+=1; continue
            owner=reg.get('owner_operator') or {}
            if not isinstance(owner,dict): raise ValueError('invalid owner operator')
            types=record.get('establishment_type',[]); products=record.get('products',[])
            if not isinstance(types,list) or not isinstance(products,list): raise ValueError('invalid types/products list')
            type_set={scalar(t) for t in types if t is not None}; codes=set()
            for product in products:
                if not isinstance(product,dict): raise ValueError('invalid product object')
                if product.get('product_code'): codes.add(scalar(product['product_code']))
            row={'week_ending':day,'fei_number':identity[1],'registration_number':identity[0],
                 'owner_operator_number':scalar(owner.get('owner_operator_number')),
                 'name':name,'city':scalar(reg.get('city')),'state_code':scalar(reg.get('state_code')),
                 'iso_country_code':scalar(reg.get('iso_country_code')),'status_code':scalar(reg.get('status_code')),
                 'reg_expiry_date_year':scalar(reg.get('reg_expiry_date_year'))}
            if any(v.startswith(('=','+','-','@')) for v in list(row.values())+list(type_set)+list(codes)):
                suppressed.add(identity); unsafe+=1; continue
            if identity in by_key:
                previous,existing_types,existing_codes=by_key[identity]
                if previous!=row:
                    conflicts.add(identity); suppressed.add(identity); continue
                existing_types.update(type_set); existing_codes.update(codes)
            else: by_key[identity]=(row,type_set,codes)
        del doc
    if records==0: raise ValueError('empty export: comparison UNKNOWN; refusing false vanished rows')
    if manifest is not None and manifest.get('records')!=records: raise ValueError('manifest record count mismatch')
    result={}
    for identity,(row,types,codes) in sorted(by_key.items()):
        if identity in suppressed: continue
        row['establishment_types']=';'.join(sorted(types)); row['product_code_count']=str(len(codes))
        result[identity]=row
    if not result: raise ValueError('no eligible establishments: comparison UNKNOWN')
    metadata={'bet_id':BET_ID,'export_date':day,'source_url':SOURCE,'input_parts':inputs,
              'source_records':records,'missing_identity_records':missing_identity,'unsafe_listing_records':unsafe,'conflicting_identities':len(conflicts),'eligible_establishments':len(result)}
    return day,result,metadata,suppressed

def changes(older,newer,new_day,suppressed=()):
    result=[]
    for identity in sorted((older.keys()|newer.keys())-set(suppressed)):
        a=older.get(identity); b=newer.get(identity); fields=[]
        if a is None: kind='appeared'
        elif b is None: kind='vanished'
        else:
            fields=[c for c in COMPARE if a[c]!=b[c]]
            if not fields: continue
            kind='changed'
        result.append(dict(b or a,week_ending=new_day,change=kind,changed_fields=';'.join(fields)))
    return result

def seal(out,artifacts):
    # Check all conflicts first; reruns may reuse only byte-identical sealed files.
    for name,blob in artifacts.items():
        path=out/name
        if path.is_symlink(): raise ValueError('symlink output refused')
        if path.exists() and path.read_bytes()!=blob: raise ValueError('sealed output drift: '+name)
    for name,blob in artifacts.items():
        path=out/name
        if path.exists(): continue
        fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=out)
        with os.fdopen(fd,'wb') as f:
            f.write(blob); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)

def fetch_export(root,opener=urllib.request.urlopen):
    """Download today's dated export into root/export_<date>/ atomically; returns the folder (existing folder reused)."""
    with opener(SOURCE,timeout=120) as r: index=json.loads(r.read().decode('utf-8'))
    section=index['results']
    for k in DATASET: section=section[k]
    day=section['export_date']; date.fromisoformat(day)
    parts=section['partitions']
    if not isinstance(parts,list) or not parts: raise ValueError('download index lists no partitions')
    folder=root/f'export_{day}'
    if folder.exists():
        if len(list(folder.glob('*.zip')))==len(parts): return folder
        raise ValueError('partial export folder present: '+str(folder))
    root.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='.pending-export-',dir=root))
    try:
        for part in parts:
            url=part['file']; name=url.rsplit('/',1)[-1]
            if not PART.search(name) or not name.endswith('.zip'): raise ValueError('unexpected part name: '+name)
            with opener(url,timeout=600) as r, (tmp/name).open('wb') as f:
                copied=0
                while True:
                    chunk=r.read(1<<20)
                    if not chunk: break
                    copied+=len(chunk)
                    if copied>MAX_PART_BYTES: raise ValueError('part exceeds size cap: '+name)
                    f.write(chunk)
                f.flush(); os.fsync(f.fileno())
        (tmp/'manifest.json').write_text(json.dumps({'parts':len(parts),'records':section.get('total_records'),'export_date':day,'source_url':SOURCE},sort_keys=True))
        os.rename(tmp,folder)
    except BaseException:
        shutil.rmtree(tmp,ignore_errors=True); raise
    return folder

def collect(offline,out):
    if EXPORT.fullmatch(offline.name): folders=[offline]
    else: folders=sorted(p for p in offline.glob('export_*') if p.is_dir() and EXPORT.fullmatch(p.name))
    if not folders: raise ValueError('no dated offline exports; network transport is not installed')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.collector.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('collector already running')
        parsed=[read_export(p) for p in folders[-2:]]; artifacts={}
        for day,rows,meta,suppressed in parsed:
            blob=csv_bytes(COLUMNS,list(rows.values())); meta['snapshot_sha256']=sha(blob)
            artifacts[f'snapshot_{day}.csv']=blob
            artifacts[f'snapshot_{day}.json']=(json.dumps(meta,sort_keys=True,indent=2)+chr(10)).encode()
        if len(parsed)==2:
            old,new=parsed; delta=changes(old[1],new[1],new[0],old[3]|new[3])
            name=f'what_changed_{old[0]}_{new[0]}'
            blob=csv_bytes(DELTA_COLUMNS,delta); artifacts[name+'.csv']=blob
            artifacts[name+'.json']=(json.dumps({'older':old[0],'newer':new[0],'sha256':sha(blob),
                'snapshot_hashes':{d:m['snapshot_sha256'] for d,r,m,s in parsed},'changes':len(delta)},sort_keys=True,indent=2)+chr(10)).encode()
        seal(out,artifacts)
        print(json.dumps({'snapshots':[{'date':d,'records':m['source_records'],'eligible':len(r)} for d,r,m,s in parsed],
                          'comparison':'available' if len(parsed)==2 else 'UNKNOWN: baseline only'},sort_keys=True))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',type=Path,help='folder of export_YYYY-MM-DD dirs (default: <out>/raw)')
    p.add_argument('--fetch',action='store_true',help='download the current export from openFDA into <offline>/export_<date>/ first')
    p.add_argument('--out',type=Path,default=STATE)
    args=p.parse_args()
    if args.offline is None and not args.fetch: p.error('supply --offline <folder> or --fetch')
    offline=args.offline if args.offline is not None else args.out/'raw'
    try:
        if args.fetch: fetch_export(offline)
        collect(offline,args.out)
    except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        print('REFUSED: '+str(exc),file=sys.stderr); return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
