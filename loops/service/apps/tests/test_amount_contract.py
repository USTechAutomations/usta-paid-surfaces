import unittest
from decimal import Decimal
from loops.service.apps import matching as m
class Contract(unittest.TestCase):
 def test_valid(self):
  self.assertEqual(m.parse_amount("USD 1,234.50"),Decimal("1234.50"))
  self.assertEqual(m.parse_amount("(45.00)"),Decimal("-45.00"))
 def test_invalid(self):
  for value in ["1e3","1O0","9"*100,"EUR $45","USD 45 USD","£45 EUR"]:
   with self.subTest(value=value):self.assertIsNone(m.parse_amount(value))
if __name__=="__main__":unittest.main()
