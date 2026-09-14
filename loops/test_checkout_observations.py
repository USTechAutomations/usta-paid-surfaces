import unittest
from unittest.mock import patch
from loops import checkout_observations as c
class Observations(unittest.TestCase):
 def test_counted_zero_and_unreadable_stay_distinct(self):
  def reader(f,s,k):return {'state':'OBSERVED','by_event':{}} if f=='good' else {'state':'UNKNOWN'}
  with patch.object(c,'REVIEWED',{'good','missing'}):d=c.collect('fixture','2026-09-11',reader)
  self.assertEqual(d['families']['good']['checkout_clicks'],0);self.assertIsNone(d['families']['missing']['checkout_clicks']);self.assertEqual(d['independent_customers'],'UNKNOWN')
 def test_invalid_counter_and_exception_are_unknown(self):
  def reader(f,s,k):
   if f=='error':raise TimeoutError()
   return {'state':'OBSERVED','by_event':{'checkout_click':True}}
  with patch.object(c,'REVIEWED',{'bad','error'}):d=c.collect('fixture','2026-09-11',reader)
  self.assertTrue(all(r['state']=='UNKNOWN' and r['checkout_clicks'] is None for r in d['families'].values()))
 def test_missing_identity_never_calls_reader(self):
  with patch.object(c,'REVIEWED',{'a'}):d=c.collect(None,'2026-09-11',lambda *a: self.fail('called'))
  self.assertEqual(d['families']['a']['state'],'UNKNOWN')
if __name__=='__main__':unittest.main()
