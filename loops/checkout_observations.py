"""Read observed click counters; never infer people, leads, payments or ROI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from scripts.install_checkout_events import REVIEWED

def collect(secret, since, read_counts):
    def one(family):
        if not secret:
            return family, {'state':'UNKNOWN','checkout_clicks':None,'reason':'signing identity unavailable'}
        try:
            row=read_counts(family,since,secret)
            if not isinstance(row, dict) or row.get('state')!='OBSERVED':
                return family, {'state':'UNKNOWN','checkout_clicks':None,'reason':'counter read unavailable'}
            counts=row.get('by_event')
            if not isinstance(counts,dict) or any(type(v) is not int or v<0 for v in counts.values()):
                return family, {'state':'UNKNOWN','checkout_clicks':None,'reason':'invalid counter'}
            return family, {'state':'OBSERVED','checkout_clicks':counts.get('checkout_click',0)}
        except Exception:
            return family, {'state':'UNKNOWN','checkout_clicks':None,'reason':'counter read failed'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=dict(pool.map(one, sorted(REVIEWED)))
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'since':since,'families':rows,
            'independent_customers':'UNKNOWN','revenue_attribution':'UNKNOWN',
            'scope':'Raw observed checkout-click events, not people or payments. Automated browser events use usta-diagnostic; other bots may remain.'}
