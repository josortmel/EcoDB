// Runs synchronously in <head> BEFORE first paint to prevent a flash of the
// wrong theme (FOUC) on launches that have a persisted theme. Reads the same
// localStorage key the Zustand `persist` store writes ('ecodb-theme').
// External file (not inline) so the strict prod CSP `script-src 'self'` allows it.
(function () {
  try {
    var raw = localStorage.getItem('ecodb-theme');
    var theme = 'light';
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && parsed.state && (parsed.state.theme === 'dark' || parsed.state.theme === 'light')) {
        theme = parsed.state.theme;
      }
    }
    document.documentElement.dataset.theme = theme;
  } catch (e) {
    document.documentElement.dataset.theme = 'light';
  }
})();
