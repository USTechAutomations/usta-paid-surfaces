"""Keep an explicit off-sale decision consistent across known offer projections."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import json
import re
import sys

MONEY=re.compile(r'\$\s*\d')
CHECKOUT=re.compile(r'https://(?:buy\.stripe\.com|checkout\.stripe\.com)/',re.I)
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
# Spellings the off-sale guard will inspect or skip. Anything else is refused
# by name rather than dropped. Do not strip before matching: a trailing space
# is an unknown spelling, not off_sale.
KNOWN_STATUS={'','live','off_sale','none','pending','external'}
PAY_BUTTON=re.compile(r'<(?:a|button)\b[^>]*\bbtn-buy\b[^>]*>',re.I)
PAY_HREF=re.compile(r'''<(?:a|button)\b[^>]*href\s*=\s*["']https://''',re.I)

class Node:
    def __init__(self,tag='',attrs=None):self.tag=tag;self.attrs=attrs or {};self.children=[]
    def text(self):return ''.join(c if isinstance(c,str) else c.text() for c in self.children)
    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c,Node):yield from c.walk()
class Surface(HTMLParser):
    def __init__(self,raw):
        super().__init__();self.root=Node();self.stack=[self.root];self.feed(raw)
    def handle_starttag(self,tag,attrs):
        node=Node(tag,dict(attrs));self.stack[-1].children.append(node)
        if tag not in VOID:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)

def _assertions(root, *, projection=False):
    for n in root.walk():
        if n.tag=='a' and CHECKOUT.search(n.attrs.get('href','')):return True
        if (n.tag=='title' or set(n.attrs.get('class','').split())&{'price','buy-price','amount'}) and MONEY.search(n.text()):return True
        if n.tag=='meta' and (n.attrs.get('name') in ('description','twitter:description','twitter:title') or n.attrs.get('property') in ('og:title','og:description')) and MONEY.search(n.attrs.get('content','')):return True
    visible=' '.join(root.text().split())
    return projection and (bool(MONEY.search(visible)) or 'Card checkout on its page' in visible)

def _family_href(href,fid):
    try:
        u=urlsplit(href)
        if u.scheme or u.netloc:return u.scheme=='https' and u.netloc=='ustechautomations.com' and u.path.rstrip('/')=='/feeds/'+fid
        return u.path.rstrip('/')=='families/'+fid
    except ValueError:return False

def checkout_url_is_web(url) -> bool:
    """True only for an address a browser can open. Placeholders fail."""
    return isinstance(url,str) and url.startswith('https://')

def _status_key(checkout: dict) -> str:
    return str((checkout or {}).get('status') or '').lower()

def _coverage_rows(coverage, short: str):
    strong_hits=[]
    named_hits=[]
    for n in coverage.walk():
        if n.tag!='tr':
            continue
        if any(c.tag=='strong' and ' '.join(c.text().split())==short for c in n.walk()):
            strong_hits.append(n)
        elif short and short in ' '.join(n.text().split()):
            named_hits.append(n)
    return strong_hits if len(strong_hits)==1 else named_hits

def _page_still_sells(raw: str) -> bool:
    """A pay button together with a printed price, which an unsellable row must not show."""
    if not raw:
        return False
    has_button=bool(PAY_BUTTON.search(raw) and PAY_HREF.search(raw))
    if not has_button:
        return False
    return _assertions(Surface(raw).root)

def unsellable_row_errors(root: Path, catalog: dict) -> tuple[list[str], int]:
    """Rows whose checkout.url is not a web address must not still offer a sale.

    Returns (errors, count of such urls that still show a price with a button).
    """
    errors=[]
    selling=0
    for family in catalog.get('families',[]):
        checkout=family.get('checkout') or {}
        url=checkout.get('url')
        if url is None or url=='' or checkout_url_is_web(url):
            continue
        fid=family.get('id','')
        page=root/'families'/fid/'index.html'
        raw=page.read_text() if page.is_file() and not page.is_symlink() else ''
        if _page_still_sells(raw):
            selling+=1
            errors.append(fid+': checkout url is not a web address and the page still offers a price or pay button.')
    return errors, selling

def off_sale_errors(root: Path, catalog: dict) -> list[str]:
    errors=[]
    inspected=0
    for family in catalog.get('families',[]):
        checkout=family.get('checkout') or {}
        fid=family.get('id','')
        key=_status_key(checkout)
        if key not in KNOWN_STATUS:
            errors.append(fid+': checkout status '+repr(str(checkout.get('status') or ''))+' is not a spelling this guard knows.')
            continue
        if key!='off_sale':continue
        inspected+=1
        if not re.fullmatch(r'[a-z0-9-]+',fid):errors.append('Off-sale family identity is unavailable.');continue
        if checkout.get('url') or MONEY.search(str(family.get('price',''))):errors.append(fid+': off_sale catalog still advertises a price or checkout URL.')
        paths=[root/'families'/fid/'index.html',root/'index.html',root/'families/coverage/index.html']
        if any(not p.is_file() or p.is_symlink() for p in paths):errors.append(fid+': off_sale product, directory or coverage projection is unavailable.');continue
        product,hub,coverage=[Surface(p.read_text()).root for p in paths]
        if _assertions(product):errors.append(fid+': off_sale product still advertises a price or checkout URL.')
        cards=[n for n in hub.walk() if n.tag=='a' and _family_href(n.attrs.get('href',''),fid)]
        short=' '.join(str(family.get('short','')).split())
        rows=_coverage_rows(coverage, short)
        if len(cards)!=1:errors.append(fid+': off_sale directory projection identity is unavailable or ambiguous.')
        if len(rows)!=1:errors.append(fid+': off_sale coverage projection identity is unavailable or ambiguous.')
        if any(_assertions(n,projection=True) for n in cards):errors.append(fid+': off_sale directory card still advertises sales.')
        if any(_assertions(n,projection=True) for n in rows):errors.append(fid+': off_sale coverage row still advertises sales.')
    extra, selling = unsellable_row_errors(root, catalog)
    errors.extend(extra)
    print(f'rows whose checkout url is not a web address: {selling}')
    print(f'off-sale rows inspected: {inspected}')
    return errors


def main(argv=None) -> int:
    argv=list(sys.argv[1:] if argv is None else argv)
    root=Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    catalog_path=Path(argv[1]) if len(argv)>1 else root/'catalog.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    errors=off_sale_errors(root, catalog)
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__=='__main__':
    raise SystemExit(main())
