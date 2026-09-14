(function () {
  try {
    if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
    var endpoint = document.currentScript && document.currentScript.getAttribute('data-click-beacon');
    document.addEventListener('click', function (event) {
      try {
        var node = event.target;
        var link = node && node.closest ? node.closest('a[data-checkout]') : null;
        if (!link) return;
        var family = link.getAttribute('data-checkout');
        var url;
        if (family === 'ttb') {
          if (!endpoint) return;
          url = endpoint + '?f=' + encodeURIComponent(family);
          if (navigator.webdriver) url += '&probe=1';
        } else if (family === 'grid') {
          url = 'https://usta-loops-260481739341.us-central1.run.app/t?f=' + encodeURIComponent(family) + '&e=checkout_click';
        } else return;
        fetch(url, {keepalive: true, mode: 'no-cors'});
      } catch (err) {}
    }, true);
  } catch (err) {}
})();
