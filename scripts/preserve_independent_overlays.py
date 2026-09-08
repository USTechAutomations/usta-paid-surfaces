#!/usr/bin/env python3
"""Retain registered independent /feeds components during a full estate rebuild.

A missing or changed current component is a refusal, never implicit permission to
remove it. Component changes use their own preserving release workflow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
import xml.etree.ElementTree as ET

REGISTRY = Path.home()/'.hermes/config/surface_registry.json'
RECEIPT = '.independent-overlay-receipt.json'
GCLOUD_BIN = 'gcloud'
MARKERS = {'pathlab-20260908-b': 'pathlab-independent-20260908',
           'workshop-20260908-c': 'workshop-independent-20260908'}

def inventory(root):
    root=Path(root); result={}
    if root.is_symlink() or not root.is_dir(): raise ValueError('Missing ordinary component directory')
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Component symlink refused')
        if path.is_file():
            if path.stat().st_size > 64*1024**2 or len(result)>10000: raise ValueError('Component bounds exceeded')
            result[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    if not result: raise ValueError('Empty component')
    return result

def components(registry):
    surfaces=[x for x in registry['side_surfaces'] if x['prefix']=='/feeds']
    if len(surfaces)!=1: raise ValueError('Missing unique feeds registry')
    rows=surfaces[0].get('components',[])
    for row in rows:
        if row['id'] not in MARKERS: raise ValueError('New component needs explicit preservation mapping')
        if not row.get('prefixes') or any(not re.fullmatch(r'/feeds/[a-z0-9-]+/',p) for p in row['prefixes']): raise ValueError('Invalid component prefixes')
    if len({p for r in rows for p in r['prefixes']})!=sum(len(r['prefixes']) for r in rows): raise ValueError('Overlapping component routes')
    return rows

def location_blocks(text):
    """Read complete top-level location blocks without treating quoted JSON as nginx."""
    blocks=[]
    for match in re.finditer(r'^  location\s+([^\n{]+)\{',text,re.M):
        depth=1; quote=None; escape=False; end=match.end()
        while end<len(text) and depth:
            c=text[end]
            if escape: escape=False
            elif c=='\\': escape=True
            elif quote:
                if c==quote:quote=None
            elif c in ('"',"'"):quote=c
            elif c=='{':depth+=1
            elif c=='}':depth-=1
            end+=1
        if depth or quote:raise ValueError('Unclosed nginx location')
        blocks.append((match.group(1).strip(),text[match.start():end]+'\n'))
    return blocks

def selected_blocks(text,slugs):
    selected=[]
    for spec,block in location_blocks(text):
        fields=spec.split();route=fields[-1]
        if any(route==('/'+s) or route.startswith('/'+s+'/') for s in slugs): selected.append((spec,block))
    for slug in slugs:
        if not any(spec=='= /'+slug for spec,_ in selected) or not any(spec=='^~ /'+slug+'/' for spec,_ in selected): raise ValueError('Missing current component route '+slug)
    return selected

def sitemap_urls(text):
    return [e.text for e in ET.fromstring(text).iter() if e.tag.split('}')[-1]=='loc']

def overlay(current,candidate,rows,head):
    current=Path(current);candidate=Path(candidate)
    current_nginx=(current/'nginx.conf').read_text();candidate_nginx=(candidate/'nginx.conf').read_text()
    hub=(candidate/'site/index.html').read_text();source_hub=(current/'site/index.html').read_text()
    sitemap=(candidate/'site/sitemap.xml').read_text();source_urls=sitemap_urls((current/'site/sitemap.xml').read_text())
    if candidate_nginx.count('  location / {')!=1 or hub.count('</body>')!=1 or sitemap.count('</urlset>')!=1:raise ValueError('Candidate layout changed')
    expected={};retained=[];sections=[];all_blocks=[]
    # Validate everything before mutating the candidate.
    for row in rows:
        slugs=[p.split('/')[2] for p in row['prefixes']]
        blocks=selected_blocks(current_nginx,slugs)
        if not any(spec=='^~ /'+slugs[0]+'/api/' for spec,_ in blocks):raise ValueError('Missing current component API route')
        if any(any(('/'+s) in spec.split()[-1] for s in slugs) for spec,_ in location_blocks(candidate_nginx)):raise ValueError('Candidate component route collision')
        section=re.findall(r'<section id="'+re.escape(MARKERS[row['id']])+r'">.*?</section>\n?',source_hub,re.S)
        if len(section)!=1 or MARKERS[row['id']] in hub:raise ValueError('Missing current or colliding candidate component hub link')
        if 'href="'+row['prefixes'][0]+'"' not in section[0]:raise ValueError('Current hub section lacks required href')
        for prefix in row['prefixes']:
            url='https://ustechautomations.com'+prefix
            if source_urls.count(url)!=1:raise ValueError('Current component lacks unique admitted sitemap entry')
            retained.append(url)
        for slug in slugs:
            facts=inventory(current/'site'/slug)
            if (candidate/'site'/slug).exists():raise ValueError('Candidate component file collision')
            expected.update({slug+'/'+name:digest for name,digest in facts.items()})
        sections.extend(section);all_blocks.extend(blocks)
    for row in rows:
        for prefix in row['prefixes']:
            slug=prefix.split('/')[2];shutil.copytree(current/'site'/slug,candidate/'site'/slug)
    blocks=''.join(block for _,block in all_blocks)
    # Keep the Workshop release markers recognized by its corrective release tool.
    workshop=next((r for r in rows if r['id']=='workshop-20260908-c'),None)
    if workshop:
        ws=set(p.split('/')[2] for p in workshop['prefixes'])
        wb=[block for spec,block in all_blocks if any(spec.split()[-1]=='/'+s or spec.split()[-1].startswith('/'+s+'/') for s in ws)]
        others=[block for spec,block in all_blocks if block not in wb]
        blocks=''.join(others)+'  # workshop-c begin\n'+''.join(wb)+'  # workshop-c end\n'
    (candidate/'nginx.conf').write_text(candidate_nginx.replace('  location / {',blocks+'  location / {',1))
    (candidate/'site/index.html').write_text(hub.replace('</body>',''.join(sections)+'</body>',1))
    existing=sitemap_urls(sitemap)
    if any(existing.count(u)>1 for u in retained):raise ValueError('Duplicate candidate sitemap URL')
    additions=''.join('<url><loc>'+u+'</loc></url>' for u in retained if u not in existing)
    (candidate/'site/sitemap.xml').write_text(sitemap.replace('</urlset>',additions+'</urlset>'))
    receipt={'head':head,'component_files':expected,'sitemap_urls':retained,'markers':[MARKERS[r['id']] for r in rows],
             'hub_sections':sections,'nginx_sha256':hashlib.sha256((candidate/'nginx.conf').read_bytes()).hexdigest()}
    (candidate/RECEIPT).write_text(json.dumps(receipt,indent=2))
    check_candidate(candidate,receipt)
    return receipt

def check_candidate(candidate,receipt):
    candidate=Path(candidate)
    for name,digest in receipt['component_files'].items():
        path=candidate/'site'/name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Candidate component changed: '+name)
    if hashlib.sha256((candidate/'nginx.conf').read_bytes()).hexdigest()!=receipt['nginx_sha256']:raise ValueError('Candidate nginx changed')
    urls=sitemap_urls((candidate/'site/sitemap.xml').read_text());hub=(candidate/'site/index.html').read_text()
    if any(urls.count(u)!=1 for u in receipt['sitemap_urls']) or any(hub.count(m)!=1 for m in receipt['markers']) or any(hub.count(section)!=1 for section in receipt['hub_sections']):raise ValueError('Candidate discovery changed')

def gcloud(account,*args):
    return json.loads(subprocess.check_output([GCLOUD_BIN,*args,'--project','usta-prod','--account',account,'--format=json']))

def current_head(account):
    service=gcloud(account,'run','services','describe','usta-feeds','--region','us-central1')
    if not any(c.get('type')=='Ready' and c.get('status')=='True' for c in service['status'].get('conditions',[])):raise ValueError('Feeds service transition incomplete; preserve after it settles')
    traffic=service['status'].get('traffic',[])
    serving=[row for row in traffic if row.get('percent',0)>0]
    if len(serving)!=1 or serving[0].get('percent')!=100:raise ValueError('Split or unknown feeds traffic; cannot choose a preservation base')
    revision=serving[0].get('revisionName')
    if not revision:raise ValueError('Missing serving revision identity')
    detail=gcloud(account,'run','revisions','describe',revision,'--region','us-central1')
    image=detail['status']['imageDigest']
    if not re.fullmatch(r'gcr.io/usta-prod/usta-feeds@sha256:[0-9a-f]{64}',image):raise ValueError('Unowned or mutable current image')
    return {'revision':revision,'generation':service['metadata']['generation'],'image':image}

def prepare(candidate,account):
    rows=components(json.loads(REGISTRY.read_text()));head=current_head(account)
    with tempfile.TemporaryDirectory(prefix='usta-feeds-preserve-') as folder:
        work=Path(folder);env={**os.environ,'DOCKER_CONFIG':str(work/'docker')};(work/'docker').mkdir()
        token=subprocess.check_output([GCLOUD_BIN,'auth','print-access-token','--account',account])
        subprocess.run(['docker','login','gcr.io','-u','oauth2accesstoken','--password-stdin'],input=token,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        subprocess.run(['docker','pull',head['image']],env=env,stdout=subprocess.DEVNULL,check=True)
        cid=subprocess.check_output(['docker','create',head['image']]).decode().strip()
        source=work/'current';(source/'site').mkdir(parents=True)
        try:
            for name in ('index.html','sitemap.xml',*[p.split('/')[2] for r in rows for p in r['prefixes']]):
                subprocess.run(['docker','cp',cid+':/usr/share/nginx/html/'+name,str(source/'site'/name)],check=True)
            subprocess.run(['docker','cp',cid+':/etc/nginx/conf.d/default.conf',str(source/'nginx.conf')],check=True)
        finally:subprocess.run(['docker','rm',cid],stdout=subprocess.DEVNULL,check=True)
        receipt=overlay(source,candidate,rows,head)
    print(json.dumps({'preserved_component_files':len(receipt['component_files']),'base':head}))

def main():
    global GCLOUD_BIN
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','check-head','verify-public'));parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--account',default='admin@ustechautomations.com');parser.add_argument('--gcloud',default='gcloud');args=parser.parse_args();GCLOUD_BIN=args.gcloud
    if args.action=='prepare':prepare(args.candidate,args.account);return
    receipt=json.loads((args.candidate/RECEIPT).read_text());check_candidate(args.candidate,receipt)
    if args.action=='check-head':
        if current_head(args.account)!=receipt['head']:raise ValueError('Current feeds head changed; rebuild preserving the newer image')
    else:
        for name,digest in receipt['component_files'].items():
            with urlopen('https://ustechautomations.com/feeds/'+name,timeout=30) as response:
                if response.status!=200 or hashlib.sha256(response.read(64*1024**2+1)).hexdigest()!=digest:raise ValueError('Public component byte mismatch: '+name)
        with urlopen('https://ustechautomations.com/feeds/sitemap.xml',timeout=30) as response:urls=sitemap_urls(response.read())
        with urlopen('https://ustechautomations.com/feeds/',timeout=30) as response:hub=response.read(4*1024**2).decode()
        if any(urls.count(u)!=1 for u in receipt['sitemap_urls']) or any(hub.count(m)!=1 for m in receipt['markers']) or any(hub.count(section)!=1 for section in receipt['hub_sections']):raise ValueError('Public component discovery mismatch')
    print(json.dumps({'status':'PASS','action':args.action,'component_files':len(receipt['component_files'])}))

if __name__=='__main__':main()
