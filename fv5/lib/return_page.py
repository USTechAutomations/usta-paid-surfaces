"""Shared private return-page session capture and token-based layout.

Only a synthetic or buyer-supplied session reaches this browser code. This module
never reads state, queries a payment provider, or writes a purchase record.
"""
import json
import re

RETURN_STYLE = '''
body[data-page="purchase-return"] main a, body[data-page="purchase-return"] footer a { color: var(--fg); text-decoration: underline; }
body[data-page="purchase-return"] .hero h1 { overflow-wrap: anywhere; }
body[data-page="purchase-return"] textarea { color: var(--fg); background: var(--bg); border: 1px solid var(--line); padding: .75rem; font: inherit; border-radius: var(--radius); width: 100%; box-sizing: border-box; overflow-wrap: anywhere; }
body[data-page="purchase-return"] .btn, body[data-page="purchase-return"] .mast-cta { min-height: 44px; white-space: normal; font-family: inherit; font-size: 1.1875rem; font-weight: 700; }
body[data-page="purchase-return"] :focus-visible { outline: 2px solid var(--fg); outline-offset: 3px; }
@media (min-width: 1024px) and (max-width: 1279px) { body[data-page="purchase-return"] .mast-nav { display: none; } }
'''


def session_capture(family):
    """Inline script placed before every externally loaded resource.

    Accept existing Stripe query returns and future fragment returns. Fragments
    avoid the first-document request exposure, but this code cannot rewrite a
    provider's already-configured return URL. No browser evidence should record
    that initial query. Store only per family, never in localStorage.
    """
    if not isinstance(family,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',family):
        raise ValueError('Unsupported return family')
    return '''<script>
(function(){
  "use strict";
  const key="fv5_sid_"+__FAMILY_JSON__;
  const values=[...new URLSearchParams(location.search).getAll("session_id"),...new URLSearchParams(location.hash.slice(1)).getAll("session_id")];
  let sid=values.length===1?values[0]:null;
  history.replaceState(null,"",location.pathname);
  const valid=value=>typeof value==="string"&&/^cs_(?:live|test)_[A-Za-z0-9]{16,80}$/.test(value);
  try{
    if(values.length){if(valid(sid))sessionStorage.setItem(key,sid);else sessionStorage.removeItem(key);}
    else sid=sessionStorage.getItem(key);
  }catch(error){}
  window.__fv5DeliverySession=valid(sid)?sid:null;
})();
</script>'''.replace('__FAMILY_JSON__',json.dumps(family))
