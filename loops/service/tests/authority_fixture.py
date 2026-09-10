"""Explicit synthetic Stripe fixture, never a production client or credential."""
import copy
import time
from loops.service.payment_claim import PRODUCTS,ClaimError
SID='cs_live_'+'SYNTHETIC1234'*4
SECRET='ab'*32  # known synthetic secret, never read from configuration
class Reader:
    def __init__(self,now=None):
        now=int(time.time()) if now is None else now;product=PRODUCTS['schemahand']
        self.calls=[];self.fail=False
        self.session={'id':SID,'object':'checkout.session','livemode':True,'payment_link':product['payment_link'],'mode':'payment',
                      'status':'complete','payment_status':'paid','amount_subtotal':19900,'amount_total':19900,'currency':'usd',
                      'created':now-120,'customer':'cus_SYNTHETIC','payment_intent':'pi_SYNTHETIC',
                      'total_details':{'amount_tax':0,'amount_discount':0,'amount_shipping':0}}
        self.line={'has_more':False,'data':[{'quantity':1,'price':{'id':product['price_id'],'product':product['product_id'],
                         'currency':'usd','unit_amount':19900,'type':'one_time'}}]}
        self.charge={'id':'ch_SYNTHETIC','object':'charge','livemode':True,'payment_intent':'pi_SYNTHETIC','amount':19900,
                     'currency':'usd','customer':'cus_SYNTHETIC','status':'succeeded','amount_captured':19900,'paid':True,'captured':True,'refunded':False,'disputed':False,
                     'amount_refunded':0,'created':now-90}
        self.intent={'id':'pi_SYNTHETIC','object':'payment_intent','livemode':True,'status':'succeeded','amount':19900,
                     'amount_received':19900,'currency':'usd','customer':'cus_SYNTHETIC','latest_charge':self.charge}
    def get(self,path,params=None):
        self.calls.append((path,params))
        if self.fail:raise ClaimError(503,'synthetic failure')
        if path=='/checkout/sessions/'+SID:return copy.deepcopy(self.session)
        if path=='/checkout/sessions/'+SID+'/line_items':return copy.deepcopy(self.line)
        if path=='/payment_intents/pi_SYNTHETIC' and params=={'expand[]':'latest_charge'}:return copy.deepcopy(self.intent)
        raise AssertionError('unexpected provider read')
