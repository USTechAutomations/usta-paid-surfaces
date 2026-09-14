import copy,hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
P=Path(__file__).resolve().parents[3]/'deploy_recovery.py'
spec=importlib.util.spec_from_file_location('deploy',P);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class QuestionnaireDeployment(unittest.TestCase):
 def test_qrelay_release_preserves_configuration_and_copies_one_file(self):
  image='gcr.io/usta-prod/usta-loops@sha256:'+'a'*64
  before=b'synthetic app';questionnaire=b'synthetic questionnaire';seen={}
  svc={'status':{'traffic':[{'revisionName':'old','percent':100}],'url':'https://fixture.invalid'},'metadata':{},'spec':{}}
  svc['spec']['template']={'metadata':{},'spec':{'containers':[{'image':image,'env':[{'name':'CONFIG','value':'fixture'}]}]}}
  svc['spec']['traffic']=[]
  def gj(*args):
   if 'revisions' in args:return {'status':{'imageDigest':image}}
   return copy.deepcopy(svc)
  def output(cmd,**kw):
   if 'print-access-token' in cmd:return 'synthetic-registry-credential'
   if 'create' in cmd:return 'fixture-container'
   raise AssertionError(cmd)
  def run(cmd,**kw):
   if cmd[:2]==['docker','cp']:
    Path(cmd[-1]).write_bytes(questionnaire if 'qrelay.py' in cmd[-2] else before)
   if cmd[:2]==['docker','build']:
    ctx=Path(cmd[-1]);seen['files']=sorted(str(p.relative_to(ctx)) for p in ctx.rglob('*') if p.is_file())
   if 'replace' in cmd:
    manifest=json.loads(Path(cmd[cmd.index('replace')+1]).read_text());seen['env']=manifest['spec']['template']['spec']['containers'][0]['env']
   return SimpleNamespace(returncode=0)
  with patch.object(d,'gjson',side_effect=gj),patch.object(d.subprocess,'check_output',side_effect=output),patch.object(d.subprocess,'run',side_effect=run),patch.object(sys,'argv',['deploy','--qrelay-only','--expected-image',image,'--expected-app-sha256',hashlib.sha256(before).hexdigest(),'--expected-qrelay-sha256',hashlib.sha256(questionnaire).hexdigest()]):d.main()
  self.assertEqual(seen['env'],[{'name':'CONFIG','value':'fixture'}])
  self.assertEqual(seen['files'],['Dockerfile','loops/service/apps/qrelay.py'])
 def test_missing_questionnaire_proof_refuses_before_provider_call(self):
  with patch.object(d,'gjson',side_effect=AssertionError('provider reached')),patch.object(sys,'argv',['deploy','--qrelay-only','--expected-app-sha256','a'*64]):
   with self.assertRaises(RuntimeError):d.main()
if __name__=='__main__':unittest.main()
