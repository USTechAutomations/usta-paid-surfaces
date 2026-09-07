/* Direct-visit attribution for the five reviewed Search tests. No cookies or storage. */
(function () {
  'use strict';
  var allowed = {
    '/feeds/permit-files/austin': ['r1', 'https://buy.stripe.com/aFafZa3cWg94gEcdTA0sU0T'],
    '/feeds/boston': ['r2', 'https://buy.stripe.com/dRmaEQ7tc9KGgEceXE0sU17'],
    '/feeds/nyc-ll84': ['r3', 'https://buy.stripe.com/7sYbIU3cW6yugEc02K0sU18'],
    '/feeds/wp-accessibility-scan': ['r4', 'https://buy.stripe.com/6oUaEQ3cW4qmew4bLs0sU2v'],
    '/feeds/pilot-logbook-digitizer': ['r5', 'https://buy.stripe.com/7sY6oA7tc4qm0Fe4j00sU2u']
  };
  var route = allowed[location.pathname.replace(/\/$/, '')];
  if (!route) return;
  var params = new URLSearchParams(location.search);
  if (params.get('ad_campaign') !== route[0]) return;
  document.documentElement.classList.add('purchase-visit');
  var group = params.get('ad_group'), arm = params.get('ad_arm');
  if (!/^g[12]$/.test(group || '') || !/^[AB]$/.test(arm || '')) return;
  function denied() {
    if (navigator.globalPrivacyControl === true || navigator.doNotTrack === '1') return true;
    var deniedNow = false;
    (window.dataLayer || []).forEach(function (entry) {
      if (entry && entry[0] === 'consent' && entry[2]) {
        var c = entry[2];
        if (c.ad_user_data === 'denied' || c.ad_storage === 'denied') deniedNow = true;
        else if (c.ad_user_data === 'granted' && c.ad_storage === 'granted') deniedNow = false;
      }
    });
    return deniedNow;
  }
  var keys = ['gclid', 'wbraid', 'gbraid'];
  var found = keys.filter(function (k) { return params.has(k); });
  if (found.length !== 1) return;
  var kind = found[0], value = params.get(kind);
  if (!/^[A-Za-z0-9_-]{10,150}$/.test(value || '')) return;
  var reference = ['usta1', route[0], group, arm, {gclid:'g',wbraid:'w',gbraid:'b'}[kind], Math.floor(Date.now()/1000).toString(36), value].join('_');
  if (reference.length > 200) return;
  function decorate() {
    document.querySelectorAll('a[data-checkout]').forEach(function (link) {
      var target = new URL(link.href, location.href);
      if (target.origin + target.pathname !== route[1]) return;
      if (denied()) {
        if ((target.searchParams.get('client_reference_id') || '').startsWith('usta1_')) {
          target.searchParams.delete('client_reference_id'); link.href = target.href;
        }
        return;
      }
      if (target.searchParams.has('client_reference_id') && !target.searchParams.get('client_reference_id').startsWith('usta1_')) return;
      target.searchParams.set('client_reference_id', reference); link.href = target.href;
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', decorate);
  else decorate();
  document.addEventListener('click', decorate, true);
  document.addEventListener('auxclick', decorate, true);
})();
