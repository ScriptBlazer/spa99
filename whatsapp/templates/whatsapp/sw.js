/* Spa 99 Office service worker: push notifications only. It never caches staff data. The frontend builds on this file
   (whatsapp/templates/whatsapp/sw.js, served at /sw.js by whatsapp.pwa). Push payload: {title, body, url, tag}. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  const options = { body: data.body || '', tag: data.tag || 'spa99', renotify: true, data: { url: data.url || '/' } };
  event.waitUntil(self.registration.showNotification(data.title || 'Spa 99 Office', options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const client of list) {
      if ('focus' in client) { client.navigate(url); return client.focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
