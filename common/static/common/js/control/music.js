/* Music: zones, players, queue, the source picker (Library or Spotify demo), the mini player, "Listen here".
   Playback into the rooms is pretend (this browser only). The files are real: Library tracks play for real when you press
   "Listen here". The queue rules live in music-model.js. */
import { $, $$, S, esc, icon, toast, announce, bus, fmtDur, fmtTotal, spoken, plural, clamp, formDialog, confirmDialog, MOTION, FIELDS } from "./core.js";
import { save, normalizeZones } from "./state.js";
import { L, asset, loadLibrary } from "./libdata.js";
import { openPanel, closePanel, panelKey } from "./panel.js";
import { sortable } from "./sortable.js";
import * as Q from "./music-model.js";

const M = () => S.st.music;
export const zoneById = (id) => M().zones.find((z) => z.id === id) || null;
const selZone = () => zoneById(M().group || M().sel) || M().zones[0] || null;
const viewZone = () => zoneById(M().group || M().sel);
const roomName = (slug) => (S.st.rooms.find((r) => r.slug === slug) || { name: slug }).name;
const src = { tab: "library", q: "" };
let audio = null;
let lastSig = "";
let miniSig = "";
let playingSig = "";
let lastTrackUid = "";
let ticker = null;
let lastSave = 0;

/* ---------- tracks ---------- */

const libTrack = (a, plName = "") => ({ id: `lib:${a.id}`, kind: "lib", assetId: a.id, title: a.title, artist: a.artist || "", dur: a.duration_seconds || 180, plName });
const spotTracks = (pl) => pl.tracks.map((t, n) => ({ id: `sp:${pl.id}:${n}`, kind: "spot", plId: pl.id, plName: pl.name, field: pl.field, ...t }));
const spotPl = (id) => S.st.spotify.find((p) => p.id === id);
const musicAssets = () => L.assets.filter((a) => a.kind === "audio");
const musicLists = () => L.playlists.filter((p) => p.kind === "music");
const listTracks = (p) => p.items.map((i) => libTrack(i.asset, p.name));

/* ---------- artwork ---------- */

function wavePath(peaks, bars = 48, h = 20) {
  if (!peaks || !peaks.length) return "";
  const per = peaks.length / bars;
  let d = "";
  for (let n = 0; n < bars; n += 1) {
    let m = 0;
    for (let k = Math.floor(n * per); k < Math.floor((n + 1) * per) && k < peaks.length; k += 1) m = Math.max(m, peaks[k]);
    const half = Math.max(0.6, m * h);
    d += `M${n * 2 + 1} ${(h - half).toFixed(1)}V${(h + half).toFixed(1)}`;
  }
  return d;
}

export function waveSvg(peaks, cls = "ctl-wave", bars = 48) {
  const d = wavePath(peaks, bars);
  return d ? `<svg class="${cls}" viewBox="0 0 ${bars * 2} 40" preserveAspectRatio="none" aria-hidden="true"><path d="${d}"/></svg>` : "";
}

/** Artwork for a track: typographic tile for Spotify samples, the swan with the waveform for Library music. */
export function artHtml(track, size = "") {
  if (!track) return `<span class="ctl-cover is-empty ${size}"></span>`;
  if (track.kind === "spot") return `<span class="ctl-cover f${track.field % FIELDS} ${size}"><span>${esc(track.plName)}</span></span>`;
  const a = track.assetId ? asset(track.assetId) : null;
  return `<span class="ctl-art-default ${size}"><img src="${esc(document.body.dataset.swan)}" alt="" draggable="false">${a ? waveSvg(a.peaks, "ctl-wave") : ""}</span>`;
}

const playlistCover = (cover) => `<span class="ctl-cover f${cover.field % FIELDS}"><span>${esc(cover.name)}</span></span>`;

/* ---------- what the rest of Control asks of music ---------- */

export function zoneOfRoom(slug) { return M().zones.find((z) => z.rooms.includes(slug)) || null; }

S.roomMusic = (room) => {
  const z = zoneOfRoom(room.slug);
  if (!z) return { text: "", zone: "" };
  const lead = M().group ? zoneById(M().group) : z;
  const cur = Q.current(lead);
  return { zone: z.id, text: `${z.name}, ${cur && lead.src ? lead.src.name || cur.title : "off"}` };
};

S.captureMusic = () => ({ zones: M().zones.map((z) => ({ id: z.id, vol: z.vol, playing: z.playing, muted: z.muted })) });
S.restoreMusic = (before) => {
  for (const b of before.zones) { const z = zoneById(b.id); if (z) { z.vol = b.vol; z.playing = b.playing; z.muted = b.muted; } }
  touchAll();
};
S.sceneMusic = (music) => {
  for (const z of M().zones) {
    if (music.on === false) z.playing = false;
    else if (music.vol !== undefined) z.vol = music.vol;
  }
  touchAll();
};

function touchAll() { syncGroup(); save(); S.render(); }

function syncGroup() {
  const g = M().group;
  if (!g) return;
  const lead = zoneById(g);
  if (!lead) { M().group = null; return; }
  for (const z of M().zones) {
    if (z === lead) continue;
    z.queue = lead.queue.map((e) => ({ ...e }));
    Object.assign(z, { i: lead.i, pos: lead.pos, playing: lead.playing, shuffle: lead.shuffle, repeat: lead.repeat, vol: lead.vol, muted: lead.muted, src: lead.src, orig: [...(lead.orig || [])] });
  }
}

function touch(zone) {
  M().last = zone.id;
  syncGroup();
  save();
  S.render();
}

/* ---------- Listen here: the real file, in this browser ---------- */

function theAudio() {
  if (!audio) { audio = new Audio(); audio.preload = "auto"; }
  return audio;
}

function syncAudio() {
  const z = M().zones.find((x) => x.listen);
  const a = theAudio();
  if (!z) { if (!a.paused) a.pause(); return; }
  const cur = Q.current(z);
  if (!cur || cur.kind !== "lib" || !z.playing) { if (!a.paused) a.pause(); return; }
  const file = asset(cur.assetId);
  if (!file) { if (!a.paused) a.pause(); return; }
  if (a.dataset.uid !== cur.uid) { a.dataset.uid = cur.uid; a.src = file.url; a.currentTime = 0; try { a.currentTime = z.pos; } catch (e) { /* not ready yet */ } }
  a.volume = z.muted ? 0 : clamp(z.vol / 100, 0, 1);
  if (a.readyState > 0 && Math.abs(a.currentTime - z.pos) > 1.5) a.currentTime = z.pos;
  if (a.paused) { const p = a.play(); if (p && p.catch) p.catch(() => { z.listen = false; toast("Press play to listen here."); S.render(); }); }
}

function setListen(zone, on) {
  for (const z of M().zones) z.listen = false;
  if (on) zone.listen = true;
  syncAudio();
  S.render();
  announce(on ? `Listening to ${zone.name} here.` : "Stopped listening here.");
}

/* ---------- transport actions ---------- */

function act(zone, name, value) {
  const lead = zone;
  if (name === "play") { if (Q.current(lead)) lead.playing = !lead.playing; }
  else if (name === "next") { if (Q.stepNext(lead, false)) lead.playing = true; }
  else if (name === "prev") Q.stepPrev(lead);
  else if (name === "shuffle") Q.setShuffle(lead, !lead.shuffle);
  else if (name === "repeat") lead.repeat = { off: "all", all: "one", one: "off" }[lead.repeat];
  else if (name === "mute") lead.muted = !lead.muted;
  else if (name === "vol") { lead.vol = value; if (value > 0) lead.muted = false; }
  else if (name === "seek") { Q.setPos(lead, value); }
  touch(lead);
  syncAudio();
}

function playTracks(zone, tracks, label, name, start = 0) {
  Q.playNow(zone, tracks, start);
  zone.src = { kind: tracks[0] && tracks[0].kind === "spot" ? "spotify" : "library", label, name };
  touch(zone);
  syncAudio();
  const cur = Q.current(zone);
  if (cur) announce(`Now playing ${cur.title} in ${zone.name} zone.`);
}

function addTracks(zone, tracks) {
  const first = zone.i < 0;
  Q.enqueue(zone, tracks);
  if (first) zone.src = { kind: tracks[0].kind === "spot" ? "spotify" : "library", label: tracks[0].kind === "spot" ? `Spotify, ${tracks[0].plName}` : "Library", name: tracks[0].plName || tracks[0].title };
  touch(zone);
  syncAudio();
  toast(`Added to ${zone.name} queue`);
}

/* ---------- the ticker: real time, silent unless Listen here ---------- */

function tickMusic(dt) {
  const lead = M().group ? zoneById(M().group) : null;
  let changedTrack = false;
  for (const z of M().zones) {
    if (lead && z !== lead) continue;
    if (!z.playing) continue;
    const ev = Q.advance(z, dt);
    if (ev) changedTrack = true;
  }
  if (lead) syncGroup();
  syncAudio();
  const z = viewZone() || selZone();
  const cur = z && Q.current(z);
  if (changedTrack) {
    if (cur && cur.uid !== lastTrackUid && z.playing) announce(`Now playing ${cur.title} in ${z.name} zone.`);
    S.render();
  } else updateProgress();
  if (cur) lastTrackUid = cur.uid;
  if (Date.now() - lastSave > 5000) { lastSave = Date.now(); save(); }
}

export function runMusic() {
  if (ticker) return;
  let last = performance.now();
  ticker = setInterval(() => {
    const now = performance.now();
    const dt = Math.min(3600, (now - last) / 1000);
    last = now;
    if (M().zones.some((z) => z.playing)) tickMusic(dt);
  }, 250);
}

/* ---------- Music page ---------- */

const stateWord = (z) => (!Q.current(z) ? "Off" : z.muted ? "Muted" : z.playing ? "Playing" : "Paused");

function zoneRowHtml(z, selected, label) {
  const cur = Q.current(z);
  return `<li><a class="ctl-zone${selected ? " is-selected" : ""}" href="?zone=${esc(z.id)}" data-zone="${esc(z.id)}"${selected ? ' aria-current="true"' : ""}>
    <span class="ctl-art-sm">${artHtml(cur)}</span><span class="ctl-zone-name">${esc(label || z.name)}</span><span class="ctl-zone-state">${stateWord(z)}</span></a></li>`;
}

function zonesSig() {
  return M().zones.map((z) => `${z.id}:${Q.current(z) ? Q.current(z).uid : ""}:${stateWord(z)}`).join("|") + `|${M().group}|${M().sel}`;
}

function renderZoneList() {
  const list = $("[data-zone-list]");
  if (!list) return;
  const grouped = M().group;
  list.innerHTML = grouped ? zoneRowHtml(zoneById(grouped), true, "All rooms") : M().zones.map((z) => zoneRowHtml(z, z.id === M().sel)).join("");
  const g = $('[data-music-act="group"]');
  if (g) { g.hidden = false; g.textContent = grouped ? "Ungroup" : "Group all"; }
  const mute = $('[data-music-act="mute-all"]');
  if (mute) mute.hidden = false;
}

function playerSig(z) {
  const cur = Q.current(z);
  return [z.id, cur ? cur.uid : "", z.queue.map((e) => e.uid).join(","), z.playing, z.shuffle, z.repeat, z.muted, z.listen, z.src ? z.src.label : "", M().group, L.loaded, z.rooms.join(",")].join("|");
}

function sourceLine(z, cur) {
  if (!cur || !z.src) return "";
  const demo = z.src.kind === "spotify" ? ' <span class="ctl-chip-demo" title="Demo: nothing is sent to real equipment.">DEMO<span class="ctl-sr">. Demo: nothing is sent to real equipment.</span></span>' : "";
  return `${esc(z.src.label)}${demo}`;
}

function roomsText(z) {
  const names = z.rooms.map(roomName);
  return names.length > 2 ? `${names[0]}, ${names[1]}, +${names.length - 2}` : names.join(", ");
}

function queueHtml(z) {
  const up = Q.upcoming(z);
  if (!up.length) return `<div class="ctl-queue-empty"><p class="ctl-soft">Nothing up next. Music stops after this track.</p></div>`;
  return `<ol class="ctl-queue-list" data-queue>${up.map((e, n) => `<li data-q="${n}">
    <button type="button" class="ctl-handle" data-handle aria-label="Move ${esc(e.title)}. Up and Down arrows reorder">${icon("dots-six-vertical")}</button>
    <button type="button" class="ctl-qplay" data-qplay="${n}" aria-label="Play ${esc(e.title)} now"><span class="ctl-art-sm">${artHtml(e)}</span><span class="ctl-qtext"><span class="ctl-qtitle">${esc(e.title)}</span><span class="ctl-soft">${esc(e.artist)}</span></span><span class="ctl-qdur">${fmtDur(e.dur)}</span></button>
    <button type="button" class="ctl-iconbtn" data-qremove="${n}" aria-label="Remove ${esc(e.title)} from the queue">${icon("x-r")}</button></li>`).join("")}</ol>`;
}

function playerHtml(z) {
  const cur = Q.current(z);
  const name = M().group ? "All rooms" : `${z.name} zone`;
  if (!cur) {
    return `<div class="ctl-pl" data-pl="${esc(z.id)}"><header class="ctl-pl-head"><div><p class="ctl-kicker">Playing in <span class="ctl-chip-demo" title="Demo: nothing is sent to real equipment.">DEMO<span class="ctl-sr">. Demo: nothing is sent to real equipment.</span></span></p><h2>${esc(name)}</h2></div><p class="ctl-soft">${esc(roomsText(z))} <button type="button" class="ctl-link" data-music-act="edit-rooms">Edit rooms</button></p></header>
      <div class="ctl-empty"><span class="ctl-empty-icon">${icon("music-notes")}</span><p class="ctl-empty-1">Nothing playing in the ${esc(M().group ? "building" : z.name)}.</p><p class="ctl-empty-2">Pick a playlist or a track.</p><button type="button" class="ctl-btn ctl-btn-primary" data-music-act="source">Choose music</button></div></div>`;
  }
  const spotify = cur.kind === "spot";
  const repeatWord = { off: "Repeat off", all: "Repeat all", one: "Repeat one" }[z.repeat];
  return `<div class="ctl-pl" data-pl="${esc(z.id)}">
    <header class="ctl-pl-head"><div><p class="ctl-kicker">Playing in <span class="ctl-chip-demo" title="Demo: nothing is sent to real equipment.">DEMO<span class="ctl-sr">. Demo: nothing is sent to real equipment.</span></span></p><h2>${esc(name)}</h2></div>
      <p class="ctl-soft">${esc(roomsText(z))} <button type="button" class="ctl-link" data-music-act="edit-rooms" data-mp="edit">Edit rooms</button></p></header>
    <div class="ctl-pl-main${MOTION.matches ? "" : " is-fresh"}">
      <div class="ctl-pl-art">${artHtml(cur, "is-lg")}</div>
      <div class="ctl-pl-info">
        <h3 class="ctl-pl-title">${esc(cur.title)}</h3>
        <p class="ctl-pl-artist">${esc(cur.artist) || "&nbsp;"}</p>
        <p class="ctl-pl-src">${sourceLine(z, cur)}</p>
        <div class="ctl-scrub"><span class="ctl-time" data-elapsed>0:00</span><span class="ctl-range is-scrub" style="--v:0"><input type="range" data-scrub min="0" max="${Math.round(cur.dur)}" step="1" value="0" aria-label="Position in ${esc(cur.title)}"></span><span class="ctl-time" data-total>${fmtDur(cur.dur)}</span></div>
        <div class="ctl-transport" role="group" aria-label="Playback">
          <button type="button" class="ctl-iconbtn ctl-toggle-icon" data-pact="shuffle" data-mp="shuffle" aria-pressed="${z.shuffle}" aria-label="Shuffle">${icon("shuffle")}</button>
          <button type="button" class="ctl-iconbtn is-lgbtn" data-pact="prev" data-mp="prev" aria-label="Previous track">${icon("skip-back")}</button>
          <button type="button" class="ctl-play" data-pact="play" data-mp="play" aria-label="${z.playing ? "Pause" : "Play"} ${esc(name)}">${icon(z.playing ? "pause" : "play")}</button>
          <button type="button" class="ctl-iconbtn is-lgbtn" data-pact="next" data-mp="next" aria-label="Next track">${icon("skip-forward")}</button>
          <button type="button" class="ctl-iconbtn ctl-toggle-icon" data-pact="repeat" data-mp="repeat" aria-pressed="${z.repeat !== "off"}" aria-label="${repeatWord}">${icon(z.repeat === "one" ? "repeat-once" : "repeat")}</button></div>
        <div class="ctl-volume"><button type="button" class="ctl-iconbtn" data-pact="mute" data-mp="mute" aria-pressed="${z.muted}" aria-label="${z.muted ? "Unmute" : "Mute"} ${esc(name)}">${icon(z.muted ? "speaker-x" : "speaker-high-r")}</button>
          <span class="ctl-range is-compact" style="--v:${z.vol / 100}"><input type="range" data-vol min="0" max="100" value="${z.vol}" aria-label="Volume, ${esc(name)}" aria-valuetext="${z.vol} percent"></span><span class="ctl-val" data-vol-text>${z.vol}</span></div>
        <div class="ctl-pl-actions">
          <button type="button" class="ctl-btn" data-pact="listen" data-mp="listen" aria-pressed="${z.listen}"${spotify ? " disabled" : ""}>${icon("headphones")}<span>Listen here</span></button>
          <button type="button" class="ctl-btn" data-music-act="source" data-mp="source">Change music</button></div>
        ${spotify ? '<p class="ctl-soft ctl-hint">Spotify plays on the spa speakers only.</p>' : ""}
      </div>
    </div>
    <section class="ctl-queue" aria-labelledby="up-next"><header><h3 id="up-next">Up next</h3>${Q.upcoming(z).length ? '<button type="button" class="ctl-link" data-music-act="clear">Clear</button>' : ""}</header>${queueHtml(z)}</section></div>`;
}

function renderPlayer(force = false) {
  const host = $("[data-player]");
  if (!host) return;
  const z = viewZone() || selZone();
  if (!z) return;
  const sig = playerSig(z);
  if (!force && sig === lastSig && $("[data-pl]", host)) { updateProgress(); return; }
  if (host.dataset.busy === "1") return;
  const focus = document.activeElement && host.contains(document.activeElement) ? document.activeElement.dataset.mp : null;
  lastSig = sig;
  host.innerHTML = playerHtml(z);
  const q = $("[data-queue]", host);
  if (q) sortable(q, { handleSel: "[data-handle]", itemSel: ":scope > li", describe: (to) => `${Q.upcoming(z)[to] ? Q.upcoming(z)[to].title : "Track"} moved to position ${to + 1}`,
    onMove: (from, to) => { if (Q.moveUpcoming(z, from, to)) { touch(z); } } });
  if (focus) { const el = $(`[data-mp="${focus}"]`, host); if (el) el.focus({ preventScroll: true }); }
  updateProgress();
}

function updateProgress() {
  const host = $("[data-player]");
  if (!host) return;
  const z = viewZone() || selZone();
  const cur = z && Q.current(z);
  if (!cur) return;
  const scrub = $("[data-scrub]", host);
  if (!scrub || scrub.dataset.drag === "1") return;
  const pos = Math.min(cur.dur, z.pos);
  if (Number(scrub.value) !== Math.round(pos)) scrub.value = Math.round(pos);
  scrub.parentElement.style.setProperty("--v", String(cur.dur ? clamp(pos / cur.dur, 0, 1) : 0));
  scrub.setAttribute("aria-valuetext", `${spoken(pos)} of ${spoken(cur.dur)}`);
  const el = $("[data-elapsed]", host);
  const text = fmtDur(pos);
  if (el && el.textContent !== text) el.textContent = text;
}

/* ---------- mini player and the Overview "Playing" rows ---------- */

function miniZone() {
  const last = zoneById(M().last);
  if (last && Q.current(last)) return last;
  return M().zones.find((z) => z.playing) || null;
}

export function renderMini() {
  const box = $("[data-mini]");
  if (!box) return;
  const onMusic = document.body.dataset.page === "music";
  const anyPlaying = M().zones.some((z) => z.playing);
  const z = miniZone();
  const cur = z && Q.current(z);
  const show = Boolean(z && cur && anyPlaying && !onMusic);
  box.hidden = !show;
  document.body.classList.toggle("has-mini", show);
  if (!show) { miniSig = ""; return; }
  const sig = `${z.id}|${cur.uid}|${z.playing}`;
  if (sig === miniSig) return;
  miniSig = sig;
  box.innerHTML = `<a class="ctl-mini-open" href="/music/?zone=${esc(z.id)}" data-zone-row="${esc(z.id)}"><span class="ctl-art-sm">${artHtml(cur)}</span>
    <span class="ctl-mini-text"><span class="ctl-mini-zone">${esc(M().group ? "All rooms" : z.name)}</span><span class="ctl-mini-title">${esc(cur.title)}</span></span></a>
    <button type="button" class="ctl-iconbtn" data-mini-act="play" aria-label="${z.playing ? "Pause" : "Play"} ${esc(z.name)} zone">${icon(z.playing ? "pause" : "play")}</button>
    <button type="button" class="ctl-iconbtn" data-mini-act="next" aria-label="Next track">${icon("skip-forward")}</button>`;
}

export function renderPlayingRows() {
  const list = $("[data-playing]");
  if (!list) return;
  const sig = M().zones.map((z) => `${z.id}:${Q.current(z) ? Q.current(z).uid : ""}:${z.playing}`).join("|");
  if (sig === playingSig && list.dataset.js === "1") return;
  playingSig = sig;
  list.dataset.js = "1";
  list.innerHTML = M().zones.map((z) => {
    const cur = Q.current(z);
    return `<li class="ctl-prow-wrap"><a class="ctl-prow" href="/music/?zone=${esc(z.id)}" data-zone-row="${esc(z.id)}"><span class="ctl-prow-zone">${esc(z.name)}</span><span class="ctl-prow-track">${cur ? esc(cur.title) : '<span class="ctl-soft">Off</span>'}</span></a>
      ${cur ? `<button type="button" class="ctl-iconbtn" data-zone-play="${esc(z.id)}" aria-label="${z.playing ? "Pause" : "Play"} ${esc(z.name)} zone">${icon(z.playing ? "pause" : "play")}</button>` : ""}</li>`;
  }).join("");
}

export function renderMusic() {
  renderMini();
  renderPlayingRows();
  if ($("[data-music]")) {
    const zs = zonesSig();
    const list = $("[data-zone-list]");
    if (list && (list.dataset.sig !== zs)) { list.dataset.sig = zs; renderZoneList(); }
    renderPlayer();
  }
}

/* ---------- source picker ---------- */

function coverFor(p) {
  const first = p.items[0] && p.items[0].asset;
  return { name: p.name, field: (p.name.length + (first ? first.title.length : 0)) % FIELDS };
}

function sourceHtml(zone) {
  const seg = `<div class="ctl-seg" role="radiogroup" aria-label="Source">${[["library", "Library"], ["spotify", "Spotify"]].map(([k, label]) =>
    `<label><input type="radio" name="src-tab" data-src-tab value="${k}"${src.tab === k ? " checked" : ""}><span>${label}</span></label>`).join("")}</div>`;
  let body = "";
  if (src.tab === "library") {
    if (!L.loaded) body = `<p class="ctl-soft">${L.error ? esc(L.error) : "Loading the Library."}</p>`;
    else {
      const lists = musicLists();
      const all = musicAssets().filter((a) => !src.q || `${a.title} ${a.artist}`.toLowerCase().includes(src.q.toLowerCase()));
      if (!musicAssets().length) body = `<div class="ctl-empty ctl-empty-sm"><p class="ctl-empty-1">No music in the Library yet.</p><a class="ctl-btn" href="/library/">Go to Library</a></div>`;
      else body = `${lists.length ? `<h3>Playlists</h3><ul class="ctl-tiles">${lists.map((p) => `<li class="ctl-ptile"><button type="button" class="ctl-ptile-play" data-play-list="${esc(p.id)}" aria-label="Play ${esc(p.name)} now">${playlistCover(coverFor(p))}</button>
        <span class="ctl-ptile-name">${esc(p.name)}</span><span class="ctl-soft">${plural(p.items.length, "track")}, ${fmtTotal(p.items.reduce((n, i) => n + (i.asset.duration_seconds || 0), 0))}</span>
        <button type="button" class="ctl-iconbtn ctl-ptile-add" data-add-list="${esc(p.id)}" aria-label="Add ${esc(p.name)} to the queue">${icon("plus")}</button></li>`).join("")}</ul>` : ""}
        <h3>All music</h3><p class="ctl-field ctl-search"><label class="ctl-sr" for="src-q">Search music</label><input id="src-q" type="text" data-src-q value="${esc(src.q)}" placeholder="Search" autocomplete="off"></p>
        ${all.length ? `<ul class="ctl-rows">${all.map((a) => `<li class="ctl-arow"><button type="button" class="ctl-arow-play" data-play-asset="${esc(a.id)}" aria-label="Play ${esc(a.title)} now"><span class="ctl-art-sm">${artHtml(libTrack(a))}</span><span class="ctl-qtext"><span class="ctl-qtitle">${esc(a.title)}</span><span class="ctl-soft">${esc(a.artist)}</span></span><span class="ctl-qdur">${fmtDur(a.duration_seconds || 0)}</span></button>
          <button type="button" class="ctl-iconbtn" data-add-asset="${esc(a.id)}" aria-label="Add ${esc(a.title)} to the queue">${icon("plus")}</button></li>`).join("")}</ul>` : '<p class="ctl-soft">Nothing matches.</p>'}`;
    }
  } else if (!M().spotify.connected) {
    body = `<div class="ctl-empty ctl-empty-sm"><span class="ctl-empty-icon">${icon("spotify-logo")}</span><p class="ctl-empty-1">Connect Spotify to play your playlists on the spa speakers.</p><button type="button" class="ctl-btn ctl-btn-primary" data-spotify="connect">Connect Spotify</button>
      <p class="ctl-soft">Demo: no Spotify account is used.</p></div>`;
  } else {
    body = `<p class="ctl-spotify-acct"><span>${icon("check")} Connected (demo)</span><span class="ctl-soft">${esc(S.st.spotify_account)}</span><button type="button" class="ctl-link" data-spotify="disconnect">Disconnect</button></p>
      <ul class="ctl-tiles">${S.st.spotify.map((p) => `<li class="ctl-ptile"><button type="button" class="ctl-ptile-play" data-play-spot="${esc(p.id)}" aria-label="Play ${esc(p.name)} now">${playlistCover({ name: p.name, field: p.field })}</button>
        <span class="ctl-ptile-name">${esc(p.name)}</span><span class="ctl-soft">${plural(p.tracks.length, "track")}, ${fmtTotal(p.tracks.reduce((n, t) => n + t.dur, 0))}</span>
        <button type="button" class="ctl-iconbtn ctl-ptile-add" data-add-spot="${esc(p.id)}" aria-label="Add ${esc(p.name)} to the queue">${icon("plus")}</button></li>`).join("")}</ul>`;
  }
  return `<div class="ctl-pn" data-source-panel><div class="ctl-pn-body"><header class="ctl-pn-head"><div><h2 class="ctl-pn-title" id="ctl-panel-title" tabindex="-1">Change music</h2><p class="ctl-soft">${esc(M().group ? "All rooms" : `${zone.name} zone`)}</p></div>
    <button type="button" class="ctl-iconbtn" data-close aria-label="Close">${icon("x-r")}</button></header>${seg}<div class="ctl-src-body">${body}</div></div></div>`;
}

function openSource(zone) {
  const draw = () => {
    const node = $("[data-source-panel]");
    if (!node) return;
    const body = node.parentElement;
    const q = $("[data-src-q]", node);
    const keep = q && document.activeElement === q ? q.selectionStart : null;
    const scroll = $(".ctl-pn-body", node) ? $(".ctl-pn-body", node).scrollTop : 0;
    const fresh = document.createElement("div");
    fresh.innerHTML = sourceHtml(zone);
    node.replaceWith(fresh.firstElementChild);
    const again = $("[data-source-panel]");
    bind(again);
    const pb = $(".ctl-pn-body", again);
    if (pb) pb.scrollTop = scroll;
    if (keep !== null) { const n = $("[data-src-q]", again); if (n) { n.focus(); n.setSelectionRange(keep, keep); } }
    return body;
  };
  const holder = document.createElement("div");
  holder.innerHTML = sourceHtml(zone);
  const node = holder.firstElementChild;
  function bind(root) {
    root.addEventListener("click", (event) => {
      const t = event.target instanceof Element ? event.target : null;
      if (!t) return;
      const id = (name) => { const el = t.closest(`[data-${name}]`); return el ? el.getAttribute(`data-${name}`) : null; };
      let v;
      if ((v = id("play-list")) !== null) { const p = L.playlists.find((x) => x.id === v); if (p && p.items.length) { playTracks(zone, listTracks(p), `Library, ${p.name}`, p.name); closePanel(); } return; }
      if ((v = id("add-list")) !== null) { const p = L.playlists.find((x) => x.id === v); if (p) addTracks(zone, listTracks(p)); return; }
      if ((v = id("play-asset")) !== null) { const a = asset(v); if (a) { playTracks(zone, [libTrack(a)], "Library", a.title); closePanel(); } return; }
      if ((v = id("add-asset")) !== null) { const a = asset(v); if (a) addTracks(zone, [libTrack(a)]); return; }
      if ((v = id("play-spot")) !== null) { const p = spotPl(v); if (p) { playTracks(zone, spotTracks(p), `Spotify, ${p.name}`, p.name); closePanel(); } return; }
      if ((v = id("add-spot")) !== null) { const p = spotPl(v); if (p) addTracks(zone, spotTracks(p)); return; }
      if ((v = id("spotify")) !== null) { if (v === "connect") connectSpotify().then(draw); else disconnectSpotify().then(draw); }
    });
    root.addEventListener("change", (event) => {
      const n = event.target;
      if (n instanceof HTMLInputElement && n.matches("[data-src-tab]")) { src.tab = n.value; draw(); const r = $(`[data-src-tab][value="${n.value}"]`); if (r) r.focus(); }
    });
    root.addEventListener("input", (event) => {
      const n = event.target;
      if (n instanceof HTMLInputElement && n.matches("[data-src-q]")) { src.q = n.value; draw(); }
    });
  }
  bind(node);
  openPanel({ key: "source", node, size: "full" });
  loadLibrary().then(() => { if (panelKey() === "source") draw(); });
}

/* ---------- Spotify (demo): a hand-off, not a fake Spotify page ---------- */

function connectSpotify() {
  return formDialog((form, close) => {
    form.innerHTML = `<h2 id="ctl-dialog-h">Connect Spotify</h2><p>Spotify will ask you to sign in and allow Spa 99 to play music on the spa speakers.</p>
      <p class="ctl-soft">Demo: no Spotify account is used.</p>
      <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button><button type="button" class="ctl-btn ctl-btn-primary" data-continue>Continue</button></div>`;
    const go = $("[data-continue]", form);
    go.addEventListener("click", () => {
      form.innerHTML = `<h2 id="ctl-dialog-h">Spotify</h2><p class="ctl-wait" role="status">Waiting for Spotify</p>`;
      setTimeout(() => {
        M().spotify.connected = true;
        save();
        form.innerHTML = `<h2 id="ctl-dialog-h">Spotify</h2><p class="ctl-ok" role="status">${icon("check")} Connected (demo)</p><p class="ctl-soft">${esc(S.st.spotify_account)}</p>`;
        S.render();
        setTimeout(() => close(true), 1000);
      }, 1200);
    });
  });
}

async function disconnectSpotify() {
  const ok = await confirmDialog({ title: "Disconnect Spotify?", body: "Anything playing from Spotify stops.", ok: "Disconnect" });
  if (!ok) return;
  M().spotify.connected = false;
  for (const z of M().zones) {
    if (z.src && z.src.kind === "spotify") { Q.clearUpcoming(z); z.queue = []; z.i = -1; z.pos = 0; z.playing = false; z.src = null; z.listen = false; }
  }
  save();
  S.render();
  toast("Spotify disconnected.");
}

/* ---------- group, mute, edit rooms ---------- */

function toggleGroup() {
  if (M().group) { M().group = null; announce("Ungrouped."); touchAll(); return; }
  const lead = selZone();
  M().group = lead.id;
  M().sel = lead.id;
  announce("Every room now follows " + lead.name + ".");
  touchAll();
}

function muteAll() {
  const before = M().zones.map((z) => [z.id, z.muted]);
  for (const z of M().zones) z.muted = true;
  touchAll();
  toast("All music muted.", () => { for (const [id, m] of before) { const z = zoneById(id); if (z) z.muted = m; } touchAll(); });
}

function editRooms(zone) {
  const speakers = S.st.rooms.filter((r) => r.caps.music);
  return formDialog((form, close) => {
    const pick = new Set();
    const draw = () => {
      const moving = [...pick].map((slug) => `Moves ${roomName(slug)} from the ${zoneOfRoom(slug).name} zone`);
      form.innerHTML = `<h2 id="ctl-dialog-h">Rooms in ${esc(zone.name)}</h2><p class="ctl-soft">A room is in one zone. Choosing it here moves it.</p>
        <div class="ctl-chips">${speakers.map((r) => {
          const mine = zone.rooms.includes(r.slug);
          return `<label class="ctl-chipbtn"><input type="checkbox" data-room-pick="${esc(r.slug)}"${mine || pick.has(r.slug) ? " checked" : ""}${mine ? " disabled" : ""}><span>${esc(r.name)}</span></label>`;
        }).join("")}</div>${moving.length ? `<p class="ctl-soft" role="status">${esc(moving.join(". "))}.</p>` : ""}
        <div class="ctl-dialog-actions"><button type="submit" value="cancel" class="ctl-btn">Cancel</button><button type="button" class="ctl-btn ctl-btn-primary" data-rooms-done>Done</button></div>`;
    };
    draw();
    form.onchange = (event) => {
      const n = event.target;
      if (!n.matches("[data-room-pick]")) return;
      if (n.checked) pick.add(n.dataset.roomPick); else pick.delete(n.dataset.roomPick);
      draw();
      const again = $(`[data-room-pick="${n.dataset.roomPick}"]`, form);
      if (again) again.focus();
    };
    form.onclick = (event) => {
      if (!(event.target instanceof Element) || !event.target.closest("[data-rooms-done]")) return;
      for (const slug of pick) { const from = zoneOfRoom(slug); if (from) from.rooms = from.rooms.filter((x) => x !== slug); zone.rooms.push(slug); }
      normalizeZones(S.st);
      close(true);
      touchAll();
    };
  });
}

/* ---------- events ---------- */

function selectZone(id) {
  if (!zoneById(id)) return;
  M().sel = id;
  M().last = id;
  save();
  history.replaceState(null, "", `${location.pathname}?zone=${id}`);
  S.render();
}

export function mountMusic() {
  const z = new URLSearchParams(location.search).get("zone");
  if (z && zoneById(z)) { M().sel = z; M().last = z; }
  lastSig = "";
  const list = $("[data-zone-list]");
  if (list) list.dataset.sig = "";
  loadLibrary().then(() => { lastSig = ""; S.render(); });
}

export function initMusic() {
  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const zoneLink = t.closest("[data-zone]");
    if (zoneLink && zoneLink.closest("[data-music]") && !event.metaKey && !event.ctrlKey) { event.preventDefault(); selectZone(zoneLink.dataset.zone); return; }
    const pact = t.closest("[data-pact]");
    if (pact && pact.closest("[data-player]")) {
      const zone = viewZone();
      if (!zone) return;
      const name = pact.dataset.pact;
      if (name === "listen") { setListen(zone, !zone.listen); return; }
      act(zone, name);
      return;
    }
    const macts = t.closest("[data-music-act]");
    if (macts) {
      const zone = viewZone() || selZone();
      const a = macts.dataset.musicAct;
      if (a === "group") toggleGroup();
      else if (a === "mute-all") muteAll();
      else if (a === "source") openSource(zone);
      else if (a === "edit-rooms") editRooms(zone);
      else if (a === "clear") {
        const removed = Q.clearUpcoming(zone);
        touch(zone);
        if (removed.length) toast("Queue cleared.", () => { Q.restoreUpcoming(zone, removed, zone.i + 1); touch(zone); });
      }
      return;
    }
    const qp = t.closest("[data-qplay]");
    if (qp) {
      const zone = viewZone();
      const n = Number(qp.dataset.qplay);
      zone.i += 1 + n;
      zone.pos = 0;
      zone.playing = true;
      touch(zone);
      syncAudio();
      return;
    }
    const qr = t.closest("[data-qremove]");
    if (qr) { const zone = viewZone(); Q.removeUpcoming(zone, Number(qr.dataset.qremove)); touch(zone); return; }
    const mini = t.closest("[data-mini-act]");
    if (mini) {
      const zone = miniZone();
      if (zone) act(zone, mini.dataset.miniAct === "play" ? "play" : "next");
      return;
    }
    const zp = t.closest("[data-zone-play]");
    if (zp) { const zone = zoneById(zp.dataset.zonePlay); if (zone) act(zone, "play"); }
  });
  document.addEventListener("input", (event) => {
    const n = event.target;
    if (!(n instanceof HTMLInputElement) || !n.closest("[data-player]")) return;
    const zone = viewZone();
    if (!zone) return;
    if (n.matches("[data-vol]")) {
      zone.vol = Number(n.value);
      if (zone.vol > 0) zone.muted = false;
      n.parentElement.style.setProperty("--v", String(zone.vol / 100));
      n.setAttribute("aria-valuetext", `${zone.vol} percent`);
      const t = $("[data-vol-text]");
      if (t) t.textContent = String(zone.vol);
      syncGroup(); syncAudio(); save();
    } else if (n.matches("[data-scrub]")) {
      n.dataset.drag = "1";
      const cur = Q.current(zone);
      n.parentElement.style.setProperty("--v", String(cur ? Number(n.value) / cur.dur : 0));
      const el = $("[data-elapsed]");
      if (el) el.textContent = fmtDur(n.value);
    }
  });
  document.addEventListener("change", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.matches("[data-scrub]")) {
      n.dataset.drag = "0";
      const zone = viewZone();
      if (zone) { act(zone, "seek", Number(n.value)); if (zone.listen && audio) audio.currentTime = zone.pos; }
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== " " || !(event.target instanceof Element)) return;
    if (!event.target.closest("[data-player]") || event.target.closest("button, input, textarea, a, select")) return;
    const zone = viewZone();
    if (zone) { event.preventDefault(); act(zone, "play"); }
  });
  bus.on("asset-deleted", (id) => {
    let stopped = null;
    for (const z of M().zones) { const r = Q.dropAsset(z, id); if (r.stopped) stopped = z; if (r.changed && z.listen) z.listen = false; }
    if (stopped) toast("This file was deleted. Music stopped.");
    touchAll();
  });
  bus.on("library", () => {
    // a file may have been deleted elsewhere: tracks that are no longer in the Library go
    const known = new Set(L.assets.map((a) => a.id));
    let stopped = false;
    for (const z of M().zones) {
      const ids = new Set(z.queue.filter((e) => e.assetId).map((e) => e.assetId));
      for (const id of ids) if (!known.has(id)) { if (Q.dropAsset(z, id).stopped) stopped = true; }
    }
    if (stopped) toast("This file was deleted. Music stopped.");
    syncGroup();
    S.render();
  });
}

/** Used by the Library: play a Library music playlist in a zone. */
export function playLibraryList(zoneId, playlist) {
  const zone = zoneById(zoneId);
  if (!zone || !playlist.items.length) return false;
  playTracks(zone, listTracks(playlist), `Library, ${playlist.name}`, playlist.name);
  return true;
}

export function playLibraryAsset(zoneId, a) {
  const zone = zoneById(zoneId);
  if (!zone) return false;
  playTracks(zone, [libTrack(a)], "Library", a.title);
  return true;
}
