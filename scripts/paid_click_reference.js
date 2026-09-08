/* Direct-visit attribution for reviewed Google/LinkedIn tests. No cookies or storage. */
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
  var linkedinCodes = {r1:'l4', r2:'l5', r3:'l3'};
  var isLinkedIn = !!linkedinCodes[route[0]] && params.get('li_campaign') === linkedinCodes[route[0]];
  var isGoogle = params.get('ad_campaign') === route[0];
  if (isLinkedIn === isGoogle) return; // No context, or conflicting channel context.
  document.documentElement.classList.add('purchase-visit');
  var group = params.get('ad_group'), arm = params.get(isLinkedIn ? 'li_arm' : 'ad_arm');
  if (isLinkedIn ? !/^[AB]$/.test(arm || '') : !((/^g[12]$/.test(group || '') && /^[AB]$/.test(arm || '')) || (group === 'gs' && arm === 'S'))) return;
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
  var keys = ['gclid', 'wbraid', 'gbraid', 'li_fat_id'];
  var found = keys.filter(function (k) { return params.has(k); });
  if (found.length !== 1) return;
  var kind = found[0], value = params.get(kind);
  var stamp = Math.floor(Date.now()/1000).toString(36), reference;
  if (isLinkedIn) {
    if (kind !== 'li_fat_id' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value || '')) return;
    reference = ['ustaL1', linkedinCodes[route[0]], arm, stamp, value.toLowerCase()].join('_');
  } else {
    if (kind === 'li_fat_id' || !/^[A-Za-z0-9_-]{10,150}$/.test(value || '')) return;
    reference = ['usta1', route[0], group, arm, {gclid:'g',wbraid:'w',gbraid:'b'}[kind], stamp, value].join('_');
  }
  if (reference.length > 200) return;
  function decorate() {
    document.querySelectorAll('a[data-checkout]').forEach(function (link) {
      var target = new URL(link.href, location.href);
      if (target.origin + target.pathname !== route[1]) return;
      if (denied()) {
        if (/^usta(?:1|L1)_/.test(target.searchParams.get('client_reference_id') || '')) {
          target.searchParams.delete('client_reference_id'); link.href = target.href;
        }
        return;
      }
      if (target.searchParams.has('client_reference_id') && !/^usta(?:1|L1)_/.test(target.searchParams.get('client_reference_id'))) return;
      target.searchParams.set('client_reference_id', reference); link.href = target.href;
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', decorate);
  else decorate();
  document.addEventListener('click', decorate, true);
  document.addEventListener('auxclick', decorate, true);
})();
