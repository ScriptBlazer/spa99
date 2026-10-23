/* The virtual tour engine (docs/design/VIRTUAL-TOUR.md, docs/features/virtual-tour.md "Room module contract").
 * boot.js decides (gate) and calls start({ root, config, modules, icons }); this file owns the renderer, the camera, look-around (drag, keys, tilt),
 * the doorway markers (HTML buttons projected from 3D points), the glide between rooms, the cross-fade, the arrival settle, history,
 * the live region and the quality tiers. One WebGL context, one rAF loop, no GSAP.
 *
 * ROOM MODULE CONTRACT (stable; rooms live in rooms/<slug>.js, take no module statements (everything arrives in ctx))
 * Note for every file here: never write the two keywords that start a module statement, followed by a space, inside a comment: Django's static hashing matches them across lines.
 *
 *   async function build(scene, ctx) { ... return room; }     (the module's named build function)
 *
 *   scene   a fresh THREE.Scene for this room (background espresso, environmentIntensity 0.5). Add meshes and lights to it.
 *   ctx     THREE    the vendored three namespace
 *           K        the builder kit bound to this scene (tour/kit.js): K.std/basic/glow materials, K.box/plane/put (baked, merged by material),
 *                    K.rbox/sector geometry, K.led/glowPlane/shadow/vista, K.inst, K.light/hemi (brief units), K.flush() (call once at the end)
 *           T        the texture generators (tour/textures.js): travertine, oak, planks, slats, moss, quilting, rings, reef, caustics, fish,
 *                    shared('halo'|'shadow'|'puff'), tex(canvas, opts), tok(name), mix(a, b, t), rgba(c, a), rng(seed)
 *           tier     'high' | 'mobile' | 'low' (low can also arrive later: see room.tier)
 *           S        texture size for room-wide maps: 1024 on high, 512 otherwise
 *           reefSize [w, h] for a big backdrop: [2048, 1024] on high, [1024, 512] otherwise
 *           env(wallToken)   a tiny warm studio PMREM in that wall colour; assign to scene.environment (or a material's envMap). Disposed with the room
 *           logo(kind, opts) the logo masks from the page's own SVG: kind 'mark' (swan) or 'stacked' (swan over SPA 99); returns { alpha, normal?, halo?, aspect } canvases
 *           idle()           await between heavy texture generators (keeps every slot under about 50 ms)
 *   room    what build returns:
 *           view     { pos: [x, y, z], yaw, pitch }   standing spot and initial look, degrees (yaw from north -z, positive turns right; pitch up positive)
 *           markers  [{ to: 'dry-sauna', at: [x, y, z] }]   doorways: slug of the destination and the 3D centre of the opening at about 1.1 m
 *           exposure number, default 1 (tone mapping exposure for this room)
 *           arrive   optional { pos, yaw, pitch, ms, input } settle start overriding the default (0.9 m behind the spot, 3 degrees lower, 1400 ms); input = ms before drag may take over
 *           ambient  true if update() animates something (the engine then renders at 30 fps at rest); false or absent: render on demand only
 *           update   optional (dt seconds, t seconds) called before each rendered frame
 *           tier     optional (name) called when the engine drops to 'low'
 *           dispose  optional, for anything the engine cannot see; the engine already disposes every geometry, material, texture and env target in the scene
 *
 * Dispose: current room and the previous one stay in memory, older ones are disposed. Everything here is idempotent and removed on dispose().
 */
import * as THREE from '../../vendor/three/three.module.min.js';
import * as T from './textures.js';
import { makeKit, DEFAULTS } from './kit.js';

const D2R = Math.PI / 180;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const wrap180 = (a) => ((((a + 180) % 360) + 360) % 360) - 180;
const PITCH_MIN = -40, PITCH_MAX = 35;

function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (t) => ((ax * t + bx) * t + cx) * t, Y = (t) => ((ay * t + by) * t + cy) * t, dX = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0) return 0; if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 6; i++) { const e = X(t) - x, d = dX(t); if (Math.abs(e) < 1e-5 || Math.abs(d) < 1e-6) break; t -= e / d; }
    if (Math.abs(X(t) - x) > 1e-3) { let lo = 0, hi = 1; for (let i = 0; i < 24; i++) { t = (lo + hi) / 2; if (X(t) < x) lo = t; else hi = t; } }
    return Y(t);
  };
}
const SOFT = bezier(0.22, 1, 0.36, 1), GLIDE = bezier(0.65, 0, 0.35, 1);   // --ease-soft, --ease-glide

const idle = () => new Promise((res) => (window.requestIdleCallback ? requestIdleCallback(() => res(), { timeout: 120 }) : setTimeout(res, 0)));

export async function start({ root, config, modules, icons }) {
  const ac = new AbortController(), on = (t, ev, fn, o) => t.addEventListener(ev, fn, { signal: ac.signal, ...o });
  const q = (s) => root.querySelector(s), body = document.body, html = document.documentElement;
  const stage = q('#tour-stage'), title = q('#tour-title'), caption = q('#tour-caption'), spaLink = q('#tour-spa-link'), list = q('#tour-rooms'), live = q('#tour-live'), ui = q('.tour-ui');
  const R = Object.fromEntries(config.rooms.map((r) => [r.slug, r]));
  const copy = config.copy, timers = new Set();
  const later = (fn, ms) => { const id = setTimeout(() => { timers.delete(id); fn(); }, ms); timers.add(id); return id; };
  const store = { get: (k) => { try { return sessionStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { sessionStorage.setItem(k, v); } catch { /* private mode */ } } };
  const suffix = document.title.includes(' | ') ? document.title.slice(document.title.lastIndexOf(' | ')) : '';
  let dead = false, slug = config.current;

  /* ---------- tier ---------- */
  const high = matchMedia('(min-width: 64em)').matches && (navigator.deviceMemory ?? 8) >= 4 && (navigator.hardwareConcurrency ?? 8) >= 4;
  let tier = store.get('tour-low') ? 'low' : high ? 'high' : 'mobile';
  const pixelRatio = () => Math.min(window.devicePixelRatio || 1, tier === 'high' ? 2 : tier === 'mobile' ? 1.5 : 1);

  /* ---------- renderer, camera, layers ---------- */
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', alpha: false });
  const canvas = renderer.domElement;
  canvas.className = 'tour-canvas'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img');
  renderer.setClearColor(T.tok('--color-espresso'));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;       // contrast in the darks, highlights roll off (kit.js header: shared look)
  const camera = new THREE.PerspectiveCamera(60, 1, 0.05, 40); camera.rotation.order = 'YXZ';
  const snap = document.createElement('canvas'); snap.className = 'tour-snap'; snap.setAttribute('aria-hidden', 'true');
  const markersEl = document.createElement('div'); markersEl.className = 'tour-markers'; markersEl.dataset.state = 'away';
  const veil = q('.tour-veil');
  stage.insertBefore(canvas, q('#tour-photo').nextSibling); stage.insertBefore(snap, veil);
  root.insertBefore(markersEl, ui);

  let raf = 0, last = 0, acc = 0, clock = 0, drew = false;       // the loop's state (declared early: resize can fire at once)
  let W = 1, H = 1;
  function resize() {
    W = stage.clientWidth || 1; H = stage.clientHeight || 1;
    renderer.setPixelRatio(pixelRatio()); renderer.setSize(W, H, false);
    const aspect = W / H;
    camera.aspect = aspect;
    camera.fov = aspect >= 1 ? 60 : aspect <= 0.6 ? 75 : 75 - (aspect - 0.6) / 0.4 * 15;
    camera.updateProjectionMatrix(); wake();
  }
  const vfov = () => camera.fov, hfov = () => 2 * Math.atan(Math.tan(camera.fov * D2R / 2) * camera.aspect) / D2R;
  const ro = new ResizeObserver(resize); ro.observe(stage);

  /* ---------- look state ---------- */
  const look = { yaw: 0, pitch: 0, ty: 0, tp: 0 }, pos = new THREE.Vector3(), vel = { y: 0, p: 0 };
  const tilt = { on: false, yaw: 0, pitch: 0, ty: 0, tp: 0, z: null, raw: null, got: false };
  let tweens = [], locked = true, dragging = null, lookTween = 0;

  function tween(ms, ease, fn, { look: drivesLook = false } = {}) {
    const tw = { t: 0, ms: Math.max(1, ms), ease, fn, look: drivesLook, done: null };
    const p = new Promise((res) => { tw.done = res; });
    tw.promise = p; tw.cancel = () => { if (tweens.includes(tw)) { tweens = tweens.filter((x) => x !== tw); if (tw.look) lookTween--; tw.done(false); } };
    if (drivesLook) lookTween++;
    tweens.push(tw); wake(); return tw;
  }
  const cancelTweens = () => { [...tweens].forEach((t) => t.cancel()); };
  /** Tween yaw/pitch (and optionally the standing position) from where they are now. Both rendered and target move together. */
  function moveTo({ yaw, pitch, p, ms, ease = SOFT }) {
    tweens.filter((t) => t.look).forEach((t) => t.cancel());
    const y0 = look.yaw, p0 = look.pitch, v0 = pos.clone(), dy = yaw === undefined ? 0 : wrap180(yaw - y0), dp = pitch === undefined ? 0 : pitch - p0;
    return tween(ms, ease, (k) => {
      look.yaw = look.ty = y0 + dy * k; look.pitch = look.tp = p0 + dp * k;
      if (p) pos.lerpVectors(v0, p, k);
    }, { look: true });
  }
  function foldTilt() { if (!tilt.on) return; look.yaw += tilt.yaw; look.pitch = clamp(look.pitch + tilt.pitch, PITCH_MIN, PITCH_MAX); look.ty = look.yaw; look.tp = look.pitch; rezero(); }

  /* ---------- tilt (gyroscope) ---------- */
  const q1 = new THREE.Quaternion(-Math.sqrt(0.5), 0, 0, Math.sqrt(0.5)), q0 = new THREE.Quaternion(), zee = new THREE.Vector3(0, 0, 1), eul = new THREE.Euler(), quat = new THREE.Quaternion(), fwd = new THREE.Vector3();
  function rezero() { tilt.z = tilt.raw ? { ...tilt.raw } : null; tilt.ty = tilt.tp = tilt.yaw = tilt.pitch = 0; }
  function onOrient(e) {
    if (e.alpha == null && e.beta == null) return;
    tilt.got = true;
    const orient = (screen.orientation ? screen.orientation.angle : window.orientation || 0) * D2R;
    eul.set((e.beta || 0) * D2R, (e.alpha || 0) * D2R, -(e.gamma || 0) * D2R, 'YXZ'); quat.setFromEuler(eul); quat.multiply(q1); quat.multiply(q0.setFromAxisAngle(zee, -orient));
    fwd.set(0, 0, -1).applyQuaternion(quat);
    tilt.raw = { ya: Math.atan2(fwd.x, -fwd.z) / D2R, pa: Math.asin(clamp(fwd.y, -1, 1)) / D2R };
    if (!tilt.z) tilt.z = { ...tilt.raw };
    if (tilt.on) { tilt.ty = wrap180(tilt.raw.ya - tilt.z.ya); tilt.tp = tilt.raw.pa - tilt.z.pa; wake(); }
  }
  let chip = null;
  const hasTilt = 'DeviceOrientationEvent' in window && matchMedia('(pointer: coarse)').matches && !store.get('tour-tilt-no');
  function setTilt(v) {
    tilt.on = v; chip?.setAttribute('aria-pressed', String(v)); chip?.classList.toggle('is-on', v);
    if (v) { tilt.z = tilt.raw ? { ...tilt.raw } : null; tilt.ty = tilt.tp = tilt.yaw = tilt.pitch = 0; } else { foldTilt(); tilt.yaw = tilt.pitch = 0; }
    if (hintEl && hintEl.classList.contains('is-in')) hintText(v ? copy.hint_tilt.body : copy.hint.body);
    wake();
  }
  if (hasTilt) {
    chip = document.createElement('button'); chip.type = 'button'; chip.className = 'tour-tilt'; chip.setAttribute('aria-pressed', 'false');
    chip.innerHTML = `<svg class="icon" aria-hidden="true" focusable="false"><use href="${icons}#device-rotate"/></svg><span></span>`;
    chip.lastChild.textContent = copy.tilt.cta_label || 'Tilt';
    root.append(chip);
    on(chip, 'click', async () => {
      if (tilt.on) return setTilt(false);
      const DOE = window.DeviceOrientationEvent;
      if (typeof DOE.requestPermission === 'function') {                       // iOS: only inside this tap
        let res = 'denied';
        try { res = await DOE.requestPermission(); } catch { /* denied or not allowed here */ }
        if (res !== 'granted') { chip.remove(); chip = null; store.set('tour-tilt-no', '1'); hintText(copy.tilt.body, 4000); return; }
        addOrient(); setTilt(true);
      } else {                                                                 // Android and others: no prompt
        addOrient(); setTilt(true);
        later(() => { if (!tilt.got && chip) { setTilt(false); chip.remove(); chip = null; } }, 1000);
      }
    });
    on(screen.orientation || window, screen.orientation ? 'change' : 'orientationchange', () => { rezero(); });
  }
  let orientOn = false;
  function addOrient() { if (!orientOn) { orientOn = true; on(window, 'deviceorientation', onOrient); } }

  /* ---------- hint (once per session) ---------- */
  let hintEl = null, hintTimer = 0;
  function hintText(text, ms) {
    if (!hintEl) {
      hintEl = document.createElement('div'); hintEl.className = 'tour-hint'; hintEl.setAttribute('aria-hidden', 'true');
      hintEl.innerHTML = `<svg class="icon" aria-hidden="true" focusable="false"><use href="${icons}#hand-grabbing"/></svg><span></span>`; root.append(hintEl);
    }
    hintEl.lastChild.textContent = text; requestAnimationFrame(() => hintEl && hintEl.classList.add('is-in'));
    clearTimeout(hintTimer); hintTimer = later(hideHint, ms || 7000);
  }
  function hideHint() { clearTimeout(hintTimer); hintEl?.classList.remove('is-in'); }
  function firstHint() {
    if (store.get('tour-hint')) return; store.set('tour-hint', '1');
    later(() => hintText(tilt.on ? copy.hint_tilt.body : copy.hint.body), 1200);
  }

  /* ---------- rooms ---------- */
  const built = new Map();          // slug -> Promise<room>
  let cur = null, prev = null;
  const disposeMat = (m) => {
    for (const k in m) { const v = m[k]; if (v && v.isTexture && !v.userData.shared) v.dispose(); }
    if (m.uniforms) for (const k in m.uniforms) { const v = m.uniforms[k].value; if (v && v.isTexture && !v.userData.shared) v.dispose(); }
    m.dispose();
  };
  function disposeRoom(r) {
    try { r.api.dispose?.(); } catch (e) { console.error('tour room dispose', e); }
    r.scene.traverse((o) => { o.geometry?.dispose(); [].concat(o.material || []).forEach(disposeMat); if (o.isInstancedMesh) o.dispose(); });
    r.targets.forEach((t) => t.dispose()); r.targets.length = 0;
  }
  function makeEnv(wall, room) {
    const pm = new THREE.PMREMGenerator(renderer), s = new THREE.Scene();
    /* a dim wall-coloured box with two hot strips and a dark floor, so metal and gloss have something to reflect (not a flat glow) */
    const box = new THREE.Mesh(new THREE.BoxGeometry(8, 4, 8), new THREE.MeshBasicMaterial({ color: kit0.col(wall).clone().multiplyScalar(0.35), side: THREE.BackSide }));
    const hotM = new THREE.MeshBasicMaterial({ color: kit0.col('--color-led').clone().multiplyScalar(5) });
    const soft = new THREE.Mesh(new THREE.PlaneGeometry(3, 0.5), hotM), soft2 = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 2.5), hotM);
    soft.rotation.x = Math.PI / 2; soft.position.y = 1.9; soft2.position.set(-3.9, 0.3, 0); soft2.rotation.y = Math.PI / 2;
    const dark = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.MeshBasicMaterial({ color: kit0.col('--color-espresso') })); dark.rotation.x = -Math.PI / 2; dark.position.y = -1.9;
    s.add(box, soft, soft2, dark);
    const rt = pm.fromScene(s, 0, 0.1, 50, { size: 128 });
    pm.dispose(); box.geometry.dispose(); box.material.dispose(); soft.geometry.dispose(); soft2.geometry.dispose(); hotM.dispose(); dark.geometry.dispose(); dark.material.dispose();
    room.targets.push(rt); return rt.texture;
  }
  const kit0 = makeKit(new THREE.Scene(), { tier });          // only for token colours outside a room

  function buildRoom(s) {
    if (built.has(s)) return built.get(s);
    const p = (async () => {
      if (!modules[s]) throw new Error('no module for ' + s);
      const t0 = performance.now(), mod = await import(modules[s]);
      const scene = new THREE.Scene(); scene.background = kit0.col('--color-espresso'); scene.environmentIntensity = DEFAULTS.env;
      const room = { slug: s, scene, api: null, targets: [] };
      const ctx = {
        THREE, T, K: makeKit(scene, { tier }), tier, S: tier === 'high' ? 1024 : 512, reefSize: tier === 'high' ? [2048, 1024] : [1024, 512],
        env: (wall) => makeEnv(wall, room), logo: (kind, o) => T.logo(kind, tier === 'high' ? 1024 : 512, o), idle,
      };
      room.api = await mod.build(scene, ctx);
      room.api.markers ||= [];
      const t1 = performance.now();
      try { await Promise.race([renderer.compileAsync(scene, camera), new Promise((res) => setTimeout(res, 1500))]); } catch { /* first render compiles */ }   // never let shader compiles hold the room up for long
      console.debug(`[tour] ${s}: built in ${Math.round(t1 - t0)} ms, shaders ${Math.round(performance.now() - t1)} ms`);
      return room;
    })();
    built.set(s, p); p.catch(() => built.delete(s));
    return p;
  }
  const prefetch = (s) => { if (modules[s]) import(modules[s]).catch(() => {}); };

  /* ---------- markers ---------- */
  let markers = [];
  const v3 = new THREE.Vector3(), dir = new THREE.Vector3();
  function setMarkers(room) {
    markersEl.replaceChildren(); markers = [];
    for (const m of room.api.markers) {
      const dest = R[m.to]; if (!dest) continue;
      const el = document.createElement('button'); el.type = 'button'; el.className = 'tour-marker'; el.dataset.to = m.to;
      el.setAttribute('aria-label', 'Walk to the ' + dest.name.toLowerCase());
      el.innerHTML = '<span class="tour-ring"></span><span class="tour-marker-label"></span>'; el.lastChild.textContent = dest.name;
      const mk = { el, to: m.to, at: new THREE.Vector3(...m.at), on: false, x: -1e4, y: -1e4 };
      const warm = () => { if (modules[m.to]) buildRoom(m.to).catch(() => {}); };
      on(el, 'pointerenter', warm); on(el, 'pointerdown', warm); on(el, 'focus', () => { warm(); if (!mk.on && !busy) turnTo(mk); });
      on(el, 'click', () => walk(mk));
      markersEl.append(el); markers.push(mk);
    }
  }
  function bearing(p) { return Math.atan2(p.x - pos.x, -(p.z - pos.z)) / D2R; }
  function turnTo(mk) {
    const d = wrap180(bearing(mk.at) - look.yaw - tilt.yaw);
    moveTo({ yaw: look.yaw + d, ms: Math.min(900, 400 + 3 * Math.abs(d)) });
  }
  function projectMarkers() {
    for (const mk of markers) {
      v3.copy(mk.at).sub(camera.position); const dist = v3.length(); camera.getWorldDirection(dir);
      const ang = Math.acos(clamp(dir.dot(v3) / (dist || 1), -1, 1)) / D2R;
      v3.copy(mk.at).project(camera);
      const vis = ang < 70 && Math.abs(v3.x) < 1.08 && Math.abs(v3.y) < 1.08;
      if (vis) { mk.x = (v3.x + 1) / 2 * W; mk.y = (1 - v3.y) / 2 * H; } else { mk.x = W / 2; mk.y = H * 0.5; }
      mk.el.style.transform = `translate3d(${mk.x.toFixed(1)}px,${mk.y.toFixed(1)}px,0)`;
      if (vis !== mk.on) { mk.on = vis; mk.el.classList.toggle('is-on', vis); }
    }
  }

  /* ---------- the loop ---------- */
  const samples = []; let sampleT = 0;
  function wake() { drew = false; if (!raf && !dead && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); } }
  function frame(now) {
    raf = 0; if (dead || document.hidden || !cur) return;
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    // tweens
    if (tweens.length) {
      for (const tw of [...tweens]) { tw.t += dt * 1000; const k = Math.min(1, tw.t / tw.ms); tw.fn(tw.ease(k)); if (k >= 1) { tweens = tweens.filter((x) => x !== tw); if (tw.look) lookTween--; tw.done(true); } }
    }
    // inertia and smoothing (only when nothing scripted drives the look)
    let moving = false;
    if (!lookTween) {
      if (!dragging && (Math.abs(vel.y) > 0.5 || Math.abs(vel.p) > 0.5)) { look.ty += vel.y * dt; look.tp = clamp(look.tp + vel.p * dt, PITCH_MIN, PITCH_MAX); const f = Math.exp(-dt / 0.25); vel.y *= f; vel.p *= f; moving = true; }
      const k = 1 - Math.exp(-dt / 0.09);
      if (Math.abs(look.ty - look.yaw) > 0.005 || Math.abs(look.tp - look.pitch) > 0.005) { look.yaw += (look.ty - look.yaw) * k; look.pitch += (look.tp - look.pitch) * k; moving = true; } else { look.yaw = look.ty; look.pitch = look.tp; }
    }
    if (tilt.on) { const k = 1 - Math.exp(-dt / 0.12); if (Math.abs(tilt.ty - tilt.yaw) > 0.02 || Math.abs(tilt.tp - tilt.pitch) > 0.02) { tilt.yaw += (tilt.ty - tilt.yaw) * k; tilt.pitch += (tilt.tp - tilt.pitch) * k; moving = true; } }
    const active = tweens.length > 0 || moving || !!dragging || !drew;
    const ambient = !!cur.api.ambient;
    if (active || ambient) {
      let step = dt;
      if (!active) { acc += dt; if (acc < 1 / 30 - 0.002) { raf = requestAnimationFrame(frame); return; } step = acc; acc = 0; }
      clock += step;
      try { cur.api.update?.(step, clock); } catch (e) { console.error('tour room update', e); }
      draw(); drew = true;
      if (active && !transitioning) sampleFrame(dt);
      raf = requestAnimationFrame(frame);
    }
  }
  function draw() {
    camera.position.copy(pos);
    camera.rotation.set(clamp(look.pitch + (tilt.on ? tilt.pitch : 0), PITCH_MIN, PITCH_MAX) * D2R, -(look.yaw + (tilt.on ? tilt.yaw : 0)) * D2R, 0);
    camera.updateMatrixWorld();
    renderer.render(cur.scene, camera);
    projectMarkers();
  }
  /** Quality: if the median frame over 2 s of motion is over 22 ms, drop to low and stay there for the session. */
  function sampleFrame(dt) {
    if (tier === 'low') return;
    samples.push(dt * 1000); sampleT += dt;
    if (sampleT < 2) return;
    samples.sort((a, b) => a - b);
    if (samples[samples.length >> 1] > 22) setLow();
    samples.length = 0; sampleT = 0;
  }
  function setLow() {
    tier = 'low'; store.set('tour-low', '1'); resize();
    built.forEach((p) => p.then((r) => r.api.tier?.('low')).catch(() => {}));
  }
  on(document, 'visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else { acc = 0; drew = false; wake(); } });

  /* ---------- input: drag, keys ---------- */
  on(canvas, 'pointerdown', (e) => {
    if (locked || (e.pointerType === 'mouse' && e.button !== 0)) return;
    canvas.setPointerCapture(e.pointerId);
    tweens.filter((t) => t.look).forEach((t) => t.cancel());                // a settle yields to the visitor
    dragging = { id: e.pointerId, x: e.clientX, y: e.clientY, s: [] }; vel.y = vel.p = 0;
    canvas.classList.add('is-drag'); hideHint(); wake();
  });
  on(canvas, 'pointermove', (e) => {
    if (!dragging || e.pointerId !== dragging.id) return;
    const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y; dragging.x = e.clientX; dragging.y = e.clientY;
    const dyaw = -dx / W * hfov(), dp = dy / H * vfov();                      // grab the room: it follows the pointer
    look.ty += dyaw; look.tp = clamp(look.tp + dp, PITCH_MIN, PITCH_MAX);
    const t = performance.now(); dragging.s.push([t, dyaw, dp]); while (dragging.s.length && t - dragging.s[0][0] > 80) dragging.s.shift();
    wake();
  });
  const release = (e) => {
    if (!dragging || e.pointerId !== dragging.id) return;
    const t = performance.now(), s = dragging.s.filter((x) => t - x[0] <= 80);
    let vy = s.reduce((a, x) => a + x[1], 0) / 0.08, vp = s.reduce((a, x) => a + x[2], 0) / 0.08;
    const coast = Math.hypot(vy, vp) * 0.25; if (coast > 20) { vy *= 20 / coast; vp *= 20 / coast; }
    vel.y = vy; vel.p = vp; dragging = null; canvas.classList.remove('is-drag'); wake();
  };
  on(canvas, 'pointerup', release); on(canvas, 'pointercancel', release);
  let keyAt = 0, keyEnd = null;
  on(canvas, 'keydown', (e) => {
    const map = { ArrowLeft: [-15, 0], ArrowRight: [15, 0], ArrowUp: [0, 8], ArrowDown: [0, -8] }[e.key];
    if (!map || locked || e.altKey || e.ctrlKey || e.metaKey) return;
    e.preventDefault(); const now = performance.now();
    if (e.repeat && now - keyAt < 350) return; keyAt = now; hideHint();
    foldTilt();
    const base = keyEnd && tweens.some((t) => t.look) ? keyEnd : { yaw: look.ty, pitch: look.tp };
    keyEnd = { yaw: base.yaw + map[0], pitch: clamp(base.pitch + map[1], PITCH_MIN, PITCH_MAX) };
    cancelTweens(); moveTo({ yaw: keyEnd.yaw, pitch: keyEnd.pitch, ms: 500 });
  });

  /* ---------- caption, title, live region, history ---------- */
  function setCaption(s, { announce = true } = {}) {
    const r = R[s];
    title.textContent = r.name;
    let line = q('#tour-line');
    if (r.line) { if (!line) { line = document.createElement('p'); line.className = 'tour-line'; line.id = 'tour-line'; title.after(line); } line.textContent = r.line; } else line?.remove();
    spaLink.href = r.spa_url; (spaLink.querySelector('span') || spaLink).textContent = r.spa_label;
    list.querySelectorAll('a').forEach((a) => { if (a.dataset.roomLink === s) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    const here = list.querySelector('[aria-current]'); if (here && list.scrollWidth > list.clientWidth) list.scrollLeft = here.offsetLeft - (list.clientWidth - here.offsetWidth) / 2;
    document.title = `${r.name}, virtual tour${suffix}`;
    canvas.setAttribute('aria-label', `3D view of the ${r.name.toLowerCase()}. Use the arrow keys to look around.`);
    root.dataset.room = s;
    if (announce) live.textContent = r.line ? `${r.name}. ${r.line}` : r.name;
  }

  /* ---------- presenting a room ---------- */
  let busy = false, transitioning = false, pending = null, target = null;
  function arrivalPose(room) {
    const v = room.api.view, a = room.api.arrive, spot = new THREE.Vector3(...v.pos);
    if (a) return { p: new THREE.Vector3(...a.pos), yaw: a.yaw, pitch: a.pitch, ms: a.ms || 1400, input: a.input ?? a.ms ?? 1400 };
    const yaw = v.yaw * D2R, back = new THREE.Vector3(-Math.sin(yaw), 0, Math.cos(yaw)).multiplyScalar(0.9);
    return { p: spot.clone().add(back), yaw: v.yaw, pitch: v.pitch - 3, ms: 1400, input: 1400 };
  }
  /** Put the room on screen and run the settle. Returns when the settle ends. */
  function present(room) {
    prev = cur === room ? prev : cur; cur = room;
    renderer.toneMappingExposure = room.api.exposure ?? DEFAULTS.exposure;
    const v = room.api.view, a = arrivalPose(room);
    pos.copy(a.p); look.yaw = look.ty = a.yaw; look.pitch = look.tp = a.pitch; vel.y = vel.p = 0; rezero(); drew = false;
    setMarkers(room);
    // keep this room and the previous one; dispose the rest
    const keep = [cur.slug, prev?.slug, target, pending?.[0]];
    built.forEach((p, k) => { if (!keep.includes(k)) p.then((r) => { if (!keep.includes(k) && r !== cur && r !== prev && built.get(k) === p) { built.delete(k); disposeRoom(r); } }).catch(() => {}); });
    const goal = new THREE.Vector3(...v.pos);
    locked = true; later(() => { if (cur === room) locked = false; }, Math.min(a.input, a.ms));
    const settle = moveTo({ yaw: v.yaw, pitch: v.pitch, p: goal, ms: a.ms });
    wake();
    return settle.promise;
  }
  function showMarkers() {
    markersEl.dataset.state = 'on';
    markersEl.classList.add('is-pulse'); later(() => markersEl.classList.remove('is-pulse'), 1700);
    // the room's neighbours: fetch their JS while the visitor looks around
    later(() => (window.requestIdleCallback || setTimeout)(() => markers.forEach((m) => prefetch(m.to))), 600);
  }

  /** Walk to a room through a marker, or jump (list, popstate). */
  async function go(s, { marker = null, push = true, focusTitle = false } = {}) {
    if (dead || s === slug || !R[s]) return;
    if (!modules[s]) { location.assign(R[s].tour_url); return; }              // no 3D room yet: the photo page
    if (busy) { pending = [s, { marker, push, focusTitle }]; return; }
    busy = true; transitioning = true; locked = true; target = s; hideHint(); cancelTweens();
    caption.classList.add('is-out'); markersEl.dataset.state = 'away';
    const ready = buildRoom(s); ready.catch(() => {});
    try {
      if (marker) {
        marker.el.classList.add('is-press');
        const d = wrap180(bearing(marker.at) - look.yaw - (tilt.on ? tilt.yaw : 0)); foldTilt();
        const turnMs = Math.abs(d) > 5 ? Math.min(900, 400 + 3 * Math.abs(d)) : 0;
        const turn = moveTo({ yaw: Math.abs(d) > 5 ? look.yaw + d : undefined, pitch: 0, ms: turnMs || 300 });
        await new Promise((r) => later(r, turnMs * 0.4));
        const fx = marker.at.x - pos.x, fz = marker.at.z - pos.z, dist = Math.hypot(fx, fz), travel = Math.min(2.5, Math.max(0, dist - 0.5));
        const end = pos.clone().add(new THREE.Vector3(fx / (dist || 1) * travel, 0, fz / (dist || 1) * travel));
        const startPos = pos.clone();
        const glide = tween(Math.min(1400, 700 + 250 * travel), GLIDE, (k) => pos.lerpVectors(startPos, end, k));
        await Promise.all([turn.promise, glide.promise]);
      }
      const t0 = performance.now(); let waiting = false;
      const stuck = later(() => { waiting = true; root.classList.add('is-wait'); }, 80);
      const give = later(() => location.assign(R[s].tour_url), 8000);
      let room; try { room = await ready; } finally { clearTimeout(stuck); clearTimeout(give); timers.delete(stuck); timers.delete(give); }
      if (waiting) root.classList.remove('is-wait');
      void t0;
      if (dead) return;
      // snapshot of the last outgoing frame, then the new room underneath
      draw();
      snap.width = canvas.width; snap.height = canvas.height; snap.getContext('2d').drawImage(canvas, 0, 0);
      snap.classList.remove('is-fading'); snap.style.opacity = '1'; void snap.offsetWidth; snap.classList.add('is-fading'); snap.style.opacity = '0';
      slug = s;
      const settled = present(room);
      later(() => { setCaption(s); caption.classList.remove('is-out'); caption.classList.add('is-in'); later(() => caption.classList.remove('is-in'), 900);
        const url = R[s].tour_url; if (push && location.pathname !== url) history.pushState({ tour: s }, '', url);
        if (focusTitle || marker) title.focus({ preventScroll: true }); }, 350);
      await settled;
      later(showMarkers, 400);
      transitioning = false; busy = false; target = null;
      if (pending) { const [ps, po] = pending; pending = null; go(ps, po); }
    } catch (err) {
      console.error('tour: could not open ' + s, err);
      location.assign(R[s].tour_url);
    }
  }
  function walk(mk) { if (!busy && !locked) go(mk.to, { marker: mk, focusTitle: true }); }

  on(list, 'click', (e) => {
    const a = e.target.closest('a[data-room-link]'); if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;
    const s = a.dataset.roomLink; if (!modules[s]) return;                   // no 3D room yet: normal navigation
    e.preventDefault(); if (s !== slug) go(s);
  });
  on(window, 'popstate', () => {
    const hit = config.rooms.find((r) => r.tour_url === location.pathname); if (hit) go(hit.slug, { push: false });
  });

  /* ---------- falling back to the photo ---------- */
  function toPhoto() {
    if (dead) return;
    const r = R[slug]; dispose();
    const fig = q('#tour-photo');
    if (r.photo) { let img = fig.querySelector('img.photo'); if (!img || fig.querySelector('picture')) { fig.replaceChildren(); img = document.createElement('img'); img.className = 'photo'; fig.append(img); } img.removeAttribute('srcset'); img.src = r.photo; img.alt = r.alt; }
    fig.style.setProperty('--focus', r.focus);
    html.classList.remove('tour-gl'); body.classList.remove('tour-3d');
    window.addEventListener('popstate', () => location.reload());
  }
  on(canvas, 'webglcontextlost', (e) => { e.preventDefault(); toPhoto(); });
  const reduced = matchMedia('(prefers-reduced-motion: reduce)'); on(reduced, 'change', () => { if (reduced.matches) toPhoto(); });

  function dispose() {
    if (dead) return; dead = true;
    cancelAnimationFrame(raf); timers.forEach(clearTimeout); timers.clear(); ro.disconnect(); ac.abort();
    built.forEach((p) => p.then(disposeRoom).catch(() => {})); built.clear();
    renderer.dispose(); renderer.forceContextLoss?.();
    [canvas, snap, markersEl, hintEl, chip].forEach((el) => el?.remove());
    caption.classList.remove('is-out', 'is-in'); body.classList.remove('tour-3d');
  }

  /* ---------- go ---------- */
  resize();
  setCaption(slug, { announce: false });
  history.replaceState({ tour: slug }, '', location.href);
  let first;
  try { first = await buildRoom(slug); } catch (err) { dispose(); throw err; }
  if (dead) return { dispose };
  const settled = present(first);
  /* the photo stays up until the first real frame is on the canvas, then the canvas fades in over it */
  requestAnimationFrame(() => requestAnimationFrame(() => { if (!dead) body.classList.add('tour-3d'); }));
  firstHint();
  settled.then(() => { if (!dead) { locked = false; transitioning = false; later(showMarkers, 400); } });
  transitioning = true;
  return { dispose, get room() { return slug; } };
}
