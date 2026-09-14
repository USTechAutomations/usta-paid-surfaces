(function () {
  var BASE = 'https://usta-loops-260481739341.us-central1.run.app/t?f=';
  var FAMILY_OK = /^[a-z0-9][a-z0-9-]{0,63}$/;

  function onClick(ev) {
    try {
      if (!ev || !ev.target || typeof ev.target.closest !== 'function') return;
      var link = ev.target.closest('a[data-checkout]');
      if (!link || typeof link.getAttribute !== 'function') return;
      var family = link.getAttribute('data-checkout');
      if (typeof family !== 'string' || !FAMILY_OK.test(family)) return;
      var nav = typeof navigator === 'undefined' ? {} : navigator;
      if (nav.doNotTrack === '1') return;
      if (nav.globalPrivacyControl === true) return;
      var f = encodeURIComponent(family);
      var e = 'checkout_click';
      if (nav.webdriver === true) {
        f = 'usta-diagnostic';
        e = 'checkout_probe';
      }
      if (typeof fetch !== 'function') return;
      var req = fetch(BASE + f + '&e=' + e, { keepalive: true, mode: 'no-cors' });
      if (req && typeof req.catch === 'function') req.catch(function () {});
    } catch (err) {}
  }

  document.addEventListener('click', onClick);
})();
