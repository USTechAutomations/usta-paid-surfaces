#!/usr/bin/env python3
"""Official OSHA SIR ZIP -> filtered report records with explicit source limits."""
from __future__ import annotations
import asyncio
import calendar
import csv
import hashlib
import heapq
import io
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

PAGE_URL = 'https://www.osha.gov/severe-injury-reports'
UA = 'USTechAutomations-OSHA/0.3 (+https://ustechautomations.com/feeds)'
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_CSV_BYTES = 256 * 1024 * 1024
MAX_SOURCE_ROWS = 500_000
STATE_NAMES = dict(line.split('|') for line in '''AL|ALABAMA
AK|ALASKA
AZ|ARIZONA
AR|ARKANSAS
CA|CALIFORNIA
CO|COLORADO
CT|CONNECTICUT
DE|DELAWARE
DC|DISTRICT OF COLUMBIA
FL|FLORIDA
GA|GEORGIA
HI|HAWAII
ID|IDAHO
IL|ILLINOIS
IN|INDIANA
IA|IOWA
KS|KANSAS
KY|KENTUCKY
LA|LOUISIANA
ME|MAINE
MD|MARYLAND
MA|MASSACHUSETTS
MI|MICHIGAN
MN|MINNESOTA
MS|MISSISSIPPI
MO|MISSOURI
MT|MONTANA
NE|NEBRASKA
NV|NEVADA
NH|NEW HAMPSHIRE
NJ|NEW JERSEY
NM|NEW MEXICO
NY|NEW YORK
NC|NORTH CAROLINA
ND|NORTH DAKOTA
OH|OHIO
OK|OKLAHOMA
OR|OREGON
PA|PENNSYLVANIA
RI|RHODE ISLAND
SC|SOUTH CAROLINA
SD|SOUTH DAKOTA
TN|TENNESSEE
TX|TEXAS
UT|UTAH
VT|VERMONT
VA|VIRGINIA
WA|WASHINGTON
WV|WEST VIRGINIA
WI|WISCONSIN
WY|WYOMING
AS|AMERICAN SAMOA
GU|GUAM
MP|NORTHERN MARIANA ISLANDS
PR|PUERTO RICO
VI|VIRGIN ISLANDS'''.splitlines())
STATE_CODES = {v: k for k, v in STATE_NAMES.items()}
MONTHS = {name: n for n, name in enumerate(calendar.month_name) if name}
REQUIRED = {'ID','UPA','EventDate','Employer','City','State','Primary NAICS','Hospitalized','Amputation','Loss of Eye','Nature','NatureTitle','Part of Body','Part of Body Title','FederalState'}


class SourceUnavailable(RuntimeError):
    """No reliable result can be reported from this source attempt."""


def _remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise SourceUnavailable('UNKNOWN: source processing timed out; no dataset output')
    return value


def _text(value):
    return str(value).strip() if value is not None else ''


def _state(value):
    text = _text(value).upper()
    return text if text in STATE_NAMES else STATE_CODES.get(text)


def validate_input(inp):
    allowed = {'state','dateFrom','dateTo','naicsPrefix','keyword','maxItems','timeoutSeconds'}
    if not isinstance(inp, dict) or set(inp) - allowed:
        raise ValueError('Input must be an object with supported filter fields')
    out = {}
    for key in ['state','dateFrom','dateTo','naicsPrefix','keyword']:
        value = inp.get(key, '')
        if not isinstance(value, str):
            raise ValueError(key + ' must be text')
        out[key] = value.strip()
    if out['state']:
        state = _state(out['state'])
        if state is None:
            raise ValueError('state must be a US state/territory name or postal abbreviation')
        out['state'] = state
    for key in ['dateFrom','dateTo']:
        if out[key]:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', out[key]):
                raise ValueError(key + ' must use YYYY-MM-DD')
            date.fromisoformat(out[key])
    if out['dateFrom'] and out['dateTo'] and out['dateFrom'] > out['dateTo']:
        raise ValueError('dateFrom must be on or before dateTo')
    if out['naicsPrefix'] and not re.fullmatch(r'\d{2,6}', out['naicsPrefix']):
        raise ValueError('naicsPrefix must be 2–6 digits supplied as text')
    if len(out['keyword']) > 100:
        raise ValueError('keyword must be at most 100 characters')
    for key, default, low, high in [('maxItems',10,1,1000),('timeoutSeconds',180,30,600)]:
        value = inp.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key} must be an integer from {low} to {high}')
        out[key] = value
    return out


class DownloadLink(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('id') == 'downloadDataset' and attrs.get('href'):
            self.urls.append(urllib.parse.urljoin(PAGE_URL, attrs['href']))


def release_from_url(url):
    parsed = urllib.parse.urlsplit(url)
    pattern = r'/sites/default/files/([A-Za-z]+)(\d{4})to([A-Za-z]+)(\d{4})\.zip'
    match = re.fullmatch(pattern, parsed.path)
    if parsed.scheme != 'https' or parsed.netloc != 'www.osha.gov' or parsed.query or parsed.fragment or not match:
        raise SourceUnavailable('UNKNOWN: official download link format changed')
    first_month, first_year, last_month, last_year = match.groups()
    try:
        first = date(int(first_year), MONTHS[first_month], 1)
        last = date(int(last_year), MONTHS[last_month], calendar.monthrange(int(last_year), MONTHS[last_month])[1])
    except (KeyError, ValueError) as exc:
        raise SourceUnavailable('UNKNOWN: official release dates cannot be read') from exc
    if first > last:
        raise SourceUnavailable('UNKNOWN: official release dates are reversed')
    return {'source_url':url,'source_period_from':first.isoformat(),'source_period_to':last.isoformat()}


def _get(url, limit, deadline):
    try:
        request = urllib.request.Request(url, headers={'User-Agent':UA})
        with urllib.request.urlopen(request, timeout=min(45, _remaining(deadline))) as response:
            if response.status != 200 or response.url != url:
                raise SourceUnavailable('UNKNOWN: official request redirected or did not return HTTP 200')
            chunks, size = [], 0
            while chunk := response.read(1024 * 1024):
                _remaining(deadline); size += len(chunk)
                if size > limit:
                    raise SourceUnavailable('UNKNOWN: official response exceeds supported size')
                chunks.append(chunk)
            return b''.join(chunks)
    except SourceUnavailable:
        raise
    except Exception as exc:
        raise SourceUnavailable('UNKNOWN: official source request failed') from exc


def fetch_source(deadline):
    page = _get(PAGE_URL, 2 * 1024 * 1024, deadline)
    parser = DownloadLink()
    try:
        parser.feed(page.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise SourceUnavailable('UNKNOWN: official download page cannot be read') from exc
    urls = set(parser.urls)
    if len(urls) != 1:
        raise SourceUnavailable('UNKNOWN: current official download link is missing or ambiguous')
    url = urls.pop(); release = release_from_url(url)
    body = _get(url, MAX_ZIP_BYTES, deadline)
    return body, release


def _date(raw):
    value = _text(raw)
    for fmt in ['%m/%d/%Y','%Y-%m-%d']:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _count(raw):
    value = _text(raw)
    if not value or value.upper() in {'UNKNOWN','N/A','NULL'}:
        return None
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
            raise ValueError('not a nonnegative integer')
        return int(amount)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise SourceUnavailable('UNKNOWN: source injury count is malformed') from exc


def _naics_match(value, prefix):
    if not prefix:
        return True
    if not value:
        return None
    group = re.fullmatch(r'(\d{2})-(\d{2})', value)
    if group:
        low, high = map(int, group.groups())
        if low > high:
            raise SourceUnavailable('UNKNOWN: source industry range is reversed')
        if low <= int(prefix[:2]) <= high:
            return True if len(prefix) == 2 else None
        return False
    if not re.fullmatch(r'\d{2,6}', value):
        return None
    if len(value) < len(prefix) and prefix.startswith(value):
        return None
    return value.startswith(prefix)


def parse_source(body, release, inp, deadline):
    if len(body) > MAX_ZIP_BYTES:
        raise SourceUnavailable('UNKNOWN: source ZIP exceeds supported size')
    counts = Counter(); ids = Counter(); upas = set(); heap = []; jurisdiction = Counter(); earliest = None; latest = None
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            expected = urllib.parse.urlsplit(release['source_url']).path.rsplit('/',1)[1][:-4]+'.csv'
            members = [info for info in archive.infolist() if info.filename.lower().endswith('.csv')]
            if len(members) != 1 or members[0].filename != expected or members[0].file_size > MAX_CSV_BYTES:
                raise SourceUnavailable('UNKNOWN: expected CSV is missing, ambiguous or too large')
            with archive.open(members[0]) as binary:
                reader = csv.DictReader(io.TextIOWrapper(binary, encoding='utf-8-sig', errors='strict'))
                if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not REQUIRED.issubset(reader.fieldnames):
                    raise SourceUnavailable('UNKNOWN: required official CSV columns changed')
                for raw in reader:
                    _remaining(deadline); counts['source_rows'] += 1
                    if counts['source_rows'] > MAX_SOURCE_ROWS or None in raw or any(raw[k] is None for k in REQUIRED):
                        raise SourceUnavailable('UNKNOWN: source row shape/count exceeds supported format')
                    source_id, upa = _text(raw['ID']), _text(raw['UPA'])
                    if not re.fullmatch(r'\d+', source_id) or not re.fullmatch(r'\d+', upa) or upa in upas:
                        raise SourceUnavailable('UNKNOWN: source identifiers malformed or UPA duplicated')
                    ids[source_id] += 1; upas.add(upa)
                    d = _date(raw['EventDate']); state = _state(raw['State'])
                    counts['unknown_dates'] += d is None; counts['unknown_states'] += state is None
                    flag = _text(raw['FederalState']); jurisdiction[flag or 'UNKNOWN'] += 1
                    if d:
                        earliest = min(earliest,d) if earliest else d; latest = max(latest,d) if latest else d
                        if not release['source_period_from'] <= d <= release['source_period_to']:
                            raise SourceUnavailable('UNKNOWN: incident date falls outside named source release')
                    item = {'id':source_id,'report_key':'OSHA-UPA-'+upa,'source_upa':upa,'event_date':d,
                        'event_date_source':_text(raw['EventDate']) or None,'date_status':'REPORTED' if d else 'UNKNOWN',
                        'employer':_text(raw['Employer']) or None,'city':_text(raw['City']) or None,
                        'state':state,'state_source':_text(raw['State']) or None,'state_status':'REPORTED' if state else 'UNKNOWN',
                        'naics':_text(raw['Primary NAICS']) or None,'hospitalized':_count(raw['Hospitalized']),
                        'amputation':_count(raw['Amputation']),'loss_of_eye':_count(raw['Loss of Eye']),
                        'nature':_text(raw['NatureTitle']) or None,'nature_code':_text(raw['Nature']) or None,
                        'body_part':_text(raw['Part of Body Title']) or None,'body_part_code':_text(raw['Part of Body']) or None,
                        'source_federal_state_flag':flag or None}
                    if inp['state'] and state != inp['state']:
                        continue
                    if (inp['dateFrom'] or inp['dateTo']) and not d:
                        counts['unknown_dates_excluded_by_filter'] += 1; continue
                    if d and ((inp['dateFrom'] and d < inp['dateFrom']) or (inp['dateTo'] and d > inp['dateTo'])):
                        continue
                    industry = _naics_match(item['naics'], inp['naicsPrefix'])
                    if industry is None:
                        counts['uncertain_industry_excluded_by_filter'] += 1; continue
                    if not industry:
                        continue
                    if inp['keyword'] and not any(inp['keyword'].casefold() in (item[k] or '').casefold() for k in ['employer','city','nature','body_part']):
                        continue
                    counts['matching_reports'] += 1
                    entry = (d or '',int(upa),item)
                    if len(heap) < inp['maxItems']:
                        heapq.heappush(heap,entry)
                    elif entry[:2] > heap[0][:2]:
                        heapq.heapreplace(heap,entry)
        if not counts['source_rows']:
            raise SourceUnavailable('UNKNOWN: source contains no report rows')
    except SourceUnavailable:
        raise
    except Exception as exc:
        raise SourceUnavailable('UNKNOWN: source ZIP/CSV could not be processed') from exc
    items = [item for _,_,item in sorted(heap, key=lambda e:e[:2], reverse=True)]
    summary = {k:counts[k] for k in ['source_rows','matching_reports','unknown_dates','unknown_states','unknown_dates_excluded_by_filter','uncertain_industry_excluded_by_filter']}
    summary.update({'duplicate_display_id_groups':sum(v>1 for v in ids.values()),'source_federal_state_flag_counts':dict(jurisdiction),'observed_event_date_from':earliest,'observed_event_date_to':latest,'omitted_due_to_max_items':counts['matching_reports']-len(items)})
    return items, summary


def fetch_current_source(deadline):
    from source_cache import read_cached_source, CacheUnavailable
    try:
        config=json.loads(Path(__file__).with_name('source_cache_config.json').read_text())
        return read_cached_source(config,lambda url,limit:_get(url,limit,deadline),release_from_url)
    except Exception as exc:
        raise SourceUnavailable(str(exc) if isinstance(exc,CacheUnavailable) else 'UNKNOWN: source cache configuration is unavailable') from exc


def collect(inp, *, source=None, fetch=None):
    inp = validate_input(inp); deadline = time.monotonic()+inp['timeoutSeconds']
    fetched = source if source is not None else (fetch or fetch_current_source)(deadline)
    body, release = fetched[:2]
    metadata = fetched[2] if len(fetched)==3 else {}
    # Validate provenance even for explicit offline tests; no arbitrary public input URL exists.
    if not isinstance(release, dict) or 'source_url' not in release or release != release_from_url(release['source_url']):
        raise SourceUnavailable('UNKNOWN: source release provenance is inconsistent')
    items, summary = parse_source(body, release, inp, deadline)
    if metadata.get('expected_source_rows',summary['source_rows'])!=summary['source_rows']:
        raise SourceUnavailable('UNKNOWN: source row count does not match the collected release')
    provenance = {**release,'source_page_url':PAGE_URL,'source_sha256':hashlib.sha256(body).hexdigest(),'source_retrieved_at':datetime.now(timezone.utc).isoformat(),'source_scope':'Published OSHA SIR file; not a complete census of US injuries',**metadata}
    for item in items:
        item.update(provenance)
    return items, {'status':'SUCCESS' if items else 'NO_MATCHES',**summary,**provenance,'returned_reports':len(items),'filters':inp}


async def main():
    from apify import Actor
    async with Actor:
        try:
            raw_input = await Actor.get_input()
            items, summary = await asyncio.to_thread(collect, {} if raw_input is None else raw_input)
        except Exception as exc:
            await Actor.set_value('SUMMARY',{'status':'UNKNOWN' if isinstance(exc,SourceUnavailable) else 'INVALID_INPUT','error':str(exc),'returned_reports':None})
            raise
        final_status = summary['status']; summary.update(status='OUTPUT_IN_PROGRESS',prepared_reports=len(items),returned_reports=None)
        await Actor.set_value('SUMMARY',summary)
        for item in items:
            await Actor.push_data(item)  # Existing automatic dataset-item event; never double-charge.
        summary.update(status=final_status,returned_reports=len(items)); await Actor.set_value('SUMMARY',summary)
        Actor.log.info(f"{final_status}: {len(items)} reports returned; {summary['omitted_due_to_max_items']} matching reports omitted by maxItems")


if __name__=='__main__':
    asyncio.run(main())
