import io
import unittest
import urllib.error
from unittest.mock import patch
from loops.service.payment_claim import StripeReader,ClaimError

class Response:
    def __init__(self,body=b'{}',encoding=None):self.body=io.BytesIO(body);self.read_sizes=[];self.headers={'Content-Encoding':encoding} if encoding else {}
    def read(self,size):self.read_sizes.append(size);return self.body.read(size)
    def __enter__(self):return self
    def __exit__(self,*args):return None
class ReaderBoundsTests(unittest.TestCase):
    def test_fixed_origin_version_and_bounded_read(self):
        response=Response();calls=[]
        class Opener:
            def open(self,request,timeout):calls.append((request,timeout));return response
        with patch('urllib.request.build_opener',return_value=Opener()):self.assertEqual(StripeReader('synthetic-key').get('/payment_intents/pi_FIXTURE',{'expand[]':'latest_charge'}),{})
        request,timeout=calls[0];self.assertTrue(request.full_url.startswith('https://api.stripe.com/v1/payment_intents/pi_FIXTURE?'))
        self.assertEqual(request.get_header('Stripe-version'),'2024-06-20');self.assertEqual(timeout,3);self.assertEqual(response.read_sizes,[2000001])
    def test_oversized_response_becomes_unknown(self):
        response=Response(b' '*2000001)
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value=response
            with self.assertRaises(ClaimError) as cm:StripeReader('synthetic').get('/payment_intents/pi_FIXTURE')
        self.assertEqual(cm.exception.status,503);self.assertEqual(response.read_sizes,[2000001])
    def test_redirect_handler_refuses_credentials_to_new_location(self):
        handlers=[]
        def build(handler):handlers.append(handler);raise ValueError('fixture stop')
        with patch('urllib.request.build_opener',side_effect=build),self.assertRaises(ClaimError):StripeReader('synthetic').get('/payment_intents/pi_FIXTURE')
        self.assertIsNone(handlers[0].redirect_request(None,None,302,'',{},'https://elsewhere.invalid/'))
    def test_encoded_payload_and_malformed_path_never_parse_or_open(self):
        response=Response(b'{}','gzip')
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value=response
            with self.assertRaises(ClaimError):StripeReader('synthetic').get('/payment_intents/pi_FIXTURE')
        self.assertEqual(response.read_sizes,[])
        for path in ('//elsewhere.invalid/key','/payment_intents/../other','/payment_intents/pi_X?bad=1'):
            with self.subTest(path=path),patch('urllib.request.build_opener') as build,self.assertRaises(ClaimError):
                StripeReader('synthetic').get(path)
            build.assert_not_called()
    def test_provider_exception_never_echoes_secret(self):
        with patch('urllib.request.build_opener',side_effect=RuntimeError('synthetic-secret')):
            with self.assertRaises(ClaimError) as cm:StripeReader('synthetic-secret').get('/payment_intents/pi_FIXTURE')
        self.assertNotIn('synthetic-secret',str(cm.exception));self.assertEqual(cm.exception.status,503)
if __name__=='__main__':unittest.main()
