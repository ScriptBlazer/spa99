/* Page beacon (docs/features/analytics.md A4, A6). Tells our own server how long this page was on screen, how far it was
   scrolled, and when a contact link (WhatsApp, phone, email, Instagram, map) is tapped. No cookie, no storage, no third party,
   nothing about the person: the path, a number of seconds, a scroll step, a kind of link.
   A12: about 1.5 seconds after the page is on screen it also sends a tiny "hello" ({p, h:1}), so a real browser is confirmed
   while still on its first page (Live shows it) and not only when it leaves. Bots that do not run scripts never send it. */
(function () {
  "use strict";
  var URL = "/a/e/";
  var MAX = 1800; // the server caps at 30 minutes too
  var shown = document.visibilityState !== "hidden" ? Date.now() : 0; // when the page last became visible
  var seconds = 0; // visible seconds not yet sent
  var first = true; // the first beacon of this page view also carries the scroll step
  var furthest = 0; // furthest scroll, as 0, 25, 50, 75 or 100

  function post(data) {
    try {
      var body = JSON.stringify(data);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(URL, new Blob([body], { type: "text/plain" }));
      } else if (window.fetch) {
        fetch(URL, { method: "POST", body: body, keepalive: true, headers: { "Content-Type": "text/plain" } });
      }
    } catch (e) { /* counting never matters to the visitor */ }
  }

  function scrolled() {
    var doc = document.documentElement;
    var total = Math.max(doc.scrollHeight, 1);
    var seen = (window.pageYOffset || doc.scrollTop || 0) + (window.innerHeight || doc.clientHeight || 0);
    var share = Math.min(seen / total, 1) * 100;
    var step = share >= 98 ? 100 : share >= 75 ? 75 : share >= 50 ? 50 : share >= 25 ? 25 : 0;
    if (step > furthest) furthest = step;
  }

  function flush() {
    if (shown) { seconds += (Date.now() - shown) / 1000; shown = 0; }
    var sent = Math.min(Math.round(seconds), MAX);
    if (sent < 1 && !first) return;
    scrolled();
    post({ p: location.pathname, t: sent, s: furthest, n: first ? 0 : 1 });
    first = false;
    seconds = 0;
  }

  var HELLO_MS = 1500;
  var helloSent = false;
  var helloTimer = 0;
  function hello() {
    helloTimer = 0;
    if (helloSent || document.visibilityState === "hidden") return;
    helloSent = true;
    post({ p: location.pathname, h: 1 });
  }
  function helloSoon() {
    if (!helloSent && !helloTimer) helloTimer = setTimeout(hello, HELLO_MS);
  }
  if (document.visibilityState !== "hidden") helloSoon();

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      clearTimeout(helloTimer); helloTimer = 0; // not on screen: the wait starts again when it is
      flush();
    } else {
      shown = Date.now();
      helloSoon();
    }
  });
  window.addEventListener("pagehide", flush);
  window.addEventListener("scroll", scrolled, { passive: true });

  var MAPS = /(^|\.)(maps\.google\.[a-z.]+|maps\.apple\.com|maps\.app\.goo\.gl|openstreetmap\.org)$|google\.[a-z.]+\/maps|goo\.gl\/maps/i;
  function kindOf(link) {
    var tagged = link.closest("[data-track]");
    if (tagged) return (tagged.getAttribute("data-track") || "").toLowerCase();
    var href = (link.getAttribute("href") || "").toLowerCase();
    if (href.indexOf("tel:") === 0) return "phone";
    if (href.indexOf("mailto:") === 0) return "email";
    var host = link.hostname || "";
    if (/(^|\.)(wa\.me|whatsapp\.com)$/.test(host)) return "whatsapp";
    if (/(^|\.)instagram\.com$/.test(host)) return "instagram";
    if (MAPS.test(host) || MAPS.test(host + link.pathname)) return "map";
    return "";
  }
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest ? event.target.closest("a") : null;
    var tagged = event.target && event.target.closest ? event.target.closest("[data-track]") : null;
    var kind = link ? kindOf(link) : tagged ? (tagged.getAttribute("data-track") || "").toLowerCase() : "";
    if (kind) post({ p: location.pathname, c: kind }); // sent the moment it happens: the tap may leave the page
  }, true);
})();
