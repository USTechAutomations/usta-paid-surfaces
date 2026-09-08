import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('preserve',Path(__file__).resolve().parents[1]/'scripts/preserve_independent_overlays.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
ROW={'id':'workshop-20260908-c','prefixes':['/feeds/workshop/','/feeds/tool/']}
HEAD={'revision':'rev1','generation':1,'image':'gcr.io/usta-prod/usta-feeds@sha256:'+'a'*64}

class Preservation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.source=self.root/'source';self.dest=self.root/'dest'
  for r in (self.source,self.dest):
   (r/'site').mkdir(parents=True);(r/'nginx.conf').write_text('server {\n  location / { try_files $uri =404; }\n}\n');(r/'site/index.html').write_text('<body><h1>Existing</h1></body>');(r/'site/sitemap.xml').write_text('<urlset><url><loc>https://ustechautomations.com/feeds/existing/</loc></url></urlset>')
  for slug in ('workshop','tool'):
   (self.source/'site'/slug).mkdir();(self.source/'site'/slug/'index.html').write_text(slug)
  (self.source/'site/workshop/engine.wasm').write_bytes(b'\0asm-runtime')
  blocks='  location ^~ /workshop/api/ { return 503 \'{"error":"not connected","nested":{}}\'; }\n'
  for slug in ('workshop','tool'):blocks+=f'  location = /{slug} {{ return 308 /feeds/{slug}/; }}\n  location ^~ /{slug}/ {{ types {{ application/wasm wasm; }} try_files $uri =404; }}\n'
  text=(self.source/'nginx.conf').read_text();(self.source/'nginx.conf').write_text(text.replace('  location / {',blocks+'  location / {'))
  (self.source/'site/index.html').write_text('<body><section id="workshop-independent-20260908"><a href="/feeds/workshop/">Workshop</a></section></body>')
  text=(self.source/'site/sitemap.xml').read_text();(self.source/'site/sitemap.xml').write_text(text.replace('</urlset>',''.join('<url><loc>https://ustechautomations.com'+x+'</loc></url>'for x in ROW['prefixes'])+'</urlset>'))
 def build(self):return p.overlay(self.source,self.dest,[ROW],HEAD)
 def test_retains_files_routes_discovery_and_current_new_pages(self):
  (self.dest/'site/new-family.txt').write_text('newer release')
  r=self.build();self.assertEqual(3,len(r['component_files']));self.assertEqual(b'\0asm-runtime',(self.dest/'site/workshop/engine.wasm').read_bytes());self.assertEqual('newer release',(self.dest/'site/new-family.txt').read_text());self.assertIn('return 503',(self.dest/'nginx.conf').read_text());self.assertIn('# workshop-c begin',(self.dest/'nginx.conf').read_text());self.assertEqual(3,len(p.sitemap_urls((self.dest/'site/sitemap.xml').read_text())))
 def test_missing_current_component_refuses(self):
  (self.source/'site/tool/index.html').unlink()
  with self.assertRaises(ValueError):self.build()
 def test_missing_runtime_api_route_refuses(self):
  text=(self.source/'nginx.conf').read_text();(self.source/'nginx.conf').write_text('\n'.join(x for x in text.splitlines() if '/workshop/api/' not in x))
  with self.assertRaises(ValueError):self.build()
 def test_missing_current_sitemap_admission_refuses(self):
  (self.source/'site/sitemap.xml').write_text('<urlset/>')
  with self.assertRaises(ValueError):self.build()
 def test_component_route_collision_refuses(self):
  text=(self.dest/'nginx.conf').read_text();(self.dest/'nginx.conf').write_text(text.replace('  location / {','  location ^~ /tool/ { return 404; }\n  location / {'))
  with self.assertRaises(ValueError):self.build()
 def test_file_symlink_refuses(self):
  (self.source/'site/tool/link').symlink_to(self.source/'site/workshop/index.html')
  with self.assertRaises(ValueError):self.build()
 def test_postprepare_byte_mutation_refuses(self):
  r=self.build();(self.dest/'site/tool/index.html').write_text('changed')
  with self.assertRaises(ValueError):p.check_candidate(self.dest,r)
 def test_postprepare_routing_mutation_refuses(self):
  r=self.build();(self.dest/'nginx.conf').write_text('removed')
  with self.assertRaises(ValueError):p.check_candidate(self.dest,r)
 def test_quoted_nested_braces_are_preserved(self):
  blocks=p.location_blocks((self.source/'nginx.conf').read_text());self.assertEqual(6,len(blocks));self.assertIn('"nested":{}',blocks[0][1])
 def test_split_traffic_refuses(self):
  with patch.object(p,'gcloud',return_value={'status':{'conditions':[{'type':'Ready','status':'True'}],'traffic':[{'revisionName':'old','percent':50},{'revisionName':'new','percent':50}]}}):
   with self.assertRaises(ValueError):p.current_head('account')
 def test_uses_serving_revision_not_latest_ready(self):
  service={'status':{'conditions':[{'type':'Ready','status':'True'}],'latestReadyRevisionName':'unserved','traffic':[{'revisionName':'served','percent':100}]},'metadata':{'generation':2}}
  with patch.object(p,'gcloud',side_effect=[service,{'status':{'imageDigest':HEAD['image']}}]) as call:
   self.assertEqual('served',p.current_head('account')['revision']);self.assertIn('served',call.call_args.args)
 def test_hub_marker_without_href_refuses(self):
  r=self.build();path=self.dest/'site/index.html';path.write_text(path.read_text().replace('href="/feeds/workshop/"','data-removed="/feeds/workshop/"'))
  with self.assertRaises(ValueError):p.check_candidate(self.dest,r)
 def test_second_fresh_build_preserves_source_template(self):
  original=(self.dest/'nginx.conf').read_text();self.build();second=self.root/'second';(second/'site').mkdir(parents=True)
  (second/'nginx.conf').write_text(original);(second/'site/index.html').write_text('<body>Existing</body>');(second/'site/sitemap.xml').write_text('<urlset></urlset>')
  r=p.overlay(self.source,second,[ROW],HEAD);self.assertEqual(3,len(r['component_files']))
 def test_explicit_gcloud_binary_needs_no_ambient_path(self):
  with patch.object(p,'GCLOUD_BIN','/opt/google/bin/gcloud'),patch.object(p.subprocess,'check_output',return_value=b'{}') as invoke:
   p.gcloud('account','run','services','list');self.assertEqual('/opt/google/bin/gcloud',invoke.call_args.args[0][0])
 def test_pending_other_deployment_refuses(self):
  service={'status':{'conditions':[{'type':'Ready','status':'Unknown'}],'traffic':[{'revisionName':'served','percent':100}]}}
  with patch.object(p,'gcloud',return_value=service):
   with self.assertRaises(ValueError):p.current_head('account')
 def test_stale_head_refuses(self):
  self.build()
  with patch.object(p,'current_head',return_value={**HEAD,'generation':2}),patch('sys.argv',['script','check-head','--candidate',str(self.dest)]):
   with self.assertRaises(ValueError):p.main()

if __name__=='__main__':unittest.main()
