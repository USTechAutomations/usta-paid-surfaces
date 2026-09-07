const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
const script=fs.readFileSync(require('node:path').join(__dirname,'../scripts/paid_click_reference.js'),'utf8');
function run(params,nav={},url='https://buy.stripe.com/aFafZa3cWg94gEcdTA0sU0T',layer=[]){
 const link={href:url};const listeners={};
 const context={URL,URLSearchParams,Date,location:{pathname:'/feeds/permit-files/austin/',search:'?ad_campaign=r1&ad_group=g1&ad_arm=A&'+params,href:'https://ustechautomations.com/feeds/permit-files/austin/'},navigator:nav,window:{dataLayer:layer},document:{documentElement:{classList:{add(){}}},readyState:'complete',querySelectorAll(){return [link]},addEventListener(event,fn){listeners[event]=fn}}};
 vm.runInNewContext(script,context);return {link,listeners,context};
}
let x=run('gclid=click_id_with_underscores');let ref=new URL(x.link.href).searchParams.get('client_reference_id');assert.match(ref,/^usta1_r1_g1_A_g_[a-z0-9]+_click_id_with_underscores$/);
assert.equal(new URL(run('wbraid=abcdef_123456').link.href).searchParams.get('client_reference_id').split('_')[4],'w');
assert.equal(new URL(run('gbraid=abcdef_123456').link.href).searchParams.get('client_reference_id').split('_')[4],'b');
for(const params of ['', 'gclid=short','gclid='+('a'.repeat(151)), 'gclid=abcdefghijk&wbraid=abcdefghijk'])assert.equal(new URL(run(params).link.href).searchParams.has('client_reference_id'),false);
assert.equal(new URL(run('gclid=abcdefghijk',{globalPrivacyControl:true}).link.href).searchParams.has('client_reference_id'),false);
assert.equal(new URL(run('gclid=abcdefghijk',{doNotTrack:'1'}).link.href).searchParams.has('client_reference_id'),false);
assert.equal(new URL(run('gclid=abcdefghijk',{},undefined,[['consent','default',{ad_storage:'denied'}]]).link.href).searchParams.has('client_reference_id'),false);
assert.equal(run('gclid=abcdefghijk',{},'https://example.com/').link.href,'https://example.com/');
assert.equal(new URL(run('gclid=abcdefghijk',{},'https://buy.stripe.com/aFafZa3cWg94gEcdTA0sU0T?client_reference_id=existing').link.href).searchParams.get('client_reference_id'),'existing');
x.context.navigator.globalPrivacyControl=true;x.listeners.click();assert.equal(new URL(x.link.href).searchParams.has('client_reference_id'),false);
console.log('PASS: reference, mobile IDs, privacy, malformed IDs, foreign links, existing references, late opt-out.');
const sitelink=run('gclid=abcdefghijk');sitelink.context.location.search='?ad_campaign=r1&ad_group=gs&ad_arm=S&gclid=abcdefghijk';vm.runInNewContext(script,sitelink.context);assert.match(new URL(sitelink.link.href).searchParams.get('client_reference_id'),/^usta1_r1_gs_S_g_/);
