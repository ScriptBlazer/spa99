/* The Office as an installable app: registers the service worker (it only makes the app installable; it holds no pages and sends no notifications).
 * A failure here never breaks the page. */
export function initApp() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
}
