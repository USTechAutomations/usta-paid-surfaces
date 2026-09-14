"""TTB-only adaptation of the existing Dataset and click-beacon build hooks.

No visitor identifiers or cookies. Clicks are request-log observations, not
proof of a human or payment. Automation is tagged for downstream exclusion.
"""
import datetime
import html
import json
import re
from pathlib import Path

BASE = 'https://ustechautomations.com/feeds/ttb'
GIF = bytes.fromhex('47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b')


def enhance(page: str, root: Path) -> str:
    if page.count('</head>') != 1:
        raise ValueError('TTB requires exactly one head')
    sample = json.loads((root / 'families/ttb/sample.json').read_text())
    rows = sample.get('rows')
    headers = sample.get('headers', [])
    if not rows or sample.get('family') != 'ttb':
        raise ValueError('UNKNOWN: TTB sample unavailable')
    old, new = headers.index('Earlier sealed copy'), headers.index('Later sealed copy')
    dates = {(row[old], row[new]) for row in rows}
    if len(dates) != 1:
        raise ValueError('UNKNOWN: TTB sample comparison dates inconsistent')
    earlier, later = [datetime.datetime.strptime(d, '%d %b %Y').date().isoformat()
                      for d in next(iter(dates))]
    description = re.search(r'<meta name="description" content="([^"]*)">', page)
    if not description:
        raise ValueError('UNKNOWN: TTB description missing')
    data = {'@context': 'https://schema.org', '@type': 'Dataset',
            'name': 'TTB permit comparison public sample',
            'description': html.unescape(description.group(1)), 'url': BASE+'/',
            'temporalCoverage': earlier+'/'+later, 'isAccessibleForFree': True,
            'creator': {'@type': 'Organization', 'name': 'US Tech Automations'},
            'distribution': [{'@type': 'DataDownload', 'contentUrl': BASE+'/'+name,
                              'encodingFormat': fmt, 'isAccessibleForFree': True}
                             for name, fmt in [('sample.csv','text/csv'),('sample.json','application/json')]]}
    # Replace our own blocks only. Rebuilding a candidate is idempotent.
    page = re.sub(r'<script\b[^>]*id="ttb-(?:dataset|click)"[^>]*>.*?</script>\s*', '', page, flags=re.S)
    encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    blocks = '<script id="ttb-dataset" type="application/ld+json">'+encoded+'</script>\n'
    if 'data-checkout="ttb"' in page:
        script = (root/'scripts/click_beacon.js').read_text()
        blocks += '<script id="ttb-click" data-click-beacon="/feeds/click/ttb.gif">'+script+'</script>\n'
    return page.replace('</head>',blocks+'</head>',1)


def write_receiver(dist: Path):
    path = dist/'click/ttb.gif'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(GIF)
