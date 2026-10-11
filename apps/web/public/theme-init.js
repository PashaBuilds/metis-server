// İlk boyamada tema yanıp sönmesini önler (CSP: harici dosya, satır içi betik yok).
(function () {
  try {
    var t = localStorage.getItem('metis.theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  } catch (e) {}
})();
