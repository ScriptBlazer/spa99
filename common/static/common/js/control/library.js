/* The Library page (REAL): files, playlists, uploads. Everything here is stored on the server through /library/... (libdata.js).
   Playback into rooms and screens is pretend; previews here play the real files in this browser. */
import { $, $$, S, esc, icon, toast, announce, bus, fmtDur, fmtSize, fmtTotal, plural, confirmDialog, formDialog, MOTION, FINE, XWIDE } from "./core.js";
import { L, asset, playlist, loadLibrary, postJSON, replaceAsset, replacePlaylist, dropAsset, dropPlaylist, refreshUsedIn, itemSeconds, playlistSeconds } from "./libdata.js";
import { addFiles, limits, uploading } from "./upload.js";
import { openPanel, closePanel, panelKey } from "./panel.js";
import { sortable } from "./sortable.js";
import { waveSvg, playLibraryList, zoneById } from "./music.js";
import { showOnScreen, screenOf } from "./screens.js";

const VIEW_KEY = "spa99.control.lib.view";
const lib = { sub: "files", tag: "all", kinds: new Set(), q: "", view: localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid", sel: new Set(), fresh: new Set() };
let root = null;
let previewAudio = null;
let playing = null;  // asset id being previewed in this browser
const LIMITS_LINE = "Music: MP3, M4A or WAV. Video: MP4 (H.264) or WebM. Pictures: JPG, PNG or WebP.";

const params = () => new URLSearchParams(location.search);
const kindWord = { audio: "Audio", video: "Video", image: "Image" };
const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1);
const dateText = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const dims = (a) => (a.width && a.height ? `${a.width}×${a.height}` : "");
const chipText = (a) => (a.kind === "image" ? dims(a) : a.duration_seconds ? fmtDur(a.duration_seconds) : "");
const tagsText = (a) => a.tags.map(cap).join(", ");

/* ---------- used in ---------- */

function usedIn(a) {
  const inList = (plId) => { const p = playlist(plId); return Boolean(p && p.items.some((i) => i.asset.id === a.id)); };
  const screens = S.st.screens.filter((s) => (s.show.t === "asset" && s.show.id === a.id) || (s.show.t === "playlist" && inList(s.show.id)));
  const zones = S.st.music.zones.filter((z) => z.queue.some((e) => e.assetId === a.id));
  return { playlists: a.playlists || [], screens, zones };
}

function usedPhrase(list) {
  const parts = [];
  const screens = new Set();
  const zones = new Set();
  const playlists = new Set();
  for (const a of list) { const u = usedIn(a); u.screens.forEach((s) => screens.add(s.id)); u.zones.forEach((z) => zones.add(z.id)); u.playlists.forEach((p) => playlists.add(p.id)); }
  if (screens.size) parts.push(`used on ${plural(screens.size, "screen")}; ${screens.size === 1 ? "it'll" : "they'll"} show Welcome instead`);
  if (zones.size) parts.push(`in ${plural(zones.size, "music queue")}; the music stops there`);
  if (playlists.size) parts.push(`in ${plural(playlists.size, "playlist")}`);
  return parts.length ? `It's ${parts.join(". It's ")}.` : "";
}

/* ---------- the meter ---------- */

export function renderMeter() {
  const m = $("[data-meter]");
  if (!m) return;
  const { used_bytes: used, max_bytes: max } = L.summary;
  const frac = max ? Math.min(1, used / max) : 0;
  const text = $("[data-meter-text]", m);
  const full = frac >= 0.9;
  if (text) text.textContent = `${fmtSize(used)} of ${fmtSize(max)}${full ? ". Library nearly full" : ""}`;
  const bar = $(".ctl-meter-bar span", m);
  if (bar) bar.style.transform = `scaleX(${frac})`;
  m.dataset.warn = full ? "1" : "";
}

/* ---------- filters ---------- */

function visible() {
  const q = lib.q.trim().toLowerCase();
  return L.assets.filter((a) => {
    if (lib.tag !== "all" && !a.tags.includes(lib.tag)) return false;
    if (lib.kinds.size && !lib.kinds.has(a.kind)) return false;
    if (q && !`${a.title} ${a.artist || ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

/* ---------- thumbnails ---------- */

function thumbInner(a, bars = 64) {
  if (a.kind === "audio") return `<span class="ctl-wavebox" data-wavebox="${a.id}">${waveSvg(a.peaks, "ctl-wave", bars) || `<span class="ctl-thumb-empty">${icon("music-notes")}</span>`}${a.peaks ? `<span class="ctl-wave-fill">${waveSvg(a.peaks, "ctl-wave", bars)}</span>` : ""}</span>`;
  if (a.kind === "image") return `<img src="${esc(a.url)}" alt="" loading="lazy" draggable="false">`;
  return a.poster_url ? `<img src="${esc(a.poster_url)}" alt="" loading="lazy" draggable="false">` : `<span class="ctl-thumb-empty">${icon("film-strip")}</span>`;
}

function tileHtml(a) {
  const sel = lib.sel.has(a.id);
  const chip = chipText(a);
  return `<li class="ctl-ftile is-${a.kind}${sel ? " is-sel" : ""}${lib.fresh.has(a.id) ? " is-new" : ""}" data-asset="${a.id}">
    <div class="ctl-fthumb">${thumbInner(a)}${chip ? `<span class="ctl-chipdata">${esc(chip)}</span>` : ""}
      <label class="ctl-fcheck"><input type="checkbox" data-sel="${a.id}"${sel ? " checked" : ""} aria-label="Select ${esc(a.title)}"><span aria-hidden="true">${icon("check")}</span></label>
      ${a.kind === "audio" ? `<button type="button" class="ctl-fplay" data-aplay="${a.id}" aria-label="Play ${esc(a.title)}">${icon("play")}</button>` : ""}</div>
    <a class="ctl-fname" href="?item=${a.id}" data-open-item="${a.id}">${esc(a.title)}</a>
    <p class="ctl-soft ctl-ftags">${esc(tagsText(a))}</p></li>`;
}

function rowHtml(a) {
  const sel = lib.sel.has(a.id);
  return `<li class="ctl-lrow${sel ? " is-sel" : ""}${lib.fresh.has(a.id) ? " is-new" : ""}" data-asset="${a.id}">
    <label class="ctl-fcheck is-row"><input type="checkbox" data-sel="${a.id}"${sel ? " checked" : ""} aria-label="Select ${esc(a.title)}"><span aria-hidden="true">${icon("check")}</span></label>
    <span class="ctl-lthumb">${thumbInner(a, 16)}</span>
    <a class="ctl-fname" href="?item=${a.id}" data-open-item="${a.id}">${esc(a.title)}</a>
    <span class="ctl-lcell">${kindWord[a.kind]}</span><span class="ctl-lcell ctl-ltags">${esc(tagsText(a))}</span>
    <span class="ctl-lcell">${esc(chipText(a) || fmtSize(a.size_bytes))}</span><span class="ctl-lcell ctl-ldate">${dateText(a.created_at)}</span>
    <a class="ctl-iconbtn" href="?item=${a.id}" data-open-item="${a.id}" aria-label="Open ${esc(a.title)}">${icon("dots-three")}</a></li>`;
}

/* ---------- the shell and the content ---------- */

function emptyHtml(iconName, one, two, buttons = "") {
  return `<div class="ctl-empty"><span class="ctl-empty-icon">${icon(iconName)}</span><p class="ctl-empty-1">${one}</p>${two ? `<p class="ctl-empty-2">${two}</p>` : ""}${buttons}</div>`;
}

function shellHtml() {
  return `<div class="ctl-lib-bar"><div class="ctl-seg ctl-seg-sub" role="radiogroup" aria-label="Library section">${[["files", "Files"], ["playlists", "Playlists"]].map(([k, label]) =>
    `<label><input type="radio" name="lib-sub" data-lib-sub value="${k}"${lib.sub === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div>
    ${lib.sub === "files" ? `<div class="ctl-filters">
      <div class="ctl-seg ctl-seg-sm" role="radiogroup" aria-label="Show">${[["all", "All"], ["music", "Music"], ["screens", "Screens"]].map(([k, label]) => `<label><input type="radio" name="lib-tag" data-lib-tag value="${k}"${lib.tag === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div>
      <div class="ctl-chips" role="group" aria-label="Type">${[["audio", "Audio"], ["video", "Video"], ["image", "Images"]].map(([k, label]) => `<button type="button" class="ctl-chipbtn" data-lib-kind="${k}" aria-pressed="${lib.kinds.has(k)}"><span>${label}</span></button>`).join("")}</div>
      <p class="ctl-field ctl-search"><label class="ctl-sr" for="lib-q">Search files</label><input id="lib-q" type="text" data-lib-q value="${esc(lib.q)}" placeholder="Search" autocomplete="off"></p>
      <div class="ctl-seg ctl-seg-sm" role="radiogroup" aria-label="View">${[["grid", "Grid"], ["list", "List"]].map(([k, label]) => `<label><input type="radio" name="lib-view" data-lib-view value="${k}"${lib.view === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div></div>`
      : `<button type="button" class="ctl-btn" data-pl-new>${icon("plus")}<span>New playlist</span></button>`}</div>
    <div data-lib-content></div><div class="ctl-selbar" data-selbar hidden></div>`;
}

function contentEl() { return $("[data-lib-content]", root); }

function renderFiles() {
  const host = contentEl();
  if (!L.loaded) { host.innerHTML = `<p class="ctl-soft">${L.error ? `${esc(L.error)} <button type="button" class="ctl-link" data-lib-retry>Try again</button>` : "Loading the Library."}</p>`; return; }
  const items = visible();
  if (!L.assets.length) {
    host.innerHTML = emptyHtml("upload-simple", "Nothing here yet.", `Drop music, video or pictures here.<br><span class="ctl-soft">${LIMITS_LINE}</span>`, '<button type="button" class="ctl-btn ctl-btn-primary" data-lib-choose>Choose files</button>');
  } else if (!items.length) {
    host.innerHTML = emptyHtml("magnifying-glass", "Nothing matches.", "", '<button type="button" class="ctl-btn" data-lib-clear>Clear filters</button>');
  } else {
    host.innerHTML = lib.view === "list" ? `<ul class="ctl-flist">${items.map(rowHtml).join("")}</ul>` : `<ul class="ctl-fgrid">${items.map(tileHtml).join("")}</ul>`;
  }
  lib.fresh.clear();
  renderSelbar();
  if (playing) markPlaying();
}

function coverHtml(p) {
  const items = p.items.slice(0, 4);
  if (!items.length) return `<span class="ctl-cover-swan"><img src="${esc(document.body.dataset.swan)}" alt="" draggable="false"></span>`;
  return `<span class="ctl-mosaic">${items.map((i) => `<span>${thumbInner(i.asset, 16)}</span>`).join("")}</span>`;
}

function renderPlaylists() {
  const host = contentEl();
  if (!L.loaded) { host.innerHTML = '<p class="ctl-soft">Loading the Library.</p>'; return; }
  if (!L.playlists.length) { host.innerHTML = emptyHtml("playlist", "No playlists yet.", "Put music or screen media in order.", '<button type="button" class="ctl-btn ctl-btn-primary" data-pl-new>New playlist</button>'); return; }
  host.innerHTML = `<ul class="ctl-pgrid">${L.playlists.map((p) => `<li class="ctl-pcard"><a class="ctl-pcard-open" href="?playlist=${p.id}" data-open-playlist="${p.id}" aria-label="${esc(p.name)}, ${p.kind === "music" ? "Music" : "Screens"} playlist"></a>
    <div class="ctl-pcover">${coverHtml(p)}</div><p class="ctl-fname-s">${esc(p.name)}</p>
    <p class="ctl-soft">${p.kind === "music" ? "Music" : "Screens"} · ${plural(p.items.length, p.kind === "music" ? "track" : "item")}${p.items.length ? `, ${fmtTotal(playlistSeconds(p))}` : ""}</p></li>`).join("")}</ul>`;
}

/* ---------- playlist page ---------- */

function plItemHtml(p, item) {
  const a = item.asset;
  const isImage = a.kind === "image";
  return `<li data-item="${item.id}"><button type="button" class="ctl-handle" data-handle aria-label="Move ${esc(a.title)}. Up and Down arrows reorder">${icon("dots-six-vertical")}</button>
    <span class="ctl-lthumb">${thumbInner(a, 16)}</span><span class="ctl-qtext"><span class="ctl-qtitle">${esc(a.title)}</span>${a.artist ? `<span class="ctl-soft">${esc(a.artist)}</span>` : ""}</span>
    ${p.kind === "screens" && isImage ? `<span class="ctl-stepper" role="group" aria-label="Show for"><button type="button" data-secs="-1" data-item-id="${item.id}" aria-label="Show for fewer seconds">&minus;</button><span class="ctl-step-val">${item.seconds || 8} s</span><button type="button" data-secs="1" data-item-id="${item.id}" aria-label="Show for more seconds">+</button></span>`
      : `<span class="ctl-qdur">${a.kind === "image" ? "" : fmtDur(a.duration_seconds || 0)}</span>`}
    <button type="button" class="ctl-iconbtn" data-pl-remove="${item.id}" aria-label="Remove ${esc(a.title)}">${icon("x-r")}</button></li>`;
}

function renderPlaylistPage(id) {
  const host = contentEl();
  const p = playlist(id);
  if (!L.loaded) { host.innerHTML = '<p class="ctl-soft">Loading the Library.</p>'; return; }
  if (!p) { host.innerHTML = emptyHtml("playlist", "That playlist is gone.", "", '<a class="ctl-btn" href="?tab=playlists" data-lib-back>Back to playlists</a>'); return; }
  const music = p.kind === "music";
  const total = playlistSeconds(p);
  host.innerHTML = `<div class="ctl-plview" data-playlist="${p.id}">
    <p><a class="ctl-back" href="?tab=playlists" data-lib-back>${icon("arrow-left")}<span>Playlists</span></a></p>
    <header class="ctl-plhead"><div class="ctl-pcover is-lg">${coverHtml(p)}</div>
      <div class="ctl-plmeta"><div class="ctl-edit" data-edit="plname"><h2 class="ctl-edit-text">${esc(p.name)}</h2><button type="button" class="ctl-iconbtn" data-edit-btn aria-label="Rename playlist">${icon("pencil-simple")}</button></div>
        <p class="ctl-soft">${music ? "Music" : "Screens"} · ${plural(p.items.length, music ? "track" : "item")}${p.items.length ? `, ${fmtTotal(total)}` : ""}</p>
        <div class="ctl-plactions">${p.items.length ? `<button type="button" class="ctl-btn ctl-btn-primary" data-pl-play>${music ? "Play in a zone" : "Show on a screen"}</button>` : ""}<button type="button" class="ctl-btn" data-pl-add>${icon("plus")}<span>Add items</span></button></div></div></header>
    ${p.items.length ? `<ol class="ctl-plitems" data-pl-items>${p.items.map((i) => plItemHtml(p, i)).join("")}</ol>` : emptyHtml("playlist", "This playlist is empty.", "", '<button type="button" class="ctl-btn ctl-btn-primary" data-pl-add>Add items</button>')}
    <p class="ctl-pl-delete"><button type="button" class="ctl-link is-danger" data-pl-delete>Delete playlist</button> <span class="ctl-soft">The files stay in the Library.</span></p></div>`;
  const list = $("[data-pl-items]", host);
  if (list) sortable(list, { handleSel: "[data-handle]", itemSel: ":scope > li", describe: (to) => `Moved to position ${to + 1}`, onMove: (from, to) => movePlaylistItem(p, from, to) });
}

async function movePlaylistItem(p, from, to) {
  const before = p.items.slice();
  const [item] = p.items.splice(from, 1);
  p.items.splice(to, 0, item);
  p.items.forEach((i, n) => { i.position = n + 1; });
  renderRoute();
  const focusIdx = to;
  const hs = $$("[data-pl-items] [data-handle]", root);
  if (hs[focusIdx]) hs[focusIdx].focus({ preventScroll: true });
  try { replacePlaylist(await postJSON(`/library/playlists/${p.id}/items/reorder/`, { item_ids: p.items.map((i) => i.id) })); }
  catch (e) { p.items = before; renderRoute(); toast(e.message); }
}

/* ---------- routing inside the page ---------- */

function renderRoute() {
  if (!root) return;
  const q = params();
  const pl = q.get("playlist");
  if (!$("[data-lib-content]", root)) rebuildShell();
  if (pl) renderPlaylistPage(pl);
  else if (lib.sub === "playlists") renderPlaylists();
  else renderFiles();
  const bar = $(".ctl-lib-bar", root);
  if (bar) bar.hidden = Boolean(pl);
  renderMeter();
}

function rebuildShell() {
  const ui = $("[data-lib-ui]", root);
  ui.innerHTML = shellHtml();
}

function go(search, replace = false) {
  history[replace ? "replaceState" : "pushState"](null, "", `${location.pathname}${search}`);
  syncLibraryUrl();
}

export function syncLibraryUrl() {
  if (!root) return;
  const q = params();
  const tab = q.get("tab");
  if (tab === "playlists" || q.get("playlist")) lib.sub = "playlists"; else lib.sub = "files";
  rebuildShell();
  renderRoute();
  const item = q.get("item");
  if (item && L.loaded && asset(item)) openItem(item, false);
  else if (panelKey() && panelKey().startsWith("item:")) closePanel();
}

/* ---------- audio preview in this browser ---------- */

function audioEl() {
  if (!previewAudio) {
    previewAudio = new Audio();
    previewAudio.addEventListener("timeupdate", () => {
      if (!playing || !previewAudio.duration) return;
      const p = previewAudio.currentTime / previewAudio.duration;
      for (const box of $$(`[data-wavebox="${playing}"]`)) box.style.setProperty("--p", String(p));
      const scrub = $("[data-item-scrub]");
      if (scrub && scrub.dataset.drag !== "1") { scrub.value = String(Math.round(previewAudio.currentTime)); scrub.parentElement.style.setProperty("--v", String(p)); const t = $("[data-item-time]"); if (t) t.textContent = fmtDur(previewAudio.currentTime); }
    });
    previewAudio.addEventListener("ended", () => stopPreview());
  }
  return previewAudio;
}

function markPlaying() {
  for (const b of $$("[data-aplay]")) { const on = b.dataset.aplay === playing; b.innerHTML = icon(on ? "pause" : "play"); b.setAttribute("aria-label", `${on ? "Pause" : "Play"} ${(asset(b.dataset.aplay) || {}).title || ""}`); }
  const big = $("[data-item-play]");
  if (big) { const on = playing && big.dataset.itemPlay === playing && !audioEl().paused; big.innerHTML = icon(on ? "pause" : "play"); big.setAttribute("aria-label", on ? "Pause" : "Play"); }
}

function togglePreview(id) {
  const a = asset(id);
  const el = audioEl();
  if (!a) return;
  if (playing === id) { if (el.paused) el.play().catch(() => {}); else el.pause(); markPlaying(); return; }
  stopPreview();
  playing = id;
  el.src = a.url;
  el.play().catch(() => { toast("This browser could not play that file."); stopPreview(); });
  markPlaying();
}

export function stopPreview() {
  if (previewAudio) { previewAudio.pause(); }
  for (const box of $$("[data-wavebox]")) box.style.setProperty("--p", "0");
  playing = null;
  markPlaying();
}

/* ---------- selection ---------- */

function renderSelbar() {
  const bar = $("[data-selbar]", root);
  if (!bar) return;
  const n = lib.sel.size;
  bar.hidden = n === 0;
  document.body.classList.toggle("has-selbar", n > 0);
  if (!n) return;
  bar.innerHTML = `<p class="ctl-selcount" role="status">${n} selected</p><button type="button" class="ctl-btn" data-sel-act="playlist">Add to playlist</button>
    <button type="button" class="ctl-btn" data-sel-act="tag">Tag</button><button type="button" class="ctl-btn is-danger" data-sel-act="delete">Delete</button><button type="button" class="ctl-btn" data-sel-act="clear">Clear</button>`;
}

function setSel(id, on) {
  if (on) lib.sel.add(id); else lib.sel.delete(id);
  for (const el of $$(`[data-asset="${id}"]`, root)) el.classList.toggle("is-sel", on);
  renderSelbar();
}

/* ---------- dialogs ---------- */

function chooseOne(title, options, empty = "") {
  return formDialog((form, close) => {
    form.innerHTML = `<h2 id="ctl-dialog-h">${esc(title)}</h2>${options.length ? `<ul class="ctl-choose">${options.map((o) => `<li><button type="button" class="ctl-choose-btn" data-choose="${esc(o.value)}"><span>${esc(o.label)}</span>${o.sub ? `<span class="ctl-soft">${esc(o.sub)}</span>` : ""}</button></li>`).join("")}</ul>` : `<p class="ctl-soft">${esc(empty)}</p>`}
      <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button></div>`;
    form.onclick = (e) => { const b = e.target instanceof Element && e.target.closest("[data-choose]"); if (b) { e.preventDefault(); close(b.dataset.choose); } };
  });
}

function newPlaylistDialog(kind = "") {
  return formDialog((form, close) => {
    form.innerHTML = `<h2 id="ctl-dialog-h">New playlist</h2>
      <p class="ctl-field"><label for="pl-name">Name</label><input id="pl-name" type="text" maxlength="120" data-pl-name autocomplete="off"></p>
      <div class="ctl-choices is-tiles" role="radiogroup" aria-label="Kind">${[["music", "Music", "Tracks, played in a zone"], ["screens", "Screens", "Videos and pictures, shown on a screen"]].map(([k, label, sub]) =>
        `<label class="ctl-choice"><input type="radio" name="pl-kind" value="${k}"${kind === k ? " checked" : ""}><span>${label}<br><span class="ctl-soft">${sub}</span></span></label>`).join("")}</div>
      <p class="ctl-error" data-pl-error role="alert"></p>
      <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button><button type="button" class="ctl-btn ctl-btn-primary" data-pl-create>Create</button></div>`;
    $("[data-pl-name]", form).focus();
    form.onclick = async (e) => {
      if (!(e.target instanceof Element) || !e.target.closest("[data-pl-create]")) return;
      const name = $("[data-pl-name]", form).value.trim();
      const chosen = $("input[name=pl-kind]:checked", form);
      const err = $("[data-pl-error]", form);
      if (!name) { err.textContent = "Give the playlist a name."; return; }
      if (!chosen) { err.textContent = "Choose Music or Screens."; return; }
      try { const made = await postJSON("/library/playlists/create/", { name, kind: chosen.value }); replacePlaylist(made); close(made); }
      catch (ex) { err.textContent = ex.message; }
    };
  });
}

async function createPlaylist(kind = "") {
  const made = await newPlaylistDialog(kind);
  if (!made) return null;
  announce(`${made.name} created.`);
  return made;
}

async function addItemsDialog(p) {
  const kinds = p.kind === "music" ? ["audio"] : ["video", "image"];
  const pool = L.assets.filter((a) => kinds.includes(a.kind));
  const inList = new Set(p.items.map((i) => i.asset.id));
  if (!pool.length) { toast(p.kind === "music" ? "No music in the Library yet." : "No videos or pictures in the Library yet."); return; }
  const picked = await formDialog((form, close) => {
    const chosen = new Set();
    form.innerHTML = `<h2 id="ctl-dialog-h">Add to ${esc(p.name)}</h2><ul class="ctl-addlist">${pool.map((a) => `<li><label class="ctl-addrow"><input type="checkbox" data-add="${a.id}"${inList.has(a.id) ? " checked disabled" : ""}>
      <span class="ctl-lthumb">${thumbInner(a, 16)}</span><span class="ctl-qtext"><span class="ctl-qtitle">${esc(a.title)}</span>${inList.has(a.id) ? '<span class="ctl-soft">In this playlist</span>' : ""}</span><span class="ctl-qdur">${esc(chipText(a))}</span></label></li>`).join("")}</ul>
      <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button><button type="button" class="ctl-btn ctl-btn-primary" data-add-go disabled>Add</button></div>`;
    const go = $("[data-add-go]", form);
    form.onchange = (e) => {
      const n = e.target;
      if (!n.matches("[data-add]")) return;
      if (n.checked) chosen.add(n.dataset.add); else chosen.delete(n.dataset.add);
      go.disabled = chosen.size === 0;
      go.textContent = chosen.size ? `Add ${chosen.size}` : "Add";
    };
    go.addEventListener("click", () => close([...chosen]));
  });
  if (!picked || !picked.length) return;
  try {
    let latest = p;
    for (const id of picked) latest = await postJSON(`/library/playlists/${p.id}/items/add/`, { asset_id: id });
    replacePlaylist(latest);
    renderRoute();
    toast(`Added ${plural(picked.length, "item")} to ${p.name}.`);
  } catch (e) { toast(e.message); renderRoute(); }
}

/* ---------- item panel ---------- */

function chipsHtml(a) {
  const locked = a.kind === "audio" ? "music" : "screens";
  const other = a.tags.filter((t) => t !== "music" && t !== "screens");
  const chip = (tag, label) => {
    const on = a.tags.includes(tag);
    const off = (a.kind !== "audio" && tag === "music");
    return `<button type="button" class="ctl-chipbtn" data-tag="${tag}" aria-pressed="${on}"${tag === locked || off ? " disabled" : ""}><span>${label}</span></button>`;
  };
  return `<div class="ctl-chips">${chip("music", "Music")}${chip("screens", "Screens")}${other.map((t) => `<span class="ctl-tag">${esc(cap(t))}<button type="button" class="ctl-tag-x" data-tag-del="${esc(t)}" aria-label="Remove tag ${esc(t)}">${icon("x-r")}</button></span>`).join("")}</div>
    <p class="ctl-field ctl-addtag"><label class="ctl-sr" for="tag-in">Add a tag</label><input id="tag-in" type="text" maxlength="30" data-tag-in placeholder="Add a tag" autocomplete="off"></p>`;
}

function previewHtml(a) {
  if (a.kind === "video") return `<video class="ctl-ivideo" controls playsinline preload="metadata"${a.poster_url ? ` poster="${esc(a.poster_url)}"` : ""} src="${esc(a.url)}"></video>`;
  if (a.kind === "image") return `<img class="ctl-iimage" src="${esc(a.url)}" alt="${esc(a.title)}" draggable="false">`;
  return `<div class="ctl-iaudio"><span class="ctl-wavebox is-large" data-wavebox="${a.id}">${waveSvg(a.peaks, "ctl-wave", 100) || ""}${a.peaks ? `<span class="ctl-wave-fill">${waveSvg(a.peaks, "ctl-wave", 100)}</span>` : ""}</span>
    <div class="ctl-iaudio-bar"><button type="button" class="ctl-play" data-item-play="${a.id}" aria-label="Play">${icon("play")}</button><span class="ctl-time" data-item-time>0:00</span>
      <span class="ctl-range is-scrub" style="--v:0"><input type="range" data-item-scrub min="0" max="${Math.round(a.duration_seconds || 0)}" step="1" value="0" aria-label="Position in ${esc(a.title)}"></span><span class="ctl-time">${fmtDur(a.duration_seconds || 0)}</span></div></div>`;
}

function usedHtml(a) {
  const u = usedIn(a);
  const items = [
    ...u.playlists.map((p) => `<li><a class="ctl-link" href="/library/?playlist=${p.id}" data-open-playlist="${p.id}">${esc(p.name)}</a> <span class="ctl-soft">playlist</span></li>`),
    ...u.screens.map((s) => `<li><a class="ctl-link" href="/screens/?screen=${esc(s.id)}">${esc(s.name)}</a> <span class="ctl-soft">screen</span></li>`),
    ...u.zones.map((z) => `<li><a class="ctl-link" href="/music/?zone=${esc(z.id)}">${esc(z.name)}</a> <span class="ctl-soft">music zone</span></li>`),
  ];
  return items.length ? `<ul class="ctl-used">${items.join("")}</ul>` : '<p class="ctl-soft">Not used anywhere yet.</p>';
}

function editHtml(field, label, text, placeholder = "") {
  return `<div class="ctl-edit" data-edit="${field}"><span class="ctl-edit-text${text ? "" : " is-empty"}">${esc(text || placeholder)}</span><button type="button" class="ctl-iconbtn" data-edit-btn aria-label="${esc(label)}">${icon("pencil-simple")}</button></div>`;
}

function itemHtml(a) {
  const soft = a.kind === "image" && a.width && (a.width < 1920 || a.height < 1080);
  return `<div class="ctl-pn" data-item-panel="${a.id}"><div class="ctl-ipreview">${previewHtml(a)}</div><div class="ctl-pn-body">
    <header class="ctl-pn-head"><div class="ctl-grow">${editHtml("title", "Rename", a.title)}<h2 class="ctl-sr" id="ctl-panel-title" tabindex="-1">${esc(a.title)}</h2></div><button type="button" class="ctl-iconbtn" data-close aria-label="Close">${icon("x-r")}</button></header>
    ${a.kind === "audio" ? `<section class="ctl-group"><h3>Artist</h3>${editHtml("artist", "Edit artist", a.artist, "Add an artist")}</section>` : ""}
    <section class="ctl-group"><h3>Tags</h3>${chipsHtml(a)}</section>
    <section class="ctl-group"><h3>Details</h3><dl class="ctl-dl"><div><dt>Type</dt><dd>${kindWord[a.kind]}, ${esc(a.mime)}</dd></div><div><dt>Size</dt><dd>${fmtSize(a.size_bytes)}</dd></div>
      ${a.kind === "image" ? `<div><dt>Dimensions</dt><dd>${esc(dims(a) || "Unknown")}</dd></div>` : `<div><dt>Length</dt><dd>${a.duration_seconds ? fmtDur(a.duration_seconds) : "Unknown"}</dd></div>${a.kind === "video" && dims(a) ? `<div><dt>Dimensions</dt><dd>${esc(dims(a))}</dd></div>` : ""}`}
      <div><dt>Uploaded by</dt><dd>${esc(a.uploaded_by || "Unknown")}</dd></div><div><dt>Date</dt><dd>${dateText(a.created_at)}</dd></div></dl>${soft ? '<p class="ctl-soft">May look soft on large screens.</p>' : ""}</section>
    <section class="ctl-group"><h3>Used in</h3><div data-usedin>${usedHtml(a)}</div></section>
    <p class="ctl-pn-delete"><button type="button" class="ctl-link is-danger" data-item-delete>Delete</button></p></div></div>`;
}

function openItem(id, push = true) {
  const a = asset(id);
  if (!a) return;
  stopPreview();
  const holder = document.createElement("div");
  holder.innerHTML = itemHtml(a);
  const node = holder.firstElementChild;
  node.addEventListener("click", (event) => onItemClick(event, id, node));
  node.addEventListener("keydown", (event) => onItemKey(event, id));
  node.addEventListener("focusout", (event) => { if (event.target instanceof Element && event.target.matches("[data-edit] input")) commitEdit(event.target, id, true); });
  node.addEventListener("input", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.matches("[data-item-scrub]")) { n.dataset.drag = "1"; const t = $("[data-item-time]", node); if (t) t.textContent = fmtDur(n.value); n.parentElement.style.setProperty("--v", String(a.duration_seconds ? n.value / a.duration_seconds : 0)); }
  });
  node.addEventListener("change", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.matches("[data-item-scrub]")) { n.dataset.drag = "0"; if (playing === id) audioEl().currentTime = Number(n.value); }
  });
  openPanel({ key: `item:${id}`, node, size: "full", onClose: () => { stopPreview(); const q = params(); q.delete("item"); const s = q.toString(); history.replaceState(null, "", `${location.pathname}${s ? `?${s}` : ""}`); } });
  if (push) { const q = params(); q.set("item", id); history.replaceState(null, "", `${location.pathname}?${q}`); }
}

function refreshItem(id) {
  const node = $(`[data-item-panel="${id}"]`);
  const a = asset(id);
  if (!node || !a) return;
  const fresh = document.createElement("div");
  fresh.innerHTML = itemHtml(a);
  const body = $(".ctl-pn-body", node);
  const scroll = body ? body.scrollTop : 0;
  const newBody = $(".ctl-pn-body", fresh);
  body.replaceWith(newBody);
  newBody.scrollTop = scroll;
  const ph = $("#ctl-panel-title", node);
  if (ph) ph.textContent = a.title;
  $("[data-usedin]", node).innerHTML = usedHtml(a);
}

async function saveAsset(id, patch) {
  try {
    const data = await postJSON(`/library/assets/${id}/update/`, patch);
    replaceAsset(data);
    refreshUsedIn();
    refreshItem(id);
    renderRoute();
    return true;
  } catch (e) { toast(e.message); refreshItem(id); return false; }
}

function startEdit(box, id) {
  const field = box.dataset.edit;
  const a = asset(id);
  const value = field === "title" ? a.title : a.artist;
  box.innerHTML = `<input type="text" maxlength="${field === "title" ? 80 : 120}" value="${esc(value)}" aria-label="${field === "title" ? "Name" : "Artist"}" data-orig="${esc(value)}">`;
  const input = $("input", box);
  input.focus();
  input.select();
}

function commitEdit(input, id, blur = false) {
  const box = input.closest("[data-edit]");
  if (!box || box.dataset.done === "1") return;
  box.dataset.done = "1";
  const field = box.dataset.edit;
  const next = input.value.trim();
  const orig = input.dataset.orig;
  if (next === orig || (field === "title" && !next)) { refreshItem(id); return; }
  saveAsset(id, { [field]: next });
}

function cancelEdit(id) { refreshItem(id); }

function onItemKey(event, id) {
  const t = event.target;
  if (!(t instanceof HTMLInputElement)) return;
  if (t.matches("[data-edit] input")) {
    if (event.key === "Enter") { event.preventDefault(); commitEdit(t, id); }
    else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); t.closest("[data-edit]").dataset.done = "1"; cancelEdit(id); }
  } else if (t.matches("[data-tag-in]") && event.key === "Enter") {
    event.preventDefault();
    const v = t.value.trim().toLowerCase();
    const a = asset(id);
    if (v && !a.tags.includes(v)) saveAsset(id, { tags: [...a.tags, v] });
  }
}

async function onItemClick(event, id, node) {
  const t = event.target instanceof Element ? event.target : null;
  if (!t) return;
  const a = asset(id);
  const btn = t.closest("[data-edit-btn]");
  if (btn) { startEdit(btn.closest("[data-edit]"), id); return; }
  if (t.closest("[data-item-play]")) { togglePreview(id); return; }
  const tag = t.closest("[data-tag]");
  if (tag && !tag.disabled) { const key = tag.dataset.tag; saveAsset(id, { tags: a.tags.includes(key) ? a.tags.filter((x) => x !== key) : [...a.tags, key] }); return; }
  const del = t.closest("[data-tag-del]");
  if (del) { saveAsset(id, { tags: a.tags.filter((x) => x !== del.dataset.tagDel) }); return; }
  if (t.closest("[data-item-delete]")) { if (await deleteAssets([id])) closePanel(); return; }
  const open = t.closest("[data-open-playlist]");
  if (open) { event.preventDefault(); closePanel(); go(`?playlist=${open.dataset.openPlaylist}`); }
}

async function deleteAssets(ids) {
  const list = ids.map(asset).filter(Boolean);
  if (!list.length) return false;
  const title = list.length === 1 ? list[0].title : `${list.length} files`;
  const ok = await confirmDialog({ title: `Delete ${title}?`, body: `${usedPhrase(list)} Deleting is final.`.trim(), ok: "Delete", danger: true });
  if (!ok) return false;
  let done = 0;
  for (const a of list) {
    try {
      const res = await postJSON(`/library/assets/${a.id}/delete/`);
      if (res.library) L.summary = res.library;
      if (playing === a.id) stopPreview();
      lib.sel.delete(a.id);
      dropAsset(a.id);
      done += 1;
    } catch (e) { toast(e.message); break; }
  }
  if (done) toast(done === 1 ? `${title} deleted.` : `${done} files deleted.`);
  renderRoute();
  S.render();
  return done > 0;
}

/* ---------- selection actions ---------- */

async function selectionAction(name) {
  const ids = [...lib.sel];
  const list = ids.map(asset).filter(Boolean);
  if (name === "clear") { lib.sel.clear(); renderRoute(); return; }
  if (name === "delete") { await deleteAssets(ids); return; }
  if (name === "tag") {
    const tag = await formDialog((form, close) => {
      form.innerHTML = `<h2 id="ctl-dialog-h">Tag ${plural(list.length, "file")}</h2><p class="ctl-field"><label for="bulk-tag">Add a tag</label><input id="bulk-tag" type="text" maxlength="30" autocomplete="off" data-bulk-tag></p>
        <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button><button type="button" class="ctl-btn ctl-btn-primary" data-bulk-go>Add tag</button></div>`;
      $("[data-bulk-tag]", form).focus();
      form.onclick = (e) => { if (e.target instanceof Element && e.target.closest("[data-bulk-go]")) close($("[data-bulk-tag]", form).value.trim().toLowerCase()); };
    });
    if (!tag) return;
    let n = 0;
    for (const a of list) { if (!a.tags.includes(tag)) { try { replaceAsset(await postJSON(`/library/assets/${a.id}/update/`, { tags: [...a.tags, tag] })); n += 1; } catch (e) { toast(e.message); break; } } }
    refreshUsedIn();
    renderRoute();
    toast(`Tagged ${plural(n, "file")}.`);
    return;
  }
  if (name === "playlist") {
    const kinds = new Set(list.map((a) => (a.kind === "audio" ? "music" : "screens")));
    if (kinds.size !== 1) { toast("Pick music or screen files, not both."); return; }
    const kind = [...kinds][0];
    const lists = L.playlists.filter((p) => p.kind === kind);
    const pick = await chooseOne("Add to playlist", [...lists.map((p) => ({ value: p.id, label: p.name, sub: plural(p.items.length, "item") })), { value: "__new__", label: "New playlist" }]);
    if (!pick) return;
    let target = playlist(pick);
    if (pick === "__new__") target = await createPlaylist(kind);
    if (!target) return;
    try {
      let latest = target;
      for (const a of list) latest = await postJSON(`/library/playlists/${target.id}/items/add/`, { asset_id: a.id });
      replacePlaylist(latest);
      lib.sel.clear();
      renderRoute();
      toast(`Added ${plural(list.length, "file")} to ${target.name}.`);
    } catch (e) { toast(e.message); }
  }
}

/* ---------- playlist actions ---------- */

async function playlistAction(event, t) {
  const box = $("[data-playlist]", root);
  const p = box && playlist(box.dataset.playlist);
  if (!p) return false;
  if (t.closest("[data-pl-add]")) { await addItemsDialog(p); return true; }
  const remove = t.closest("[data-pl-remove]");
  if (remove) {
    try { replacePlaylist(await postJSON(`/library/playlists/${p.id}/items/remove/`, { item_id: Number(remove.dataset.plRemove) })); renderRoute(); }
    catch (e) { toast(e.message); }
    return true;
  }
  const secs = t.closest("[data-secs]");
  if (secs) {
    const item = p.items.find((i) => i.id === Number(secs.dataset.itemId));
    const next = Math.min(60, Math.max(4, (item.seconds || 8) + Number(secs.dataset.secs)));
    if (next === (item.seconds || 8)) return true;
    item.seconds = next;
    renderRoute();
    try { replacePlaylist(await postJSON(`/library/playlists/${p.id}/items/seconds/`, { item_id: item.id, seconds: next })); } catch (e) { toast(e.message); }
    const again = $(`[data-secs][data-item-id="${item.id}"][data-secs="${secs.dataset.secs}"]`, root);
    if (again) again.focus({ preventScroll: true });
    return true;
  }
  if (t.closest("[data-pl-play]")) {
    if (p.kind === "music") {
      const zones = S.st.music.zones;
      const zone = await chooseOne("Play in a zone", zones.map((z) => ({ value: z.id, label: z.name })));
      if (zone && playLibraryList(zone, p)) toast(`Playing ${p.name} in ${zoneById(zone).name}.`);
    } else {
      const screen = await chooseOne("Show on a screen", S.st.screens.map((s) => ({ value: s.id, label: s.name })));
      if (screen && showOnScreen(screen, { t: "playlist", id: p.id })) toast(`${p.name} is showing on ${screenOf(screen).name}.`);
    }
    return true;
  }
  if (t.closest("[data-pl-delete]")) {
    const ok = await confirmDialog({ title: `Delete ${p.name}?`, body: "The files stay in the Library.", ok: "Delete playlist", danger: true });
    if (!ok) return true;
    try { await postJSON(`/library/playlists/${p.id}/delete/`); dropPlaylist(p.id); toast("Playlist deleted."); go("?tab=playlists"); }
    catch (e) { toast(e.message); }
    return true;
  }
  const editBtn = t.closest("[data-edit='plname'] [data-edit-btn]");
  if (editBtn) {
    const holder = editBtn.closest("[data-edit]");
    holder.innerHTML = `<input type="text" maxlength="120" value="${esc(p.name)}" aria-label="Playlist name">`;
    const input = $("input", holder);
    input.focus(); input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return; done = true;
      const name = input.value.trim();
      if (save && name && name !== p.name) { try { replacePlaylist(await postJSON(`/library/playlists/${p.id}/update/`, { name })); } catch (e) { toast(e.message); } }
      renderRoute();
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); finish(true); } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); } });
    input.addEventListener("blur", () => finish(true));
    return true;
  }
  return false;
}

/* ---------- events (delegated; the page is swapped, the listeners stay) ---------- */

async function onClick(event) {
  const t = event.target instanceof Element ? event.target : null;
  if (!t || !root || !root.isConnected) return;
  if (t.closest("[data-lib-upload], [data-lib-choose]")) { const input = $("[data-lib-input]", root); if (input) input.click(); return; }
  const kind = t.closest("[data-lib-kind]");
  if (kind) { const k = kind.dataset.libKind; if (lib.kinds.has(k)) lib.kinds.delete(k); else lib.kinds.add(k); kind.setAttribute("aria-pressed", String(lib.kinds.has(k))); renderFiles(); return; }
  if (t.closest("[data-lib-clear]")) { lib.tag = "all"; lib.kinds.clear(); lib.q = ""; rebuildShell(); renderRoute(); return; }
  if (t.closest("[data-lib-retry]")) { loadLibrary(true).then(renderRoute); return; }
  const aplay = t.closest("[data-aplay]");
  if (aplay) { event.preventDefault(); togglePreview(aplay.dataset.aplay); return; }
  const openItemEl = t.closest("[data-open-item]");
  if (openItemEl && !event.metaKey && !event.ctrlKey && !event.shiftKey) { event.preventDefault(); openItem(openItemEl.dataset.openItem); return; }
  const openPl = t.closest("[data-open-playlist]");
  if (openPl && openPl.closest("[data-library]") && !event.metaKey && !event.ctrlKey) { event.preventDefault(); go(`?playlist=${openPl.dataset.openPlaylist}`); return; }
  if (t.closest("[data-lib-back]")) { event.preventDefault(); go("?tab=playlists"); return; }
  const sel = t.closest("[data-sel-act]");
  if (sel) { selectionAction(sel.dataset.selAct); return; }
  if (t.closest("[data-pl-new]")) {
    const made = await createPlaylist();
    if (made) go(`?playlist=${made.id}`);
    return;
  }
  if (t.closest("[data-playlist]") || t.closest("[data-pl-add]")) { if (await playlistAction(event, t)) return; }
}

function onChange(event) {
  const n = event.target;
  if (!(n instanceof HTMLInputElement) || !root || !root.isConnected) return;
  if (n.matches("[data-sel]")) { setSel(n.dataset.sel, n.checked); return; }
  if (n.matches("[data-lib-sub]")) { go(n.value === "playlists" ? "?tab=playlists" : "", false); return; }
  if (n.matches("[data-lib-tag]")) { lib.tag = n.value; renderFiles(); return; }
  if (n.matches("[data-lib-view]")) { lib.view = n.value; localStorage.setItem(VIEW_KEY, n.value); renderFiles(); }
  if (n.matches("[data-lib-input]")) { addFiles(n.files); n.value = ""; }
}

function onInput(event) {
  const n = event.target;
  if (n instanceof HTMLInputElement && n.matches("[data-lib-q]")) { lib.q = n.value; renderFiles(); }
}

/** Hover a video tile: it plays muted from the start (fine pointers only, never with reduced motion). */
function onHover(event, on) {
  if (!FINE.matches || MOTION.matches) return;
  const thumb = event.target instanceof Element ? event.target.closest(".ctl-ftile.is-video .ctl-fthumb") : null;
  if (!thumb) return;
  if (!on) {
    if (event.relatedTarget instanceof Node && thumb.contains(event.relatedTarget)) return;
    const v = $("video", thumb);
    if (v) v.remove();
    return;
  }
  if ($("video", thumb)) return;
  const a = asset(thumb.closest("[data-asset]").dataset.asset);
  if (!a) return;
  const video = document.createElement("video");
  video.muted = true; video.loop = true; video.playsInline = true; video.src = a.url;
  video.className = "ctl-hovervideo";
  thumb.prepend(video);
  video.play().catch(() => video.remove());
}

/* ---------- drag and drop: only on this page ---------- */

let dragDepth = 0;
const hasFiles = (e) => e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files");

function initDrop() {
  const overlay = () => $("[data-drop]");
  const onLibrary = () => Boolean(root && root.isConnected);
  document.addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    if (!onLibrary()) return;
    dragDepth += 1;
    const o = overlay();
    if (o) o.hidden = false;
  });
  document.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  document.addEventListener("dragleave", (e) => {
    if (!hasFiles(e) || !onLibrary()) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) { const o = overlay(); if (o) o.hidden = true; }
  });
  document.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();  // dropping a file anywhere in Control never opens it or uploads it by surprise
    dragDepth = 0;
    const o = overlay();
    if (o) o.hidden = true;
    if (onLibrary()) addFiles(e.dataTransfer.files);
  });
}

/* ---------- mount ---------- */

export function mountLibrary() {
  root = $("[data-library]");
  if (!root) return;
  limits.audio = Number(root.dataset.limitAudio) || limits.audio;
  limits.video = Number(root.dataset.limitVideo) || limits.video;
  limits.image = Number(root.dataset.limitImage) || limits.image;
  const upload = $("[data-lib-upload]");
  if (upload) upload.hidden = false;
  document.documentElement.classList.add("lib-js");
  lib.sel.clear();
  rebuildShell();
  renderRoute();
  loadLibrary(true).then(() => { syncLibraryUrl(); renderMeter(); });
}

export function unmountLibrary() {
  stopPreview();
  root = null;
  document.body.classList.remove("has-selbar");
  document.documentElement.classList.remove("lib-js");
}

export function initLibrary() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("input", onInput);
  document.addEventListener("mouseover", (e) => onHover(e, true));
  document.addEventListener("mouseout", (e) => onHover(e, false));
  initDrop();
  bus.on("library-changed", (d) => {
    if (d && d.added) lib.fresh.add(d.added.id);
    refreshUsedIn();
    renderRoute();
  });
}
