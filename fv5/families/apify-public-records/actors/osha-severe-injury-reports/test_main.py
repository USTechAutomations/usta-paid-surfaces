import asyncio
import csv
import io
import time
import unittest
import zipfile
from unittest.mock import AsyncMock,Mock,patch
import main

URL='https://www.osha.gov/sites/default/files/January2015toNovember2025.zip'
RELEASE=main.release_from_url(URL)
HEAD=['ID','UPA','EventDate','Employer','City','State','Primary NAICS','Hospitalized','Amputation','Loss of Eye','Nature','NatureTitle','Part of Body','Part of Body Title','FederalState','Address1','Final Narrative']
BASE=['2015010015','931176','1/2/2025','SYNTHETIC INDUSTRIAL FIRM','TEST CITY','NEW YORK','236220','1.00','0.00','0.00','121','Fractures','311','Arm(s)','1','123 PRIVATE TEST ADDRESS','PRIVATE WORKER NAME']

def zipped(rows=None,headers=None):
 text=io.StringIO();w=csv.writer(text);w.writerow(headers or HEAD);w.writerows(rows if rows is not None else [BASE]);out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('January2015toNovember2025.csv',text.getvalue())
 return out.getvalue()

def modified(**kwargs):
 row=list(BASE)
 for key,value in kwargs.items():row[HEAD.index(key)]=value
 return row

def collect(inp=None,rows=None,body=None):return main.collect(inp or {},source=(body if body is not None else zipped(rows),RELEASE))

class InputTests(unittest.TestCase):
 def test_boundaries_and_types(self):
  for inp in [[],False,0,'',{'maxItems':True},{'maxItems':0},{'maxItems':1001},{'timeoutSeconds':0},{'state':'XX'},{'dateFrom':'2025-02-30'},{'dateTo':'2025-1-1'},{'dateFrom':'2025-04-01','dateTo':'2025-01-01'},{'naicsPrefix':23},{'naicsPrefix':'2x'},{'keyword':['oil']},{'other':1}]:
   with self.subTest(inp=inp),self.assertRaises(ValueError):main.validate_input(inp)
 def test_small_default(self):self.assertEqual(main.validate_input({})['maxItems'],10)
 def test_state_case_names_and_abbreviations(self):
  for state in ['ny','New York',' NY ']:self.assertEqual(main.validate_input({'state':state})['state'],'NY')
 def test_invalid_input_never_fetches(self):
  with patch.object(main,'fetch_source') as fetch,self.assertRaises(ValueError):main.collect({'maxItems':False})
  fetch.assert_not_called()

class SourceTests(unittest.TestCase):
 def test_real_role_button_anchor_discovery(self):
  parser=main.DownloadLink();parser.feed('<a role="button" id="downloadDataset" href="/sites/default/files/January2015toNovember2025.zip">Download</a>');self.assertEqual(parser.urls,[URL])
 def test_unowned_malformed_and_reversed_release_refused(self):
  for url in [URL.replace('www.osha.gov','attacker.test'),URL+'?redirect=x',URL.replace('November2025','January2014'),URL.replace('January','Mysterious')]:
   with self.subTest(url=url),self.assertRaises(main.SourceUnavailable):main.release_from_url(url)
 def test_current_page_and_zip_fetch(self):
  page=f'<a id="downloadDataset" href="{URL}">Download</a>'.encode()
  with patch.object(main,'_get',side_effect=[page,zipped()]) as get:
   body,release=main.fetch_source(time.monotonic()+30);self.assertEqual(release,RELEASE);self.assertEqual(get.call_args_list[0].args[0],main.PAGE_URL);self.assertTrue(body.startswith(b'PK'))
 def test_http_error_unknown(self):
  with patch.object(main.urllib.request,'urlopen',side_effect=OSError('offline')),self.assertRaises(main.SourceUnavailable):main._get(URL,1000,time.monotonic()+20)
 def test_html_page_without_current_link_unknown(self):
  with patch.object(main,'_get',return_value=b'<html>Access denied</html>'),self.assertRaises(main.SourceUnavailable):main.fetch_source(time.monotonic()+20)
 def test_redirect_unknown(self):
  class Reply(io.BytesIO):status=200;url='https://www.osha.gov/error'
  with patch.object(main.urllib.request,'urlopen',return_value=Reply(b'error')),self.assertRaises(main.SourceUnavailable):main._get(URL,1000,time.monotonic()+20)

class ParseTests(unittest.TestCase):
 def test_old_ny_and_date_failures_repaired(self):
  rows,summary=collect({'state':'NY','dateFrom':'2025-01-01','dateTo':'2025-12-31'});self.assertEqual(len(rows),1);self.assertEqual(rows[0]['event_date'],'2025-01-02');self.assertEqual(rows[0]['state'],'NY')
 def test_counts_and_titles_have_correct_types(self):
  rows,_=collect();x=rows[0];self.assertEqual((x['hospitalized'],x['amputation'],x['nature'],x['body_part']),(1,0,'Fractures','Arm(s)'));self.assertEqual(x['nature_code'],'121')
 def test_missing_count_unknown_not_zero(self):
  rows,_=collect(rows=[modified(Amputation='',**{'Loss of Eye':''})]);self.assertIsNone(rows[0]['amputation']);self.assertIsNone(rows[0]['loss_of_eye'])
 def test_negative_and_fractional_counts_fail(self):
  for val in ['-1.00','0.5','NaN']:
   with self.assertRaises(main.SourceUnavailable):collect(rows=[modified(Hospitalized=val)])
 def test_reused_display_id_preserves_unique_upa(self):
  rows,summary=collect(rows=[BASE,modified(UPA='967503',State='TEXAS',Employer='SECOND SYNTHETIC FIRM')]);self.assertEqual(len(rows),2);self.assertEqual(len(set(x['report_key'] for x in rows)),2);self.assertEqual(summary['duplicate_display_id_groups'],1)
 def test_duplicate_upa_fails(self):
  with self.assertRaises(main.SourceUnavailable):collect(rows=[BASE,BASE])
 def test_newest_order_and_cap_omission(self):
  rows,summary=collect({'maxItems':1},rows=[BASE,modified(UPA='967503',EventDate='11/30/2025')]);self.assertEqual(rows[0]['source_upa'],'967503');self.assertEqual(summary['matching_reports'],2);self.assertEqual(summary['omitted_due_to_max_items'],1)
 def test_no_matches_distinct_from_unavailable(self):
  rows,summary=collect({'state':'TX'});self.assertEqual(rows,[]);self.assertEqual(summary['status'],'NO_MATCHES')
 def test_private_fields_not_returned_or_searched(self):
  rows,_=collect();self.assertNotIn('PRIVATE WORKER',str(rows));self.assertNotIn('PRIVATE TEST ADDRESS',str(rows));rows,_=collect({'keyword':'PRIVATE WORKER'});self.assertEqual(rows,[])
 def test_keyword_searches_promised_classification(self):
  rows,_=collect({'keyword':'fractures'});self.assertEqual(len(rows),1)
 def test_naics_range_and_uncertain_detail(self):
  r=modified(**{'Primary NAICS':'48-49'})
  rows,_=collect({'naicsPrefix':'49'},rows=[r]);self.assertEqual(len(rows),1)
  rows,s=collect({'naicsPrefix':'491'},rows=[r]);self.assertEqual(rows,[]);self.assertEqual(s['uncertain_industry_excluded_by_filter'],1)
 def test_unknown_date_excluded_only_with_date_filter(self):
  r=modified(EventDate='UNKNOWN');rows,s=collect(rows=[r]);self.assertIsNone(rows[0]['event_date']);self.assertEqual(s['unknown_dates'],1)
  rows,s=collect({'dateFrom':'2025-01-01'},rows=[r]);self.assertEqual(rows,[]);self.assertEqual(s['unknown_dates_excluded_by_filter'],1)
 def test_unknown_state_never_falsely_matches(self):
  r=modified(State='UNKNOWN');rows,s=collect(rows=[r]);self.assertIsNone(rows[0]['state']);self.assertEqual(s['unknown_states'],1)
  rows,_=collect({'state':'NY'},rows=[r]);self.assertEqual(rows,[])
 def test_schema_error_and_empty_source_unknown(self):
  for body in [b'<html>Error</html>',b'PKbroken',zipped(headers=['ID'],rows=[['1']]),zipped(rows=[])]:
   with self.assertRaises(main.SourceUnavailable):collect(body=body)
 def test_date_outside_declared_source_unknown(self):
  with self.assertRaises(main.SourceUnavailable):collect(rows=[modified(EventDate='1/1/2026')])
 def test_timeout_and_size_unknown(self):
  with self.assertRaises(main.SourceUnavailable):main.parse_source(zipped(),RELEASE,main.validate_input({}),time.monotonic()-1)
  with patch.object(main,'MAX_ZIP_BYTES',1),self.assertRaises(main.SourceUnavailable):collect()
 def test_source_metadata_and_raw_flag_preserved(self):
  rows,s=collect();self.assertEqual(rows[0]['source_federal_state_flag'],'1');self.assertEqual(s['source_period_to'],'2025-11-30');self.assertEqual(len(s['source_sha256']),64)

class AdapterTests(unittest.IsolatedAsyncioTestCase):
 async def test_falsy_non_object_input_never_runs_default_search(self):
  class ActorStub:
   async def __aenter__(self):return self
   async def __aexit__(self,*args):return False
  for raw in [[],False,0,'']:
   actor=ActorStub();actor.get_input=AsyncMock(return_value=raw);actor.set_value=AsyncMock();actor.log=Mock();actor.push_data=AsyncMock()
   with self.subTest(raw=raw),patch('apify.Actor',actor),patch.object(main,'fetch_source') as fetch,self.assertRaises(ValueError):await main.main()
   fetch.assert_not_called();actor.push_data.assert_not_called();self.assertEqual(actor.set_value.call_args.args[1]['status'],'INVALID_INPUT')

if __name__=='__main__':unittest.main()
