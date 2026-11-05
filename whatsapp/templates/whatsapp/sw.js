/* Spa 99 Office service worker: push notifications and a tap that opens the chat. It never caches pages or staff data, and has no fetch handler
   (served at /sw.js by whatsapp.pwa, Office host only). Push payload: {title, body, url, tag}: title is his name, body his first line, tag the chat or thread id. */
const ICON = "{{ icon }}";
const BADGE = "{{ badge }}";

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  const url = data.url || '/';
  const tag = data.tag || 'spa99';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    // a chat he has open and can see needs no notification (the page path is the chat's /whatsapp/<id>/; a ?gold= does not change the path)
    if (windows.some((w) => w.visibilityState === 'visible' && new URL(w.url).pathname === url)) return;
    // a second message from the same chat replaces the first; from the third on it counts them
    const earlier = (await self.registration.getNotifications({ tag })).reduce((n, existing) => Math.max(n, (existing.data && existing.data.count) || 1), 0);
    const count = earlier + 1;
    const body = count >= 3 ? `${count} new messages` : (data.body || '');
    await self.registration.showNotification(data.title || 'Spa 99 Office', { body, tag, renotify: true, icon: ICON, badge: BADGE, data: { url, count } });
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (list) => {
    for (const client of list) {
      if ('focus' in client) {
        try { await client.focus(); if (new URL(client.url).pathname !== url && 'navigate' in client) await client.navigate(url); return; } catch (e) { /* try the next window */ }
      }
    }
    return self.clients.openWindow(url);
  }));
});
