/* The unread counts (WhatsApp chats and Email threads with unread messages): the navigation badges, the page title and the installed app's icon badge
 * (WhatsApp plus Email). One module for both: a page of one section sets its own count; every other page polls quietly. */
const base = { whatsapp: '', email: '' };
const COUNT = { whatsapp: 'waUnread', email: 'emUnread' };
const URLS = { whatsapp: '/whatsapp/unread/', email: '/email/unread/' };

const read = (channel) => Number(document.body.dataset[COUNT[channel]]) || 0;

function paint(channel, total) {
  document.querySelectorAll(`[data-office-badge="${channel}"]`).forEach((badge) => {
    badge.replaceChildren();
    if (!total) return;
    badge.append(document.createTextNode(total > 99 ? '99+' : String(total)));
    const sr = document.createElement('span');
    sr.className = 'sr-only';
    sr.textContent = ' unread';
    badge.append(sr);
  });
}

function set(channel, total, title) {
  total = Number(total) || 0;
  if (title) base[channel] = title;
  if (!base[channel]) base[channel] = document.title.replace(/^\(\d+\+?\)\s*/, '');
  if (document.body.dataset.officeSection === channel) document.title = `${total ? `(${total}) ` : ''}${base[channel]}`;
  document.body.dataset[COUNT[channel]] = String(total);
  paint(channel, total);
  const all = read('whatsapp') + read('email');
  if ('setAppBadge' in navigator) (all ? navigator.setAppBadge(all) : navigator.clearAppBadge()).catch(() => {});
}

export const setUnread = (total, title) => set('whatsapp', total, title);
export const setEmailUnread = (total, title) => set('email', total, title);

/** On every Office page: a quiet check once a minute while the page is visible, for each channel this page does not already show live. */
export function pollUnread() {
  const channels = Object.keys(URLS).filter((c) => document.body.dataset.officeSection !== c && document.querySelector(`[data-office-badge="${c}"]`));
  if (!channels.length) return;
  const check = async (channel) => {
    try {
      const response = await fetch(URLS[channel], { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (response.ok) set(channel, (await response.json()).unread_total);
    } catch { /* quiet */ }
  };
  const run = async () => {
    if (document.visibilityState === 'visible') await Promise.all(channels.map(check));
    setTimeout(run, 60000);
  };
  setTimeout(run, 60000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') channels.forEach(check); });
}
