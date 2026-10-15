// Burger menu for small screens (the CSS only collapses the nav when this script has set the `js` class).
(() => {
  const toggle = document.querySelector('.nav-toggle'), nav = document.getElementById('site-nav');
  if (!toggle || !nav) return;
  const set = open => { nav.classList.toggle('open', open); toggle.setAttribute('aria-expanded', open); };
  toggle.addEventListener('click', () => set(!nav.classList.contains('open')));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && nav.classList.contains('open')) { set(false); toggle.focus(); }
  });
})();
