import unittest
from unittest.mock import AsyncMock,Mock,patch
import main

class InputAdapterTests(unittest.IsolatedAsyncioTestCase):
 async def exercise(self,raw):
  class ActorStub:
   async def __aenter__(self):return self
   async def __aexit__(self,*args):return False
  actor=ActorStub();actor.get_input=AsyncMock(return_value=raw);actor.set_value=AsyncMock();actor.log=Mock();actor.push_data=AsyncMock()
  def collect(inp):
   main.validate_input(inp)
   return [],{'status':'NO_MATCHES','omitted_due_to_max_items':0}
  with patch('apify.Actor',actor),patch.object(main,'collect',side_effect=collect):await main.main()
  return actor
 async def test_falsy_non_object_input_is_rejected(self):
  for raw in [[],False,0,'']:
   with self.subTest(raw=raw),self.assertRaises(ValueError):await self.exercise(raw)
 async def test_none_and_empty_object_keep_documented_defaults(self):
  for raw in [None,{}]:
   actor=await self.exercise(raw);self.assertEqual(actor.set_value.call_args.args[1]['status'],'NO_MATCHES');actor.push_data.assert_not_called()
