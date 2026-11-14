(() => {
  'use strict';

  const names = {
    overview: 'Overview',
    kiosk: 'QR Timekeeping',
    reviews: 'Verification',
    exports: 'Payroll Exports'
  };
  const views = Array.from(document.querySelectorAll('[data-view]'));
  const links = Array.from(document.querySelectorAll('[data-view-link]'));
  const currentView = document.getElementById('current-view');

  function renderRoute() {
    const requested = window.location.hash.replace(/^#/, '').toLowerCase();
    const selected = Object.prototype.hasOwnProperty.call(names, requested)
      ? requested
      : 'overview';

    for (const view of views) {
      view.hidden = view.dataset.view !== selected;
    }
    for (const link of links) {
      if (link.dataset.viewLink === selected) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    }
    if (currentView) currentView.textContent = names[selected];
    document.title = names[selected] + ' | SiteGuard QR';
  }

  const year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());
  window.addEventListener('hashchange', renderRoute);
  renderRoute();
})();
