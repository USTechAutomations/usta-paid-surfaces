# bet_id: fda-device-establishment-week; kill_date: 2026-10-08
import copy, csv, hashlib, importlib.util, io, json, os, re, subprocess, sys, tempfile, unittest, zipfile
from collections import Counter
from pathlib import Path
ROOT=Path(os.environ.get('FDA_FIXTURE_ROOT',Path(__file__).resolve().parent if Path(__file__).resolve().parent.name!='tests' else Path(__file__).resolve().parents[2]))
WT=Path(os.environ.get('FDA_WORKTREE',ROOT/'wt-feeds-fda-device-establishment-week'))
COLLECT=WT/'scripts/collect_fda_device_establishment_week.py'
SLICE=WT/'scripts/slice_fda_device_establishment_week.py'
REAL=ROOT/'raw/export_2026-09-07'
ALLOWED={'week_ending','fei_number','registration_number','owner_operator_number','name','city','state_code','iso_country_code','establishment_types','status_code','reg_expiry_date_year','product_code_count','change','changed_fields'}

def run_logged(cmd, **kwargs):
    result=subprocess.run(cmd, **kwargs)
    with (ROOT/'subprocess-exits.jsonl').open('a') as f:
        f.write(json.dumps({'command':[str(x) for x in cmd],'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})+chr(10))
    return result

def rows(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))

def export(root,day,records,parts=2):
    folder=root/('export_'+day); folder.mkdir(parents=True,exist_ok=True)
    for i in range(parts):
        with zipfile.ZipFile(folder/f'part-{i+1}-of-{parts}.zip','w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('data.json',json.dumps({'meta':{'export_date':day},'results':records[i::parts]}))
    (folder/'manifest.json').write_text(json.dumps({'parts':parts,'records':len(records)}))

class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert COLLECT.exists(), 'collector absent: implement the named artifact first'
        (ROOT/'test-artifacts').mkdir(exist_ok=True)
        unique={}
        for file in sorted(REAL.glob('*.zip')):
            with zipfile.ZipFile(file) as z:
                for member in z.namelist():
                    if not member.endswith('.json'): continue
                    for record in json.loads(z.read(member))['results']:
                        reg=record.get('registration',{})
                        key=(reg.get('registration_number'),reg.get('fei_number'))
                        if all(key) and key not in unique:
                            unique[key]=record
                        if len(unique)==305: break
                    if len(unique)==305: break
            if len(unique)==305: break
        assert len(unique)==305, 'insufficient eligible source fixtures'
        cls.selected=list(unique.values())
        (ROOT/'fixture-evidence.json').write_text(json.dumps({'fixture_kind':'synthetic temporal comparison using real records; NOT historical FDA changes','source':str(REAL),'selected_unique':len(unique)},indent=2))

    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp(prefix='fda-',dir=ROOT/'test-artifacts'))
        self.src=self.tmp/'raw'; self.out=self.tmp/'out'
        self.old=copy.deepcopy(self.selected[:300]); self.new=copy.deepcopy(self.selected[5:305])
        for r in self.new[:3]: r['registration']['status_code']='TEST_CHANGED'
        export(self.src,'2026-08-31',self.old); export(self.src,'2026-09-07',self.new)

    def run_collector(self,ok=True):
        p=run_logged([sys.executable,'-B',str(COLLECT),'--offline',str(self.src),'--out',str(self.out)],capture_output=True,text=True)
        with (ROOT/'acceptance-exits.jsonl').open('a') as f: f.write(json.dumps({'test':self.id(),'tool':'collector','exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})+'\n')
        if ok: self.assertEqual(p.returncode,0,p.stderr)
        else: self.assertNotEqual(p.returncode,0,p.stdout)
        return p

    def test_known_good_counts_fields_and_privacy(self):
        self.run_collector()
        changed=rows(self.out/'what_changed_2026-08-31_2026-09-07.csv')
        self.assertEqual(Counter(r['change'] for r in changed),{'vanished':5,'appeared':5,'changed':3})
        self.assertTrue(all(r['changed_fields']=='status_code' for r in changed if r['change']=='changed'))
        for p in self.out.glob('*.csv'):
            with p.open() as f: headers=next(csv.reader(f))
            self.assertTrue(set(headers)<=ALLOWED,headers)
            self.assertFalse(any(re.search('address|zip|postal|agent',c,re.I) for c in headers))
        before={p.name:p.read_bytes() for p in self.out.iterdir() if p.is_file() and p.suffix in ('.csv','.json')}
        self.run_collector()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.out.iterdir() if p.is_file() and p.suffix in ('.csv','.json')})

    def test_empty_newer_refused_without_false_vanished(self):
        export(self.src,'2026-09-07',[])
        self.run_collector(False)
        self.assertFalse(list(self.out.glob('*.csv')))

    def test_malformed_and_incomplete_refused(self):
        self.new[0]['registration']=[]
        export(self.src,'2026-09-07',self.new)
        self.run_collector(False)
        self.assertFalse(list(self.out.glob('*.csv')))
        export(self.src,'2026-09-07',self.selected[:300])
        (self.src/'export_2026-09-07/part-2-of-2.zip').rename(self.tmp/'quarantined-part.zip')
        self.run_collector(False)
        self.assertFalse(list(self.out.glob('*.csv')))

    def test_listing_duplicates_aggregated_and_names_kept(self):
        duplicate=copy.deepcopy(self.old[1]); duplicate['products']=[{'product_code':'ZZZ'}]
        export(self.src,'2026-08-31',self.old+[duplicate])
        export(self.src,'2026-09-07',self.old+[duplicate,duplicate])
        self.run_collector()
        snap=rows(self.out/'snapshot_2026-09-07.csv')
        self.assertEqual(len(snap),300)
        self.assertEqual(rows(self.out/'what_changed_2026-08-31_2026-09-07.csv'),[])
        self.assertEqual({r['name'] for r in snap},{r['registration']['name'].strip() for r in self.old})
        meta=json.loads((self.out/'snapshot_2026-09-07.json').read_text())
        self.assertNotIn('dropped_listing_records',meta); self.assertEqual(meta['source_records'],302)

    def test_fetch_writes_dated_export_atomically(self):
        spec=importlib.util.spec_from_file_location('collector',COLLECT); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        parts={}
        for i in range(2):
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z: z.writestr('data.json',json.dumps({'meta':{'export_date':'2026-09-14'},'results':self.new[i::2]}))
            parts[f'https://download.open.fda.gov/device/registrationlisting/device-registrationlisting-000{i+1}-of-0002.json.zip']=buf.getvalue()
        index=json.dumps({'results':{'device':{'registrationlisting':{'export_date':'2026-09-14','total_records':len(self.new),
            'partitions':[{'file':u,'records':1} for u in parts]}}}}).encode()
        calls=[]
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*a): return False
        def opener(url,timeout=0):
            calls.append(url)
            if url==mod.SOURCE: return Resp(index)
            if url in parts: return Resp(parts[url])
            raise OSError('unexpected url '+url)
        root=self.tmp/'fetched'
        folder=mod.fetch_export(root,opener=opener)
        self.assertEqual(folder,root/'export_2026-09-14'); self.assertEqual(len(calls),3)
        self.assertEqual(sorted(p.name for p in folder.iterdir()),['device-registrationlisting-0001-of-0002.json.zip','device-registrationlisting-0002-of-0002.json.zip','manifest.json'])
        self.assertFalse([p for p in root.iterdir() if p.name.startswith('.pending')])
        self.assertEqual(mod.fetch_export(root,opener=opener),folder); self.assertEqual(len(calls),4)
        day,result,meta,_=mod.read_export(folder); self.assertEqual((day,len(result)),('2026-09-14',300))
        def broken(url,timeout=0):
            if url==mod.SOURCE: return Resp(index)
            raise OSError('network down')
        with self.assertRaises(OSError): mod.fetch_export(self.tmp/'fetched2',opener=broken)
        self.assertFalse([p for p in (self.tmp/'fetched2').iterdir()])
        p=run_logged([sys.executable,'-B',str(COLLECT),'--out',str(self.tmp/'noargs')],capture_output=True,text=True); self.assertEqual(p.returncode,2)

    def test_snapshot_immutable_and_concurrent_lock(self):
        self.run_collector()
        before=(self.out/'snapshot_2026-09-07.csv').read_bytes()
        self.new[0]['registration']['status_code']='DRIFT'
        export(self.src,'2026-09-07',self.new)
        self.run_collector(False)
        self.assertEqual((self.out/'snapshot_2026-09-07.csv').read_bytes(),before)
        import fcntl
        with (self.out/'.collector.lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.run_collector(False)

    def test_slicer_sample_and_page(self):
        self.run_collector()
        page=self.tmp/'family'
        p=run_logged([sys.executable,'-B',str(SLICE),'--state',str(self.out),'--out',str(page)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        sample=rows(page/'sample.csv')
        self.assertEqual(Counter(r['change'] for r in sample),{'vanished':5,'appeared':5,'changed':3})
        self.assertIn('name',sample[0]); self.assertTrue(set(sample[0])<=ALLOWED)
        blob=json.loads((page/'sample.json').read_text()); self.assertEqual(blob['rows_published'],13); self.assertEqual(blob['headers'],list(sample[0]))
        self.assertIn('Sample ready',body:=(page/'index.html').read_text()); self.assertNotIn('Sample not ready',body)
        body=(page/'index.html').read_text()
        import html
        for r in self.old[:5]: self.assertIn(html.escape(r['registration']['name']),body)
        self.assertNotIn('https://buy.stripe.com',body)
        self.assertNotIn('ttb-new-permits',body)
        self.assertNotIn('TEST_CHANGED',body)

    def test_baseline_is_unknown_not_zero(self):
        baseline=self.tmp/'baseline'; export(baseline,'2026-09-07',self.new)
        self.src=baseline; p=self.run_collector()
        self.assertIn('UNKNOWN',p.stdout)
        self.assertFalse(list(self.out.glob('what_changed_*.csv')))
        page=self.tmp/'baseline-page'
        p=run_logged([sys.executable,'-B',str(SLICE),'--state',str(self.out),'--out',str(page)],capture_output=True,text=True)
        # The catalog clears a public sample; one copy cannot produce one. A page saying
        # both "sample ready" and "not ready" is a lie, so the slicer refuses to write it.
        self.assertEqual(p.returncode,2,p.stdout); self.assertIn('one copy held',p.stderr)
        self.assertFalse(page.exists())

    def test_excluded_identity_never_becomes_false_vanished(self):
        conflict=copy.deepcopy(self.new[0]); conflict['registration']['name']='Conflicting Owner Medical Inc'
        unsafe=copy.deepcopy(self.new[1]); unsafe['registration']['city']='=HYPERLINK(unsafe)'
        missing=copy.deepcopy(self.new[3]); missing['registration'].update(registration_number='',fei_number='')
        export(self.src,'2026-09-07',self.new+[conflict,unsafe,missing])
        self.run_collector()
        delta=rows(self.out/'what_changed_2026-08-31_2026-09-07.csv')
        excluded={r['registration']['registration_number'] for r in (conflict,unsafe)}
        self.assertFalse(any(r['registration_number'] in excluded for r in delta))
        current=rows(self.out/'snapshot_2026-09-07.csv')
        self.assertFalse(any(r['registration_number'] in excluded for r in current))
        meta=json.loads((self.out/'snapshot_2026-09-07.json').read_text())
        self.assertEqual(meta['conflicting_identities'],1)
        self.assertEqual(meta['unsafe_listing_records'],1)
        self.assertEqual(meta['missing_identity_records'],1)

    def test_sample_cap_escape_and_tamper_refusal(self):
        visible=min(self.old[:30],key=lambda r:(str(r['registration']['registration_number']),str(r['registration']['fei_number'])))
        visible['registration']['name']='<script>alert(1)</script> Medical Inc'
        export(self.src,'2026-08-31',self.old)
        export(self.src,'2026-09-07',self.selected[30:305])
        self.run_collector()
        page=self.tmp/'capped'
        cmd=[sys.executable,'-B',str(SLICE),'--state',str(self.out),'--out',str(page)]
        p=run_logged(cmd,capture_output=True,text=True); self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(len(rows(page/'sample.csv')),25)
        body=(page/'index.html').read_text(); self.assertNotIn('<script>alert',body); self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; Medical Inc',body)
        delta=self.out/'what_changed_2026-08-31_2026-09-07.csv'
        delta.write_text(delta.read_text().replace('vanished','appeared',1))
        before=(page/'index.html').read_bytes()
        p=run_logged(cmd,capture_output=True,text=True); self.assertNotEqual(p.returncode,0)
        self.assertIn('metadata mismatch',p.stderr); self.assertEqual((page/'index.html').read_bytes(),before)

    def test_missing_and_invalid_json_refused(self):
        self.src=self.tmp/'absent'
        self.run_collector(False); self.assertFalse(list(self.out.glob('*.csv')))
        self.src=self.tmp/'broken'; export(self.src,'2026-09-07',self.old)
        with zipfile.ZipFile(self.src/'export_2026-09-07/part-1-of-2.zip','w') as z:
            z.writestr('data.json','{broken')
        self.run_collector(False); self.assertFalse(list(self.out.glob('*.csv')))

    def test_catalog_contract(self):
        bet=json.loads((ROOT/'BET.json').read_text())
        catalog=json.loads((WT/'catalog.json').read_text())
        matching=[r for r in catalog['families'] if r['id']=='fda-device-establishment-week']
        self.assertEqual(len(matching),1)
        self.assertEqual(matching[0]['price'],bet['price'])
        self.assertEqual(matching[0]['checkout']['url'],'TO-MINT')

if __name__=='__main__': unittest.main()
