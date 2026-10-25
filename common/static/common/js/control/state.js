/* The pretend state of the building, and how it is kept in this browser (localStorage only, never sent anywhere).
   server = the JSON the page printed (#ctl-demo); st = that plus whatever this browser saved. Library files and playlists are
   NOT here: they are real and live on the server (library.js). */
import { S, DAY, clamp, rand, londonNow } from "./core.js";
import { advance, playNow } from "./music-model.js";

export const KEY = "spa99.control.demo.v2";
const OLD_KEYS = ["spa99.control.demo.v1"];
const STALE_MS = 10 * 60 * 1000;
let resetting = false;
let saveTimer = 0;

export function freshPeople(s, min) {
  const hour = Math.floor(min / 60);
  const lane = (min - s.lane_start + DAY) % DAY;
  const open = !s.week[0].closed.some((c) => lane >= c.start && lane < c.start + c.len);
  for (const r of s.rooms) r.people = 0;
  if (!open) return;
  const f = s.curve[hour % 24] + (s.curve[(hour + 1) % 24] - s.curve[hour % 24]) * (min % 60) / 60;
  let left = Math.round(s.capacity * f);
  const bag = s.rooms.flatMap((r) => Array(s.weights[r.slug] || 5).fill(r));
  while (left > 0) { bag[Math.floor(Math.random() * bag.length)].people += 1; left -= 1; }
}

export function freshen(s) {
  for (const r of s.rooms) {
    const c = r.caps.climate;
    if (c) {
      const goal = r.heater ? r.target : s.ambient[c.kind === "water" ? "water" : "temp"];
      r.base = goal;
      r.cur = goal;
      if (c.humidity) r.hum = r.heater ? r.hum_target : 40;
    }
  }
  freshPeople(s, londonNow().min);
  s.alerts = s.alerts.filter((a) => a.resolveAt > Date.now());
}

/** Zones as they start (DEMO): two playing Spotify sample playlists, the rest quiet. */
function seedZones(base) {
  return base.zones.map((z) => {
    const zone = { id: z.id, name: z.name, rooms: [...z.rooms], vol: z.vol, muted: false, shuffle: false, repeat: "off", playing: false, pos: 0,
      queue: [], i: -1, orig: [], listen: false, src: null };
    const start = base.zone_start[z.id];
    const pl = start && base.spotify.find((p) => p.id === start[0]);
    if (pl) {
      const tracks = pl.tracks.map((t, n) => ({ id: `sp:${pl.id}:${n}`, kind: "spot", plId: pl.id, plName: pl.name, field: pl.field, ...t }));
      playNow(zone, tracks, start[1]);
      zone.pos = start[2] || 0;
      zone.src = { kind: "spotify", label: `Spotify, ${pl.name}`, name: pl.name, plId: pl.id };
    }
    return zone;
  });
}

function seedScreens(base) {
  return base.screens.map((s) => ({ ...s, sched: { on: false, rows: [] } }));
}

/** Every room with speakers belongs to exactly one zone (a room that went missing from the saved zones goes back to its own). */
export function normalizeZones(s) {
  const speakers = s.rooms.filter((r) => r.caps.music).map((r) => r.slug);
  const seen = new Set();
  for (const zone of s.music.zones) {
    zone.rooms = zone.rooms.filter((slug) => speakers.includes(slug) && !seen.has(slug));
    zone.rooms.forEach((slug) => seen.add(slug));
  }
  for (const slug of speakers) {
    if (seen.has(slug)) continue;
    const home = s.zones.find((z) => z.rooms.includes(slug));
    const zone = (home && s.music.zones.find((z) => z.id === home.id)) || s.music.zones[0];
    if (zone) zone.rooms.push(slug);
  }
}

/** Saved scene edits, kept only for scenes and rooms that still exist, with numbers in range. */
function cleanEdits(raw, s) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  for (const sc of s.scenes) {
    const mine = raw[sc.key];
    if (!mine || typeof mine !== "object") continue;
    const rooms = {};
    for (const r of s.rooms) {
      const v = mine.rooms && mine.rooms[r.slug];
      if (v && Number.isFinite(v.bright) && Number.isFinite(v.warmth)) rooms[r.slug] = { bright: clamp(Math.round(v.bright), 0, 100), warmth: clamp(Math.round(v.warmth / 100) * 100, 2200, 4000) };
    }
    const zones = {};
    for (const z of s.zones) {
      const v = mine.zones && mine.zones[z.id];
      if (typeof v === "string" && (v === "keep" || v === "off" || /^(sp|lib):[\w-]+$/.test(v))) zones[z.id] = v;
    }
    out[sc.key] = { rooms, zones };
  }
  return out;
}

export function restore(base) {
  OLD_KEYS.forEach((k) => localStorage.removeItem(k));
  const s = structuredClone(base);
  const t = londonNow();
  s.scene = { key: s.active_scene, changed: false, since: s.scenes.find((x) => x.key === s.active_scene).time };
  s.runs = {};
  s.sceneEdits = {};  // what the scene editor saved: { sceneKey: { rooms: { slug: { bright, warmth } }, zones: { zoneId: choice } } }
  s.staff = 0;
  s.nextPeople = 0;
  s.nextAlert = 0;
  s.clockMin = t.min;
  s.alerts.forEach((a) => { a.resolveAt = Date.now() + rand(60, 120) * 1000; });
  for (const r of s.rooms) { r.lights.last = r.lights.bright || 60; }
  s.screens = seedScreens(base);
  s.music = { zones: seedZones(base), group: null, sel: base.zones[0] ? base.zones[0].id : null, last: base.zones[0] ? base.zones[0].id : null, spotify: { connected: true } };
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { saved = null; }
  if (!saved || saved.v !== base.v) {
    if (saved) localStorage.removeItem(KEY);  // unknown version: dropped
    return s;
  }
  for (const r of s.rooms) {
    const mine = saved.rooms && saved.rooms[r.slug];
    if (mine) Object.assign(r, mine);
  }
  for (const sc of s.screens) {
    const mine = saved.screens && saved.screens[sc.id];
    if (mine) Object.assign(sc, mine);
  }
  if (saved.scene && s.scenes.some((x) => x.key === saved.scene.key)) s.scene = saved.scene;
  s.runs = saved.runs || {};
  s.sceneEdits = cleanEdits(saved.sceneEdits, s);
  s.staff = saved.staff || 0;
  if (Array.isArray(saved.alerts)) s.alerts = saved.alerts.filter((a) => s.rooms.some((r) => r.slug === a.room));
  if (saved.music && Array.isArray(saved.music.zones)) {
    const elapsed = Math.max(0, (Date.now() - (saved.t || Date.now())) / 1000);
    const known = new Set(base.zones.map((z) => z.id));
    s.music.zones = s.music.zones.map((zone) => {
      const mine = saved.music.zones.find((x) => x.id === zone.id);
      if (!mine) return zone;
      const rooms = Array.isArray(mine.rooms) ? mine.rooms.filter((slug) => s.rooms.some((r) => r.slug === slug && r.caps.music)) : zone.rooms;
      Object.assign(zone, mine, { rooms, name: zone.name, listen: false });
      if (zone.playing) advance(zone, elapsed);  // the clock kept running while the tab was closed
      return zone;
    });
    normalizeZones(s);
    s.music.group = known.has(saved.music.group) ? saved.music.group : null;
    s.music.sel = known.has(saved.music.sel) ? saved.music.sel : s.music.sel;
    s.music.last = known.has(saved.music.last) ? saved.music.last : s.music.last;
    if (saved.music.spotify) s.music.spotify = saved.music.spotify;
    if (saved.music.edited) s.music.edited = saved.music.edited;
  }
  if (Date.now() - (saved.t || 0) > STALE_MS) freshen(s);  // live readings from an old visit are not shown as current
  return s;
}

export function writeNow() {
  const st = S.st;
  if (resetting || !st) return;
  const rs = {};
  for (const r of st.rooms) {
    const { lights, music, heater, target, hum_target, base, cur, hum, people, tank } = r;
    rs[r.slug] = { lights, music, heater, target, hum_target, base, cur, hum, people, tank };
  }
  const ss = {};
  for (const s of st.screens) ss[s.id] = { show: s.show, power: s.power, loop: s.loop, playing: s.playing, notice: s.notice, sched: s.sched };
  const zones = st.music.zones.map(({ id, rooms, vol, muted, shuffle, repeat, playing, pos, queue, i, orig, src }) => ({ id, rooms, vol, muted, shuffle, repeat, playing, pos, queue, i, orig, src }));
  try {
    localStorage.setItem(KEY, JSON.stringify({ v: st.v, t: Date.now(), rooms: rs, screens: ss, scene: st.scene, runs: st.runs, sceneEdits: st.sceneEdits, staff: st.staff, alerts: st.alerts,
      music: { zones, group: st.music.group, sel: st.music.sel, last: st.music.last, spotify: st.music.spotify } }));
  } catch (e) { /* storage full or blocked: the demo still works for this visit */ }
}

/** Save soon (many changes in a row make one write). */
export function save() {
  if (saveTimer) return;
  saveTimer = setTimeout(() => { saveTimer = 0; writeNow(); }, 250);
}

export function resetDemo() {
  resetting = true;  // starting values come from a fresh page, built from the real hours and rooms. The Library is untouched.
  localStorage.removeItem(KEY);
  location.assign(location.pathname);
}
