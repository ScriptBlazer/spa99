/* Screens: six pretend screens that show REAL Library video, pictures and screen playlists (or the built-in slides).
   Live previews are the real files at small size: muted looping video (at most 3 playing at once, only while on screen),
   pictures, playlists that advance at their real timings, and the slides as scaled HTML. State is pretend (this browser). */
import { $, $$, S, MOTION, FINE, esc, icon, toast, toastInfo, announce, bus, fmtDur, plural, DAY, clock, formDialog } from "./core.js";
import { save } from "./state.js";
import { L, asset, playlist, loadLibrary, itemSeconds } from "./libdata.js";
import { openPanel, closePanel, panelKey } from "./panel.js";

const st = () => S.st;
export const screenOf = (id) => st().screens.find((s) => s.id === id);
const SLIDES = [["welcome", "Welcome"], ["hours", "Hours"], ["menu", "Menu"], ["notices", "Notices"]];
const SAVE_DATA = Boolean(navigator.connection && navigator.connection.saveData);
const previews = new Set();
let ticker = null;
const pv = { tab: "slides", filter: "video", scope: "this" };

/* ---------- what a screen shows right now ---------- */

const rt = (s) => (s.rt || (s.rt = { idx: 0, el: 0 }));
const slideLabel = (k) => (SLIDES.find((x) => x[0] === k) || [0, "Welcome"])[1];

/** -> { kind: off|slide|image|video|loading, ... , sig } */
export function resolve(s) {
  if (!s.power) return { kind: "off", sig: "off" };
  const show = s.show;
  if (show.t === "slide") return { kind: "slide", k: show.k, sig: `slide:${show.k}` };
  if (!L.loaded) return { kind: "loading", sig: "loading" };
  if (show.t === "asset") {
    const a = asset(show.id);
    if (!a) return { kind: "slide", k: "welcome", missing: true, sig: "slide:welcome" };
    return { kind: a.kind === "video" ? "video" : "image", a, sig: `asset:${a.id}:${a.url}` };
  }
  const p = playlist(show.id);
  if (!p || !p.items.length) return { kind: "slide", k: "welcome", missing: !p, sig: "slide:welcome" };
  const idx = rt(s).idx % p.items.length;
  const item = p.items[idx];
  return { kind: item.asset.kind === "video" ? "video" : "image", a: item.asset, p, idx, item, sig: `pl:${p.id}:${idx}:${item.asset.id}` };
}

export function screenText(s) {
  if (!s.power) return "Off";
  const loop = s.loop ? "looping" : "once";
  const show = s.show;
  if (show.t === "slide") return slideLabel(show.k);
  if (!L.loaded) return "Library";
  if (show.t === "asset") { const a = asset(show.id); return a ? `${a.title}, ${loop}` : "Welcome"; }
  const p = playlist(show.id);
  return p ? `${p.name}, ${plural(p.items.length, "item")}, ${loop}` : "Welcome";
}

const stateWord = (s) => (!s.power ? "Off" : s.playing ? "Playing" : "Paused");

export function setShow(s, show) {
  s.show = show;
  s.power = true;
  s.playing = true;
  s.rt = { idx: 0, el: 0 };
}

/* ---------- live previews ---------- */

function slideLayer(k, s) {
  const tpl = $("#ctl-tile-tpl");
  const tile = tpl.content.firstElementChild.cloneNode(true);
  tile.removeAttribute("data-tile");
  tile.dataset.content = k;
  const note = $("[data-notice]", tile);
  if (note) { note.removeAttribute("data-notice"); note.dataset.noticeText = ""; note.textContent = s.notice; }
  return tile;
}

class Preview {
  constructor(host, id, { still = false, priority = 0 } = {}) {
    this.host = host;
    this.id = id;
    this.still = still;
    this.priority = priority;
    this.visible = true;
    this.manual = false;
    this.sig = "";
    this.layer = null;
    this.video = null;
    this.stage = document.createElement("div");
    this.stage.className = "ctl-stage";
    host.replaceChildren(this.stage);
    this.note = document.createElement("span");
    this.note.className = "ctl-prev-note";
    this.note.hidden = true;
    this.btn = document.createElement("button");
    this.btn.type = "button";
    this.btn.className = "ctl-prev-play";
    this.btn.hidden = true;
    this.btn.setAttribute("aria-label", "Play the preview");
    this.btn.innerHTML = icon("play");
    this.btn.addEventListener("click", (e) => { e.stopPropagation(); this.manual = true; reconcile(); });
    host.append(this.note, this.btn);
    if (typeof IntersectionObserver !== "undefined") {
      this.io = new IntersectionObserver((entries) => { this.visible = entries[entries.length - 1].isIntersecting; reconcile(); });
      this.io.observe(host);
    }
    previews.add(this);
    this.update();
  }

  destroy() {
    if (this.io) this.io.disconnect();
    previews.delete(this);
    if (this.video) this.video.pause();
  }

  update() {
    const s = screenOf(this.id);
    if (!s) return;
    const res = resolve(s);
    if (res.sig !== this.sig) this.swap(res, s);
    else if (res.kind === "slide") {
      const note = $(".ctl-s-title[data-notice-text]", this.layer);
      if (note && note.textContent !== s.notice) note.textContent = s.notice;
    }
    if (this.video) this.video.loop = s.show.t === "asset" ? s.loop : false;
    reconcile();
  }

  swap(res, s) {
    const layer = document.createElement("div");
    layer.className = "ctl-layer";
    let video = null;
    if (res.kind === "off") layer.innerHTML = '<div class="ctl-slide ctl-slide-off is-on"><p>Off</p></div>';
    else if (res.kind === "loading") layer.innerHTML = "";
    else if (res.kind === "slide") layer.append(slideLayer(res.k, s));
    else if (res.kind === "image") layer.innerHTML = `<img src="${esc(res.a.url)}" alt="" draggable="false">`;
    else if (this.still) layer.innerHTML = res.a.poster_url ? `<img src="${esc(res.a.poster_url)}" alt="" draggable="false">` : "";
    else {
      video = document.createElement("video");
      video.muted = true;
      video.defaultMuted = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "");
      video.preload = "metadata";
      if (res.a.poster_url) video.poster = res.a.poster_url;
      video.src = res.a.url;
      layer.append(video);
    }
    const old = this.layer;
    if (this.video && this.video !== video) this.video.pause();
    this.layer = layer;
    this.video = video;
    this.sig = res.sig;
    this.stage.append(layer);
    if (old) {
      if (MOTION.matches || !old.isConnected) old.remove();
      else {
        layer.classList.add("is-entering");
        requestAnimationFrame(() => requestAnimationFrame(() => layer.classList.remove("is-entering")));
        setTimeout(() => old.remove(), 300);
      }
    }
  }
}

/** Decide which videos play: on screen, tab visible, screen playing, at most 3 at once (priority first). */
export function reconcile() {
  const reduced = MOTION.matches || SAVE_DATA;
  const list = [...previews].filter((p) => p.video && p.host.isConnected).sort((a, b) => b.priority - a.priority);
  let playing = 0;
  for (const p of list) {
    const s = screenOf(p.id);
    const want = Boolean(s && s.power && s.playing && p.visible && !document.hidden && (!reduced || p.manual));
    const room = playing < 3;
    if (want && room) {
      playing += 1;
      p.note.hidden = true;
      p.btn.hidden = true;
      const run = p.video.play();
      if (run && run.catch) run.catch(() => {});
    } else {
      p.video.pause();
      p.note.hidden = !(want && !room);
      p.note.textContent = "Playing";
      p.btn.hidden = !(reduced && !p.manual && s && s.power);
    }
  }
}

export function mountPreview(host, screen, { replace = null, still = false, priority = 0 } = {}) {
  if (replace) replace.remove();
  if (host._preview) host._preview.destroy();
  host._preview = new Preview(host, screen.id, { still, priority });
  return host._preview;
}

/** Forget previews whose host left the page (after a tab change). */
export function pruneMounts() {
  for (const p of [...previews]) if (!p.host.isConnected) p.destroy();
}

/* ---------- the pages' screen scopes ---------- */

export function renderScreens() {
  for (const scope of $$("[data-screen]")) {
    const s = screenOf(scope.dataset.screen);
    if (!s) continue;
    const summary = $('[data-f="summary"]', scope);
    if (summary) summary.textContent = screenText(s);
    const word = $('[data-f="state_word"]', scope);
    if (word) word.textContent = stateWord(s);
    const btn = $('[data-act="screen-play"]', scope);
    if (btn) {
      btn.hidden = false;
      const key = `${s.power}${s.playing}`;
      if (btn.dataset.state !== key) {
        btn.dataset.state = key;
        btn.innerHTML = icon(s.power && s.playing ? "pause" : "play");
        btn.setAttribute("aria-label", `${s.power && s.playing ? "Pause" : "Play"} ${s.name}`);
        btn.disabled = !s.power;
      }
    }
  }
  for (const host of $$("[data-prev]")) {
    const s = screenOf(host.dataset.prev);
    if (s && !host._preview) mountPreview(host, s, { still: false });
  }
  for (const a of $$("[data-thumb]")) {
    const s = screenOf(a.dataset.thumb);
    if (!s) continue;
    if (!a._preview) mountPreview(a, s, { still: true });
    a.setAttribute("aria-label", `${s.name}: ${screenText(s)}`);
  }
  for (const p of previews) p.update();
  const pn = $("[data-screen-panel]");
  if (pn) paintScreenPanel(pn);
}

/* ---------- playlists advance at their real timings ---------- */

function tickPlaylists(dt) {
  let moved = false;
  for (const s of st().screens) {
    if (!s.power || !s.playing || s.show.t !== "playlist" || !L.loaded) continue;
    const p = playlist(s.show.id);
    if (!p || !p.items.length) continue;
    const r = rt(s);
    r.el += dt;
    let guard = 0;
    while (guard < 50 && r.el >= itemSeconds(p.items[r.idx % p.items.length])) {
      r.el -= itemSeconds(p.items[r.idx % p.items.length]);
      if (r.idx + 1 >= p.items.length) {
        if (s.loop) r.idx = 0;
        else { s.playing = false; r.el = 0; moved = true; break; }
      } else r.idx += 1;
      moved = true;
      guard += 1;
    }
  }
  if (moved) renderScreens();
}

export function runScreens() {
  if (ticker || document.hidden) return;
  let last = performance.now();
  ticker = setInterval(() => { const now = performance.now(); tickPlaylists(Math.min(2, (now - last) / 1000)); last = now; }, 500);
}
export function haltScreens() { clearInterval(ticker); ticker = null; reconcile(); }

/* ---------- the chooser: Slides and Library (used in the panel and in the schedule rows) ---------- */

function showLabel(show, s) {
  if (show.t === "slide") return slideLabel(show.k);
  if (show.t === "asset") { const a = asset(show.id); return a ? a.title : "Welcome"; }
  const p = playlist(show.id);
  return p ? p.name : "Welcome";
}

function thumbOf(a) {
  if (a.kind === "image") return `<img src="${esc(a.url)}" alt="" loading="lazy" draggable="false">`;
  return a.poster_url ? `<img src="${esc(a.poster_url)}" alt="" loading="lazy" draggable="false">` : `<span class="ctl-thumb-empty">${icon("film-strip")}</span>`;
}

export function chooserHtml(s, current) {
  const lib = pv.tab === "library";
  const isOn = (show) => current && JSON.stringify(current) === JSON.stringify(show);
  let body = "";
  if (!lib) {
    body = `<ul class="ctl-picks">${SLIDES.map(([k, label]) => `<li><button type="button" class="ctl-pick${isOn({ t: "slide", k }) ? " is-on" : ""}" data-pick='${esc(JSON.stringify({ t: "slide", k }))}' aria-pressed="${Boolean(isOn({ t: "slide", k }))}">
      <span class="ctl-pick-prev" data-slide-prev="${k}"></span><span class="ctl-pick-name">${label}</span></button></li>`).join("")}</ul>
      <p class="ctl-field ctl-notice-field"><label for="ctl-notice">Notice text</label><input id="ctl-notice" type="text" maxlength="80" data-notice-input value="${esc(s ? s.notice : "")}" autocomplete="off"></p>`;
  } else if (!L.loaded) {
    body = `<p class="ctl-soft">${L.error ? esc(L.error) : "Loading the Library."}</p>`;
  } else {
    const f = pv.filter;
    const items = [];
    if (f === "video" || f === "image") for (const a of L.assets) if (a.kind === f) items.push({ show: { t: "asset", id: a.id }, name: a.title, thumb: thumbOf(a), meta: a.kind === "video" ? fmtDur(a.duration_seconds) : "" });
    if (f === "playlist") for (const p of L.playlists) if (p.kind === "screens") {
      const first = p.items[0];
      items.push({ show: { t: "playlist", id: p.id }, name: p.name, thumb: first ? thumbOf(first.asset) : `<span class="ctl-thumb-empty">${icon("playlist")}</span>`, meta: plural(p.items.length, "item") });
    }
    const filters = `<div class="ctl-seg ctl-seg-sm" role="radiogroup" aria-label="Type">${[["video", "Videos"], ["image", "Images"], ["playlist", "Playlists"]].map(([k, label]) =>
      `<label><input type="radio" name="lib-filter" data-lib-filter value="${k}"${f === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div>`;
    body = `${filters}${items.length ? `<ul class="ctl-picks is-lib">${items.map((it) => `<li><button type="button" class="ctl-pick${isOn(it.show) ? " is-on" : ""}" data-pick='${esc(JSON.stringify(it.show))}' aria-pressed="${Boolean(isOn(it.show))}">
      <span class="ctl-pick-prev">${it.thumb}${it.meta ? `<span class="ctl-chipdata">${esc(it.meta)}</span>` : ""}</span><span class="ctl-pick-name">${esc(it.name)}</span></button></li>`).join("")}</ul>`
      : `<div class="ctl-empty ctl-empty-sm"><p class="ctl-empty-1">${f === "playlist" ? "No screen playlists yet." : f === "video" ? "No videos in the Library yet." : "No pictures in the Library yet."}</p><a class="ctl-btn" href="/library/">Go to Library</a></div>`}`;
  }
  return `<div class="ctl-seg" role="radiogroup" aria-label="Show">${[["slides", "Slides"], ["library", "Library"]].map(([k, label]) =>
    `<label><input type="radio" name="show-tab" data-show-tab value="${k}"${pv.tab === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div>${body}`;
}

function fillSlidePreviews(root, s) {
  for (const el of $$("[data-slide-prev]", root)) {
    el.replaceChildren(slideLayer(el.dataset.slidePrev, s || { notice: "" }));
  }
}

/* ---------- the screen panel ---------- */

function toggleHtml(name, label, on, extra = "") {
  return `<label class="ctl-toggle"><input type="checkbox" role="switch" ${extra} ${on ? "checked" : ""} aria-label="${esc(label)}"><span class="ctl-toggle-track" aria-hidden="true"></span><span class="ctl-toggle-word">${on ? "On" : "Off"}</span></label>`;
}

function panelHtml(s) {
  const room = st().rooms.find((r) => r.slug === s.room);
  return `<div class="ctl-pn" data-screen-panel="${esc(s.id)}"><div class="ctl-pn-body">
    <header class="ctl-pn-head"><div><h2 class="ctl-pn-title" id="ctl-panel-title" tabindex="-1">${esc(s.name)}</h2><p class="ctl-soft">${esc(room ? room.name : "")}</p></div>
      <button type="button" class="ctl-iconbtn" data-close aria-label="Close">${icon("x-r")}</button></header>
    <section class="ctl-group"><h3>On the screen <span class="ctl-chip-demo" title="Demo: nothing is sent to real equipment.">DEMO<span class="ctl-sr">. Demo: nothing is sent to real equipment.</span></span></h3>
      <div class="ctl-prev is-big" data-panel-prev></div><p class="ctl-pn-row"><span data-sp="summary"></span><span class="ctl-state" data-sp="state"></span></p></section>
    <section class="ctl-group"><div class="ctl-transport" role="group" aria-label="Playback">
      <button type="button" class="ctl-iconbtn" data-sp-act="prev" aria-label="Previous item">${icon("skip-back")}</button>
      <button type="button" class="ctl-play" data-sp-act="play" aria-label="Pause"></button>
      <button type="button" class="ctl-iconbtn" data-sp-act="next" aria-label="Next item">${icon("skip-forward")}</button>
      <button type="button" class="ctl-iconbtn ctl-toggle-icon" data-sp-act="loop" aria-pressed="false" aria-label="Loop">${icon("repeat")}</button></div>
      <div class="ctl-line"><span class="ctl-label">Screen on</span>${toggleHtml("power", `${s.name} screen on`, s.power, 'data-sp-power')}</div></section>
    <section class="ctl-group"><h3>Show</h3><div data-sp-chooser></div>
      <div class="ctl-choices" role="radiogroup" aria-label="Show on">
        <label class="ctl-choice"><input type="radio" name="scope" data-sp-scope value="this"${pv.scope === "this" ? " checked" : ""}><span>This screen</span></label>
        <label class="ctl-choice"><input type="radio" name="scope" data-sp-scope value="all"${pv.scope === "all" ? " checked" : ""}><span>All screens</span></label></div></section>
    <section class="ctl-group" data-sp-sched></section>
    <p class="ctl-note">Saved in this browser only.</p></div></div>`;
}

function paintScreenPanel(node) {
  const s = screenOf(node.dataset.screenPanel);
  if (!s) return;
  const set = (sel, text) => { const el = $(sel, node); if (el && el.textContent !== text) el.textContent = text; };
  set('[data-sp="summary"]', screenText(s));
  set('[data-sp="state"]', stateWord(s));
  const play = $('[data-sp-act="play"]', node);
  const key = `${s.power}${s.playing}`;
  if (play.dataset.state !== key) {
    play.dataset.state = key;
    play.innerHTML = icon(s.power && s.playing ? "pause" : "play");
    play.setAttribute("aria-label", s.power && s.playing ? "Pause" : "Play");
    play.disabled = !s.power;
  }
  const isPl = s.show.t === "playlist";
  for (const b of $$('[data-sp-act="prev"], [data-sp-act="next"]', node)) b.hidden = !isPl;
  const loop = $('[data-sp-act="loop"]', node);
  loop.setAttribute("aria-pressed", String(s.loop));
  const power = $("[data-sp-power]", node);
  power.checked = s.power;
  power.parentElement.querySelector(".ctl-toggle-word").textContent = s.power ? "On" : "Off";
}

function renderChooser(node, s) {
  const host = $("[data-sp-chooser]", node);
  const focused = document.activeElement && host.contains(document.activeElement) ? document.activeElement : null;
  const keep = focused && focused.matches("input[type=text]") ? { start: focused.selectionStart } : null;
  host.innerHTML = chooserHtml(s, s.show);
  fillSlidePreviews(host, s);
  if (keep) { const input = $("[data-notice-input]", host); if (input) { input.focus(); input.setSelectionRange(keep.start, keep.start); } }
  else if (focused && focused.dataset.showTab !== undefined) { const r = $(`[data-show-tab][value="${focused.value}"]`, host); if (r) r.focus(); }
  else if (focused && focused.dataset.libFilter !== undefined) { const r = $(`[data-lib-filter][value="${focused.value}"]`, host); if (r) r.focus(); }
}

function renderSched(node, s) {
  const host = $("[data-sp-sched]", node);
  const rows = s.sched.rows;
  host.innerHTML = `<h3>Schedule</h3><div class="ctl-line"><span class="ctl-label">Change through the day</span>${toggleHtml("sched", "Change through the day", s.sched.on, "data-sched-on")}</div>
    ${s.sched.on ? `<ul class="ctl-sched-rows">${rows.map((r, n) => `<li><input type="time" class="ctl-time-input" value="${esc(r.t)}" data-sched-time="${n}" aria-label="Time of change ${n + 1}">
      <button type="button" class="ctl-btn ctl-sched-what" data-sched-what="${n}">${esc(showLabel(r.show, s))}</button>
      <button type="button" class="ctl-iconbtn" data-sched-del="${n}" aria-label="Remove change ${n + 1}">${icon("x-r")}</button></li>`).join("")}</ul>
      ${rows.length < 4 ? '<button type="button" class="ctl-btn" data-sched-add>Add a change</button>' : '<p class="ctl-soft">Four changes is the most for one screen.</p>'}
      <p class="ctl-soft">Shown on the Schedule tab.</p>` : ""}`;
}

const sortRows = (s) => s.sched.rows.sort((a, b) => a.t.localeCompare(b.t));

function changed() { save(); S.render(); bus.emit("screens-changed"); }

function applyPick(s, show) {
  const targets = pv.scope === "all" ? st().screens : [s];
  for (const t of targets) setShow(t, JSON.parse(JSON.stringify(show)));
  changed();
  announce(`${s.name}${targets.length > 1 ? " and all screens" : ""} now show ${showLabel(show, s)}.`);
}

export function openScreen(id, { push = true } = {}) {
  const s = screenOf(id);
  if (!s) return;
  const holder = document.createElement("div");
  holder.innerHTML = panelHtml(s);
  const node = holder.firstElementChild;
  renderChooser(node, s);
  renderSched(node, s);
  paintScreenPanel(node);
  const host = $("[data-panel-prev]", node);
  loadLibrary();
  node.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const act = t.closest("[data-sp-act]");
    if (act) {
      const a = act.dataset.spAct;
      if (a === "play") { s.playing = !s.playing; if (s.playing) s.power = true; }
      else if (a === "loop") s.loop = !s.loop;
      else if (a === "prev" || a === "next") {
        const p = s.show.t === "playlist" ? playlist(s.show.id) : null;
        if (p && p.items.length) { const r = rt(s); r.idx = (r.idx + (a === "next" ? 1 : -1) + p.items.length) % p.items.length; r.el = 0; }
      }
      changed();
      return;
    }
    const pick = t.closest("[data-pick]");
    if (pick) { applyPick(s, JSON.parse(pick.dataset.pick)); renderChooser(node, s); return; }
    const del = t.closest("[data-sched-del]");
    if (del) { s.sched.rows.splice(Number(del.dataset.schedDel), 1); renderSched(node, s); changed(); return; }
    if (t.closest("[data-sched-add]")) {
      s.sched.rows.push({ t: "12:00", show: { t: "slide", k: "welcome" } });
      sortRows(s); renderSched(node, s); changed(); return;
    }
    const what = t.closest("[data-sched-what]");
    if (what) {
      const row = s.sched.rows[Number(what.dataset.schedWhat)];
      chooseDialog(s, row.show).then((show) => { if (show) { row.show = show; renderSched(node, s); changed(); } });
    }
  });
  node.addEventListener("input", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.matches("[data-notice-input]")) { s.notice = n.value.slice(0, 80); changed(); }
  });
  node.addEventListener("change", (event) => {
    const n = event.target;
    if (!(n instanceof HTMLInputElement)) return;
    if (n.matches("[data-show-tab]")) { pv.tab = n.value; renderChooser(node, s); }
    else if (n.matches("[data-lib-filter]")) { pv.filter = n.value; renderChooser(node, s); }
    else if (n.matches("[data-sp-scope]")) pv.scope = n.value;
    else if (n.matches("[data-sp-power]")) { s.power = n.checked; if (n.checked) s.playing = true; changed(); }
    else if (n.matches("[data-sched-on]")) {
      s.sched.on = n.checked;
      if (n.checked && !s.sched.rows.length) {
        s.sched.rows = [{ t: "05:00", show: { t: "slide", k: "welcome" } }, { t: "18:00", show: { t: "slide", k: "hours" } }, { t: "02:30", show: { t: "slide", k: "notices" } }];
      }
      renderSched(node, s); changed();
    } else if (n.matches("[data-sched-time]")) {
      const row = s.sched.rows[Number(n.dataset.schedTime)];
      if (row && /^\d\d:\d\d$/.test(n.value)) { row.t = n.value; sortRows(s); renderSched(node, s); changed(); }
    }
  });
  openPanel({ key: `screen:${id}`, node, size: "full", onClose: (quiet) => { if (!quiet && location.search) history.replaceState(null, "", location.pathname); } });
  mountPreview(host, s, { priority: 10 });
  if (push) history.replaceState(null, "", `${location.pathname}?screen=${id}`);
  const unsub = bus.on("library", () => { if (panelKey() === `screen:${id}`) { renderChooser(node, s); renderSched(node, s); } else unsub(); });
}

/** A small dialog with the same chooser (for the schedule rows). Resolves with a show object or null. */
function chooseDialog(s, current) {
  return formDialog((form, close) => {
    form.innerHTML = `<h2 id="ctl-dialog-h">What to show</h2><div data-dlg-chooser></div><div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button></div>`;
    const host = $("[data-dlg-chooser]", form);
    const draw = () => { host.innerHTML = chooserHtml(s, current); fillSlidePreviews(host, s); };
    draw();
    loadLibrary().then(draw);
    form.onclick = (event) => {
      const pick = event.target instanceof Element && event.target.closest("[data-pick]");
      if (pick) { event.preventDefault(); close(JSON.parse(pick.dataset.pick)); }
    };
    form.onchange = (event) => {
      const n = event.target;
      if (n.matches("[data-show-tab]")) { pv.tab = n.value; draw(); }
      else if (n.matches("[data-lib-filter]")) { pv.filter = n.value; draw(); }
    };
  });
}

/* ---------- schedule: the Screens lane, and changes at their time ---------- */

const laneMin = (min) => (min - st().lane_start + DAY) % DAY;

export function renderSchedLane() {
  const track = $("[data-slane-track]");
  if (!track) return;
  const groups = new Map();
  for (const s of st().screens) {
    if (!s.sched.on) continue;
    for (const r of s.sched.rows) {
      const [h, m] = r.t.split(":").map(Number);
      const key = r.t;
      if (!groups.has(key)) groups.set(key, { t: r.t, min: h * 60 + m, rows: [] });
      groups.get(key).rows.push({ screen: s.name, what: showLabel(r.show, s) });
    }
  }
  const markers = [...groups.values()].map((g) => {
    const pct = (laneMin(g.min) / 14.4).toFixed(3);
    return `<button type="button" class="ctl-smark" style="left:${pct}%" data-sev='${esc(JSON.stringify(g.rows))}' data-time="${esc(g.t)}" aria-haspopup="dialog" aria-expanded="false" aria-label="${esc(`${g.t}, ${g.rows.map((x) => `${x.screen} shows ${x.what}`).join(", ")}`)}"></button>`;
  });
  const html = markers.join("") || '<span class="ctl-slane-none">No screen changes set. Add them in Screens.</span>';
  if (track.dataset.sig !== html) { track.dataset.sig = html; track.innerHTML = html; }
}

bus.on("minute", (t) => {
  for (const s of st().screens) {
    if (!s.sched.on) continue;
    const row = s.sched.rows.find((r) => r.t === t.clock);
    if (row) { setShow(s, JSON.parse(JSON.stringify(row.show))); }
  }
  changed();
});

/* ---------- a deleted file: screens fall back to Welcome ---------- */

function fallBackIfMissing(announceIt) {
  let n = 0;
  for (const s of st().screens) {
    const gone = (show) => (show.t === "asset" && !asset(show.id)) || (show.t === "playlist" && !playlist(show.id));
    if (gone(s.show)) { s.show = { t: "slide", k: "welcome" }; n += 1; }
    for (const r of s.sched.rows) if (gone(r.show)) r.show = { t: "slide", k: "welcome" };
  }
  if (n && announceIt) toastInfo(n === 1 ? "A screen was showing a deleted file. It shows Welcome now." : `${n} screens were showing deleted files. They show Welcome now.`);
  if (n) { save(); S.render(); }
}

bus.on("library", () => fallBackIfMissing(true));
bus.on("asset-deleted", () => fallBackIfMissing(true));
bus.on("playlist-deleted", () => fallBackIfMissing(true));

export function initScreens() {
  S.screenText = screenText;
  S.mountPreview = (host, screen, opts) => mountPreview(host, screen, { still: false, ...opts });
  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const open = t.closest("[data-open-screen]");
    if (open && !event.metaKey && !event.ctrlKey && !event.shiftKey) { event.preventDefault(); openScreen(open.dataset.openScreen); return; }
    const play = t.closest('[data-act="screen-play"]');
    if (play) {
      const s = screenOf(play.closest("[data-screen]").dataset.screen);
      if (s) { s.playing = !s.playing; changed(); }
    }
  });
  document.addEventListener("visibilitychange", reconcile);
  bus.on("screens-changed", () => { for (const p of previews) p.update(); });
}

export { closePanel };

/** Used by the Library: show something on one screen. */
export function showOnScreen(screenId, show) {
  const s = screenOf(screenId);
  if (!s) return false;
  setShow(s, show);
  changed();
  return true;
}
