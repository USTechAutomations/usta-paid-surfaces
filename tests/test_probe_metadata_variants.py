import unittest,tempfile,datetime,contextlib,io,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_live as P
class MetadataVariants(unittest.TestCase):
 def test_real_sweep_handles_variants_and_oversize(self):
  site='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.invalid/fixture</loc></url></urlset>'
  cases=[('<meta name="data-newest" content="2020-01-01"><meta name="data-cadence-days" content="1"><!-- '+P.PAUSED_PHRASE+' -->',1),("<meta name='data-newest' content='2020-01-01'><meta name='data-cadence-days' content='1'>",1),('<meta content="2020-01-01" name="data-newest"><meta content="1" name="data-cadence-days">',1),(f'<meta name="data-newest" content="{datetime.date.today()}"><meta name="data-cadence-days" content="'+('9'*5000)+'">',2),('<meta name="data-newest" content="2020-01-01"><meta name="data-newest" content="2026-09-11"><meta name="data-cadence-days" content="1">',2)]
  for html,expected in cases:
   with self.subTest(expected=expected),tempfile.TemporaryDirectory() as d,patch.object(P,'ALERT',Path(d)/'alert.md'),patch.object(P,'check_directory',return_value={'status':'pass','report':{'ok':1},'problem':''}),patch.object(P,'fetch',side_effect=[(200,site),(200,html)]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    self.assertEqual(P.main(),expected)

 def test_oversized_response_remains_unknown(self):
  from unittest.mock import MagicMock
  response=MagicMock()
  response.__enter__.return_value=response
  response.status=200
  response.read.return_value=b'x'*(P.MAX_BODY_BYTES+1)
  with patch.object(P.urllib.request,'urlopen',return_value=response):
   code,reason=P.fetch('https://example.invalid/fixture')
  self.assertEqual(code,0)
  self.assertIn('too large',reason)
  response.read.assert_called_once_with(P.MAX_BODY_BYTES+1)
