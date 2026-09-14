"""Dated official office-hours facts. Stale or changed retained evidence is UNKNOWN."""
import datetime as dt,hashlib,stat
from pathlib import Path
SOURCE = {'url': 'https://www.austintexas.gov/development-services/schedule-appointment-permitting-and-development-center-pdc', 'http_status': 200, 'fetched_at': '2026-09-10T23:58:57.960722+00:00', 'sha256': 'b2885a45e074b618b7987f1055f864070d400cc3e0f1a1087a0b60a34acef37f', 'office': 'Austin Permitting and Development Center', 'hours': 'Monday–Friday 08:00–16:00 local time', 'scope': 'walk-in appointments for named services; not all departments or holidays', 'effective_date': 'UNKNOWN', 'source_path': '/home/gmullins/.hermes/state/clerk-clock/source-evidence/20260910/austin-office-source.html'}
def office_details(office, now=None):
 unknown={'hours':'UNKNOWN','source_url':None,'read_at':None,'scope':'official office-hours evidence unavailable or stale for this run'}
 if office!='austin':return unknown
 now=now or dt.datetime.now(dt.timezone.utc)
 stamp=dt.datetime.fromisoformat(SOURCE['fetched_at'])
 if not 0 <= (now-stamp).total_seconds() <= 86400:return unknown
 p=Path(SOURCE['source_path'])
 try:
  if p.is_symlink() or not stat.S_ISREG(p.stat().st_mode):return unknown
  if hashlib.sha256(p.read_bytes()).hexdigest()!=SOURCE['sha256']:return unknown
 except OSError:return unknown
 return {'hours':SOURCE['hours'],'source_url':SOURCE['url'],'read_at':SOURCE['fetched_at'],'source_sha256':SOURCE['sha256'],'effective_date':'UNKNOWN','scope':SOURCE['scope']}
