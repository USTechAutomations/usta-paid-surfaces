"""Existing loop-product thank-you pages use private on-demand key retrieval."""
from html import escape
from brand.shell import masthead, footer
from fv5.lib.return_page import session_capture, RETURN_STYLE

BASE="https://ustechautomations.com/feeds"
SERVICE="https://usta-loops-260481739341.us-central1.run.app"
FAMILIES={"qrelay","ledgermatch","casepack","schemahand","acacheck"}

def thanks_page(family, name):
    if family not in FAMILIES:raise ValueError("unsupported product")
    body='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">
__SESSION_CAPTURE__
<title>__NAME__ — your key</title><link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css?v=customer20260909">
<meta name="description" content="Retrieve the paid key for your confirmed __NAME__ purchase.">
<style>__RETURN_STYLE__</style>
</head><body data-family="__FAMILY__" data-page="purchase-return"><a class="skip" href="#main">Skip to content</a>
__HEADER__
<section class="hero"><div class="wrap"><p class="eyebrow">Your purchase</p><h1>Your key</h1><p class="lede">__NAME__</p>
<p class="lede">Retrieve your key from your confirmed Stripe purchase. This tab retains access when refreshed. If you close it or lose access, contact us with your receipt number.</p></div></section>
<main id="main"><div class="wrap"><section class="contact">
<p id="status" class="lede" role="status" aria-live="polite">Checking your purchase…</p>
<div id="key-panel" hidden><label for="paid-key">Your key</label><textarea id="paid-key" readonly rows="3" style="width:100%;box-sizing:border-box;overflow-wrap:anywhere"></textarea>
<p>Paste this key into the key box in the tool. Keep your key private.</p></div>
<p><button id="action" class="btn btn-buy" type="button" disabled>Checking purchase</button></p>
<p><a href="__BASE__/__FAMILY__/">Open __NAME__</a></p>
<p>Need help with this purchase? <a href="mailto:operations@ustechautomations.com?subject=__FAMILY__%20purchase">Contact us</a> with your receipt number.</p>
<noscript><p>Enable JavaScript to retrieve your key from this purchase return page.</p></noscript>
</section></div></main>
__FOOTER__
<script>
(function(){
  "use strict";
  const sid=window.__fv5DeliverySession || null;
  delete window.__fv5DeliverySession;
  const status=document.getElementById("status"),action=document.getElementById("action"),field=document.getElementById("paid-key");
  let key="";
  async function retrieve(){
    action.disabled=true;status.textContent="Checking your purchase…";
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),25000);
    try{
      const response=await fetch("__SERVICE__/pro/claim",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({family:"__FAMILY__",session_id:sid}),cache:"no-store",credentials:"omit",referrerPolicy:"no-referrer",signal:controller.signal});
      const data=await response.json();
      if(response.ok&&data.ok&&data.family==="__FAMILY__"&&typeof data.key==="string"&&data.key.length>0&&data.key.length<=4096){
        key=data.key;field.value=key;document.getElementById("key-panel").hidden=false;
        status.textContent="Your key is available. Copy it into the tool.";action.textContent="Copy key";
      }else{status.textContent=data.reason||"We could not verify the purchase. Please retry.";action.textContent="Try again";}
    }catch(error){status.textContent="We could not reach payment verification. Please retry.";action.textContent="Try again";}
    finally{clearTimeout(timeout);action.disabled=false;}
  }
  action.addEventListener("click",async()=>{
    if(!key){await retrieve();return;}
    try{await navigator.clipboard.writeText(key);status.textContent="Key copied. Paste it into the tool.";}
    catch(error){field.focus();field.select();status.textContent="Select and copy the key above.";}
  });
  if(!sid){status.textContent="Open this page from your Stripe purchase return link.";action.textContent="Purchase return link required";return;}
  retrieve();
})();
</script></body></html>'''
    return (body.replace("__SESSION_CAPTURE__",session_capture(family)).replace("__RETURN_STYLE__",RETURN_STYLE).replace("__HEADER__",masthead(" / "+escape(name)+" / Your key"))
            .replace("__FOOTER__",footer()).replace("__NAME__",escape(name))
            .replace("__FAMILY__",family).replace("__BASE__",BASE).replace("__SERVICE__",SERVICE))
