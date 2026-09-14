from __future__ import annotations
import sqlite3,tempfile,unittest,threading
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import manual_artifacts as m
DB_SIZE=3291238400
DB_MTIME_NS=m.DB.stat().st_mtime_ns
class AddressPacketTests(unittest.TestCase):
 def _one(self):
  c=sqlite3.connect(f'file:{m.DB}?mode=ro',uri=True)
  try:return c.execute("select lower(jurisdiction),upper(trim(address)) from seller_signals where jurisdiction in (?,?,?,?,?,?) and address is not null and trim(address)<>'' group by lower(jurisdiction),upper(trim(address)) having count(*)=1 limit 1",m.ALLOWED_CITIES).fetchone()
  finally:c.close()
 def build(self,root,**kw):
  kw.setdefault('expected_db_size',DB_SIZE);kw.setdefault('expected_db_mtime_ns',DB_MTIME_NS)
  return m.build_address_packet(output_root=root,**kw)
 def test_valid_six_city_scope_maps_public_schema_and_canonical_guard(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD');out=Path(r['output']);text=(out/'artifact.csv').read_text()
   self.assertEqual(r['metadata']['scope']['row_count'],4);self.assertEqual(r['metadata']['guard']['verdict'],'CLEAN');self.assertEqual(text.splitlines()[0],','.join(m.OUT_HEADERS));self.assertEqual((out/'metadata.json').read_text(),__import__('json').dumps(r['metadata'],indent=2,sort_keys=True)+'\n');self.assertNotRegex(text.lower(),r'owner_name|contractor_name|intent_score|signals_json|payload_json');self.assertRegex(r['metadata']['selected_rows_sha256'],r'^[0-9a-f]{64}$')
 def test_wrong_and_thin_scope_refuse(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(m.ScopeUnavailable):self.build(Path(td),city='austin',street='NOT IN STORE')
   city,street=self._one();self.assertIsNotNone(city)
   with self.assertRaises(m.ScopeUnavailable):self.build(Path(td),city=city,street=street)
 def test_pinned_permission_source_and_guard(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(m.SourceUnknown):self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD',expected_db_size=DB_SIZE-1)
   with self.assertRaises(m.ScopeUnavailable):self.build(Path(td),city='los-angeles',street='ANY')
 def test_existing_output_is_never_clobbered(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD');out=Path(r['output']);original=(out/'artifact.csv').read_bytes();(out/'artifact.csv').write_bytes(b'changed')
   with self.assertRaises(m.ImmutableArtifactError):self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD')
   self.assertEqual((out/'artifact.csv').read_bytes(),b'changed');self.assertNotEqual(original,(out/'artifact.csv').read_bytes())
 def test_partial_package_is_never_completed_or_overwritten(self):
  with tempfile.TemporaryDirectory() as td:
   r=self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD');out=Path(r['output']);saved=(out/'metadata.json').read_bytes();(out/'metadata.json').unlink()
   with self.assertRaises(m.ImmutableArtifactError):self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD')
   self.assertFalse((out/'metadata.json').exists());self.assertTrue((out/'artifact.csv').exists());self.assertNotEqual(saved,b'')
 def test_empty_existing_package_is_never_replaced(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);scope='austin'+'\0'+'1613 WETHERSFIELD RD';target=m._package_path(root,'address-packet',scope);target.mkdir(mode=0o700)
   with self.assertRaises(m.ImmutableArtifactError):self.build(root,city='austin',street='1613 WETHERSFIELD RD')
   self.assertEqual(list(target.iterdir()),[])
 def test_floor_cannot_be_lowered(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(m.ScopeUnavailable):self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD',min_rows=0)
 def test_unknown_guard_never_commits(self):
  original=m._guard_module
  class Bad:
   def scan(self,*args,**kwargs):return ('UNKNOWN','fixture outage')
  try:
   m._guard_module=lambda:Bad()
   with tempfile.TemporaryDirectory() as td:
    with self.assertRaises(m.SourceUnknown):self.build(Path(td),city='austin',street='1613 WETHERSFIELD RD')
    self.assertEqual(list(Path(td).iterdir()),[])
  finally:m._guard_module=original
 def test_non_private_root_refuses(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'public';root.mkdir(mode=0o755)
   with self.assertRaises(m.SourceUnknown):self.build(root,city='austin',street='1613 WETHERSFIELD RD')
 def test_concurrent_identical_commit_has_one_immutable_package(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);results=[];errors=[]
   def run():
    try:results.append(m._commit_package(root,'race','scope',b'a\n',b'b\n',lambda p,**kw:('CLEAN',''),store=m.DB,record=m.RECORD))
    except Exception as e:errors.append(e)
   threads=[threading.Thread(target=run) for _ in range(2)]
   [t.start() for t in threads];[t.join() for t in threads]
   self.assertEqual(len(results),2);self.assertFalse(errors)
   package=results[0];self.assertTrue((package/'artifact.csv').read_bytes()==b'a\n');self.assertEqual(package,results[1])
   self.assertFalse(any(p.name.startswith(('.guard-','.package-')) for p in root.iterdir()))


class ClerkClockTests(unittest.TestCase):
 def test_raw_verified_quarter_build_and_guard(self):
  import clerk_clock
  with tempfile.TemporaryDirectory() as td:
   r=clerk_clock.build_clerk_clock(office='austin',quarter='2026-Q3',output_root=Path(td),expected_db_size=DB_SIZE,expected_db_mtime_ns=DB_MTIME_NS)
   out=Path(r['output']); self.assertEqual(r['metadata']['scope']['verified_transitions'],128);self.assertEqual(r['metadata']['guard']['verdict'],'CLEAN');self.assertIn('median_days,p25,p75',out.joinpath('artifact.csv').read_text())
   self.assertRegex(r['metadata']['selected_observations_sha256'],r'^[0-9a-f]{64}$');self.assertIn('timing summary only',r['metadata']['fulfillment_component'])
 def test_insufficient_quarter_and_unknown_office_refuse(self):
  import clerk_clock
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(clerk_clock.ScopeUnavailable):clerk_clock.build_clerk_clock(office='montgomery-md',quarter='2026-Q2',output_root=Path(td),expected_db_size=DB_SIZE,expected_db_mtime_ns=DB_MTIME_NS)
   with self.assertRaises(clerk_clock.ScopeUnavailable):clerk_clock.build_clerk_clock(office='boston',quarter='2026-Q3',output_root=Path(td),expected_db_size=DB_SIZE,expected_db_mtime_ns=DB_MTIME_NS)
 def test_floor_and_same_day_model_versions(self):
  import clerk_clock
  with self.assertRaises(clerk_clock.ScopeUnavailable):
   with tempfile.TemporaryDirectory() as td:clerk_clock.build_clerk_clock(office='austin',quarter='2026-Q3',output_root=Path(td),expected_db_size=DB_SIZE,expected_db_mtime_ns=DB_MTIME_NS,min_observations=0)
  self.assertEqual(clerk_clock._collapse_daily([('2026-01-01','open','m1'),('2026-01-01','open','m2'),('2026-01-02','closed','m2')]),[('2026-01-01','open'),('2026-01-02','closed')])
  with self.assertRaises(clerk_clock.SourceUnknown):clerk_clock._collapse_daily([('2026-01-01','open','m1'),('2026-01-01','closed','m2')])


if __name__=='__main__':unittest.main(verbosity=2)
