#!/usr/bin/env python3
'''Read sealed FDA CSVs through the estate renderer and its existing gates.'''
from __future__ import annotations
import argparse, csv, datetime as dt, html, io, json, os, re, sys, tempfile, urllib.parse
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_family as house
from collect_fda_device_establishment_week import BET_ID, KILL_DATE, STATE, COLUMNS, DELTA_COLUMNS, COMPARE, csv_bytes, sha, key
FAMILY=BET_ID
SAMPLE_CAP=25
TABLE_CAP=12
SAMPLE_COLUMNS=DELTA_COLUMNS
SAMPLE_MIX=(('vanished',10),('appeared',10),('changed',5))
PAIR=re.compile(r'^what_changed_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{4}-[0-9]{2}-[0-9]{2})[.]csv$')

def _d(iso):
    return dt.date.fromisoformat(iso).strftime('%-d %B %Y')

def read_csv(path,columns):
    blob=path.read_bytes(); reader=csv.DictReader(io.StringIO(blob.decode('utf-8')))
    if tuple(reader.fieldnames or ())!=tuple(columns): raise ValueError('unexpected CSV schema: '+path.name)
    rows=list(reader); seen=set()
    for r in rows:
        if None in r or any(v is None for v in r.values()): raise ValueError('invalid CSV width')
        if any(any(ord(c)<32 for c in v) or v.startswith(('=','+','-','@')) for v in r.values()): raise ValueError('unsafe CSV value')
        if not all(key(r)) or key(r) in seen: raise ValueError('duplicate or missing identity')
        seen.add(key(r))
    return blob,rows

class Data:
    def __init__(self,state=STATE):
        self.state=Path(state); self.rows=[]; self.latest=None; self.sizes={}
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
        self.sizes[day]=len(rows)
        return blob

    def kind(self,change):
        return sorted((r for r in self.rows if r['change']==change),key=key)

    @property
    def vanished(self):
        return self.kind('vanished')[:SAMPLE_CAP]

    @property
    def sample_rows(self):
        out=[]
        for change,cap in SAMPLE_MIX: out+=self.kind(change)[:cap]
        for change,cap in SAMPLE_MIX:
            if len(out)>=SAMPLE_CAP: break
            out+=self.kind(change)[cap:cap+SAMPLE_CAP-len(out)]
        return out[:SAMPLE_CAP]

_DATA=None
def data(): return _DATA if _DATA is not None else Data()
def slices(): return []
def sample():
    return list(SAMPLE_COLUMNS),[[r[c] for c in SAMPLE_COLUMNS] for r in data().sample_rows]

HEAD=['Registration','Business','City','State','Country','What it does']
CELLS=('registration_number','name','city','state_code','iso_country_code','establishment_types')
def _cells(rows):
    return [[html.escape(r[c]) for c in CELLS] for r in rows]

def family_spec():
    d=data(); row=house.fam_row(FAMILY)
    if not row: raise ValueError('family missing from catalog')
    if row.get('checkout',{}).get('url')!='TO-MINT': raise ValueError('staged family requires TO-MINT checkout')
    if d.latest:
        old,new=d.latest; stamp=f'{_d(old)} to {_d(new)}'
        gone=d.kind('vanished'); came=d.kind('appeared'); moved=d.kind('changed')
        days=(date.fromisoformat(new)-date.fromisoformat(old)).days
        desc=(f'{len(gone)} FDA device establishments stopped being registered and {len(came)} appeared '
              f'between {_d(old)} and {_d(new)}. One national file a week. $49/mo.')
        lede=(f'Between {_d(old)} and {_d(new)}, {len(came):,} device establishments appeared on the FDA register, '
              f'{len(gone):,} stopped being listed, and {len(moved):,} changed a detail. Every one is in the file; '
              f'the first rows of each kind are printed below with the two export dates they came from.')
        secs=[house.section(f'Establishments that stopped being listed between {_d(old)} and {_d(new)}',f'{len(gone):,} establishments',
                f'<p>The FDA publishes its whole device establishment register and overwrites it every week. We seal a dated copy and compare it '
                f'with the one before. <strong>These {len(gone):,} registrations are in the {_d(old)} copy and not in the {_d(new)} one.</strong> '
                f'Whether the firm closed, let its registration lapse, or the FDA rebuilt its file, we did not see and will not imply.</p>\n'
                +house.table(HEAD,_cells(gone[:TABLE_CAP]),f'{min(TABLE_CAP,len(gone))} of the {len(gone):,} that stopped being listed',stamp)),
              house.section(f'Establishments that appeared between {_d(old)} and {_d(new)}',f'{len(came):,} establishments',
                f'<p>In the {_d(new)} copy and not in the {_d(old)} one. New manufacturers, importers and repackagers, at home and abroad, '
                f'the week they show up.</p>\n'
                +house.table(HEAD,_cells(came[:TABLE_CAP]),f'{min(TABLE_CAP,len(came))} of the {len(came):,} that appeared',stamp)),
              house.section('Establishments whose details changed',f'{len(moved):,} establishments',
                f'<p>Same registration, different detail: a new owner number, a changed status, a move to another city or country, '
                f'a different set of operations, or a new expiry year. The file names the fields that changed on every row.</p>\n'
                +house.table(HEAD+['Changed'],[c+[html.escape(r["changed_fields"].replace(";", ", "))] for c,r in zip(_cells(moved[:TABLE_CAP]),moved[:TABLE_CAP])],
                             f'{min(TABLE_CAP,len(moved))} of the {len(moved):,} that changed',stamp)),
              house.section('What you get',None,
                '<ul class="spec">\n'
                '<li><strong>One national CSV every Wednesday</strong><span class="sub">Establishments that appeared, stopped being listed, '
                'or changed since the previous weekly FDA export. Every country in one file.</span></li>\n'
                '<li><strong>Fourteen columns</strong><span class="sub">Export date, FEI number, registration number, owner number, business name, city, state, '
                'country, what the site does, status, expiry year, how many product codes it lists, what kind of change, and which fields changed. '
                'No street address, no phone, no person&#39;s name.</span></li>\n'
                '<li><strong>The two export dates in every row</strong><span class="sub">So a row can be checked against the FDA register on the day.</span></li>\n'
                '<li><strong>An honest empty week</strong><span class="sub">A week with no changes is sent as 0 plus the two export dates. '
                'A week where the FDA file could not be read says so instead of repeating the last one.</span></li>\n'
                '</ul>\n<div class="honest">\n'
                f'<p><strong>The sample on this page spans {days} days, not one week.</strong> The FDA overwrites its export every week and keeps no history. '
                f'The oldest dated copy we could obtain is {_d(old)}, so the first comparison covers {_d(old)} to {_d(new)}. '
                'Weekly files start with the first pair of copies we seal ourselves, one week apart.</p>\n'
                '<p><strong>The FDA gives the register away.</strong> You can download the whole file free at '
                '<a href="https://open.fda.gov/apis/device/registrationlisting/">open.fda.gov</a> any week. What you are paying for is the comparison: '
                'the dated copy it overwrote, and the list of what moved between the two. Registration is not FDA approval, and a row that '
                'stopped being listed is not proof of closure or of anything the FDA decided.</p>\n'
                f'<p><strong>Newest copy read {_d(new)}.</strong> Rows from copies with missing identifiers, conflicting duplicates, or '
                'spreadsheet-unsafe values are left out and counted, never guessed.</p>\n</div>')]
        status='Sample ready'; ready=True
        sizes=f'{d.sizes.get(old,0):,} and {d.sizes.get(new,0):,} establishments in the two copies'
    else:
        if row.get('sample_status')=='pass': raise ValueError('catalog clears a sample this state cannot produce: one copy held, no comparison; set sample_status to unknown or seal a second copy')
        desc='FDA device establishment weekly changes: which manufacturers and importers appeared, stopped being listed, or changed. $49/mo.'
        lede='We hold one dated copy of the FDA device establishment register. Until a second copy is sealed there is nothing to compare, so no sample is shown yet.'
        secs=[house.section('Sample not ready',None,'<p>One dated copy is not a comparison. This page grows its tables the week a second copy is sealed. '
              'That is not evidence that nothing changed.</p>'+('<p>Copy held: '+html.escape(_d(d.newest))+'.</p>' if d.newest else ''))]
        status='Sample not ready'; ready=False; sizes='one copy held'
    if len(desc)>house.MAX_DESC: raise ValueError('description exceeds house limit')
    return dict(id=FAMILY,ready=ready,group=row['group'],cadence=row['cadence'],cadence_long=row['cadence_long'],
        crumb='Device establishment changes',h1='FDA device establishment changes, one national file a week',buyer=html.escape(row['buyer']),
        desc=desc,lede=lede,pill_label=status,pill_text=status,sections=secs,sample_dt='Public sample',
        subj=urllib.parse.quote('FDA device establishment weekly file'),contact_h2='Start the thread',
        contact_p='Ask which dated copies we hold. We reply with the count of appeared, gone and changed rows for the newest pair before you spend anything.',
        contact_cta='Email us for the $49/mo checkout link',contact_note='We tell you the row counts and the two export dates before you pay.',
        foot=f'Every count and date on this page was read out of the sealed copies named above: {sizes}. '
             'Nothing in the file is a person&#39;s name, street address or phone number.')

def sample_json(headers,values):
    return (json.dumps({'family':FAMILY,'generated':dt.date.today().isoformat(),
        'note':'Real rows out of dated copies we sealed ourselves. Nothing here is made up.',
        'where_these_rows_came_from':'Where these rows came from, and anything their publisher requires to be printed alongside them, is set out on the page this file came from: https://ustechautomations.com/feeds/'+FAMILY,
        'rows_published':len(values),'columns':len(headers),'headers':headers,'rows':values},indent=2)+'\n').encode('utf-8')

def write_outputs(state,out):
    global _DATA
    _DATA=Data(state); headers,values=sample(); spec=family_spec(); out.mkdir(parents=True,exist_ok=True); dest=out/'index.html'
    if dest.exists() and house.DO_NOT_RUN in dest.read_text()[:800]: raise ValueError('existing page forbids regeneration')
    def put(name,blob):
        if (out/name).is_symlink(): raise ValueError('symlink output refused')
        fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=out)
        with os.fdopen(fd,'wb') as f: f.write(blob)
        os.chmod(tmp,0o664); os.replace(tmp,out/name)
    # Sample files are settled BEFORE the page renders: the renderer counts the
    # sample's rows and columns off the disk, so the page can only describe a file
    # that is already there (same order as build_slices.write_sample).
    linked=bool(values) and house.fam_row(FAMILY).get('sample_status')=='pass'
    if linked:
        put('sample.csv',csv_bytes(headers,[dict(zip(headers,v)) for v in values])); put('sample.json',sample_json(headers,values))
    else:
        for name in ('sample.csv','sample.json'):
            if (out/name).is_file(): (out/name).unlink()
    put('index.html',house.render(spec).encode('utf-8'))
    artifacts={'sample.csv':None} if linked else {}
    print(json.dumps({'sample_rows':len(values) if 'sample.csv' in artifacts else 0,'comparison':_DATA.latest or 'UNKNOWN','checkout':'TO-MINT'}))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--state',type=Path,default=STATE)
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'families'/FAMILY); a=p.parse_args()
    try: write_outputs(a.state,a.out)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print('REFUSED: '+str(exc),file=sys.stderr); return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
