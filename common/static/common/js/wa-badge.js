/* The WhatsApp unread count (chats with unread messages): the navigation badges, the page title and the installed app's icon badge. */
let baseTitle = '';

export function setUnread(total, title) {
  total = Number(total) || 0;
  if (title) baseTitle = title;
  if (!baseTitle) baseTitle = document.title.replace(/^\(\d+\+?\)\s*/, '');
  if (document.body.dataset.officeSection === 'whatsapp') document.title = `${total ? `(${total}) ` : ''}${baseTitle}`;
  document.body.dataset.waUnread = String(total);
  document.querySelectorAll('[data-office-badge="whatsapp"]').forEach((badge) => {
    badge.replaceChildren();
    if (!total) return;
    badge.append(document.createTextNode(total > 99 ? '99+' : String(total)));
    const sr = document.createElement('span');
    sr.className = 'sr-only';
    sr.textContent = ' unread';
    badge.append(sr);
  });
  if ('setAppBadge' in navigator) (total ? navigator.setAppBadge(total) : navigator.clearAppBadge()).catch(() => {});
}

/** On every Office page but the chats themselves: a quiet check once a minute while the page is visible. */
export function pollUnread() {
  if (document.body.dataset.officeSection === 'whatsapp' || !document.querySelector('[data-office-badge="whatsapp"]')) return;
  const run = async () => {
    if (document.visibilityState === 'visible') {
      try {
        const response = await fetch('/whatsapp/unread/', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
        if (response.ok) setUnread((await response.json()).unread_total);
      } catch { /* quiet */ }
    }
    setTimeout(run, 60000);
  };
  setTimeout(run, 60000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') fetch('/whatsapp/unread/', { credentials: 'same-origin' }).then((r) => r.ok && r.json()).then((d) => d && setUnread(d.unread_total)).catch(() => {}); });
}
