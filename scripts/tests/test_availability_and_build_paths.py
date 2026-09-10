"""Source projection drift and actual build main dispatch, in disposable roots."""
import contextlib,copy,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1];MAIN=Path('/home/gmullins/code/usta-paid-surfaces')
sys.path.insert(0,str(MAIN/'scripts'));sys.path.insert(0,str(HERE))
from availability_truth import off_sale_errors
spec=importlib.util.spec_from_file_location('build_under_test',Path(os.environ.get('BUILD_PATH_TEST_SOURCE',str(HERE/'build_site.py'))));build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
class Availability(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.family={'id':'example','short':'Example','price':'Not on sale','checkout':{'status':'off_sale','url':''}}
  self.catalog={'families':[self.family]};self.product=self.root/'families/example/index.html';self.product.parent.mkdir(parents=True);self.product.write_text('<h1>Example</h1><p class="price">Not on sale</p>')
  self.hub=self.root/'index.html';self.hub.write_text('<a class="card" href="families/example/"><span class="amount">Not on sale</span></a>')
  self.coverage=self.root/'families/coverage/index.html';self.coverage.parent.mkdir();self.coverage.write_text('<tr><td><strong>Example</strong></td><td>Not on sale</td></tr>')
 def errors(self):return off_sale_errors(self.root,self.catalog)
 def test_consistent_off_sale_passes_without_mutating_copy(self):
  before=[p.read_bytes() for p in [self.product,self.hub,self.coverage]];self.assertEqual(self.errors(),[]);self.assertEqual(before,[p.read_bytes() for p in [self.product,self.hub,self.coverage]])
 def test_stale_catalog_price_or_checkout_refused(self):
  self.family['price']='$19/mo';self.assertTrue(self.errors());self.family['price']='Not on sale';self.family['checkout']['url']='https://buy.stripe.com/synthetic';self.assertTrue(self.errors())
 def test_stale_product_price_or_checkout_refused(self):
  for raw in ['<p class="price"><span>$19/mo</span></p>','<a href="https://buy.stripe.com/synthetic">Subscribe</a>','<meta name="description" content="Buy for $19/mo">','<title>Example — $19/mo</title>']:
   self.product.write_text(raw);self.assertTrue(self.errors())
 def test_stale_directory_and_coverage_each_refused(self):
  self.hub.write_text('<a href="families/example/"><span>$19/mo</span>Card checkout on its page</a>');self.assertTrue(any('directory' in x for x in self.errors()));self.hub.write_text('<a href="families/example/">Not on sale</a>')
  self.coverage.write_text('<tr><td><strong>Example</strong></td><td>$19/mo</td></tr>');self.assertTrue(any('coverage' in x for x in self.errors()))
 def test_missing_projection_is_unknown_not_pass(self):
  self.coverage.unlink();self.assertTrue(self.errors())
 def test_unrelated_priced_family_is_unchanged(self):
  self.catalog['families'].append({'id':'other','price':'$49','checkout':{'status':'live','url':'https://buy.stripe.com/synthetic'}});self.assertEqual(self.errors(),[])
 def test_zero_matches_and_alternate_quotes_layout_do_not_hide_sales(self):
  self.hub.write_text('<p>No matching card</p>');self.assertTrue(any('unavailable' in e for e in self.errors()))
  self.hub.write_text("<a data-ref='directory' href = 'families/example/'>\n <span>$19/mo</span></a>")
  self.coverage.write_text("<tr class='row'> <td> <strong>  Example  </strong></td> <td>$19/mo</td></tr>")
  self.assertTrue(any('directory card' in e for e in self.errors()));self.assertTrue(any('coverage row' in e for e in self.errors()))
 def test_void_elements_cannot_hide_later_price_text(self):
  self.product.write_text('<p class="price"><img src="sample.svg"><br>$19/mo</p>');self.assertTrue(any('product' in e for e in self.errors()))
class BuildPaths(unittest.TestCase):
 def test_actual_main_copies_ordinary_and_extras_local_scripts(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'published.txt').write_text('# synthetic baseline\n');(root/'styles.css').write_text('/* fixture */');(root/'index.html').write_text('<main>Fixture directory</main>');(root/'extras.json').write_text('[{"id":"tool","short":"Tool"}]')
   cat={'families':[{'id':'ordinary','name':'Ordinary'},{'id':'tool','name':'Tool','kind':'build'}]}
   for fid in ['ordinary','tool']:
    folder=root/'families'/fid;folder.mkdir(parents=True);(folder/'index.html').write_text('<main>Fixture</main><script src="tool.js"></script>');(folder/'tool.js').write_text('window.fixture='+json.dumps(fid)+';')
   with patch.multiple(build,ROOT=root,DIST=root/'dist',CATALOG=cat,PUBLISHED=root/'published.txt',RETIRED_REASONS=root/'retired.json'),patch.object(build,'build_veto',return_value=({},None)),patch.object(build,'build_page',side_effect=lambda p,*a,**kw:p.read_text()),patch.object(build.family_status,'status',return_value=None),patch.object(build,'check_freshness') as fresh,contextlib.redirect_stdout(io.StringIO()):
    build.main();fresh.assert_called_once_with(root/'dist')
   for fid in ['ordinary','tool']:self.assertEqual((root/'dist'/fid/'tool.js').read_bytes(),(root/'families'/fid/'tool.js').read_bytes())
   self.assertFalse(any('buyer' in str(p) for p in (root/'dist').rglob('*')))
 def test_canonical_source_shell_is_idempotent_and_preserves_style_cache_query(self):
  import re
  from html.parser import HTMLParser
  class Inspect(HTMLParser):
   def __init__(self):super().__init__();self.ids=[];self.classes=[]
   def handle_starttag(self,t,a):
    attrs=dict(a)
    if 'id' in attrs:self.ids.append(attrs['id'])
    self.classes.extend(attrs.get('class','').split())
  for family in ('schemahand','grant-fit'):
   with self.subTest(family=family),tempfile.TemporaryDirectory() as tmp:
    src=MAIN/'families'/family/'index.html';first=build.build_page(src,family,family)
    p=Path(tmp)/'index.html';p.write_text(first);second=build.build_page(p,family,family)
    self.assertEqual(first,second)
    parsed=Inspect();parsed.feed(first)
    for name in ('crumbbar','foot-grid','foot-bottom'):self.assertEqual(parsed.classes.count(name),1)
    self.assertEqual(first.count("'gtm.start'"),1);self.assertEqual(len(parsed.ids),len(set(parsed.ids)))
    before=re.search(r'<link rel="stylesheet" href="([^"]*)"',src.read_text()).group(1)
    if '?' in before:self.assertIn('?'+before.split('?',1)[1],first)
if __name__=='__main__':unittest.main()
