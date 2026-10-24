/* The scene editor. Tapping a scene chip (Daytime, Evening, ...) opens a panel showing what that scene sets: each room's light and
   warmth, and what each music zone plays. "Save scene" keeps it (this browser only, in the demo state); "Apply now" is a separate
   button that sets the rooms to the saved scene. Nothing here applies a scene by itself: the chip only opens the editor. */
import { $, $$, S, esc, icon, toast, announce, clamp, WIDE } from "./core.js";
import { save } from "./state.js";
import { openPanel, closePanel, panelKey } from "./panel.js";
import { sceneOf, sceneRoom, sceneZone, applyScene } from "./lights.js";
import { scenePlaylists } from "./music.js";
import { loadLibrary } from "./libdata.js";

let editor = null;  // { key, node, work, base }

const WARM = { min: 2200, max: 4000, step: 100 };

const snapshot = (work) => JSON.stringify(work);
const fraction = (value, lo, hi) => clamp((value - lo) / (hi - lo), 0, 1);

/** The values the editor starts from: the saved edit, else the scene's own values (a room it leaves alone shows its current light). */
function initialWork(sc) {
  const rooms = {};
  for (const r of S.st.rooms) {
    if (!r.caps.lights) continue;
    const v = sceneRoom(sc, r);
    rooms[r.slug] = v ? { bright: v.bright, warmth: v.warmth } : { bright: r.lights.on ? r.lights.bright : 0, warmth: r.lights.warmth };
  }
  const zones = {};
  for (const z of S.st.music.zones) zones[z.id] = sceneZone(sc, z.id);
  return { rooms, zones };
}

function rangeHtml(field, slug, { min, max, step = 1, value, label, warm = false }) {
  return `<span class="ctl-range${warm ? " is-warm" : ""} is-compact" style="--v:${fraction(value, min, max)}"><input type="range" data-sc="${field}" data-slug="${esc(slug)}" min="${min}" max="${max}" step="${step}" value="${value}" aria-label="${esc(label)}"></span>`;
}

function roomsHtml(work) {
  return S.st.rooms.filter((r) => work.rooms[r.slug]).map((r) => {
    const v = work.rooms[r.slug];
    return `<li class="ctl-sc-room" data-sc-room="${esc(r.slug)}"><p class="ctl-sc-name">${esc(r.name)}</p>
      <div class="ctl-row"><span class="ctl-label">Light</span>${rangeHtml("bright", r.slug, { min: 0, max: 100, value: v.bright, label: `Light in ${r.name}` })}<span class="ctl-val" data-sc-val="bright">${v.bright ? `${v.bright}%` : "Off"}</span></div>
      <div class="ctl-row"><span class="ctl-label">Warmth</span>${rangeHtml("warmth", r.slug, { ...WARM, value: v.warmth, label: `Warmth in ${r.name}`, warm: true })}<span class="ctl-val" data-sc-val="warmth">${v.warmth}K</span></div></li>`;
  }).join("");
}

function zonesHtml(work) {
  return S.st.music.zones.map((z) => {
    const names = z.rooms.map((slug) => (S.st.rooms.find((r) => r.slug === slug) || { name: slug }).name);
    return `<li class="ctl-sc-zone"><label><span class="ctl-sc-name">${esc(z.name)}</span><span class="ctl-soft ctl-sc-rooms">${esc(names.join(", "))}</span>
      <select class="ctl-select" data-sc-zone="${esc(z.id)}" aria-label="Music in the ${esc(z.name)} zone">${optionsHtml(work.zones[z.id])}</select></label></li>`;
  }).join("");
}

function optionsHtml(current) {
  const list = scenePlaylists();
  const known = ["keep", "off", ...list.map((p) => p.value)];
  const extra = known.includes(current) ? "" : `<option value="${esc(current)}" selected>Playlist no longer available</option>`;
  return `<option value="keep"${current === "keep" ? " selected" : ""}>Leave the music as it is</option><option value="off"${current === "off" ? " selected" : ""}>Music off</option>`
    + list.map((p) => `<option value="${esc(p.value)}"${p.value === current ? " selected" : ""}>${esc(p.label)}</option>`).join("") + extra;
}

function paintState() {
  if (!editor) return;
  const { node, work, base, key } = editor;
  const dirty = snapshot(work) !== base;
  const saveBtn = $("[data-sc-save]", node);
  const applyBtn = $("[data-sc-apply]", node);
  saveBtn.disabled = !dirty;
  applyBtn.disabled = dirty;
  const hasEdit = Boolean(S.st.sceneEdits[key]);
  $("[data-sc-reset]", node).hidden = !hasEdit;
  $("[data-sc-note]", node).textContent = dirty ? "You have changes that are not saved. Save the scene, then apply it." : "Saved in this browser only.";
}

function build(sc) {
  const work = initialWork(sc);
  const holder = document.createElement("div");
  holder.innerHTML = `<div class="ctl-pn ctl-sc" data-scene-editor="${esc(sc.key)}"><div class="ctl-pn-body">
    <header class="ctl-pn-head"><div>
      <p class="ctl-kicker">Scene <span class="ctl-chip-demo" title="Demo: nothing is sent to real equipment.">DEMO<span class="ctl-sr">. Demo: nothing is sent to real equipment.</span></span></p>
      <h2 class="ctl-pn-title" id="ctl-panel-title" tabindex="-1">${esc(sc.label)}</h2>
      <p class="ctl-soft ctl-sc-text">${esc(sc.text || "")}</p></div>
      <button type="button" class="ctl-iconbtn" data-close aria-label="Close">${icon("x-r")}</button></header>
    <section class="ctl-group" aria-labelledby="sc-rooms"><h3 id="sc-rooms">Rooms</h3><ul class="ctl-sc-list">${roomsHtml(work)}</ul></section>
    <section class="ctl-group" aria-labelledby="sc-music"><h3 id="sc-music">Music</h3><ul class="ctl-sc-list">${zonesHtml(work)}</ul></section>
    <div class="ctl-sc-actions"><button type="button" class="ctl-btn ctl-btn-primary" data-sc-save>Save scene</button>
      <button type="button" class="ctl-btn" data-sc-apply>Apply now</button>
      <button type="button" class="ctl-link" data-sc-reset hidden>Back to the original</button></div>
    <p class="ctl-note" data-sc-note>Saved in this browser only.</p></div></div>`;
  const node = holder.firstElementChild;
  editor = { key: sc.key, node, work, base: snapshot(work) };

  node.addEventListener("input", (event) => {
    const n = event.target;
    if (!(n instanceof HTMLInputElement) || !n.dataset.sc || !editor) return;
    const slug = n.dataset.slug;
    const v = editor.work.rooms[slug];
    if (!v) return;
    const field = n.dataset.sc;
    v[field] = Number(n.value);
    n.parentElement.style.setProperty("--v", String(fraction(v[field], Number(n.min), Number(n.max))));
    n.setAttribute("aria-valuetext", field === "bright" ? (v.bright ? `${v.bright} percent` : "Off") : `${v.warmth} kelvin`);
    const out = $(`[data-sc-room="${CSS.escape(slug)}"] [data-sc-val="${field}"]`, node);
    if (out) out.textContent = field === "bright" ? (v.bright ? `${v.bright}%` : "Off") : `${v.warmth}K`;
    paintState();
  });
  node.addEventListener("change", (event) => {
    const n = event.target;
    if (n instanceof HTMLSelectElement && n.dataset.scZone && editor) { editor.work.zones[n.dataset.scZone] = n.value; paintState(); }
  });
  node.addEventListener("click", async (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t || !editor) return;
    if (t.closest("[data-sc-save]")) {
      S.st.sceneEdits[editor.key] = structuredClone(editor.work);
      editor.base = snapshot(editor.work);
      save();
      paintState();
      toast(`${sc.label} saved.`);
      announce(`${sc.label} scene saved.`);
    } else if (t.closest("[data-sc-apply]")) {
      if (Object.values(editor.work.zones).some((v) => v.startsWith("lib:"))) await loadLibrary();
      applyScene(editor.key);
      if (!WIDE.matches) closePanel();  // on a phone the sheet covers the rooms: close it so the change is seen
    } else if (t.closest("[data-sc-reset]")) {
      delete S.st.sceneEdits[editor.key];
      save();
      openScene(editor.key);
      toast(`${sc.label} is back to the original.`);
    }
  });
  return node;
}

/** Open the editor for one scene (a chip). Does not apply anything. */
export function openScene(key) {
  const sc = sceneOf(key);
  if (!sc || sc.hidden) return;
  const node = build(sc);
  openPanel({ key: `scene:${key}`, node, size: "full", onClose: () => { if (editor && editor.node === node) editor = null; } });
  paintState();
  // the Library playlists arrive a moment later: add them to the lists without losing a choice already made
  loadLibrary().then(() => {
    if (!editor || editor.node !== node) return;
    for (const select of $$("[data-sc-zone]", node)) select.innerHTML = optionsHtml(editor.work.zones[select.dataset.scZone]);
  });
}

export function initScenes() {
  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    const chip = t && t.closest("[data-scene]");
    if (!chip) return;
    event.preventDefault();
    if (panelKey() === `scene:${chip.dataset.scene}`) { closePanel(); return; }
    openScene(chip.dataset.scene);
  });
}
