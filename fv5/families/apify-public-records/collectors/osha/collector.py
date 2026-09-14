#!/usr/bin/env python3
"""Collect an official OSHA release privately; publish only allowlisted fields."""
from pathlib import Path
import argparse,base64,csv,datetime,fcntl,hashlib,importlib.util,io,json,math,os,re,subprocess,sys,time,urllib.request,zipfile


def load_actor(path):
    spec=importlib.util.spec_from_file_location('osha_source_actor',Path(path)/'main.py');actor=importlib.util.module_from_spec(spec);spec.loader.exec_module(actor);return actor


def download(actor):
    sys.path.insert(0,'/home/gmullins/Claude CLI/harness/browser');import hand
    with hand.Browser(headless=True) as ctx:
        page=hand._fresh_page(ctx)
        try:
            response=page.goto(actor.PAGE_URL,wait_until='domcontentloaded',timeout=30000)
            if not response or response.status!=200:raise RuntimeError('UNKNOWN: official source page did not return200')
            link=page.locator('a#downloadDataset');link.wait_for(state='attached',timeout=20000)
            url=urllib.parse.urljoin(actor.PAGE_URL,link.get_attribute('href'));release=actor.release_from_url(url)
            result=page.evaluate('''async ({url,limit})=>{
                const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
                try {
                    const r=await fetch(url,{redirect:'error',cache:'no-store',signal:controller.signal});
                    if(r.status!==200||r.url!==url) return {status:r.status,url:r.url,error:'Expected official file response'};
                    const reader=r.body.getReader();const chunks=[];let size=0;
                    for(;;){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>limit){controller.abort();throw new Error('Source exceeds size limit');}chunks.push(part.value);}
                    let binary='';for(const chunk of chunks){for(let i=0;i<chunk.length;i+=32768)binary+=String.fromCharCode(...chunk.subarray(i,i+32768));}
                    return {status:r.status,url:r.url,content_type:r.headers.get('content-type'),body_b64:btoa(binary)};
                } finally {clearTimeout(timer);}
            }''',{'url':url,'limit':actor.MAX_ZIP_BYTES})
            if result.get('status')!=200 or not result.get('body_b64'):raise RuntimeError('UNKNOWN: official browser download did not return data')
            body=base64.b64decode(result['body_b64'],validate=True)
            if not body.startswith(b'PK\x03\x04'):raise RuntimeError('UNKNOWN: official download is not a ZIP')
            evidence={'collected_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'page_http':response.status,'download_http':result['status'],'source_url':url,'source_bytes':len(body),'source_sha256':hashlib.sha256(body).hexdigest(),'content_type':result['content_type'],'browser':'canonical hand.Browser private runtime; no cookies exported'}
            return body,release,evidence
        finally:page.close()


def sanitize(actor,body,release,evidence):
    inp=actor.validate_input({'maxItems':1000,'timeoutSeconds':120});items,summary=actor.parse_source(body,release,inp,time.monotonic()+120)
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as original,zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as clean:
        name=[n for n in original.namelist() if n.lower().endswith('.csv')][0]
        data=io.StringIO(newline='')
        with original.open(name) as source:
            reader=csv.DictReader(io.TextIOWrapper(source,encoding='utf-8-sig'));fields=[n for n in reader.fieldnames if n in actor.REQUIRED];writer=csv.DictWriter(data,fieldnames=fields,lineterminator='\n');writer.writeheader()
            for row in reader:writer.writerow({name:row[name] for name in fields})
        entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;clean.writestr(entry,data.getvalue().encode('utf-8'),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    artifact=out.getvalue();clean_items,clean_summary=actor.parse_source(artifact,release,inp,time.monotonic()+120)
    if items!=clean_items or summary!=clean_summary:raise RuntimeError('UNKNOWN: sanitized data changed parser output')
    if evidence['page_http']!=200 or evidence['download_http']!=200 or evidence['source_sha256']!=hashlib.sha256(body).hexdigest():raise RuntimeError('UNKNOWN: source evidence does not match downloaded bytes')
    digest=hashlib.sha256(artifact).hexdigest();manifest={'schema_version':1,'status':'SUCCESS','collected_at':evidence['collected_at'],
        'source':{'url':release['source_url'],'sha256':evidence['source_sha256'],'bytes':len(body),'page_http':evidence['page_http'],'download_http':evidence['download_http']},
        'artifact':{'key':'source-'+digest+'.zip','sha256':digest,'bytes':len(artifact)},'source_rows':summary['source_rows'],'columns':fields,'collector_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return artifact,manifest,summary


def preflight(store):
    r=subprocess.run(['python3','/home/gmullins/.hermes/scripts/check_company_network.py','--policy','/home/gmullins/.hermes/config/company_network.json'],capture_output=True,text=True)
    if r.returncode!=0 or 'PASS' not in r.stdout:raise RuntimeError('UNKNOWN: company network guard did not pass')
    sys.path.insert(0,'/home/gmullins/code/market-services/api-access');from access import Client
    c=Client('apify');u=c.get('/v2/users/me')['data'];limits=c.get('/v2/users/me/limits')['data'];s=c.get('/v2/key-value-stores/'+store)['data']
    price=u['plan']['monthlyBasePriceUsd'];credits=u['plan']['monthlyUsageCreditsUsd'];cap=limits['limits']['maxMonthlyUsageUsd'];used=limits['current']['monthlyUsageUsd']
    numeric=all(type(value) in (int,float) and math.isfinite(value) and value>=0 for value in [price,credits,cap,used])
    if not numeric or s['userId']!=u['id'] or u['plan']['id']!='FREE' or u['plan']['isEnabled'] is not True or price!=0 or cap>credits or credits!=5 or used+.4>=credits:raise RuntimeError('UNKNOWN: source publication ownership/free-plan guard did not pass')
    return c


def publish(c,store,artifact,manifest):
    from access import NoRedirect
    base='https://api.apify.com/v2/key-value-stores/'+store+'/records/'
    def put(key,body,kind):
        req=urllib.request.Request(base+key,data=body,headers={'Authorization':'Bearer '+c.token,'Content-Type':kind},method='PUT')
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=40) as response:
            if response.status not in [200,201]:raise RuntimeError('UNKNOWN: source record write refused')
    def public_get(key):
        with urllib.request.build_opener(NoRedirect()).open(base+key,timeout=40) as response:
            if response.status!=200:raise RuntimeError('UNKNOWN: public source record unavailable')
            return response.read()
    put(manifest['artifact']['key'],artifact,'application/zip')
    checked=public_get(manifest['artifact']['key'])
    if hashlib.sha256(checked).hexdigest()!=manifest['artifact']['sha256']:raise RuntimeError('UNKNOWN: public artifact checksum mismatch; latest pointer preserved')
    put('LATEST.json',json.dumps(manifest).encode(),'application/json')
    if json.loads(public_get('LATEST.json'))!=manifest:raise RuntimeError('UNKNOWN: public latest-pointer readback mismatch')
    return {'artifact_http':200,'manifest_http':200,'anonymous_readback':True,'manifest_url':base+'LATEST.json','artifact_url':base+manifest['artifact']['key']}


def acquire_lock(state):
    handle=(state/'collector.lock').open('a')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception:handle.close();raise
    return handle


def prune_generated_bundles(state,keep=3):
    accepted=[]
    for child in state.iterdir():
        if not child.is_dir() or child.is_symlink() or not re.fullmatch(r'\d{8}T\d{6}Z',child.name):continue
        result=child/'result.json'
        try:
            if json.loads(result.read_text()).get('status')=='SUCCESS':accepted.append(child)
        except (OSError,ValueError):continue
    for old in sorted(accepted,reverse=True)[keep:]:
        for name in ['source.zip','sanitized.zip']:
            f=old/name
            if f.is_file() and not f.is_symlink():f.unlink()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--actor-dir',required=True);parser.add_argument('--state-dir',required=True);parser.add_argument('--store-id');parser.add_argument('--publish',action='store_true');args=parser.parse_args();state=Path(args.state_dir);state.mkdir(parents=True,exist_ok=True)
    try:lock=acquire_lock(state)
    except BlockingIOError:
        print(json.dumps({'status':'UNKNOWN','error':'Another source collection is active; no shared state changed'}));return 1
    attempt=state/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');attempt.mkdir(exist_ok=False)
    try:
        client=preflight(args.store_id) if args.publish and args.store_id else None
        if args.publish and client is None:raise RuntimeError('UNKNOWN: no owned source store configured')
        actor=load_actor(args.actor_dir);body,release,evidence=download(actor);(attempt/'source.zip').write_bytes(body);(attempt/'source-evidence.json').write_text(json.dumps(evidence,indent=2));artifact,manifest,summary=sanitize(actor,body,release,evidence);(attempt/'sanitized.zip').write_bytes(artifact);(attempt/'manifest.json').write_text(json.dumps(manifest,indent=2));(attempt/'summary.json').write_text(json.dumps(summary,indent=2));publication=publish(client,args.store_id,artifact,manifest) if args.publish else None
        result={'status':'SUCCESS','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attempt':str(attempt),'source_rows':summary['source_rows'],'source_sha256':evidence['source_sha256'],'publication':publication}
    except Exception as exc:result={'status':'UNKNOWN','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attempt':str(attempt),'error':str(exc)}
    (attempt/'result.json').write_text(json.dumps(result,indent=2));tmp=state/'last_attempt.tmp';tmp.write_text(json.dumps(result,indent=2));os.replace(tmp,state/'last_attempt.json');print(json.dumps(result))
    if result['status']=='SUCCESS':prune_generated_bundles(state)
    lock.close();return 0 if result['status']=='SUCCESS' else 1

if __name__=='__main__':raise SystemExit(main())
