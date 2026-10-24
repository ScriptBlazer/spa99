/* Rooms, lights, climate, scenes, the floor plan and the simulation (all pretend, all in this browser).
   The photo preview: layers() gives the opacity of each stacked layer from brightness and warmth (same maths as
   control/present.py layers()). Only opacity changes, so dragging a slider is cheap. */
import { $, $$, S, MOTION, WIDE, clamp, rand, londonNow, DAY, toast, announce, esc, bus, plural } from "./core.js";
import { save, freshen } from "./state.js";
import { openPanel, panelKey } from "./panel.js";

const TICK_MS = 5000;
const view = { alertsOpen: false, alertSig: "", pop: null, popBtn: null };
let timer = null;
let glides = [];
let glideFrame = 0;
let frame = 0;

const st = () => S.st;
export const roomOf = (slug) => st().rooms.find((r) => r.slug === slug);
const sceneOf = (key) => st().scenes.find((s) => s.key === key);
export const screenOf = (id) => st().screens.find((s) => s.id === id);

/* ---------- derived values ---------- */

const laneMin = (min) => (min - st().lane_start + DAY) % DAY;
export function isOpen(min = londonNow().min) {
  const lane = laneMin(min);
  return !st().week[0].closed.some((c) => lane >= c.start && lane < c.start + c.len);
}
function curve(min) {
  const hour = Math.floor(min / 60);
  const a = st().curve[hour % 24];
  const b = st().curve[(hour + 1) % 24];
  return a + (b - a) * (min % 60) / 60;
}
const goalPeople = (min) => (isOpen(min) ? Math.round(st().capacity * curve(min)) : 0);
export const totalPeople = () => st().rooms.reduce((n, r) => n + r.people, 0);

export function status(r) {
  if (st().alerts.some((a) => a.room === r.slug)) return ["Alert", "danger"];
  if (!isOpen()) return ["Closed", "muted"];
  if (st().scene.key === "cleaning" && !st().scene.changed) return ["Cleaning", "soft"];
  const c = r.caps.climate;
  if (c) {
    if (!r.heater) return ["Off", "muted"];
    const gap = r.cur - r.target;
    if (Math.abs(gap) <= c.tol) return ["At target", "ok"];
    return [gap < 0 ? "Heating" : "Cooling", "warn"];
  }
  return ["Open", "ok"];
}
const peopleText = (n) => (n ? (n === 1 ? "1 person" : `${n} people`) : "Empty");
const temp = (v, d) => `${v.toFixed(d)}°C`;

function presetOf(r) {
  for (const p of st().presets) {
    if (p.lights.on !== r.lights.on) continue;
    if (p.lights.on && (p.lights.bright !== r.lights.bright || p.lights.warmth !== r.lights.warmth)) continue;
    return p.key;
  }
  return "";
}

/** Opacity of each photo layer (brief section 5). */
export function layers(on, bright, warmth) {
  if (!on) return { night: 0.94, lamps: 0, pool: 0, warm: 0, cool: 0 };
  const d = 0.88 * (1 - bright / 100) ** 1.2;
  return { night: d, lamps: d * 0.85, pool: d * 0.6, warm: clamp((3000 - warmth) / 800, 0, 1) * 0.28, cool: clamp((warmth - 3000) / 1000, 0, 1) * 0.35 };
}

function roomFields(r) {
  const L = r.lights;
  const c = r.caps.climate;
  const [word, tone] = status(r);
  const screen = r.caps.screen ? screenOf(r.caps.screen) : null;
  const music = S.roomMusic ? S.roomMusic(r) : { text: "", zone: "" };
  return {
    name: r.name, badge: word, badge_tone: tone,
    bright: L.bright, bright_text: L.on ? `${L.bright}%` : "Off", bright_num: `${L.bright}%`, bright_vt: `${L.bright} percent`,
    warmth: L.warmth, warmth_text: `${L.warmth}K`, warmth_vt: `${L.warmth} kelvin`,
    trim: r.music.trim, trim_text: String(r.music.trim), trim_vt: `${r.music.trim} percent`,
    heater: r.heater, heater_word: r.heater ? "On" : "Off", heater_label: c ? c.heater : "",
    cur_text: c ? temp(r.cur, c.decimals) : "", target_text: c ? temp(r.target, 0) : "",
    hum_text: c && c.humidity ? `${Math.round(r.hum)}% humidity` : "", hum_target_text: c && c.humidity ? `${r.hum_target}%` : "",
    tank_text: r.tank !== undefined ? temp(r.tank, 1) : "",
    preset: r.hint || presetOf(r), people_text: peopleText(r.people),
    music_text: music.text, screen_text: screen ? S.screenText(screen) : "",
  };
}

/* ---------- warm colour for the plan ---------- */

let warmStops = null;
function warmColour(kelvin) {
  if (!warmStops) {
    const style = getComputedStyle(document.body);
    warmStops = st().warm_stops.map((k) => {
      const m = /#([0-9a-f]{6})/i.exec(style.getPropertyValue(`--ctl-warm-${k}`));
      const n = m ? parseInt(m[1], 16) : 0xffffff;
      return { k, rgb: [(n >> 16) & 255, (n >> 8) & 255, n & 255] };
    });
  }
  const k = clamp(kelvin, warmStops[0].k, warmStops[warmStops.length - 1].k);
  for (let i = 1; i < warmStops.length; i += 1) {
    const a = warmStops[i - 1];
    const b = warmStops[i];
    if (k <= b.k) {
      const t = (k - a.k) / (b.k - a.k);
      return `rgb(${a.rgb.map((v, j) => Math.round(v + (b.rgb[j] - v) * t)).join(" ")})`;
    }
  }
  return "";
}

/* ---------- painting ---------- */

export function paint(scope, fields) {
  for (const n of $$("[data-f]", scope)) {
    const k = n.dataset.f;
    if (!(k in fields)) continue;
    const v = fields[k];
    if (n instanceof HTMLInputElement) {
      if (n.type === "range") {
        if (n.value !== String(v)) n.value = v;
        n.setAttribute("aria-valuetext", fields[`${k}_vt`] || String(v));
        const lo = Number(n.min);
        const hi = Number(n.max);
        n.parentElement.style.setProperty("--v", String(clamp((Number(v) - lo) / (hi - lo), 0, 1)));
      } else if (n.type === "checkbox") {
        n.checked = Boolean(v);
      } else if (n.type === "radio") {
        n.checked = n.value === String(v);
      } else if (document.activeElement !== n && n.value !== String(v)) {
        n.value = v;
      }
    } else {
      if (n.textContent !== String(v)) n.textContent = v;
      if (k === "badge") n.dataset.tone = fields.badge_tone;
    }
  }
}

function paintPhoto(scope, r) {
  const photo = $("[data-photo]", scope);
  if (!photo) return;
  const o = layers(r.lights.on, r.lights.bright, r.lights.warmth);
  for (const [k, v] of Object.entries(o)) photo.style.setProperty(`--o-${k}`, v.toFixed(3));
  const chip = $(".ctl-offchip", photo);
  if (chip) chip.hidden = r.lights.on;
}

function paintPlan(r, f) {
  const [word, tone] = status(r);
  const opacity = r.lights.on ? 0.12 + (r.lights.bright / 100) * 0.55 : 0;
  const colour = warmColour(r.lights.warmth);
  const line1 = tone === "danger" ? "Alert" : r.lights.on ? `${r.lights.bright}%  ${r.lights.warmth}K` : "Off";
  const line2 = r.caps.climate && r.heater ? f.cur_text : "";
  const rest = [r.lights.on ? `Lights ${r.lights.bright} percent, ${r.lights.warmth} kelvin.` : "Lights off.",
    r.caps.climate && r.heater ? `${Math.round(r.cur)} degrees.` : "", r.people ? `${peopleText(r.people)}.` : "", tone === "danger" ? "Alert." : ""].filter(Boolean).join(" ");
  for (const g of $$(`radialGradient[data-lg="${r.slug}"]`)) g.style.setProperty("--lc", colour);
  for (const a of $$(`[data-plan-room="${r.slug}"]`)) {
    a.dataset.tone = tone;
    a.classList.toggle("is-off", !r.lights.on);
    a.classList.toggle("is-selected", panelKey() === `room:${r.slug}`);
    $(".pr-light", a).style.opacity = opacity.toFixed(3);
    const one = $('[data-pv="1"]', a);
    if (one && one.textContent !== line1) one.textContent = line1;
    const two = $('[data-pv="2"]', a);
    if (two && two.textContent !== line2) two.textContent = line2;
    const count = $("[data-pc]", a);
    if (count) { const t = r.people ? String(r.people) : ""; if (count.textContent !== t) count.textContent = t; }
    if (!a.dataset.shape) a.dataset.shape = $(".pr-name", a).textContent.replace(/\s+/g, " ").trim();
    const label = `${a.dataset.shape}. ${rest}`;
    if (a.getAttribute("aria-label") !== label) a.setAttribute("aria-label", label);
  }
}

function sentence() {
  const people = totalPeople();
  const s = st();
  if (!isOpen()) return `Closed. Opens at ${s.opens_at}.`;
  const guests = people === 1 ? "1 guest in" : `${people} guests in`;
  if (people >= s.capacity - 2) return `Nearly full. ${guests}.`;
  return `${s.hours_line}. ${guests}.`;
}

export function renderLights() {
  const s = st();
  const t = londonNow();
  const open = isOpen(t.min);
  const people = totalPeople();
  const bands = people === 0 ? 0 : Math.max(0, people + s.staff);
  const lockers = Math.min(s.lockers_total, Math.round(people * 1.2));
  const nearly = open && people >= s.capacity - 2;
  const sc = sceneOf(s.scene.key);
  const n = s.alerts.length;
  paint(document, {
    date: t.date, clock: t.clock, in: people, cap: s.capacity, bands, lockers, sentence: sentence(),
    "in-label": !open ? "Closed" : nearly ? "Nearly full" : "In the building",
    scene_now: s.scene.changed ? `Now: ${sc.label}, changed` : `Now: ${sc.label} · since ${s.scene.since}`,
    "alerts-n": n, "alerts-label": n === 0 ? "No alerts" : n === 1 ? "Alert" : "Alerts",
  });
  const label = $('[data-f="in-label"]');
  if (label) { if (!open) label.dataset.tone = "muted"; else if (nearly) label.dataset.tone = "warn"; else delete label.dataset.tone; }
  const al = $('[data-f="alerts-label"]');
  if (al) { if (n === 0) al.dataset.tone = "ok"; else delete al.dataset.tone; }
  for (const b of $$("[data-scene]")) b.setAttribute("aria-pressed", String(b.dataset.scene === s.scene.key && !sc.hidden));
  for (const scope of $$("[data-room]")) {
    const r = roomOf(scope.dataset.room);
    if (!r) continue;
    const f = roomFields(r);
    paint(scope, f);
    scope.dataset.tone = f.badge_tone;
    paintPhoto(scope, r);
  }
  for (const r of s.rooms) paintPlan(r, roomFields(r));
  renderBell();
  if (view.alertsOpen) {
    const sig = s.alerts.map((a) => a.id).join();
    if (sig !== view.alertSig) renderAlertList();
  }
  for (const ev of $$("[data-ev]")) ev.classList.toggle("is-off", s.runs[ev.dataset.ev] === false);
  const now = $("[data-nowline]");
  if (now) {
    const lane = laneMin(t.min);
    now.style.left = `${(lane / 14.4).toFixed(3)}%`;
    now.classList.toggle("is-flip", lane / 14.4 > 88);
  }
}
export const queueRender = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; S.render(); }); };

/* ---------- changes made by hand ---------- */

function changed(r) {
  if (r) { glides = glides.filter((g) => g.r !== r); delete r.hint; }
  if (sceneOf(st().scene.key) && !st().scene.changed) st().scene.changed = true;
  save();
  S.render();
}

export function setScreenSlide(id, content) {
  const s = screenOf(id);
  if (!s) return;
  if (content === "off") s.power = false;
  else { s.show = { t: "slide", k: content }; s.power = true; }
}

function onField(n) {
  const f = n.dataset.f;
  const scope = n.closest("[data-room]");
  const r = scope && scope.dataset.room ? roomOf(scope.dataset.room) : null;
  if (!r) return false;
  const L = r.lights;
  if (f === "bright") { L.bright = Number(n.value); L.on = L.bright > 0; if (L.bright > 0) L.last = L.bright; }
  else if (f === "warmth") L.warmth = Number(n.value);
  else if (f === "trim") r.music.trim = Number(n.value);
  else if (f === "heater") r.heater = n.checked;
  else if (f === "preset") { applyPreset(r, n.value); return true; }
  else return false;
  changed(r);
  return true;
}

function applyPreset(r, key) {
  const p = st().presets.find((x) => x.key === key);
  if (!p) return;
  r.hint = key;
  glide([{ r, lights: p.lights.on ? { ...p.lights } : { on: false } }], {});
  if (sceneOf(st().scene.key) && !st().scene.changed) st().scene.changed = true;
}

function step(r, kind, delta) {
  const c = r.caps.climate;
  if (!c) return;
  if (kind === "target") r.target = clamp(r.target + delta * c.step, c.min, c.max);
  else if (c.humidity) r.hum_target = clamp(r.hum_target + delta, c.humidity.min, c.humidity.max);
  changed(r);
}

function lightOn(r) {
  r.lights.on = true;
  if (!r.lights.bright) r.lights.bright = r.lights.last || 60;
  changed(r);
}

/* ---------- scenes: values glide, room by room ---------- */

function targetFor(r, sc) {
  const out = {};
  if (sc.lights !== null && sc.lights !== undefined && r.caps.lights) {
    out.lights = { on: true, bright: (sc.exceptions && sc.exceptions[r.slug]) ?? sc.lights, warmth: sc.warmth };
  }
  if (sc.heaters && r.caps.climate) out.heater = sc.heaters === "on" || Boolean(sc.chiller_stays && r.caps.climate.kind === "water");
  return out;
}

function capture() {
  return {
    scene: { ...st().scene },
    rooms: st().rooms.map((r) => ({ r, lights: { ...r.lights }, heater: r.heater })),
    screens: Object.fromEntries(st().screens.map((s) => [s.id, { show: { ...s.show }, power: s.power, notice: s.notice }])),
    music: S.captureMusic ? S.captureMusic() : null,
  };
}

export function applyScene(key) {
  const sc = sceneOf(key);
  if (!sc) return;
  const before = capture();
  if (!sc.hidden) st().scene = { key: sc.key, changed: false, since: sc.time };
  st().rooms.forEach((r) => { delete r.hint; });
  const items = st().rooms.map((r) => ({ r, ...targetFor(r, sc) }));
  const touched = items.filter((it) => it.lights || it.heater !== undefined).length;
  const screens = {};
  for (const s of st().screens) {
    const content = (sc.screens && (sc.screens[s.id] ?? sc.screens["*"])) || null;
    if (content) screens[s.id] = { content, notice: sc.notice && content === "notices" ? sc.notice : undefined };
  }
  glide(items, screens);
  if (sc.music && S.sceneMusic) S.sceneMusic(sc.music);
  toast(`${sc.label} applied to ${plural(touched, "room")}.`, () => undo(before));
  announce(`${sc.label} scene applied.`);
}

function undo(before) {
  st().scene = before.scene;
  const items = before.rooms.map((x) => ({ r: x.r, lights: { ...x.lights }, heater: x.heater }));
  st().rooms.forEach((r) => { delete r.hint; });
  const screens = {};
  for (const [id, v] of Object.entries(before.screens)) screens[id] = { restore: v };
  glide(items, screens);
  if (before.music && S.restoreMusic) S.restoreMusic(before.music);
}

function glide(items, screens) {
  glides = glides.filter((g) => !items.some((it) => it.r === g.r));
  const reduce = MOTION.matches;
  const t0 = performance.now();
  const dur = Number.parseFloat(getComputedStyle(document.body).getPropertyValue("--ctl-glide")) || 2000;
  items.forEach((it, i) => {
    const L = it.lights;
    const g = { r: it.r, delay: reduce ? 0 : i * 60, dur: reduce ? 0 : dur, started: false, t0,
      from: { bright: it.r.lights.bright, warmth: it.r.lights.warmth }, to: {}, discrete: () => {} };
    if (L && L.bright !== undefined) { g.to.bright = L.bright; g.to.warmth = L.warmth; }
    g.discrete = () => {
      if (L) it.r.lights.on = L.on;
      if (it.heater !== undefined) it.r.heater = it.heater;
    };
    glides.push(g);
  });
  for (const [id, v] of Object.entries(screens)) {
    const s = screenOf(id);
    if (!s) continue;
    if (v.restore) { s.show = { ...v.restore.show }; s.power = v.restore.power; s.notice = v.restore.notice; continue; }
    if (v.content === "off") s.power = false; else { s.show = { t: "slide", k: v.content }; s.power = true; }
    if (v.notice !== undefined) s.notice = v.notice;
  }
  bus.emit("screens-changed");
  if (reduce) { runGlides(performance.now()); return; }
  if (!glideFrame) glideFrame = requestAnimationFrame(tickGlide);
}

function tickGlide(now) {
  glideFrame = 0;
  runGlides(now);
  if (glides.length) glideFrame = requestAnimationFrame(tickGlide);
}

let ease = null;
function easing() {
  if (ease) return ease;
  const raw = getComputedStyle(document.body).getPropertyValue("--ease-soft");
  const m = /cubic-bezier\(([^)]+)\)/.exec(raw);
  ease = bezier(...(m ? m[1].split(",").map(Number) : [0.22, 1, 0.36, 1]));
  return ease;
}

function runGlides(now) {
  const live = [];
  for (const g of glides) {
    const elapsed = now - g.t0 - g.delay;
    if (elapsed < 0) { live.push(g); continue; }
    if (!g.started) { g.started = true; g.discrete(); }
    const p = g.dur ? clamp(elapsed / g.dur, 0, 1) : 1;
    const e = p >= 1 ? 1 : easing()(p);
    const L = g.r.lights;
    if (g.to.bright !== undefined) {
      L.bright = p >= 1 ? g.to.bright : Math.round(g.from.bright + (g.to.bright - g.from.bright) * e);
      L.warmth = p >= 1 ? g.to.warmth : Math.round((g.from.warmth + (g.to.warmth - g.from.warmth) * e) / 10) * 10;
      if (L.bright > 0) L.last = L.bright;
    }
    if (p < 1) live.push(g);
  }
  const done = live.length === 0;
  glides = live;
  S.render();
  if (done) save();
}

export function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1; const bx = 3 * (x2 - x1) - cx; const ax = 1 - cx - bx;
  const cy = 3 * y1; const by = 3 * (y2 - y1) - cy; const ay = 1 - cy - by;
  const sx = (t) => ((ax * t + bx) * t + cx) * t;
  const sy = (t) => ((ay * t + by) * t + cy) * t;
  return (x) => {
    let t = x;
    for (let i = 0; i < 8; i += 1) {
      const err = sx(t) - x;
      const d = (3 * ax * t + 2 * bx) * t + cx;
      if (Math.abs(err) < 1e-5 || Math.abs(d) < 1e-6) break;
      t -= err / d;
    }
    return sy(clamp(t, 0, 1));
  };
}

/* ---------- the room panel ---------- */

export function openRoom(slug, { push = true } = {}) {
  const r = roomOf(slug);
  const tpl = $("#ctl-room-tpl");
  if (!r || !tpl) return;
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.dataset.room = slug;
  if (!r.caps.climate) $$('[data-cap="climate"]', node).forEach((x) => x.remove());
  if (!(r.caps.climate && r.caps.climate.humidity)) $$('[data-cap="humidity"]', node).forEach((x) => x.remove());
  const music = S.roomMusic ? S.roomMusic(r) : { zone: "" };
  if (!r.caps.music || !music.zone) $$('[data-cap="music"]', node).forEach((x) => x.remove());
  else { const a = $('[data-f="music_open"]', node); if (a) a.href = `/music/?zone=${music.zone}`; }
  if (r.caps.screen) {
    const a = $('[data-f="screen_open"]', node);
    if (a) a.href = `/screens/?screen=${r.caps.screen}`;
    const slot = $("[data-tile-slot]", node);
    const tile = $("#ctl-tile-tpl") && $("#ctl-tile-tpl").content.firstElementChild.cloneNode(true);
    if (slot && tile) {
      tile.dataset.tile = r.caps.screen;
      const note = $("[data-notice]", tile);
      if (note) note.dataset.notice = r.caps.screen;
      slot.replaceWith(tile);
      if (S.mountPreview) S.mountPreview(tile.parentElement, screenOf(r.caps.screen), { replace: tile });
    }
  } else {
    $$('[data-cap="screen"]', node).forEach((x) => x.remove());
  }
  fillPhoto(node, r);
  openPanel({ key: `room:${slug}`, node, rail: true, size: "peek", onClose: () => { if (location.search) history.replaceState(null, "", location.pathname); S.render(); } });
  if (push) history.replaceState(null, "", `${location.pathname}?room=${slug}`);
  S.render();
}

function fillPhoto(node, r) {
  const photo = $("[data-photo]", node);
  if (!photo) return;
  if (r.photo) {
    const pic = document.createElement("picture");
    pic.innerHTML = `<source media="(max-width: 47.99em)" srcset="${esc(r.photo.small)}"><img src="${esc(r.photo.large)}" alt="" width="800" height="533" draggable="false" decoding="async">`;
    photo.prepend(pic);
  } else {
    const swan = document.createElement("span");
    swan.className = "ctl-swan";
    swan.setAttribute("aria-hidden", "true");
    photo.prepend(swan);
  }
  const lamps = $(".l-lamps", photo);
  if (lamps && r.lamps) lamps.style.setProperty("--lamps", r.lamps);
  const chip = $(".ctl-offchip", photo);
  if (chip) chip.setAttribute("aria-label", `Lights are off in ${r.name}. Turn them on`);
}

/* ---------- alerts (the bell) ---------- */

function renderBell() {
  const n = st().alerts.length;
  const badge = $(".ctl-badge");
  const bell = $(".ctl-bell");
  if (badge) { badge.hidden = n === 0; if (badge.textContent !== String(n)) badge.textContent = n; }
  if (bell) bell.setAttribute("aria-label", n ? `Alerts, ${n} open` : "Alerts");
}

function renderAlertList() {
  const box = $("#ctl-alerts");
  view.alertSig = st().alerts.map((a) => a.id).join();
  box.replaceChildren();
  const h = document.createElement("h3");
  h.textContent = "Open alerts";
  box.append(h);
  if (!st().alerts.length) {
    const p = document.createElement("p");
    p.className = "ctl-soft";
    p.textContent = "No alerts";
    box.append(p);
    return;
  }
  const ul = document.createElement("ul");
  for (const a of st().alerts) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = a.text;
    const room = document.createElement("span");
    room.className = "ctl-alert-room";
    room.textContent = `${(roomOf(a.room) || { name: a.room }).name}, since ${a.since}`;
    text.append(room);
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ctl-btn";
    b.dataset.seen = a.id;
    b.textContent = "Mark as seen";
    li.append(text, b);
    ul.append(li);
  }
  box.append(ul);
}

function openAlerts(btn) {
  const box = $("#ctl-alerts");
  view.alertsOpen = true;
  box.hidden = false;
  renderAlertList();
  if (WIDE.matches) {
    const rect = btn.getBoundingClientRect();
    box.style.top = `${rect.bottom + 8}px`;
    box.style.left = `${clamp(rect.right - box.offsetWidth, 8, innerWidth - box.offsetWidth - 8)}px`;
    box.style.right = "auto";
    box.style.bottom = "auto";
  }
  btn.setAttribute("aria-expanded", "true");
  const first = $("button", box);
  (first || box).focus?.({ preventScroll: true });
}

function closeAlerts(restore = true) {
  const box = $("#ctl-alerts");
  if (!view.alertsOpen) return;
  view.alertsOpen = false;
  box.hidden = true;
  const btn = $(".ctl-bell");
  if (btn) { btn.setAttribute("aria-expanded", "false"); if (restore) btn.focus({ preventScroll: true }); }
}

export const alertsOpen = () => view.alertsOpen;
export { closeAlerts };

/* ---------- schedule popover ---------- */

export function openPop(btn) {
  const box = $("[data-pop]");
  if (!box) return;
  closePop(false);
  let title; let timeText; let text; let key = null;
  if (btn.dataset.sev !== undefined) {  // a screens marker
    const rows = JSON.parse(btn.dataset.sev);
    title = "Screens";
    timeText = btn.dataset.time;
    text = rows.map((x) => `${x.screen}: ${x.what}`).join(". ") + ".";
  } else {
    const day = st().week[Number(btn.dataset.day)];
    const ev = day && day.events.find((e) => e.key === btn.dataset.ev);
    if (!ev) return;
    key = ev.key;
    title = ev.name;
    timeText = `${ev.time}, ${day.label === "Today" ? day.short : `${day.label} ${day.short.split(" ").slice(1).join(" ")}`}`;
    text = ev.skipped ? `${ev.text} Skipped on this day, closed.` : ev.text;
  }
  view.pop = { key };
  view.popBtn = btn;
  $("[data-pop-title]", box).textContent = title;
  $("[data-pop-time]", box).textContent = timeText;
  $("[data-pop-text]", box).textContent = text;
  const controls = $$("[data-pop-scene]", box);
  controls.forEach((x) => { x.hidden = key === null; });
  if (key) paint(box, { runs: st().runs[key] !== false, runs_word: st().runs[key] !== false ? "On" : "Off" });
  box.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  if (WIDE.matches) {
    const rect = btn.getBoundingClientRect();
    const h = box.offsetHeight;
    let top = rect.bottom + 8;
    if (top + h > innerHeight - 8) top = Math.max(8, rect.top - h - 8);
    box.style.top = `${top}px`;
    box.style.left = `${clamp(rect.left, 8, innerWidth - box.offsetWidth - 8)}px`;
    box.style.right = "auto";
    box.style.bottom = "auto";
  }
  $("[data-pop-title]", box).focus({ preventScroll: true });
}

export function closePop(restore = true) {
  const box = $("[data-pop]");
  if (!box || box.hidden) return;
  box.hidden = true;
  if (view.popBtn) {
    view.popBtn.setAttribute("aria-expanded", "false");
    if (restore) view.popBtn.focus({ preventScroll: true });
  }
  view.pop = null;
  view.popBtn = null;
}

/* ---------- the simulation: one timer, paused while the tab is hidden ---------- */

function peopleStep() {
  const s = st();
  const min = londonNow().min;
  const total = totalPeople();
  const goal = goalPeople(min);
  const addTo = () => {
    const bag = s.rooms.flatMap((r) => Array(s.weights[r.slug] || 5).fill(r));
    return bag[Math.floor(Math.random() * bag.length)];
  };
  const takeFrom = () => {
    const full = s.rooms.filter((r) => r.people > 0);
    return full[Math.floor(Math.random() * full.length)];
  };
  if (!isOpen(min)) {
    for (let i = 0; i < Math.ceil(total / 3) && totalPeople() > 0; i += 1) takeFrom().people -= 1;
  } else if (total < goal - 1 && total < s.capacity) addTo().people += 1;
  else if (total > goal + 1) takeFrom().people -= 1;
  else {
    const roll = Math.random();
    if (roll < 0.35 && total < s.capacity) addTo().people += 1;
    else if (roll < 0.7 && total > 0) takeFrom().people -= 1;
    else if (total > 0) { takeFrom().people -= 1; addTo().people += 1; }
  }
  if (Math.random() < 0.1) s.staff = Math.round(rand(-1, 1));
}

function drift(r, seconds) {
  const c = r.caps.climate;
  const s = st();
  if (c) {
    const ambient = s.ambient[c.kind === "water" ? "water" : "temp"];
    const goal = r.heater ? r.target : ambient;
    const stepSize = (c.rate / 15) * seconds;
    r.base += clamp(goal - r.base, -stepSize, stepSize);
    const noise = r.heater && Math.abs(goal - r.base) < 0.01 ? rand(-c.drift, c.drift) : 0;
    r.cur = r.base + noise;
    if (c.humidity) {
      const hGoal = r.heater ? r.hum_target : 40;
      r.hum = r.heater ? clamp(hGoal + rand(-c.humidity.drift, c.humidity.drift), 0, 100) : r.hum + clamp(hGoal - r.hum, -2, 2);
    }
  }
  if (r.tank !== undefined) r.tank = r.caps.tank.target + rand(-r.caps.tank.drift, r.caps.tank.drift);
}

function onMinute(t) {
  const s = st();
  s.clockMin = t.min;
  for (const ev of s.week[0].events) {
    if (ev.time === t.clock && s.runs[ev.key] !== false && !ev.skipped) { applyScene(ev.key); break; }
  }
  bus.emit("minute", t);
}

function tick() {
  const s = st();
  const now = Date.now();
  const t = londonNow();
  if (t.min !== s.clockMin) onMinute(t);
  for (const r of s.rooms) drift(r, TICK_MS / 1000);
  if (!s.nextPeople) s.nextPeople = now + rand(20, 40) * 1000;
  if (now >= s.nextPeople) { peopleStep(); s.nextPeople = now + rand(20, 40) * 1000; }
  s.alerts = s.alerts.filter((a) => a.resolveAt > now);
  if (!s.nextAlert) s.nextAlert = now + rand(180, 360) * 1000;
  if (now >= s.nextAlert) {
    s.nextAlert = now + rand(180, 360) * 1000;
    const free = s.alert_pool.filter((p) => !s.alerts.some((a) => a.id === p.id));
    if (s.alerts.length < 2 && free.length) {
      const pick = free[Math.floor(Math.random() * free.length)];
      s.alerts.push({ ...pick, since: t.clock, resolveAt: now + rand(60, 120) * 1000 });
      announce(`Alert: ${pick.text}`);
    }
  }
  save();
  S.render();
}

export function runSim() {
  if (timer || document.hidden) return;
  timer = setInterval(tick, TICK_MS);
}
export function haltSim() { clearInterval(timer); timer = null; }

export function onVisible() {
  freshen(st());  // jump straight to fresh values, no catch-up
  st().nextPeople = 0;
  S.render();
  runSim();
}

/* ---------- events ---------- */

export function initLights() {
  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const scene = t.closest("[data-scene]");
    if (scene) { applyScene(scene.dataset.scene); return; }
    const act = t.closest("[data-act]");
    if (act && act.closest("[data-room]")) {
      const r = roomOf(act.closest("[data-room]").dataset.room);
      if (!r) return;
      if (act.dataset.act === "light-on") { event.preventDefault(); lightOn(r); }
      else step(r, act.dataset.act, Number(act.dataset.delta));
      return;
    }
    const bell = t.closest(".ctl-bell");
    if (bell) { if (view.alertsOpen) closeAlerts(); else openAlerts(bell); return; }
    const seen = t.closest("[data-seen]");
    if (seen) {
      st().alerts = st().alerts.filter((a) => a.id !== seen.dataset.seen);
      save();
      S.render();
      const next = $("#ctl-alerts button");
      (next || $("#ctl-alerts")).focus?.({ preventScroll: true });
      return;
    }
    const ev = t.closest("[data-ev], [data-sev]");
    if (ev) { if (view.popBtn === ev) closePop(); else openPop(ev); return; }
    if (t.closest("[data-pop-close]")) { closePop(); return; }
    if (t.closest("[data-pop-run]")) { const key = view.pop && view.pop.key; closePop(false); if (key) applyScene(key); return; }
    if (view.alertsOpen && !t.closest("#ctl-alerts")) closeAlerts(false);
    if (view.pop && !t.closest("[data-pop]")) closePop(false);
  });
  document.addEventListener("input", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.dataset.f && n.type === "range") onField(n);
  });
  document.addEventListener("change", (event) => {
    const n = event.target;
    if (!(n instanceof HTMLInputElement) || !n.dataset.f) return;
    if (n.type === "checkbox" || n.type === "radio") {
      if (onField(n)) return;
      if (n.dataset.f === "runs" && view.pop && view.pop.key) { st().runs[view.pop.key] = n.checked; save(); S.render(); }
    }
  });
}
