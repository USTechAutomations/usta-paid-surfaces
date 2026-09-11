import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest,io,sys
from unittest.mock import patch
import check_urls as c
class Stability(unittest.TestCase):
 def check(self,witness,status):
  url='https://ustechautomations.com/feeds/'
  rows=[{'url':url,'path':'/feeds/','what':'hub'}]
  m={'rows':[{'url':url,'path':'/feeds/','kind':'hub'}],'directory_sha256':'a'*64}
  response={'status':status,'final':url,'location':'','outcome':'ok' if status==200 else 'other'}
  with patch.object(sys,'argv',['check_urls','--directory','--quiet','--pace','0']),patch.object(c,'targets',return_value=(rows,m)),patch.object(c,'witness_mark',return_value=witness),patch.object(c,'fetch',return_value=response.copy()),patch.object(c.time,'sleep'),patch('sys.stdout',new_callable=io.StringIO):
   with self.assertRaises(SystemExit) as e:c.main()
  return e.exception.code
 def test_unavailable_witness_cannot_call_link_broken(self):
  self.assertEqual(self.check({'seen':False,'mark':'','via':''},404),2)
 def test_good_witness_and_good_link(self):
  self.assertEqual(self.check({'seen':True,'mark':'same','body_sha256':'a'*64,'via':'body'},200),0)
 def test_good_witness_and_bad_link(self):
  self.assertEqual(self.check({'seen':True,'mark':'same','body_sha256':'a'*64,'via':'body'},404),1)
 def test_directory_changed_before_first_witness(self):
  self.assertEqual(self.check({'seen':True,'mark':'same','body_sha256':'b'*64,'via':'body'},200),3)
