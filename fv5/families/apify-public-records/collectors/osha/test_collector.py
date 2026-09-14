from pathlib import Path
import sys,io,json,zipfile,unittest,hashlib,tempfile,types
from unittest.mock import patch
candidate=Path(__file__).parents[1]/'candidate'
actor_dir=candidate if candidate.is_dir() else Path(__file__).parents[2]/'actors/osha-severe-injury-reports'
sys.path.insert(0,str(actor_dir))
import main as actor
from test_main import zipped,RELEASE
import collector

class CollectorTests(unittest.TestCase):
 def evidence(self,body):return {'page_http':200,'download_http':200,'collected_at':'2026-09-12T00:00:00+00:00','source_sha256':hashlib.sha256(body).hexdigest()}
 def test_private_columns_removed_and_source_identity_preserved(self):
  body=zipped();clean,m,s=collector.sanitize(actor,body,RELEASE,self.evidence(body));self.assertEqual(m['source']['sha256'],hashlib.sha256(body).hexdigest());self.assertEqual(m['source_rows'],1)
  with zipfile.ZipFile(io.BytesIO(clean)) as z:text=z.read(z.namelist()[0]).decode()
  self.assertNotIn('PRIVATE WORKER',text);self.assertNotIn('PRIVATE TEST ADDRESS',text);self.assertEqual(set(m['columns']),actor.REQUIRED)
 def test_sanitization_deterministic(self):
  body=zipped();a,_,_=collector.sanitize(actor,body,RELEASE,self.evidence(body));b,_,_=collector.sanitize(actor,body,RELEASE,self.evidence(body));self.assertEqual(a,b)
 def test_source_proof_mismatch_refused(self):
  body=zipped();e=self.evidence(body);e['source_sha256']='f'*64
  with self.assertRaises(RuntimeError):collector.sanitize(actor,body,RELEASE,e)
 def test_bad_source_fails_without_replacement(self):
  with self.assertRaises(actor.SourceUnavailable):collector.sanitize(actor,b'error',RELEASE,self.evidence(b'error'))
 def test_failed_public_artifact_read_never_changes_latest(self):
  sys.path.insert(0,'/home/gmullins/code/market-services/api-access');import access
  body=zipped();artifact,m,_=collector.sanitize(actor,body,RELEASE,self.evidence(body));calls=[]
  class Response(io.BytesIO):status=200
  class Opener:
   def open(self,req,timeout):
    if isinstance(req,str):calls.append(('GET',req));return Response(b'wrong bytes')
    calls.append((req.get_method(),req.full_url));return Response(b'')
  class Client:token='FIXTURE_NO_CREDENTIAL'
  with patch.object(collector.urllib.request,'build_opener',return_value=Opener()),self.assertRaises(RuntimeError):collector.publish(Client(),'A'*17,artifact,m)
  self.assertFalse(any(method=='PUT' and url.endswith('LATEST.json') for method,url in calls))
class OperationTests(unittest.TestCase):
 def test_duplicate_collector_is_refused(self):
  with tempfile.TemporaryDirectory() as tmp:
   first=collector.acquire_lock(Path(tmp))
   try:
    with self.assertRaises(BlockingIOError):collector.acquire_lock(Path(tmp))
   finally:first.close()
 def test_only_old_generated_bundles_are_pruned(self):
  with tempfile.TemporaryDirectory() as tmp:
   state=Path(tmp)
   for n in range(4):
    child=state/f'20260912T00000{n}Z';child.mkdir();(child/'result.json').write_text('{"status":"SUCCESS"}');(child/'source.zip').write_bytes(b'fixture');(child/'sanitized.zip').write_bytes(b'fixture')
   collector.prune_generated_bundles(state);self.assertFalse((state/'20260912T000000Z/source.zip').exists());self.assertTrue((state/'20260912T000000Z/result.json').exists());self.assertTrue((state/'20260912T000001Z/source.zip').exists())
class GuardTests(unittest.TestCase):
 def check(self,usage=1,cap=5,price=0,enabled=True,network='PASS'):
  sys.path.insert(0,'/home/gmullins/code/market-services/api-access');import access
  class Client:
   def get(self,path):
    if path.endswith('/limits'):return {'data':{'limits':{'maxMonthlyUsageUsd':cap},'current':{'monthlyUsageUsd':usage}}}
    if path.endswith('/me'):return {'data':{'id':'owner','plan':{'id':'FREE','isEnabled':enabled,'monthlyBasePriceUsd':price,'monthlyUsageCreditsUsd':5}}}
    return {'data':{'userId':'owner'}}
  with patch.object(access,'Client',return_value=Client()),patch.object(collector.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=network)):
   return collector.preflight('A'*17)
 def test_free_plan_and_company_guard_pass(self):self.assertIsNotNone(self.check())
 def test_unknown_over_cap_or_paid_conditions_refuse(self):
  for kw in [{'usage':float('nan')},{'cap':float('nan')},{'usage':4.8},{'cap':10},{'price':1},{'enabled':False},{'network':'UNKNOWN'}]:
   with self.subTest(kw=kw),self.assertRaises(RuntimeError):self.check(**kw)
if __name__=='__main__':unittest.main()
