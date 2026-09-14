"""Bounded, aggregate-only Combined Log report. UA matches are not identity proof."""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from signatures import AI_BOT_SIGNATURES

QUOTED = r'"((?:[^"\\\r\n]|\\(?:["\\]|x[0-9A-Fa-f]{2}))*)"'
LINE = re.compile(r'^\S+ \S+ \S+ \[([^\]\r\n]+)\] ' + QUOTED + r' ([1-5][0-9]{2}) ([0-9]+|-) ' + QUOTED + ' ' + QUOTED + r'$')
REQUEST = re.compile(r'^[A-Z]+ [^\s]+ HTTP/[0-9]+(?:\.[0-9]+)?$')
MONTHS = dict(zip('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), range(1,13)))
STAMP = re.compile(r'^(\d{2})/([A-Z][a-z]{2})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})$')

def timestamp(raw):
    m = STAMP.fullmatch(raw)
    if not m or m[2] not in MONTHS or int(m[8])>23 or int(m[9])>59:
        raise ValueError('invalid timestamp')
    d,mo,y,h,mi,s,sign,oh,om=m.groups()
    return datetime.fromisoformat(f'{y}-{MONTHS[mo]:02}-{d}T{h}:{mi}:{s}{sign}{oh}:{om}').astimezone(timezone.utc).isoformat()

def analyze(stream, max_bytes=104857600, max_lines=1000000):
    if not isinstance(max_bytes,int) or not isinstance(max_lines,int) or min(max_bytes,max_lines)<1:
        raise ValueError('invalid limits')
    total=known=named=named_bytes=unknown=read=0
    machines={}; first=last=None; digest=hashlib.sha256()
    while True:
        line=stream.readline(min(65537,max_bytes-read+1))
        if not line: break
        if not isinstance(line,bytes): raise ValueError('binary stream required')
        read+=len(line)
        if read>max_bytes or len(line)>65536: raise ValueError('input size limit exceeded')
        total+=1
        if total>max_lines: raise ValueError('line count limit exceeded')
        digest.update(line)
        try:
            raw=line.decode('utf-8').rstrip('\r\n')
            if any(ord(c)<32 or ord(c)==127 for c in raw): raise ValueError()
            m=LINE.fullmatch(raw)
            if not m: raise ValueError()
            ts,request,status,size,referer,ua=m.groups()
            unescape=lambda value: re.sub(r'\\(x[0-9A-Fa-f]{2}|["\\])',lambda match:chr(int(match[1][1:],16)) if match[1].startswith('x') else match[1],value)
            request=unescape(request);ua=unescape(ua)
            if any(ord(c)<32 or ord(c)==127 for c in request):raise ValueError()
            if not REQUEST.fullmatch(request): raise ValueError()
            ts=timestamp(ts)
            if len(size)>20: raise ValueError()
            n=None if size=='-' else int(size)
        except (ValueError,UnicodeError,OverflowError):
            raise ValueError(f'invalid Combined Log record at line {total}') from None
        first=ts if first is None else min(first,ts)
        last=ts if last is None else max(last,ts)
        known+=n or 0; unknown+=n is None
        family=next((f for token,f in AI_BOT_SIGNATURES if token in ua.lower()),None)
        if family:
            named+=1; named_bytes+=n or 0
            row=machines.setdefault(family,{'machine_name':family,'hits':0,'bytes':0,'unknown_byte_requests':0})
            row['hits']+=1; row['bytes']+=n or 0; row['unknown_byte_requests']+=n is None
    if not total: raise ValueError('empty log')
    rows=sorted(machines.values(),key=lambda r:(-r['hits'],r['machine_name']))
    for row in rows: row['share_pct']=round(100*row['hits']/total,2)
    return {'schema_version':1,'requests':total,'named_requests':named,'other_requests':total-named,
            'named_share_pct':round(100*named/total,2),'known_bytes':known,'named_known_bytes':named_bytes,
            'unknown_byte_requests':unknown,'byte_totals_status':'PARTIAL' if unknown else 'MEASURED',
            'named_byte_share_pct':None if unknown or not known else round(100*named_bytes/known,2),
            'first_request_utc':first,'last_request_utc':last,'machines':rows,
            'input_sha256':digest.hexdigest(),'input_bytes':read,
            'method':'First case-insensitive UA substring match in retained 20-family list; not client identity proof.'}

def render_csv(result):
    out=io.StringIO(newline=''); w=csv.writer(out);w.writerow(['machine_name','hits','bytes','share_pct'])
    for r in result['machines']:
        w.writerow([r['machine_name'],r['hits'],'' if r['unknown_byte_requests'] else r['bytes'],f"{r['share_pct']:.2f}"])
    return out.getvalue()

def render_report(result):
    r=result
    lines=['# Machine Visitor Ledger','',f"Coverage (UTC): {r['first_request_utc']} to {r['last_request_utc']}.",
           f"Requests: {r['requests']}. Named-machine requests: {r['named_requests']} ({r['named_share_pct']:.2f}%).",
           f"Other requests: {r['other_requests']}; unmatched does not mean human.",
           f"Known bytes: {r['known_bytes']}; known named-machine bytes: {r['named_known_bytes']}.",
           f"Byte totals: {r['byte_totals_status']}; unknown size requests: {r['unknown_byte_requests']}.",
           'Named-machine byte share: '+('UNKNOWN.' if r['named_byte_share_pct'] is None else f"{r['named_byte_share_pct']:.2f}%."),
           '',r['method'],'','CSV rows include all matched families; a blank bytes cell means that family has unknown byte sizes.',
           'Raw-log deletion evidence is recorded separately by the managed job; this parser does not delete files.','']
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser(); p.add_argument('log'); a=p.parse_args()
    try:
        with open(a.log,'rb') as f: result=analyze(f)
    except (OSError,ValueError):
        print('Log unavailable or invalid; no report produced.',file=sys.stderr); return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':sys.exit(main())
