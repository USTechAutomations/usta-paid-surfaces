#!/usr/bin/env python3
'''Read sealed FDA CSVs through the estate renderer and its existing gates.'''
from __future__ import annotations
import argparse, csv, html, io, json, os, re, sys, tempfile, urllib.parse
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_family as house
from collect_fda_device_establishment_week import BET_ID, KILL_DATE, STATE, BUSINESS, COLUMNS, DELTA_COLUMNS, COMPARE, csv_bytes, sha, key
FAMILY=BET_ID
SAMPLE_CAP=25
SAMPLE_COLUMNS=tuple(c for c in DELTA_COLUMNS if c!='name')
PAIR=re.compile(r'^what_changed_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{4}-[0-9]{2}-[0-9]{2})[.]csv$')

def read_csv(path,columns):
    blob=path.read_bytes(); reader=csv.DictReader(io.StringIO(blob.decode('utf-8')))
    if tuple(reader.fieldnames or ())!=tuple(columns): raise ValueError('unexpected CSV schema: '+path.name)
    rows=list(reader); seen=set()
    for r in rows:
        if None in r or any(v is None for v in r.values()): raise ValueError('invalid CSV width')
        if not BUSINESS.search(r['name']): raise ValueError('person-like name in sealed CSV')
        if any(any(ord(c)<32 for c in v) or v.startswith(('=','+','-','@')) for v in r.values()): raise ValueError('unsafe CSV value')
        if not all(key(r)) or key(r) in seen: raise ValueError('duplicate or missing identity')
        seen.add(key(r))
    return blob,rows

class Data:
    def __init__(self,state=STATE):
        self.state=Path(state); self.rows=[]; self.latest=None
        snapshots=sorted(self.state.glob('snapshot_*.csv')); self.dates=[]
        for p in snapshots:
            day=p.stem.removeprefix('snapshot_'); date.fromisoformat(day); self.dates.append(day)
        self.newest=self.dates[-1] if self.dates else None
        pairs=[]
        for p in self.state.glob('what_changed_*.csv'):
            m=PAIR.fullmatch(p.name)
            if not m: raise ValueError('malformed comparison filename')
            old,new=m.groups(); date.fromisoformat(old); date.fromisoformat(new)
            if old>=new: raise ValueError('unordered export dates')
            pairs.append((new,old,p))
        if not pairs:
            if snapshots: self.snapshot(self.newest)
            return
        new,old,path=max(pairs)
        if self.newest!=new: raise ValueError('latest snapshot lacks comparison; refusing stale sample')
        meta=json.loads(path.with_suffix('.json').read_text()); blob,self.rows=read_csv(path,DELTA_COLUMNS)
        if meta.get('sha256')!=sha(blob) or meta.get('older')!=old or meta.get('newer')!=new or meta.get('changes')!=len(self.rows): raise ValueError('comparison metadata mismatch')
        for day in (old,new):
            if meta.get('snapshot_hashes',{}).get(day)!=sha(self.snapshot(day)): raise ValueError('comparison snapshot hash mismatch')
        for r in self.rows:
            fields=r['changed_fields'].split(';') if r['changed_fields'] else []
            if r['week_ending']!=new or r['change'] not in ('appeared','vanished','changed'): raise ValueError('invalid delta row')
            if r['change']=='changed':
                if not fields or len(fields)!=len(set(fields)) or not set(fields)<=set(COMPARE): raise ValueError('invalid changed fields')
            elif fields: raise ValueError('unexpected changed fields')
        self.latest=(old,new)

    def snapshot(self,day):
        p=self.state/f'snapshot_{day}.csv'; blob,rows=read_csv(p,COLUMNS); meta=json.loads(p.with_suffix('.json').read_text())
        if not rows or meta.get('snapshot_sha256')!=sha(blob) or meta.get('export_date')!=day or meta.get('eligible_establishments')!=len(rows): raise ValueError('snapshot metadata mismatch')
        if any(r['week_ending']!=day for r in rows): raise ValueError('snapshot date mismatch')
        return blob

    @property
    def vanished(self):
        return sorted((r for r in self.rows if r['change']=='vanished'),key=key)[:SAMPLE_CAP]

_DATA=None
def data(): return _DATA if _DATA is not None else Data()
def slices(): return []
def sample():
    return list(SAMPLE_COLUMNS),[[r[c] for c in SAMPLE_COLUMNS] for r in data().vanished]

def family_spec():
    d=data(); row=house.fam_row(FAMILY)
    if not row: raise ValueError('family missing from catalog')
    if row.get('checkout',{}).get('url')!='TO-MINT': raise ValueError('staged family requires TO-MINT checkout')
    if d.latest:
        old,new=d.latest
        lede=f'FDA device establishment exports dated {old} and {new}, compared. The table shows eligible business registrations present in the earlier export and absent from the later export.'
        head=['Export date','Registration','Business','City','State','Country','Establishment operations']
        cells=[[html.escape(r[c]) for c in ('week_ending','registration_number','name','city','state_code','iso_country_code','establishment_types')] for r in d.vanished]
        body=house.table(head,cells,f'{len(d.vanished)} vanished business registrations shown',old+' to '+new)
        status='Dated comparison available; checkout unavailable'
    else:
        lede='Weekly registration changes are UNKNOWN: a genuine earlier export is needed before a vanished-firms sample can be shown.'
        body='<p>No historical comparison is available. This is not evidence that no firms vanished.</p>'
        if d.newest: body+='<p>Baseline export date: '+html.escape(d.newest)+'.</p>'
        status='Historical comparison UNKNOWN'
    sections=[house.section('Vanished from the latest compared export','',body),
        house.section('What the weekly file contains','',
            '<p>A dated CSV of business establishments that appeared, vanished, or changed between exports. Changed rows identify the fields that differ. Repeated product listings are grouped by registration number and FEI; product codes are counted once.</p>'),
        house.section('Scope and source','',
            '<p>Source: <a href=https://open.fda.gov/apis/device/registrationlisting/>openFDA device registration and listing bulk exports</a>. Absence from an export does not prove permanent closure, noncompliance, or loss of authorization. Registration does not mean FDA approval.</p>'
            '<p>Names without a recognized business word and records missing establishment identifiers are excluded. Conflicting duplicate identities and spreadsheet-unsafe values are also withheld. The downloadable sample contains only vanished rows and omits the firm name; the table retains eligible business names. Street addresses, postal codes, agents and contact details are excluded.</p>'
            '<p>Planned refresh: Monday after the weekly FDA export. Checkout and automated subscriber delivery are not connected. Missing or invalid source data withholds a comparison.</p>')]
    return dict(id=FAMILY,ready=False,group=row['group'],cadence=row['cadence'],cadence_long=row['cadence_long'],
        crumb='Device establishment changes',h1='FDA device establishment weekly changes',buyer=html.escape(row['buyer']),
        desc='Dated FDA device establishment changes: appeared, vanished and changed registrations. Business-only CSV; historical sample pending.',
        lede=lede,pill_label=status,pill_text=status,sections=sections,sample_dt='Historical sample',
        subj=urllib.parse.quote('FDA device establishment weekly file'),contact_h2='Availability',
        contact_p='This draft has no checkout or automated delivery. The proposed subscription price is shown above.',
        contact_cta='Ask about availability',contact_note='No payment can be taken from this page.',
        hero_note='Checkout unavailable. Historical sample remains gated until a genuine dated comparison is reviewed.',
        delivery='Checkout and automated delivery are not connected.',
        foot='Rows describe differences between dated FDA exports. Missing history stays UNKNOWN; test fixtures are not historical evidence.')

def write_outputs(state,out):
    global _DATA
    _DATA=Data(state); headers,values=sample(); spec=family_spec(); out.mkdir(parents=True,exist_ok=True); dest=out/'index.html'
    if dest.exists() and house.DO_NOT_RUN in dest.read_text()[:800]: raise ValueError('existing page forbids regeneration')
    if len(spec['desc'])>house.MAX_DESC: raise ValueError('description exceeds house limit')
    page=house.render(spec)
    artifacts={'sample.csv':csv_bytes(headers,[dict(zip(headers,v)) for v in values]),'index.html':page.encode('utf-8')}
    for name in artifacts:
        if (out/name).is_symlink(): raise ValueError('symlink output refused')
    for name,blob in artifacts.items():
        fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=out)
        with os.fdopen(fd,'wb') as f: f.write(blob)
        os.replace(tmp,out/name)
    print(json.dumps({'sample_rows':len(values),'comparison':_DATA.latest or 'UNKNOWN','checkout':'TO-MINT'}))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--state',type=Path,default=STATE)
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'families'/FAMILY); a=p.parse_args()
    try: write_outputs(a.state,a.out)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print('REFUSED: '+str(exc),file=sys.stderr); return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
