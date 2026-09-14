"""Attach tested click observations to explicitly reviewed existing offer families.

No pageview, price, checkout or delivery mutation. Automated clicks use the
shared diagnostic family. TTB and existing tool handlers remain separate.
"""
from pathlib import Path
import re
from html.parser import HTMLParser
REVIEWED = frozenset(['agentic-commerce', 'air-permits', 'trustee-sales', 'chicago', 'los-angeles', 'baton-rouge', 'washington-dc', 'boston', 'nyc-ll84', 'metro-file', 'stamper-appendix', 'predictor-diet', 'machine-visitor-ledger', 'clean-room-corpus', 'address-packet', 'access-affidavits', 'texas-formulary', 'changeover-atlas', 'carrier-register', 'clerk-clock', 'frozen-custody', 'wrong-wall', 'cannabis-tape', 'stormwater-noi', 'hts-revision-seal', 'new-prime-awards', 'storm-warned-counties', 'pilot-logbook-digitizer', 'wp-accessibility-scan', 'kdp-lens', 'patent-practitioner-directory', 'enforcement-action-board', 'customs-broker-exam-bank', 'hazmat-ship-pack', 'contractor-audit-file', 'nutrition-label-forge', 'ai-disclosure-notice', 'notary-journal', 'qrelay', 'casepack'])
SCRIPT = Path(__file__).with_name('checkout_events.js')
MARKER = 'usta-offer-click-observation'

def _observation_spans(raw):
    """Find real script elements; comments and plain mentions are not scripts."""
    starts=[0]
    for m in re.finditer("\n",raw):starts.append(m.end())
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.start=None
            self.spans=[]
        def position(self):
            line,col=self.getpos()
            return starts[line-1]+col
        def handle_starttag(self,tag,attrs):
            if tag!='script':return
            ids=[value for name,value in attrs if name=='id']
            if MARKER in ids:
                if len(ids)!=1 or self.start is not None:
                    raise ValueError('Ambiguous existing observation script')
                self.start=self.position()
        def handle_endtag(self,tag):
            if tag=='script' and self.start is not None:
                end=raw.find('>',self.position())
                if end<0:raise ValueError('Unterminated observation script')
                self.spans.append((self.start,end+1));self.start=None
    parser=Scripts();parser.feed(raw);parser.close()
    if parser.start is not None:raise ValueError('Unterminated observation script')
    return parser.spans

def attach(raw, family):
    if family not in REVIEWED:
        return raw
    if not re.search(r'data-checkout=[\'"]'+re.escape(family)+r'[\'"]', raw):
        return raw
    tag = '<script id="'+MARKER+'">'+SCRIPT.read_text()+'</script>'
    matches = _observation_spans(raw)
    if len(matches) > 1:
        raise ValueError('Ambiguous existing observation script')
    if matches:
        start, end = matches[0]
        return raw[:start]+tag+raw[end:]
    if raw.count('</body>') != 1:
        raise ValueError('Ambiguous offer document')
    return raw.replace('</body>', tag+'\n</body>', 1)
def install(dist):
    changed=[]
    for family in sorted(REVIEWED):
        path=Path(dist)/family/'index.html'
        if not path.exists():
            continue
        raw=path.read_text();new=attach(raw,family)
        if new != raw:
            path.write_text(new);changed.append(family)
    return changed
