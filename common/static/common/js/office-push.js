/* The Office as an app: the service worker (push only, nothing cached), the notifications sheet in the person menu, and the install hints
 * (docs/features/whatsapp-design.md section 7). The browser's permission prompt only ever follows a tap, never a page load. */
import { csrfToken } from './api.js';
import { toast } from './feedback.js';
import { pollUnread } from './wa-badge.js';

const DISMISS_KEY = 'office-install-dismissed';
const CHOOSE_KEY = 'office-notify-choice-dismissed';
const DAYS30 = 30 * 86400000;

const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const standalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
const iosVersion = () => { const m = /OS (\d+)[_.](\d+)/.exec(navigator.userAgent); return m ? Number(m[1]) + Number(m[2]) / 100 : 0; };
const supported = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const recent = (key) => { try { const t = Number(localStorage.getItem(key)); return t && Date.now() - t < DAYS30; } catch { return false; } };
const remember = (key) => { try { localStorage.setItem(key, String(Date.now())); } catch { /* private mode */ } };

function base64ToBytes(text) {
  const padded = (text + '='.repeat((4 - (text.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

const post = (url, body) => fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() }, body: JSON.stringify(body || {}) });

export function initPush() {
  if (!document.querySelector('[data-notify-sheet]')) return;
  pollUnread();
  const sheet = document.querySelector('[data-notify-sheet]');
  const ROW = { off: 'Off', on: 'On', muted: 'Muted', blocked: 'Blocked', ios: 'Add to Home Screen', unsupported: 'Not available', unconfigured: 'Not available' };
  let config = null;
  let deferred = null;
  let state = 'off';
  let registration = null;

  // The service worker: Office host only (the page itself is only served there). A failure here never breaks the page.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((r) => { registration = r; }).catch(() => {});
  }

  window.addEventListener('beforeinstallprompt', (event) => { event.preventDefault(); deferred = event; render(); });
  window.addEventListener('appinstalled', () => { deferred = null; render(); });

  async function loadConfig() {
    try {
      const response = await fetch('/whatsapp/push/config/', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (response.ok) config = await response.json();
    } catch { /* the sheet says what it can */ }
    return config;
  }

  async function currentSubscription() {
    if (!supported()) return null;
    try { const reg = registration || await navigator.serviceWorker.getRegistration('/'); return reg ? await reg.pushManager.getSubscription() : null; } catch { return null; }
  }

  async function compute() {
    if (!config) await loadConfig();
    if (!config || !config.configured) return 'unconfigured';
    if (!supported()) return isIOS() && !standalone() && iosVersion() >= 16.04 ? 'ios' : 'unsupported';
    if (config.muted) return 'muted';
    if (Notification.permission === 'denied') return 'blocked';
    if (Notification.permission === 'granted' && await currentSubscription()) return 'on';
    return 'off';
  }

  async function render() {
    state = await compute();
    sheet.dataset.state = state;
    sheet.querySelectorAll('[data-notify-for]').forEach((el) => { el.hidden = el.dataset.notifyFor !== state; });
    sheet.querySelector('[data-notify-mute-row]').hidden = !(state === 'on' || state === 'muted');
    sheet.querySelector('[data-notify-mute]').checked = !!(config && config.muted);
    sheet.querySelector('[data-notify-install]').hidden = !(deferred && !standalone());
    sheet.querySelector('[data-notify-ios]').hidden = !isIOS();
    const host = sheet.querySelector('[data-notify-host]');
    if (host) host.textContent = location.host;
    document.querySelectorAll('[data-notify-state]').forEach((el) => { el.textContent = ROW[state]; });
    cards();
  }

  // The cards at the top of the chat list (phone): install hint, and the one-time "set up notifications" once the app is installed.
  async function cards() {
    const install = document.querySelector('[data-install-card]');
    if (!install) return;
    const ios = install.querySelector('[data-install-ios]');
    const chrome = install.querySelector('[data-install-chrome]');
    const phoneWidth = window.matchMedia('(max-width: 63.99em)').matches;
    const showIos = isIOS() && !standalone() && iosVersion() >= 16.04 && phoneWidth && !recent(DISMISS_KEY);
    const showChrome = !!deferred && !standalone() && phoneWidth && !recent(DISMISS_KEY);
    ios.hidden = !showIos;
    chrome.hidden = !showChrome || showIos;
    install.hidden = !(showIos || showChrome);
    const choose = document.querySelector('[data-choose-card]');
    if (choose) choose.hidden = !(standalone() && supported() && config && config.configured && !config.muted && state === 'off' && Notification.permission === 'default' && !recent(CHOOSE_KEY));
  }
  document.querySelector('[data-install-dismiss]')?.addEventListener('click', () => { remember(DISMISS_KEY); render(); });
  document.querySelector('[data-choose-dismiss]')?.addEventListener('click', () => { remember(CHOOSE_KEY); render(); });
  document.addEventListener('click', async (event) => {
    if (!event.target.closest('[data-install-now]') || !deferred) return;
    deferred.prompt();
    try { await deferred.userChoice; } catch { /* closed */ }
    deferred = null;
    render();
  });

  // opening the sheet from the person menu (or a card)
  const open = async (opener) => {
    const menu = document.querySelector('[data-person-menu]');
    if (menu) menu.open = false;
    await render();
    sheet.notifyOpener = opener || document.querySelector('.o-disc--btn');
    if (!sheet.open) sheet.showModal();
  };
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-notify-open]');
    if (button) { event.preventDefault(); open(button); }
  });
  sheet.querySelector('[data-notify-close]').addEventListener('click', () => sheet.close());
  let down = false;
  sheet.addEventListener('pointerdown', (event) => { down = event.target === sheet; });
  sheet.addEventListener('click', (event) => { if (event.target === sheet && down) sheet.close(); });
  sheet.addEventListener('close', () => sheet.notifyOpener?.focus?.({ preventScroll: true }));

  // the person menu shows the state as soon as it opens
  document.querySelector('[data-person-menu]')?.addEventListener('toggle', (event) => { if (event.target.open) render(); });

  const working = (button, text, on) => {
    if (on) { button.dataset.was = button.textContent; button.textContent = text; button.setAttribute('aria-busy', 'true'); button.disabled = true; }
    else { button.textContent = button.dataset.was || button.textContent; button.removeAttribute('aria-busy'); button.disabled = false; }
  };

  sheet.querySelector('[data-notify-on]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    working(button, 'Asking your phone', true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') { await render(); return; }
      const reg = registration || await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64ToBytes(config.vapid_public_key) });
      const json = sub.toJSON();
      const response = await post(config.urls.subscribe, { endpoint: json.endpoint, keys: json.keys });
      if (!response.ok) throw new Error('subscribe refused');
      config.devices = (config.devices || 0) + 1;
      toast('Notifications are on for this device.');
    } catch {
      toast('Notifications could not be turned on. Try again.', { kind: 'error' });
    } finally { working(button, '', false); await render(); }
  });

  sheet.querySelector('[data-notify-off]').addEventListener('click', async () => {
    try {
      const sub = await currentSubscription();
      if (sub) { const endpoint = sub.endpoint; await sub.unsubscribe(); await post(config.urls.unsubscribe, { endpoint }); }
      toast('Notifications are off for this device.');
    } catch { toast('That could not be turned off. Try again.', { kind: 'error' }); }
    await render();
  });

  sheet.querySelector('[data-notify-test]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    working(button, 'Sending', true);
    try {
      const response = await post(config.urls.test, {});
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.sent) toast('Test sent.'); else toast('No device answered. Try turning notifications off and on.', { kind: 'error' });
    } catch { toast('The test could not be sent.', { kind: 'error' }); } finally { working(button, '', false); }
  });

  sheet.querySelector('[data-notify-mute]').addEventListener('change', async (event) => {
    const muted = event.currentTarget.checked;
    try {
      const response = await post(config.urls.mute, { muted });
      if (!response.ok) throw new Error('mute refused');
      config.muted = muted;
      toast(muted ? 'Muted on every device.' : 'Notifications are back on.');
    } catch { event.currentTarget.checked = !muted; toast('That could not be saved. Try again.', { kind: 'error' }); }
    await render();
  });

  if (document.querySelector('[data-install-card]')) loadConfig().then(render); // only the chat list needs the state before it is asked for
}
