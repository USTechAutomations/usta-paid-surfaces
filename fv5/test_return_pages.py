import json,re,tempfile,unittest
from pathlib import Path
from fv5.lib.ppp import thanks_page_html
from fv5.build_thanks import eta_for
from fv5.lib.return_page import session_capture
ROOT=Path(__file__).resolve().parents[1]
KEYS={'qrelay','ledgermatch','casepack','schemahand','acacheck'}
class ReturnPages(unittest.TestCase):
 def test_selected_families_keep_key_or_private_contract(self):
  catalog={r['id']:r for r in json.loads((ROOT/'catalog.json').read_text())['families']};selected=[]
  for directory in (ROOT/'fv5/families').iterdir():
   if (directory/'fulfil.py').exists() and directory.name in catalog and catalog[directory.name].get('checkout',{}).get('status') not in ('HOLD','EXTERNAL'):selected.append(directory.name)
  self.assertEqual(len(selected),15);self.assertEqual(len(set(selected)&KEYS),5)  # 13 + la-appeal-packet + silent-refusal-kit
  for family in selected:
   html=thanks_page_html(family,catalog[family]['name'],eta_for(ROOT/'fv5/families'/family))
   self.assertLess(html.index('history.replaceState'),html.index('<link'))
   self.assertLess(html.index('name="referrer" content="no-referrer"'),html.index('<link'))
   self.assertIn('sessionStorage',html);self.assertNotIn('localStorage.',html)
   self.assertIn('/pro/claim' if family in KEYS else '/delivery/',html)
   self.assertNotIn('/delivery/',html) if family in KEYS else self.assertNotIn('/pro/claim',html)
   self.assertIn('method: "POST"' if family not in KEYS else 'method:"POST"',html)
   self.assertNotIn('cache: "reload"',html);self.assertNotIn('fetch(private',html)
   self.assertEqual(len(re.findall(r'<h1\b',html)),1)
 def test_family_rejects_script_injection(self):
  with self.assertRaises(ValueError):session_capture('</script>')
 def test_product_names_are_escaped_in_both_modes(self):
  for family in ('qrelay','notary-journal'):
   html=thanks_page_html(family,'Synthetic <img onerror="reject">',15)
   self.assertNotIn('<img onerror=',html);self.assertIn('&lt;img',html)
 def test_eta_never_executes_fulfillment(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'fulfil.py').write_text('ETA_MINUTES = 12\nraise RuntimeError("must never execute")\n')
   self.assertEqual(eta_for(root),12)
   (root/'fulfil.py').write_text('ETA_MINUTES = True\n')
   with self.assertRaises(ValueError):eta_for(root)
   (root/'fulfil.py').write_text('raise RuntimeError("not executed")\n');self.assertEqual(eta_for(root),15)
if __name__=='__main__':unittest.main()
