"""Private Metro File producer from verified retained status snapshots.
No crawling, payment mutation, sending, or public routing. Never a full board dump.
"""
import argparse,csv,datetime as dt,hashlib,io,json,os,shutil,sqlite3,tempfile
from pathlib import Path
import manual_artifacts as common
import clerk_clock
from metro_changes import changes,render_transitions_csv
METROS=('austin','cincinnati','montgomery-md','new-york','san-francisco')
COMMON_SHA='7424ef99359449145bdda43b33afb08532b4031900458f0e03a69b48f0906809'

def build(metro,through_day,output_root):
    if metro not in METROS:raise common.ScopeUnavailable('metro is outside reviewed paid scope')
    if dt.date.fromisoformat(through_day).isoformat()!=through_day:raise common.ScopeUnavailable('canonical ISO day required')
    if hashlib.sha256(Path(common.__file__).read_bytes()).hexdigest()!=COMMON_SHA:raise common.SourceUnknown('private package helper changed')
    permission_sha,entries=common._record();guard=common._guard_module();verify,verifier_sha=clerk_clock._snapshot_verifier()
    before=common.DB.stat();conn=sqlite3.connect(common.DB.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    selected=[];seals=hashlib.sha256()
    try:
        conn.execute('PRAGMA query_only=on');conn.execute('BEGIN')
        for record in conn.execute('SELECT * FROM permit_prediction_snapshots WHERE jurisdiction=? AND snapshot_date<=? ORDER BY permit_id,snapshot_date,model_version',(metro,through_day)):
            row=dict(record)
            if len(selected)>=1000000:raise common.SourceUnknown('snapshot bound exceeded')
            if not verify(row):raise common.SourceUnknown('retained snapshot seal does not verify')
            seals.update((str(row['content_sha256'])+'\n').encode())
            selected.append({k:row[k] for k in ('permit_id','jurisdiction','snapshot_date','sealed_at','model_version','status','issue_date','valuation_usd','permit_class','apn','zip_code')})
        conn.commit()
    finally:conn.close()
    after=common.DB.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise common.SourceUnknown('retained store changed during read')
    result=changes(selected,metro,through_day)
    credit=str(entries[metro].get('required_text') or '')
    prefix=('# '+credit+'\n') if credit else ''
    transitions=(prefix+render_transitions_csv(result['transitions'])).encode()
    buf=io.StringIO(newline='');buf.write(prefix)
    writer=csv.DictWriter(buf,fieldnames=['jurisdiction','date','state','snapshot_rows'],lineterminator='\n');writer.writeheader()
    for row in result['coverage']:writer.writerow({'jurisdiction':metro,**row})
    coverage=buf.getvalue().encode()
    root=common._private_root(Path(output_root));stage=Path(tempfile.mkdtemp(prefix='.metro-',dir=root));stage.chmod(0o700)
    artifacts={'transitions.csv':transitions,'coverage.csv':coverage}
    try:
        guards={}
        for name,body in artifacts.items():
            common._write_exclusive(stage/name,body)
            verdict,reason=guard.scan(stage/name,store=str(common.DB),record=str(common.RECORD))
            if verdict!='CLEAN':raise common.SourceUnknown(f'{name} outbound guard: {verdict}')
            guards[name]={'verdict':verdict,'reason':str(reason)}
        manifest={'family':'metro-file','scope':{'metro':metro,'through_day':through_day},
                  'source':{'path':str(common.DB),'size':before.st_size,'mtime_ns':before.st_mtime_ns,'verified_snapshot_rows':len(selected),'ordered_seals_sha256':seals.hexdigest(),'verifier_sha256':verifier_sha},
                  'permission':{'path':str(common.RECORD),'sha256':permission_sha,'source_id':metro,'verdict':entries[metro]['verdict']},
                  'transitions':len(result['transitions']),'changed_permits':len({r['permit_id'] for r in result['transitions']}),
                  'coverage_present_days':sum(r['state']=='PRESENT' for r in result['coverage']),
                  'coverage_hole_days':sum(r['state']=='HOLE' for r in result['coverage']),
                  'artifacts':{name:hashlib.sha256(body).hexdigest() for name,body in artifacts.items()},
                  'guards':guards,'guard_sha256':common.EXPECTED_GUARD_SHA,
                  'limits':['Changes are observed across retained days, not exact real-world change times.','permit_class is the retained intent label, not the city permit type.'],
                  'buyer_order':None,'customer_delivery':False,'sent':False}
        scope=metro+'\0'+through_day+'\0'+seals.hexdigest()
        final=common._package_path(root,'metro-file',scope)
        for value in guards.values():value['reason']=value['reason'].replace(str(stage),str(final))
        common._write_exclusive(stage/'manifest.json',(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
        common._rename_noreplace(stage,final)
        return {'output':str(final),'manifest':manifest}
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metro',required=True,choices=METROS);p.add_argument('--through-day',required=True);p.add_argument('--output-root',type=Path,default=Path.home()/'.hermes/state/metro-file/private-artifacts')
    a=p.parse_args();r=build(a.metro,a.through_day,a.output_root)
    print(json.dumps({'output':r['output'],'transitions':r['manifest']['transitions'],'coverage_hole_days':r['manifest']['coverage_hole_days']},sort_keys=True))
