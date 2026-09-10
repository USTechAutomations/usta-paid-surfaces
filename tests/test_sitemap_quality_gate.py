#!/usr/bin/env python3
from __future__ import annotations
import datetime,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(os.environ.get('SITEMAP_CONSUMER_ROOT','/home/gmullins/code/usta-paid-surfaces')).resolve(); CANONICAL=Path('/home/gmullins/code/usta-paid-surfaces')
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(1,str(CANONICAL/'scripts'))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
quality=load('sitemap_quality_gate',ROOT/'scripts/sitemap_quality_gate.py')
build_site=load('plan023_build_site',ROOT/'scripts/build_site.py')
build_mirror_sitemap=load('plan023_build_mirror',ROOT/'scripts/build_mirror_sitemap.py')
sys.path.insert(0,'/home/gmullins/Claude CLI/permits-engine');from permits_engine.page_quality import gate
class SitemapQualityGateTests(unittest.TestCase):
 def result(self,family,verdict):return {'family_id':f'/feeds/{family}','verdict':verdict,'summary':{},'requested':1,'fetched':1,'unreadable':0}
 def test_fail_withholds_pass_admits_and_stale_unknown_retains_last_decision(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'gate.json'; now=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
   gate.write_results([self.result('failed','FAIL'),self.result('passed','PASS'),self.result('stale','FAIL')],path,counted_at=now)
   self.assertEqual((False,'FAIL'),quality.admission('failed',gate_api=gate,gate_path=path))
   self.assertEqual((True,'PASS'),quality.admission('passed',gate_api=gate,gate_path=path))
   with mock.patch.object(gate,'family_verdict',return_value='UNKNOWN'):
    self.assertEqual((False,'UNKNOWN'),quality.admission('stale',gate_api=gate,gate_path=path))
   self.assertEqual((False,'SOURCE_USE_HOLD'),quality.admission('passed',source_use_hold=True,gate_api=gate,gate_path=path))
 def test_missing_malformed_import_and_api_errors_are_explicit_unknown(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);missing=root/'missing.json';malformed=root/'bad.json';malformed.write_text('{}')
   valid=root/'valid.json';gate.write_results([self.result('x','PASS')],valid,counted_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
   for path in (missing,malformed):
    with self.assertRaises(quality.QualityGateUnavailable) as caught:quality.require_available(gate_api=gate,gate_path=path)
    self.assertEqual('UNKNOWN',caught.exception.status)
   broken=mock.Mock(default_path=lambda:valid,SCHEMA=gate.SCHEMA)
   broken.family_verdict.side_effect=OSError('read failed')
   with self.assertRaises(quality.QualityGateUnavailable) as caught:quality.admission('x',gate_api=broken,gate_path=valid)
   self.assertEqual('UNKNOWN',caught.exception.status)
   with mock.patch.object(quality,'_canonical_gate',side_effect=ImportError('missing')):
    with self.assertRaises(quality.QualityGateUnavailable):quality.require_available()
 def test_feed_sitemap_keeps_route_and_excludes_only_failed_promotion(self):
  with tempfile.TemporaryDirectory() as td:
   dist=Path(td); (dist/'hospital-mrf').mkdir();(dist/'texas-formulary').mkdir()
   (dist/'hospital-mrf/index.html').write_text('<h1>held route still serves</h1>');(dist/'texas-formulary/index.html').write_text('<h1>unrelated</h1>')
   family_map={'hospital-mrf':{},'texas-formulary':{}}
   def admitted(fid,**_kw):return (False,'FAIL') if fid=='hospital-mrf' else (True,'PASS')
   with mock.patch.object(build_site,'DIST',dist),mock.patch.object(build_site,'FAMILY_BY_ID',family_map),mock.patch.object(build_site,'sitemap_admission',side_effect=admitted):promoted,_dated,held=build_site.write_sitemap(['/feeds/hospital-mrf','/feeds/texas-formulary'])
   sitemap=(dist/'sitemap.xml').read_text();self.assertTrue((dist/'hospital-mrf/index.html').is_file());self.assertNotIn('/feeds/hospital-mrf</loc>',sitemap);self.assertTrue((dist/'texas-formulary/index.html').is_file());self.assertIn('/feeds/texas-formulary</loc>',sitemap);self.assertEqual((1,{'hospital-mrf':'FAIL'}),(promoted,held))
 def test_unavailable_gate_aborts_before_overwriting_existing_dist(self):
  with tempfile.TemporaryDirectory() as td:
   dist=Path(td)/'dist';dist.mkdir();sentinel=dist/'current-public-byte';sentinel.write_text('preserve me')
   with mock.patch.object(build_site,'DIST',dist),mock.patch.object(build_site,'sitemap_gate_preflight',side_effect=quality.QualityGateUnavailable('UNKNOWN')):
    with self.assertRaises(quality.QualityGateUnavailable):build_site.main()
   self.assertEqual('preserve me',sentinel.read_text())
 def test_mirror_builder_uses_same_promotion_decision(self):
  pages=['families/hospital-mrf/index.html','families/texas-formulary/index.html']
  catalog={'families':[{'id':'hospital-mrf'},{'id':'texas-formulary'}]}
  def text(path):return json.dumps(catalog) if path=='catalog.json' else '<h1>route</h1>'
  def admitted(fid,**_kw):return (False,'FAIL') if fid=='hospital-mrf' else (True,'UNKNOWN')
  with mock.patch.object(build_mirror_sitemap,'sitemap_gate_preflight'),mock.patch.object(build_mirror_sitemap,'committed_pages',return_value=pages),mock.patch.object(build_mirror_sitemap,'retired_addrs',return_value=[]),mock.patch.object(build_mirror_sitemap,'committed_text',side_effect=text),mock.patch.object(build_mirror_sitemap,'sitemap_admission',side_effect=admitted):xml,n,_dated,_skipped=build_mirror_sitemap.build()
  self.assertNotIn('/families/hospital-mrf/',xml);self.assertIn('/families/texas-formulary/',xml);self.assertEqual(1,n)
if __name__=='__main__':unittest.main()
