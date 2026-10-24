/* Control shell: boots the state, wires every module, swaps the page when you change tab (so music keeps playing and
   uploads keep going), and handles the keys and clicks that belong to the whole shell. */
import { $, $$, S, MOTION, WIDE, bus } from "./core.js";
import { restore, save, writeNow, resetDemo } from "./state.js";
import { initLights, renderLights, runSim, haltSim, onVisible, openRoom, closePop, alertsOpen, closeAlerts } from "./lights.js";
import { initScreens, renderScreens, renderSchedLane, runScreens, haltScreens, pruneMounts, openScreen, reconcile } from "./screens.js";
import { initMusic, renderMusic, runMusic, mountMusic, zoneById } from "./music.js";
import { initLibrary, mountLibrary, unmountLibrary, syncLibraryUrl, renderMeter } from "./library.js";
import { initUpload, renderTray } from "./upload.js";
import { initScenes } from "./scenes.js";
import { loadLibrary, L } from "./libdata.js";
import { openPanel, closePanel, closePanelQuietly, panelKey, trapTab, initSheet } from "./panel.js";

const ROUTES = ["/", "/rooms/", "/music/", "/screens/", "/schedule/", "/library/"];
let currentPath = location.pathname;
let navigating = false;
let pendingPop = false;  // Back or Forward pressed while a page was still loading: handled when it finishes
let overviewMod = null;  // the 3D model (loads three.js, only on the Overview)

/** History rules: only a real tab change pushes ONE entry. Opening or closing a panel, picking a zone, a Library view, all
    replace the current entry, so Back always means "the previous tab" and can never loop. */

/** The Overview shows the 3D model (the 2D plan stays as the fallback). Other tabs release it. */
function syncOverview() {
  if (document.body.dataset.page !== "overview") { if (overviewMod) overviewMod.disposeOverview(); return; }
  import("./overview3d.js").then((mod) => {
    overviewMod = mod;
    if (document.body.dataset.page === "overview") mod.mountOverview();
  }).catch(() => { /* three.js did not load: the 2D plan is already showing */ });
}

function renderAll() {
  renderLights();
  renderScreens();
  renderMusic();
  renderSchedLane();
}

function usesLibrary() {
  return S.st.screens.some((s) => s.show.t !== "slide") || S.st.music.zones.some((z) => z.queue.some((e) => e.assetId));
}

/** Open whatever the address asks for (?room=, ?screen=, ?zone=). Library reads its own ?item= and ?playlist=. */
function syncFromUrl() {
  const page = document.body.dataset.page;
  const q = new URLSearchParams(location.search);
  if (page === "overview" || page === "rooms") {
    const room = q.get("room");
    if (room && S.st.rooms.some((r) => r.slug === room)) openRoom(room, { push: false });
    else if (panelKey() && panelKey().startsWith("room:")) closePanel();
  } else if (page === "screens") {
    const screen = q.get("screen");
    if (screen && S.st.screens.some((s) => s.id === screen)) openScreen(screen, { push: false });
    else if (panelKey() && panelKey().startsWith("screen:")) closePanel();
  } else if (page === "music") {
    mountMusic();
    S.render();
  } else if (page === "library") syncLibraryUrl();
}

function mount() {
  const page = document.body.dataset.page;
  pruneMounts();
  closePop(false);
  if (page === "library") mountLibrary(); else unmountLibrary();
  if (page === "music") mountMusic();
  S.render();
  syncOverview();
  if (page !== "library") syncFromUrl();
  if (usesLibrary() || page === "screens" || page === "music") loadLibrary().then(() => S.render());
  renderTray(true);
}

/* ---------- tab changes without a full page load ---------- */

function setCurrent(doc) {
  document.title = doc.title;
  const page = doc.body.dataset.page;
  document.body.dataset.page = page;
  for (const el of $$("[data-nav]")) { if (el.dataset.nav === page) el.setAttribute("aria-current", "page"); else el.removeAttribute("aria-current"); }
  const title = $("[data-pagetitle]");
  const next = doc.querySelector("[data-pagetitle]");
  if (title && next) title.textContent = next.textContent;
}

async function navigate(href, { push = true } = {}) {
  if (navigating) { if (!push) pendingPop = true; return; }
  navigating = true;
  const url = new URL(href, location.href);
  try {
    const res = await fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } });
    const path = new URL(res.url).pathname;
    if (!res.ok || !ROUTES.includes(path)) { location.assign(url); return; }
    const doc = new DOMParser().parseFromString(await res.text(), "text/html");
    const main = doc.getElementById("ctl-main");
    if (!main || !doc.body.classList.contains("control")) { location.assign(url); return; }
    const apply = () => {
      closePanelQuietly();
      if (overviewMod) overviewMod.disposeOverview();
      const here = $("#ctl-main");
      here.innerHTML = main.innerHTML;
      setCurrent(doc);
      if (push) {
        // the entry we leave keeps its page only (an open room or screen is not part of "where I was")
        if (location.search && currentPath !== "/music/") history.replaceState(null, "", location.pathname);
        history.pushState(null, "", url);
      }
      currentPath = new URL(res.url).pathname;
      window.scrollTo(0, 0);
      mount();
      here.focus({ preventScroll: true });
    };
    if (document.startViewTransition && !MOTION.matches) await document.startViewTransition(apply).updateCallbackDone;
    else apply();
  } catch (e) {
    location.assign(url);
  } finally {
    navigating = false;
    if (pendingPop) {
      pendingPop = false;
      if (location.pathname !== currentPath) navigate(location.href, { push: false });
      else syncFromUrl();
    }
  }
}

function onLinkClick(event) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const a = event.target instanceof Element ? event.target.closest("a[href]") : null;
  if (!a || a.target || a.hasAttribute("download") || a.hasAttribute("data-no-pjax") || a.hasAttribute("data-close")) return;
  const url = new URL(a.getAttribute("href"), location.href);
  if (url.origin !== location.origin || !ROUTES.includes(url.pathname)) return;
  event.preventDefault();
  if (url.pathname === currentPath) {
    if (url.search === location.search) return;
    history.replaceState(null, "", url);  // same tab: a panel or a selection, not a new page
    syncFromUrl();
    return;
  }
  navigate(url);
}

/* ---------- the shell ---------- */

function onClick(event) {
  const t = event.target instanceof Element ? event.target : null;
  if (!t) return;
  const open = t.closest("[data-open-room]");
  if (open && !event.metaKey && !event.ctrlKey && !event.shiftKey) { event.preventDefault(); openRoom(open.dataset.openRoom); return; }
  if (t.closest("[data-close]")) { event.preventDefault(); closePanel(); return; }
  if (t.closest("[data-backdrop]")) { closePanel(); return; }
  if (t.closest("[data-reset]")) {
    if (panelKey() === "more") closePanel();
    const d = $("[data-reset-dialog]");
    if (d && d.showModal) d.showModal();
    return;
  }
  if (t.closest("[data-more-open]")) {
    const tpl = $("#ctl-more-tpl");
    openPanel({ key: "more", node: tpl.content.firstElementChild.cloneNode(true), size: "peek" });
    return;
  }
  const who = $("[data-who]");
  if (who && who.open && !t.closest("[data-who]")) who.open = false;
}

function onKeydown(event) {
  if (event.key === " " && event.target instanceof Element && event.target.matches("[data-open-room]")) { event.preventDefault(); openRoom(event.target.dataset.openRoom); return; }
  if (event.key === "Escape") {
    if ($("[data-reset-dialog]")?.open || $("[data-dialog]")?.open) return;
    if ($("[data-pop]") && !$("[data-pop]").hidden) { closePop(); return; }
    if (alertsOpen()) { closeAlerts(); return; }
    const who = $("[data-who]");
    if (who && who.open) { who.open = false; $("summary", who).focus(); return; }
    if (panelKey()) { closePanel(); return; }
    return;
  }
  trapTab(event);
}

export function boot() {
  const node = document.getElementById("ctl-demo");
  if (!node) return;
  const server = JSON.parse(node.textContent);
  S.server = server;
  S.st = restore(server);
  S.save = save;
  S.render = renderAll;
  initLights();
  initScenes();
  initScreens();
  initMusic();
  initUpload();
  initLibrary();
  initSheet();
  document.addEventListener("click", onClick);
  document.addEventListener("click", onLinkClick);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("popstate", () => {
    if (location.pathname !== currentPath) navigate(location.href, { push: false });
    else syncFromUrl();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { haltSim(); haltScreens(); return; }
    onVisible();
    runScreens();
  });
  const dialog = $("[data-reset-dialog]");
  if (dialog) {
    dialog.addEventListener("close", () => { if (dialog.returnValue === "reset") resetDemo(); });
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close("cancel"); });
  }
  window.addEventListener("pagehide", writeNow);
  mount();
  runSim();
  runScreens();
  runMusic();
}
