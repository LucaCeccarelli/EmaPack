(() => {
  const el = document.getElementById('installPrompt');
  const closeBtn = document.getElementById('installPromptClose');
  const textEl = document.getElementById('installPromptText');
  if (!el || !closeBtn || !textEl) return;

  const DISMISS_KEY = 'packema-install-dismissed';
  const SESSION_KEY = 'packema-install-shown';
  const safeStorage = (storage, key) => {
    try { return storage.getItem(key); } catch { return null; }
  };

  const isStandalone = window.navigator.standalone === true
    || window.matchMedia('(display-mode: standalone)').matches;
  if (isStandalone) return;
  if (safeStorage(localStorage, DISMISS_KEY)) return;
  if (safeStorage(sessionStorage, SESSION_KEY)) return;
  if (!window.matchMedia('(max-width: 600px)').matches) return;

  const ua = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/.test(ua);
  if (!isIOS && !isAndroid) return;

  const script = document.currentScript;
  textEl.textContent = isIOS ? script.dataset.msgIos : script.dataset.msgAndroid;

  const timer = setTimeout(() => {
    el.hidden = false;
    try { sessionStorage.setItem(SESSION_KEY, '1'); } catch { /* ignore */ }
  }, 1500);

  closeBtn.addEventListener('click', () => {
    clearTimeout(timer);
    el.hidden = true;
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
  });
})();
