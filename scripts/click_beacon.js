(function () {
  try {
    if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
    document.addEventListener('click', function (event) {
      try {
        var node = event.target;
        var link = node && node.closest ? node.closest('a[data-checkout]') : null;
        if (!link) return;
        var family = link.getAttribute('data-checkout');
        if (!family) return;
        var url = 'https://ustechautomations.com/feeds/click/' + family + '.gif?f=' + family;
        fetch(url, {keepalive: true, mode: 'no-cors'});
      } catch (err) {}
    }, true);
  } catch (err) {}
})();
