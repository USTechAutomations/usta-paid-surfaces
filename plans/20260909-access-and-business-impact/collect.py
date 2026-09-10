"""Read-only audit. Writes sanitized evidence only beside this file."""
import concurrent.futures as cf
import datetime as dt
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

OUT = Path(__file__).resolve().parent
HOME = Path('/home/gmullins')
ROOT = HOME / 'code/usta-paid-surfaces'
NOW = dt.datetime.now(dt.timezone.utc).isoformat()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]; self.title=[]; self.intitle=False
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a' and 'href' in attrs: self.links.append(attrs['href'])
        if tag=='title': self.intitle=True
    def handle_endtag(self,tag):
        if tag=='title': self.intitle=False
    def handle_data(self,data):
        self.text.append(data)
        if self.intitle: self.title.append(data)

def fetch(url):
    row={'url':url,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':None}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'USTA-owned-audit/1'})
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read(3000000); row.update(status=r.status,final_url=r.url,content_type=r.headers.get_content_type(),sha256=hashlib.sha256(raw).hexdigest())
        if row['content_type']=='text/html':
            page=Page();page.feed(raw.decode('utf8','replace'))
            text=' '.join(' '.join(page.text).split())
            row.update(title=''.join(page.title),links=page.links,
                manual_delivery=bool(re.search(r'person emails|reply to your receipt email with|by email each week|we email you within',text,re.I)),
                pending=bool(re.search(r'STORE-PENDING|TO-MINT|checkout unavailable|processing unavailable',text,re.I)))
        elif row['content_type']=='application/json':
            try:row['body']=json.loads(raw)
            except ValueError:row['body_state']='UNKNOWN'
    except urllib.error.HTTPError as e:row.update(status=e.code,state='HTTP_ERROR')
    except Exception as e:row.update(state='UNKNOWN',reason=type(e).__name__)
    return row

old=json.loads((HOME/'reports/weekly-page-outline-20260908/current-root-probes.json').read_text())
urls={x['url'] for x in old if x['url'].startswith('https://ustechautomations.com/')}
urls.update('https://ustechautomations.com'+p for p in ['/feeds/catalog-migration/','/feeds/','/feeds/pathlab/api/catalog','/feeds/workshop/api/catalog'])
urls.update(['https://usta-loops-260481739341.us-central1.run.app/health',
             'https://usta-entitlements-260481739341.us-central1.run.app/health',
             'https://usta-fit-api-260481739341.us-central1.run.app/health',
             'http://127.0.0.1:8875/health','http://127.0.0.1:8876/health',
             'http://127.0.0.1:8769/health'])
with cf.ThreadPoolExecutor(max_workers=10) as pool: pages=list(pool.map(fetch,sorted(urls)))
save('pages.json',pages)
print('PAGES',len(pages),{str(s):sum(x['status']==s for x in pages) for s in {x['status'] for x in pages}},flush=True)

db=sqlite3.connect('file:'+str(HOME/'.hermes/state/business_metrics.db')+'?mode=ro',uri=True)
money={'at':NOW,'source':'business_metrics.db::revenue_events','all':db.execute("SELECT source,COUNT(*),SUM(value_cents),MIN(occurred_at),MAX(occurred_at) FROM revenue_events WHERE kind='revenue_received' GROUP BY source").fetchall(),'week':db.execute("SELECT source,COUNT(*),SUM(value_cents) FROM revenue_events WHERE kind='revenue_received' AND datetime(occurred_at)>=datetime('2026-09-02T07:00:00Z') GROUP BY source").fetchall()}
save('recorded-payments.json',money); print('RECORDED_PAYMENTS',money,flush=True)

sys.path.insert(0,str(HOME/'code/market-services/api-access'))
import access
with cf.ThreadPoolExecutor(max_workers=4) as pool:
    providers=list(pool.map(access.probe,[k for k,v in access.REGISTRY['platforms'].items() if v['mode']=='api']))
providers=[{k:v for k,v in r.items() if k not in ['identity','permissions_observed','token_expires_in']} for r in providers]
save('provider-access.json',providers)
print('ACCESS',[(r['platform'],r['state']) for r in providers],flush=True)
apify=[]
try:
    c=access.Client('apify')
    for id in ['bTrifrQ2s7Hm0wTWH','e3oDHVvlGp63sgmy3','gbVczPhpoCEDPIfKY']:
        d=c.get('/v2/acts/'+id)['data']
        apify.append({k:d.get(k) for k in ['id','name','isPublic','isDeprecated','stats','pricingInfos']})
except Exception as e:apify.append({'state':'UNKNOWN','reason':type(e).__name__})
save('apify-detail.json',apify)
print('APIFY_DETAIL',[(x.get('name'),x.get('isPublic'),x.get('isDeprecated')) for x in apify],flush=True)

sys.path.insert(0,str(HOME/'code/market-services/stripe-readback'))
import common
try:
    key=common.load_key()
    def stripe_get(path, params=None):
        return access.http_json('https://api.stripe.com/v1'+path+('?' + urllib.parse.urlencode(params) if params else ''),{'Authorization':'Bearer '+key})
    rows=[];params={'created[gte]':1788332400,'limit':100};complete=False
    for _ in range(20):
        data=stripe_get('/checkout/sessions',params)
        for s in data['data']:
            rows.append({k:s.get(k) for k in ['created','status','payment_status','amount_total','currency','livemode','payment_link']})
        if not data.get('has_more'):complete=True;break
        params['starting_after']=data['data'][-1]['id']
    save('stripe-week.json',{'at':NOW,'state':'KNOWN','complete':complete,'sessions':rows})
    print('STRIPE_WEEK',{'complete':complete,'sessions':len(rows),'paid':sum(r['payment_status']=='paid' for r in rows)},flush=True)
    w=stripe_get('/webhook_endpoints',{'limit':100})
    save('stripe-webhooks.json',{'at':NOW,'complete':not w.get('has_more'),'endpoints':[{k:e.get(k) for k in ['url','status','enabled_events','livemode']} for e in w['data']]})
except Exception as e:
    save('stripe-read-error.json',{'at':NOW,'state':'UNKNOWN','reason':type(e).__name__,'http_status':getattr(e,'status',None)})
    print('STRIPE_UNKNOWN',type(e).__name__,flush=True)

spec=importlib.util.spec_from_file_location('gsc',HOME/'.hermes/scripts/gsc_submit_sitemap.py')
gsc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gsc)
try:
    tok=gsc.token();status,body=gsc.api('GET','/sitemaps',tok)
    data=json.loads(body)
    save('gsc-access.json',{'at':NOW,'http':status,'sitemaps':[{k:s.get(k) for k in ['path','lastSubmitted','lastDownloaded','isPending','warnings','errors']} for s in data.get('sitemap',[])]})
    print('GSC_ACCESS',status,flush=True)
except Exception as e:
    save('gsc-access.json',{'at':NOW,'state':'UNKNOWN','reason':type(e).__name__})
    print('GSC_UNKNOWN',type(e).__name__,flush=True)

raw=subprocess.run(['git','-C',str(ROOT),'log','--all','--since=2026-09-02T00:00:00-07:00','--diff-filter=A','--format=','--name-only','--','families/*/index.html'],capture_output=True,text=True,check=True).stdout
ids=sorted({s.split('/')[1] for s in raw.splitlines() if len(s.split('/'))==3})
save('source-new-families.json',{'since':'2026-09-02T00:00:00-07:00','ids':ids})
print('SOURCE_NEW_FAMILIES',len(ids),flush=True)
