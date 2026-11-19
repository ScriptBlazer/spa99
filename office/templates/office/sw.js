/* Spa 99 Office service worker. It exists so the Office can be installed as an app. It does nothing else: no push, no cache and no fetch handler, so it never holds pages
   or staff data. Served at /sw.js by office.pwa, Office host only. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
