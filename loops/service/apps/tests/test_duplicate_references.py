import itertools,unittest
from decimal import Decimal
from loops.service.apps import matching as m

def rows(amounts):return [{"ref":"INV-1","line":i+1,"date":None,"amount":Decimal(str(n))} for i,n in enumerate(amounts)]
class DuplicateReferences(unittest.TestCase):
 def test_all_permutations_match_the_same_multiset(self):
  amounts=[100,100,200,300]
  for permutation in set(itertools.permutations(amounts)):
   result=m.compare(rows(amounts),rows(permutation))
   self.assertEqual(result["counts"]["matched"],4)
   self.assertEqual(result["counts"]["amount_differs"],0)
 def test_exact_matches_before_residual_discrepancy(self):
  result=m.compare(rows([100,200]),rows([200,300]))
  self.assertEqual(result["counts"]["matched"],1)
  self.assertEqual(result["counts"]["amount_differs"],1)
 def test_unequal_duplicate_counts_preserve_missing_row(self):
  result=m.compare(rows([100,100]),rows([100]))
  self.assertEqual(result["counts"]["matched"],1)
  self.assertEqual(result["counts"]["missing_on_b"],1)
 def test_inputs_are_not_mutated(self):
  a=rows([100,200]);b=rows([200,100]);before=repr((a,b));m.compare(a,b);self.assertEqual(repr((a,b)),before)
