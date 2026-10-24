/* Spa 99 Control demo (docs/design/CONTROL.md section 10). Plain ES module, no library.
   The page prints one JSON state (#ctl-demo). This file owns it after that: sliders, toggles, presets, scenes, the drift
   simulation, alerts, the schedule popover and the screens. State survives a reload in localStorage under one key.
   It never sends anything to the server: no fetch, no XHR, no form posts. */

const KEY = "spa99.control.demo.v1";
const STALE_MS = 10 * 60 * 1000;
const TICK_MS = 5000;
const DAY = 1440;
const MOTION = matchMedia("(prefers-reduced-motion: reduce)");
const WIDE = matchMedia("(min-width: 48em)");

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const rand = (low, high) => low + Math.random() * (high - low);
const pad = (n) => String(n).padStart(2, "0");
const clock = (min) => `${pad(Math.floor(((min % DAY) + DAY) % DAY / 60))}:${pad(((min % 60) + 60) % 60)}`;

const clockFormat = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short", day: "numeric", month: "short" });
const dataNode = document.getElementById("ctl-demo");
if (dataNode) start(JSON.parse(dataNode.textContent));

function start(server) {
  const view = { room: null, lastFocus: null, pop: null, popBtn: null, alertsOpen: false };
  let st = restore(server);
  let timer = null;
  let glides = [];
  let frame = 0;
  let resetting = false;

  const rooms = () => st.rooms;
  const roomOf = (slug) => st.rooms.find((r) => r.slug === slug);
  const screenOf = (id) => st.screens.find((s) => s.id === id);
  const sceneOf = (key) => st.scenes.find((s) => s.key === key);
  const effective = (screen) => (screen.power ? screen.content : "off");
  const optionLabel = (key) => (st.screen_options.find((o) => o.key === key) || { label: key }).label;

  /* ---------- state: server values plus whatever this browser saved ---------- */

  function restore(base) {
    const s = structuredClone(base);
    const t = londonNow();
    s.scene = { key: s.active_scene, changed: false, since: s.scenes.find((x) => x.key === s.active_scene).time };
    s.runs = {};
    s.staff = 0;
    s.nextPeople = 0;
    s.nextAlert = 0;
    s.clockMin = t.min;
    s.alerts.forEach((a) => { a.resolveAt = Date.now() + rand(60, 120) * 1000; });
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
    s.staff = saved.staff || 0;
    if (Array.isArray(saved.alerts)) s.alerts = saved.alerts.filter((a) => s.rooms.some((r) => r.slug === a.room));
    if (Date.now() - (saved.t || 0) > STALE_MS) freshen(s, true);  // live readings from an old visit are not shown as current
    return s;
  }

  function save() {
    if (resetting) return;
    const rs = {};
    for (const r of st.rooms) {
      const { lights, music, heater, target, hum_target, base, cur, hum, people, tank } = r;
      rs[r.slug] = { lights, music, heater, target, hum_target, base, cur, hum, people, tank };
    }
    const ss = {};
    for (const s of st.screens) ss[s.id] = { content: s.content, power: s.power, notice: s.notice };
    try {
      localStorage.setItem(KEY, JSON.stringify({ v: st.v, t: Date.now(), rooms: rs, screens: ss, scene: st.scene, runs: st.runs, staff: st.staff, alerts: st.alerts }));
    } catch (e) { /* storage full or blocked: the demo still works for this visit */ }
  }

  /* ---------- time ---------- */

  function londonNow() {
    const p = Object.fromEntries(clockFormat.formatToParts(new Date()).map((x) => [x.type, x.value]));
    const min = (Number(p.hour) % 24) * 60 + Number(p.minute);
    return { min, clock: clock(min), date: `${p.weekday} ${p.day} ${p.month}` };
  }
  const laneMin = (min) => (min - st.lane_start + DAY) % DAY;
  function isOpen(min = londonNow().min) {
    const lane = laneMin(min);
    return !st.week[0].closed.some((c) => lane >= c.start && lane < c.start + c.len);
  }
  function curve(min) {
    const hour = Math.floor(min / 60);
    const a = st.curve[hour % 24];
    const b = st.curve[(hour + 1) % 24];
    return a + (b - a) * (min % 60) / 60;
  }
  const goalPeople = (min) => (isOpen(min) ? Math.round(st.capacity * curve(min)) : 0);
  const totalPeople = () => st.rooms.reduce((n, r) => n + r.people, 0);

  /* ---------- derived values and display strings (same rules as control/present.py) ---------- */

  function status(r) {
    if (st.alerts.some((a) => a.room === r.slug)) return ["Alert", "danger"];
    if (!isOpen()) return ["Closed", "muted"];
    if (st.scene.key === "cleaning" && !st.scene.changed) return ["Cleaning", "soft"];
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
    for (const p of st.presets) {
      if (p.lights.on !== r.lights.on) continue;
      if (p.lights.on && (p.lights.bright !== r.lights.bright || p.lights.warmth !== r.lights.warmth)) continue;
      if (r.caps.music) {
        if (p.music.on !== r.music.on) continue;
        if (p.music.on && (p.music.playlist !== r.music.playlist || p.music.vol !== r.music.vol)) continue;
      }
      return p.key;
    }
    return "";
  }

  function roomFields(r) {
    const L = r.lights;
    const M = r.music;
    const c = r.caps.climate;
    const [word, tone] = status(r);
    const screen = r.caps.screen ? screenOf(r.caps.screen) : null;
    return {
      name: r.name, badge: word, badge_tone: tone,
      bright: L.bright, bright_text: L.on ? `${L.bright}%` : "Off", bright_num: `${L.bright}%`, bright_vt: `${L.bright} percent`,
      warmth: L.warmth, warmth_text: `${L.warmth}K`, warmth_vt: `${L.warmth} kelvin`,
      lights_on: L.on, lights_on_word: L.on ? "On" : "Off",
      vol: M.vol, vol_text: String(M.vol), vol_vt: `${M.vol} percent`,
      music_on: M.on, music_on_word: M.on ? "On" : "Off", music_text: M.on ? M.playlist : "Off", playlist: M.playlist,
      heater: r.heater, heater_word: r.heater ? "On" : "Off", heater_label: c ? c.heater : "",
      cur_text: c ? temp(r.cur, c.decimals) : "", target_text: c ? temp(r.target, 0) : "",
      hum_text: c && c.humidity ? `${Math.round(r.hum)}% humidity` : "", hum_target_text: c && c.humidity ? `${r.hum_target}%` : "",
      tank_text: r.tank !== undefined ? temp(r.tank, 1) : "",
      preset: r.hint || presetOf(r), screen_text: screen ? optionLabel(effective(screen)) : "", screen_choice: screen ? effective(screen) : "",
      people_text: peopleText(r.people),
    };
  }

  function screenFields(s) {
    return {
      content: effective(s), power: s.power, power_word: s.power ? "On" : "Off", notice: s.notice,
      summary: `${s.name} screen shows ${optionLabel(effective(s))}.`,
    };
  }

  /* ---------- warm glow ---------- */

  let warmStops = null;
  function warmColour(kelvin) {
    if (!warmStops) {
      const style = getComputedStyle(document.body);
      warmStops = st.warm_stops.map((k) => {
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

  /* ---------- drawing: write state into every element that shows it ---------- */

  function paint(scope, fields) {
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

  function render() {
    const t = londonNow();
    const open = isOpen(t.min);
    const people = totalPeople();
    const bands = people === 0 ? 0 : Math.max(0, people + st.staff);
    const lockers = Math.min(st.lockers_total, Math.round(people * 1.2));
    const nearly = open && people >= st.capacity - 2;
    const sc = sceneOf(st.scene.key);
    paint(document, {
      date: t.date, clock: t.clock, in: people, cap: st.capacity, bands, lockers,
      "in-label": !open ? "Closed" : nearly ? "Nearly full" : "In the building",
      scene_now: st.scene.changed ? `Now: ${sc.label}, changed` : `Now: ${sc.label} · since ${st.scene.since}`,
    });
    const label = $('[data-f="in-label"]');
    if (label) {
      if (!open) label.dataset.tone = "muted"; else if (nearly) label.dataset.tone = "warn"; else delete label.dataset.tone;
    }
    for (const b of $$("[data-scene]")) b.setAttribute("aria-pressed", String(b.dataset.scene === st.scene.key && !sc.hidden));
    for (const scope of $$("[data-room]")) {
      const r = roomOf(scope.dataset.room);
      if (!r) continue;
      const f = roomFields(r);
      paint(scope, f);
      scope.dataset.tone = f.badge_tone;
      if (scope.classList.contains("ctl-card")) {
        scope.style.setProperty("--glow-c", warmColour(r.lights.warmth));
        scope.style.setProperty("--glow-a", r.lights.on ? (0.04 + (r.lights.bright / 100) * 0.24).toFixed(3) : "0");
      }
    }
    for (const scope of $$("[data-screen]")) {
      const s = screenOf(scope.dataset.screen);
      if (s) paint(scope, screenFields(s));
    }
    for (const tile of $$("[data-tile]")) {
      const s = screenOf(tile.dataset.tile);
      if (!s) continue;
      tile.dataset.content = effective(s);
      const note = $("[data-notice]", tile);
      if (note && note.textContent !== s.notice) note.textContent = s.notice;
    }
    const lane = laneMin(t.min);
    const now = $("[data-nowline]");
    if (now) {
      now.style.left = `${(lane / 14.4).toFixed(3)}%`;
      now.classList.toggle("is-flip", lane / 14.4 > 88);
    }
    for (const ev of $$("[data-ev]")) ev.classList.toggle("is-off", st.runs[ev.dataset.ev] === false);
    renderAlertsCell();
    if (view.alertsOpen) {
      const sig = st.alerts.map((a) => a.id).join();
      if (sig !== view.alertSig) renderAlertList();
    }
  }
  const queueRender = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); }); };

  /* ---------- changes made by hand ---------- */

  function changed(r) {
    if (r) { glides = glides.filter((g) => g.r !== r); delete r.hint; }
    if (sceneOf(st.scene.key) && !st.scene.changed) st.scene.changed = true;
    save();
    render();
  }

  function setScreen(id, content) {
    const s = screenOf(id);
    if (!s) return;
    if (content === "off") s.power = false; else { s.content = content; s.power = true; }
  }

  function onField(n) {
    const f = n.dataset.f;
    const scope = n.closest("[data-room]");
    const r = scope && scope.dataset.room ? roomOf(scope.dataset.room) : null;
    if (r) {
      const L = r.lights;
      const M = r.music;
      if (f === "bright") { L.bright = Number(n.value); L.on = L.bright > 0; }
      else if (f === "warmth") L.warmth = Number(n.value);
      else if (f === "lights_on") { L.on = n.checked; if (n.checked && L.bright === 0) L.bright = 60; }
      else if (f === "vol") { M.vol = Number(n.value); if (M.vol > 0) M.on = true; }
      else if (f === "music_on") M.on = n.checked;
      else if (f === "playlist") { M.playlist = n.value; M.on = true; }
      else if (f === "heater") r.heater = n.checked;
      else if (f === "screen_choice") setScreen(r.caps.screen, n.value);
      else if (f === "preset") { applyPreset(r, n.value); return; }
      else return;
      changed(r);
      return;
    }
    const screenScope = n.closest("[data-screen]");
    if (screenScope) {
      const s = screenOf(screenScope.dataset.screen);
      if (!s) return;
      if (f === "content") setScreen(s.id, n.value);
      else if (f === "power") s.power = n.checked;
      else if (f === "notice") s.notice = n.value.slice(0, 80);
      else return;
      save();
      render();
      return;
    }
    if (f === "runs" && view.pop) {
      st.runs[view.pop.key] = n.checked;
      save();
      render();
    }
  }

  function applyPreset(r, key) {
    const p = st.presets.find((x) => x.key === key);
    if (!p) return;
    r.hint = key;
    const target = { lights: { ...p.lights } };
    if (r.caps.music) target.music = { ...p.music };
    if (!p.lights.on) target.lights = { on: false };
    glide([{ r, ...target }], {});
    if (sceneOf(st.scene.key) && !st.scene.changed) st.scene.changed = true;
  }

  function step(r, kind, delta) {
    const c = r.caps.climate;
    if (!c) return;
    if (kind === "target") r.target = clamp(r.target + delta * c.step, c.min, c.max);
    else if (c.humidity) r.hum_target = clamp(r.hum_target + delta, c.humidity.min, c.humidity.max);
    changed(r);
  }

  /* ---------- scenes: values glide, room by room ---------- */

  function targetFor(r, sc) {
    const out = {};
    if (sc.lights !== null && sc.lights !== undefined && r.caps.lights) {
      out.lights = { on: true, bright: (sc.exceptions && sc.exceptions[r.slug]) ?? sc.lights, warmth: sc.warmth };
    }
    if (sc.music && r.caps.music) out.music = { ...sc.music };
    if (sc.heaters && r.caps.climate) out.heater = sc.heaters === "on" || Boolean(sc.chiller_stays && r.caps.climate.kind === "water");
    return out;
  }

  function capture() {
    return {
      scene: { ...st.scene },
      rooms: st.rooms.map((r) => ({ r, lights: { ...r.lights }, music: { ...r.music }, heater: r.heater })),
      screens: Object.fromEntries(st.screens.map((s) => [s.id, { content: s.content, power: s.power, notice: s.notice }])),
    };
  }

  function applyScene(key) {
    const sc = sceneOf(key);
    if (!sc) return;
    const before = capture();
    if (!sc.hidden) st.scene = { key: sc.key, changed: false, since: sc.time };
    st.rooms.forEach((r) => { delete r.hint; });
    const items = st.rooms.map((r) => ({ r, ...targetFor(r, sc) }));
    const touched = items.filter((it) => it.lights || it.music || it.heater !== undefined).length;
    const screens = {};
    for (const s of st.screens) {
      const content = (sc.screens && (sc.screens[s.id] ?? sc.screens["*"])) || null;
      if (content) screens[s.id] = { content, notice: sc.notice && content === "notices" ? sc.notice : undefined };
    }
    glide(items, screens);
    toast(`${sc.label} applied to ${touched} ${touched === 1 ? "room" : "rooms"}.`, () => undo(before));
  }

  function undo(before) {
    st.scene = before.scene;
    const items = before.rooms.map((x) => ({ r: x.r, lights: { ...x.lights }, music: { ...x.music }, heater: x.heater }));
    st.rooms.forEach((r) => { delete r.hint; });
    glide(items, before.screens);
  }

  function glide(items, screens) {
    glides = glides.filter((g) => !items.some((it) => it.r === g.r));
    const reduce = MOTION.matches;
    const t0 = performance.now();
    items.forEach((it, i) => {
      const L = it.lights;
      const M = it.music;
      const g = { r: it.r, delay: reduce ? 0 : i * 60, dur: reduce ? 0 : Number.parseFloat(getComputedStyle(document.body).getPropertyValue("--ctl-glide")) || 2000, started: false, t0,
        from: { bright: it.r.lights.bright, warmth: it.r.lights.warmth, vol: it.r.music.vol }, to: {}, discrete: () => {} };
      if (L && L.bright !== undefined) { g.to.bright = L.bright; g.to.warmth = L.warmth; }
      if (M && M.vol !== undefined) g.to.vol = M.vol;
      g.discrete = () => {
        if (L) it.r.lights.on = L.on;
        if (M) { it.r.music.on = M.on; if (M.playlist) it.r.music.playlist = M.playlist; }
        if (it.heater !== undefined) it.r.heater = it.heater;
      };
      glides.push(g);
    });
    // screens change at once (the tile cross-fades by itself)
    for (const [id, v] of Object.entries(screens)) {
      const s = screenOf(id);
      if (!s) continue;
      if (v.content === "off") s.power = false; else { s.content = v.content; s.power = true; }
      if (v.power !== undefined) s.power = v.power;
      if (v.notice !== undefined) s.notice = v.notice;
    }
    if (reduce) { runGlides(performance.now()); return; }
    queueGlide();
  }

  let glideFrame = 0;
  function queueGlide() { if (!glideFrame) glideFrame = requestAnimationFrame(tickGlide); }
  function tickGlide(now) {
    glideFrame = 0;
    runGlides(now);
    if (glides.length) queueGlide();
  }

  const ease = bezier(...(() => {
    const raw = getComputedStyle(document.body).getPropertyValue("--ease-soft");
    const m = /cubic-bezier\(([^)]+)\)/.exec(raw);
    return m ? m[1].split(",").map(Number) : [0.22, 1, 0.36, 1];
  })());

  function runGlides(now) {
    const live = [];
    for (const g of glides) {
      const elapsed = now - g.t0 - g.delay;
      if (elapsed < 0) { live.push(g); continue; }
      if (!g.started) { g.started = true; g.discrete(); }
      const p = g.dur ? clamp(elapsed / g.dur, 0, 1) : 1;
      const e = p >= 1 ? 1 : ease(p);
      const L = g.r.lights;
      const M = g.r.music;
      if (g.to.bright !== undefined) {
        L.bright = p >= 1 ? g.to.bright : Math.round(g.from.bright + (g.to.bright - g.from.bright) * e);
        L.warmth = p >= 1 ? g.to.warmth : Math.round((g.from.warmth + (g.to.warmth - g.from.warmth) * e) / 10) * 10;
      }
      if (g.to.vol !== undefined) M.vol = p >= 1 ? g.to.vol : Math.round(g.from.vol + (g.to.vol - g.from.vol) * e);
      if (p < 1) live.push(g);
    }
    const done = live.length === 0;
    glides = live;
    render();
    if (done) save();
  }

  function bezier(x1, y1, x2, y2) {
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

  /* ---------- toast ---------- */

  function toast(text, onUndo) {
    const host = $("[data-toasts]");
    const el = document.createElement("div");
    el.className = "ctl-toast";
    el.setAttribute("role", "status");
    const span = document.createElement("span");
    span.textContent = text;
    el.append(span);
    let left = 6000;
    let last = performance.now();
    let hover = false;
    if (onUndo) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = "Undo";
      b.addEventListener("click", () => { onUndo(); remove(); });
      el.append(b);
    }
    const remove = () => {
      clearInterval(iv);
      if (MOTION.matches) { el.remove(); return; }
      el.classList.add("is-out");
      setTimeout(() => el.remove(), 170);
    };
    el.addEventListener("mouseenter", () => { hover = true; });
    el.addEventListener("mouseleave", () => { hover = false; });
    el.addEventListener("focusin", () => { hover = true; });
    el.addEventListener("focusout", () => { hover = false; });
    const iv = setInterval(() => {
      const now = performance.now();
      if (!hover) left -= now - last;
      last = now;
      if (left <= 0) remove();
    }, 200);
    while (host.children.length >= 2) host.firstElementChild.remove();
    host.append(el);
  }

  /* ---------- drawer ---------- */

  const drawer = () => $("[data-drawer]");
  const backdrop = () => $("[data-backdrop]");

  function openRoom(slug) {
    const r = roomOf(slug);
    const box = drawer();
    const tpl = $("#ctl-drawer-tpl");
    if (!r || !box || !tpl) return;
    const wasOpen = !box.hidden;
    if (!wasOpen) view.lastFocus = document.activeElement;
    const body = tpl.content.firstElementChild.cloneNode(true);
    body.dataset.room = slug;
    if (!r.caps.climate) $$('[data-cap="climate"]', body).forEach((x) => x.remove());
    if (!(r.caps.climate && r.caps.climate.humidity)) $$('[data-cap="humidity"]', body).forEach((x) => x.remove());
    if (!r.caps.music) $$('[data-cap="music"]', body).forEach((x) => x.remove());
    if (r.caps.screen) {
      const slot = $("[data-tile-slot]", body);
      const tile = $("#ctl-tile-tpl").content.firstElementChild.cloneNode(true);
      tile.dataset.tile = r.caps.screen;
      $("[data-notice]", tile).dataset.notice = r.caps.screen;
      slot.replaceWith(tile);
    } else {
      $$('[data-cap="screen"]', body).forEach((x) => x.remove());
    }
    box.replaceChildren(body);
    box.hidden = false;
    backdrop().hidden = false;
    if (!wasOpen && !MOTION.matches) { box.classList.remove("is-in"); void box.offsetWidth; box.classList.add("is-in"); }
    document.body.style.overflow = "hidden";
    view.room = slug;
    history.replaceState(null, "", `${location.pathname}?room=${slug}`);
    render();
    $("#ctl-drawer-title", box).focus({ preventScroll: true });
  }

  function closeDrawer() {
    const box = drawer();
    if (!box || box.hidden) return;
    const slug = view.room || ($("[data-room]", box) || {}).dataset?.room;
    box.hidden = true;
    box.replaceChildren();
    backdrop().hidden = true;
    document.body.style.overflow = "";
    view.room = null;
    history.replaceState(null, "", location.pathname);
    const back = view.lastFocus && document.contains(view.lastFocus) ? view.lastFocus : $(`[data-open-room="${slug}"]`);
    if (back) back.focus({ preventScroll: true });
    view.lastFocus = null;
  }

  function tabStops(box) {
    return $$("a[href], button:not([disabled]), input:not([disabled])", box).filter((x) => {
      if (x.type === "radio" && x.name) {
        const group = $$(`input[type="radio"][name="${x.name}"]`, box);
        const on = group.find((g) => g.checked);
        return on ? on === x : group[0] === x;
      }
      return true;
    });
  }

  function trap(event) {
    const box = drawer();
    if (!box || box.hidden || event.key !== "Tab") return;
    const stops = tabStops(box);
    if (!stops.length) return;
    const first = stops[0];
    const last = stops[stops.length - 1];
    const active = document.activeElement;
    if (!box.contains(active)) { event.preventDefault(); first.focus(); }
    else if (event.shiftKey && (active === first || active.id === "ctl-drawer-title")) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
  }

  /* ---------- schedule popover ---------- */

  function openPop(btn) {
    const box = $("[data-pop]");
    if (!box) return;
    const day = st.week[Number(btn.dataset.day)];
    const ev = day && day.events.find((e) => e.key === btn.dataset.ev);
    if (!ev) return;
    closePop(false);
    view.pop = { key: ev.key };
    view.popBtn = btn;
    $("[data-pop-title]", box).textContent = ev.name;
    $("[data-pop-time]", box).textContent = `${ev.time}, ${day.label === "Today" ? day.short : `${day.label} ${day.short.split(" ").slice(1).join(" ")}`}`;
    $("[data-pop-text]", box).textContent = ev.skipped ? `${ev.text} Skipped on this day, closed.` : ev.text;
    paint(box, { runs: st.runs[ev.key] !== false, runs_word: st.runs[ev.key] !== false ? "On" : "Off" });
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

  function closePop(restore = true) {
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

  /* ---------- alerts ---------- */

  function renderAlertsCell() {
    const cell = $("[data-alerts-cell]");
    if (!cell) return;
    const n = st.alerts.length;
    if (String(n) !== cell.dataset.count) {
      cell.dataset.count = String(n);
      cell.innerHTML = n
        ? '<button type="button" class="ctl-alert-btn" data-alerts-open aria-haspopup="dialog" aria-expanded="false" aria-controls="ctl-alerts"><span class="ctl-num" data-f="alert-count"></span><span class="ctl-lbl" data-f="alert-label"></span></button>'
        : '<p class="ctl-num" data-f="alert-count"></p><p class="ctl-lbl" data-f="alert-label" data-tone="ok"></p>';
    }
    paint(cell, { "alert-count": n, "alert-label": n === 0 ? "No alerts" : n === 1 ? "Alert" : "Alerts" });
    const btn = $("[data-alerts-open]", cell);
    if (btn) btn.setAttribute("aria-expanded", String(view.alertsOpen));
  }

  function renderAlertList() {
    const box = $("#ctl-alerts");
    view.alertSig = st.alerts.map((a) => a.id).join();
    box.replaceChildren();
    const h = document.createElement("h3");
    h.textContent = "Open alerts";
    box.append(h);
    if (!st.alerts.length) {
      const p = document.createElement("p");
      p.className = "ctl-soft";
      p.textContent = "No alerts";
      box.append(p);
      return;
    }
    const ul = document.createElement("ul");
    for (const a of st.alerts) {
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
      box.style.left = `${clamp(rect.left, 8, innerWidth - box.offsetWidth - 8)}px`;
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
    const btn = $("[data-alerts-open]");
    if (btn) { btn.setAttribute("aria-expanded", "false"); if (restore) btn.focus({ preventScroll: true }); }
  }

  /* ---------- the simulation: one timer, paused while the tab is hidden ---------- */

  function peopleStep() {
    const min = londonNow().min;
    const total = totalPeople();
    const goal = goalPeople(min);
    const addTo = () => {
      const bag = st.rooms.flatMap((r) => Array(st.weights[r.slug] || 5).fill(r));
      return bag[Math.floor(Math.random() * bag.length)];
    };
    const takeFrom = () => {
      const full = st.rooms.filter((r) => r.people > 0);
      return full[Math.floor(Math.random() * full.length)];
    };
    if (!isOpen(min)) {
      for (let i = 0; i < Math.ceil(total / 3) && totalPeople() > 0; i += 1) takeFrom().people -= 1;
    } else if (total < goal - 1 && total < st.capacity) addTo().people += 1;
    else if (total > goal + 1) takeFrom().people -= 1;
    else {
      const roll = Math.random();
      if (roll < 0.35 && total < st.capacity) addTo().people += 1;
      else if (roll < 0.7 && total > 0) takeFrom().people -= 1;
      else if (total > 0) { takeFrom().people -= 1; addTo().people += 1; }
    }
    if (Math.random() < 0.1) st.staff = Math.round(rand(-1, 1));
  }

  function drift(r, seconds) {
    const c = r.caps.climate;
    if (c) {
      const ambient = st.ambient[c.kind === "water" ? "water" : "temp"];
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

  function freshen(s, quiet) {
    const t = londonNow();
    const open = (() => { const lane = (t.min - s.lane_start + DAY) % DAY; return !s.week[0].closed.some((c) => lane >= c.start && lane < c.start + c.len); })();
    for (const r of s.rooms) {
      const c = r.caps.climate;
      if (c) {
        const goal = r.heater ? r.target : s.ambient[c.kind === "water" ? "water" : "temp"];
        r.base = goal;
        r.cur = goal;
        if (c.humidity) r.hum = r.heater ? r.hum_target : 40;
      }
    }
    if (open) {
      const hour = Math.floor(t.min / 60);
      const frac = s.curve[hour % 24] + (s.curve[(hour + 1) % 24] - s.curve[hour % 24]) * (t.min % 60) / 60;
      let left = Math.round(s.capacity * frac);
      for (const r of s.rooms) r.people = 0;
      const bag = s.rooms.flatMap((r) => Array(s.weights[r.slug] || 5).fill(r));
      while (left > 0) { bag[Math.floor(Math.random() * bag.length)].people += 1; left -= 1; }
    } else {
      for (const r of s.rooms) r.people = 0;
    }
    s.alerts = s.alerts.filter((a) => a.resolveAt > Date.now());
    if (!quiet) save();
  }

  function onMinute(t) {
    st.clockMin = t.min;
    for (const ev of st.week[0].events) {
      if (ev.time === t.clock && st.runs[ev.key] !== false && !ev.skipped) { applyScene(ev.key); break; }
    }
  }

  function tick() {
    const now = Date.now();
    const t = londonNow();
    if (t.min !== st.clockMin) onMinute(t);
    for (const r of st.rooms) drift(r, TICK_MS / 1000);
    if (!st.nextPeople) st.nextPeople = now + rand(20, 40) * 1000;
    if (now >= st.nextPeople) { peopleStep(); st.nextPeople = now + rand(20, 40) * 1000; }
    const before = st.alerts.length;
    st.alerts = st.alerts.filter((a) => a.resolveAt > now);
    if (!st.nextAlert) st.nextAlert = now + rand(180, 360) * 1000;
    if (now >= st.nextAlert) {
      st.nextAlert = now + rand(180, 360) * 1000;
      const free = st.alert_pool.filter((p) => !st.alerts.some((a) => a.id === p.id));
      if (st.alerts.length < 2 && free.length) {
        const pick = free[Math.floor(Math.random() * free.length)];
        st.alerts.push({ ...pick, since: t.clock, resolveAt: now + rand(60, 120) * 1000 });
        const live = $("[data-live]");
        if (live) live.textContent = `Alert: ${pick.text}`;
      }
    }
    save();
    render();
  }

  function run() {
    if (timer || document.hidden) return;
    timer = setInterval(tick, TICK_MS);
  }
  function halt() { clearInterval(timer); timer = null; }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { halt(); return; }
    freshen(st);  // jump straight to fresh values, no catch-up
    st.nextPeople = 0;
    render();
    run();
  });

  /* ---------- events ---------- */

  document.addEventListener("click", (event) => {
    const t = event.target instanceof Element ? event.target : null;
    if (!t) return;
    const open = t.closest("[data-open-room]");
    if (open && !event.metaKey && !event.ctrlKey && !event.shiftKey) { event.preventDefault(); openRoom(open.dataset.openRoom); return; }
    if (t.closest("[data-close]")) { event.preventDefault(); closeDrawer(); return; }
    const scene = t.closest("[data-scene]");
    if (scene) { applyScene(scene.dataset.scene); return; }
    const act = t.closest("[data-act]");
    if (act) {
      const scope = act.closest("[data-room]");
      const r = scope && roomOf(scope.dataset.room);
      if (r) step(r, act.dataset.act, Number(act.dataset.delta));
      return;
    }
    if (t.closest("[data-reset]")) { const d = $("[data-reset-dialog]"); if (d && d.showModal) d.showModal(); return; }
    const alertsBtn = t.closest("[data-alerts-open]");
    if (alertsBtn) { if (view.alertsOpen) closeAlerts(); else openAlerts(alertsBtn); return; }
    const seen = t.closest("[data-seen]");
    if (seen) {
      st.alerts = st.alerts.filter((a) => a.id !== seen.dataset.seen);
      save();
      render();
      const next = $("#ctl-alerts button");
      (next || $("#ctl-alerts")).focus?.({ preventScroll: true });
      return;
    }
    const ev = t.closest("[data-ev]");
    if (ev) { if (view.popBtn === ev) closePop(); else openPop(ev); return; }
    if (t.closest("[data-pop-close]")) { closePop(); return; }
    if (t.closest("[data-pop-run]")) { const key = view.pop && view.pop.key; closePop(false); if (key) applyScene(key); return; }
    if (view.alertsOpen && !t.closest("#ctl-alerts")) closeAlerts(false);
    if (view.pop && !t.closest("[data-pop]")) closePop(false);
    const who = $("[data-who]");
    if (who && who.open && !t.closest("[data-who]")) who.open = false;
  });

  document.addEventListener("input", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.dataset.f && (n.type === "range" || n.type === "text")) onField(n);
  });
  document.addEventListener("change", (event) => {
    const n = event.target;
    if (n instanceof HTMLInputElement && n.dataset.f && (n.type === "checkbox" || n.type === "radio")) onField(n);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === " " && event.target instanceof Element && event.target.matches("[data-open-room]")) { event.preventDefault(); openRoom(event.target.dataset.openRoom); return; }
    if (event.key === "Escape") {
      if ($("[data-reset-dialog]")?.open) return;
      if (view.pop) { closePop(); return; }
      if (view.alertsOpen) { closeAlerts(); return; }
      const who = $("[data-who]");
      if (who && who.open) { who.open = false; $("summary", who).focus(); return; }
      closeDrawer();
      return;
    }
    trap(event);
  });

  const dialog = $("[data-reset-dialog]");
  if (dialog) {
    dialog.addEventListener("close", () => {
      if (dialog.returnValue !== "reset") return;
      resetting = true;  // starting values come from a fresh page, built from the real hours and rooms
      localStorage.removeItem(KEY);
      location.assign(location.pathname);
    });
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close("cancel"); });
  }

  window.addEventListener("pagehide", save);

  /* ---------- go ---------- */

  const open = new URLSearchParams(location.search).get("room");
  const box = drawer();
  if (box && !box.hidden && $("[data-room]", box)) {
    view.room = open;
    document.body.style.overflow = "hidden";
    const title = $("#ctl-drawer-title", box);
    if (title) title.focus({ preventScroll: true });
  }
  render();
  run();
}
