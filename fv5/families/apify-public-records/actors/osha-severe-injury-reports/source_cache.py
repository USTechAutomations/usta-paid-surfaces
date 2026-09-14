"""Read the owned public copy; stale, altered or unavailable data is UNKNOWN."""
import hashlib
import json
import re
from datetime import datetime,timezone

class CacheUnavailable(RuntimeError):pass

def read_cached_source(config, get, release_parser, now=None):
    try:
        store=config['store_id'];max_age=config['max_age_seconds']
        if not isinstance(store,str) or not re.fullmatch(r'[A-Za-z0-9]{17}',store) or type(max_age) is not int or not 3600<=max_age<=172800:
            raise CacheUnavailable('UNKNOWN: source cache configuration is invalid')
        base='https://api.apify.com/v2/key-value-stores/'+store+'/records/'
        manifest=json.loads(get(base+'LATEST.json',65536))
        if type(manifest.get('schema_version')) is not int or manifest['schema_version']!=1 or manifest.get('status')!='SUCCESS':
            raise CacheUnavailable('UNKNOWN: source cache has no accepted release')
        observed=datetime.fromisoformat(manifest['collected_at']);now=now or datetime.now(timezone.utc)
        if observed.tzinfo is None or not -300<=(now-observed).total_seconds()<=max_age:
            raise CacheUnavailable('UNKNOWN: source collection is stale or its clock is invalid')
        source=manifest['source'];artifact=manifest['artifact']
        release=release_parser(source['url'])
        if source['page_http']!=200 or source['download_http']!=200 or type(manifest['source_rows']) is not int or not 1<=manifest['source_rows']<=500000:
            raise CacheUnavailable('UNKNOWN: source collection lacks required evidence')
        for value in [source['sha256'],artifact['sha256']]:
            if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):
                raise CacheUnavailable('UNKNOWN: source checksum is invalid')
        if artifact['key']!='source-'+artifact['sha256']+'.zip' or type(artifact['bytes']) is not int or not 0<artifact['bytes']<=64*1024*1024:
            raise CacheUnavailable('UNKNOWN: source artifact identity is invalid')
        url=base+artifact['key'];body=get(url,64*1024*1024)
        if len(body)!=artifact['bytes'] or hashlib.sha256(body).hexdigest()!=artifact['sha256']:
            raise CacheUnavailable('UNKNOWN: source artifact checksum does not match')
        metadata={'source_sha256':source['sha256'],'source_collected_at':manifest['collected_at'],'source_collection_age_seconds':max(0,int((now-observed).total_seconds())),
            'source_delivery':'Validated copy refreshed by the USTA source collector','data_artifact_url':url,'data_artifact_sha256':artifact['sha256'],'expected_source_rows':manifest['source_rows']}
        return body,release,metadata
    except CacheUnavailable:raise
    except Exception as exc:raise CacheUnavailable('UNKNOWN: source cache could not be read or validated') from exc
