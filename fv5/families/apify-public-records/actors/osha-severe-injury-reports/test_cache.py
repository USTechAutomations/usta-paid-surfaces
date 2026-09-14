import hashlib,json,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import main
from source_cache import read_cached_source,CacheUnavailable
from test_main import zipped,RELEASE

NOW=datetime(2026,9,12,tzinfo=timezone.utc)
class CacheTests(unittest.TestCase):
 def data(self):
  body=zipped();sha=hashlib.sha256(body).hexdigest();m={'schema_version':1,'status':'SUCCESS','collected_at':NOW.isoformat(),'source':{'url':RELEASE['source_url'],'sha256':'a'*64,'page_http':200,'download_http':200},'artifact':{'key':'source-'+sha+'.zip','sha256':sha,'bytes':len(body)},'source_rows':1};return body,m
 def read(self,m,body,now=NOW):
  return read_cached_source({'store_id':'A'*17,'max_age_seconds':172800},lambda url,limit:json.dumps(m).encode() if url.endswith('LATEST.json') else body,main.release_from_url,now)
 def test_current_hash_checked_copy_and_provenance(self):
  body,m=self.data();b,r,meta=self.read(m,body);self.assertEqual((b,r),(body,RELEASE));self.assertEqual(meta['source_sha256'],'a'*64);self.assertEqual(meta['expected_source_rows'],1)
  items,s=main.collect({},source=(b,r,meta));self.assertEqual(s['source_sha256'],'a'*64);self.assertEqual(s['data_artifact_sha256'],hashlib.sha256(body).hexdigest())
 def test_stale_or_future_collection_unknown_before_artifact_fetch(self):
  for collected in [NOW-timedelta(days=3),NOW+timedelta(hours=1)]:
   body,m=self.data();m['collected_at']=collected.isoformat();calls=[]
   def get(url,limit):calls.append(url);return json.dumps(m).encode()
   with self.assertRaises(CacheUnavailable):read_cached_source({'store_id':'A'*17,'max_age_seconds':172800},get,main.release_from_url,NOW)
   self.assertEqual(len(calls),1)
 def test_corrupt_body_unknown(self):
  body,m=self.data()
  with self.assertRaises(CacheUnavailable):self.read(m,body+b'changed')
 def test_failed_collection_or_untrusted_key_unknown(self):
  for change in ['status','key','source','rows']:
   body,m=self.data()
   if change=='status':m['status']='UNKNOWN'
   if change=='key':m['artifact']['key']='../../private'
   if change=='source':m['source']['url']='https://attacker.test/data.zip'
   if change=='rows':m['source_rows']=True
   with self.subTest(change=change),self.assertRaises(CacheUnavailable):self.read(m,body)
 def test_missing_manifest_unknown(self):
  with self.assertRaises(CacheUnavailable):read_cached_source({'store_id':'A'*17,'max_age_seconds':172800},lambda url,limit:b'<html>error</html>',main.release_from_url,NOW)
 def test_record_count_mismatch_unknown(self):
  body,m=self.data();m['source_rows']=2;b,r,meta=self.read(m,body)
  with self.assertRaises(main.SourceUnavailable):main.collect({},source=(b,r,meta))
 def test_unreadable_runtime_config_unknown(self):
  with patch.object(main.Path,'read_text',side_effect=OSError('missing')),self.assertRaises(main.SourceUnavailable):main.fetch_current_source(0)
if __name__=='__main__':unittest.main()
