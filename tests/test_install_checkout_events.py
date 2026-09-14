import importlib.util,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('events',Path(__file__).resolve().parents[1]/'scripts/install_checkout_events.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Installer(unittest.TestCase):
 def test_rebuild_is_idempotent_and_preserves_offer(self):
  raw='<body><a data-checkout="kdp-lens" href="https://buy.stripe.com/example">Buy $49</a></body>'
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'kdp-lens/index.html';p.parent.mkdir();p.write_text(raw)
   self.assertEqual(m.install(td),['kdp-lens']);first=p.read_bytes();self.assertEqual(m.install(td),[]);self.assertEqual(p.read_bytes(),first);self.assertIn('Buy $49',p.read_text())
 def test_missing_button_has_no_event_script(self):self.assertEqual(m.attach('<body>No checkout</body>','kdp-lens'),'<body>No checkout</body>')
 def test_existing_separate_handlers_not_modified(self):
  raw='<body><a data-checkout="ttb">Subscribe</a></body>';self.assertEqual(m.attach(raw,'ttb'),raw)
 def test_ambiguous_marker_refused(self):
  with self.assertRaises(ValueError):m.attach('<body><a data-checkout="kdp-lens">Buy</a>usta-offer-click-observation</body>','kdp-lens')
if __name__=='__main__':unittest.main()
