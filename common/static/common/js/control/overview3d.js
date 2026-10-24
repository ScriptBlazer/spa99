/* The Overview as a simple 3D model of the real ground floor (docs/design/CONTROL.md section 4.1).
   Clean massing: a light slab, light floors and thin low walls drawn from the plan outlines (control/plan.py model()), no textures.
   A room's light shows only as a soft warm tint on its floor (strength = brightness, colour = the warmth scale). Rooms with no
   controls (plant, WCs, stairs, lift, electrical) are slightly darker and have no label or click.
   Camera: starts straight above, fitted to the building. Drag to tilt (top view to 55 degrees) and turn, wheel or pinch to zoom,
   shift-drag or two fingers to move. Tap or click a room (a drag is not a tap) to open its panel.
   Renders only when something changes. No WebGL, or reduced motion: this module does nothing and the 2D plan stays. */
import * as THREE from "../../vendor/three/three.module.min.js";
import { $, MOTION, bus, clamp } from "./core.js";
import { warmRgb, openRoom, status, roomOf } from "./lights.js";
import { panelKey } from "./panel.js";

const FOV = 26;  // degrees: a long lens so the plan stays true to shape
const MAX_POLAR = (55 * Math.PI) / 180;
const ZOOM = [0.85, 3];
const WALL_H = 22;  // plan units (the building is 1200 long): low, so you see in
const WALL_HALF = 4;  // each room's own half of the shared wall (plan.py INSET)
const SLAB = 6;
const PAD = 10;
const TAP_PX = 6;

let inst = null;

/* ---------- geometry helpers (plan units, y down) ---------- */

function area(p) {
  let a = 0;
  for (let i = 0; i < p.length; i += 1) { const q = p[(i + 1) % p.length]; a += p[i][0] * q[1] - q[0] * p[i][1]; }
  return a / 2;
}

/** The outline moved outwards by d (inwards when negative). Works for the plan's simple outlines. */
function offsetPoly(p, d) {
  const n = p.length;
  const out = area(p) > 0 ? 1 : -1;
  const lines = p.map((a, i) => {
    const b = p[(i + 1) % n];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    const e = [(b[0] - a[0]) / len, (b[1] - a[1]) / len];
    const nx = out > 0 ? e[1] : -e[1];
    const ny = out > 0 ? -e[0] : e[0];
    return { p: [a[0] + nx * d, a[1] + ny * d], e };
  });
  return p.map((pt, i) => {
    const a = lines[(i + n - 1) % n];
    const b = lines[i];
    const cross = a.e[0] * b.e[1] - a.e[1] * b.e[0];
    if (Math.abs(cross) < 1e-9) return b.p;
    const t = ((b.p[0] - a.p[0]) * b.e[1] - (b.p[1] - a.p[1]) * b.e[0]) / cross;
    return [a.p[0] + a.e[0] * t, a.p[1] + a.e[1] * t];
  });
}

function inside(p, x, y) {
  let hit = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i, i += 1) {
    if ((p[i][1] > y) !== (p[j][1] > y) && x < ((p[j][0] - p[i][0]) * (y - p[i][1])) / (p[j][1] - p[i][1]) + p[i][0]) hit = !hit;
  }
  return hit;
}

function centroid(p) {
  let a = 0; let cx = 0; let cy = 0;
  for (let i = 0; i < p.length; i += 1) {
    const q = p[(i + 1) % p.length];
    const f = p[i][0] * q[1] - q[0] * p[i][1];
    a += f; cx += (p[i][0] + q[0]) * f; cy += (p[i][1] + q[1]) * f;
  }
  const c = a ? [cx / (3 * a), cy / (3 * a)] : p[0];
  if (inside(p, c[0], c[1])) return c;
  const xs = p.map((v) => v[0]); const ys = p.map((v) => v[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
}

const shapeOf = (pts) => { const s = new THREE.Shape(); pts.forEach(([x, y], i) => (i ? s.lineTo(x, -y) : s.moveTo(x, -y))); s.closePath(); return s; };
const pathOf = (pts) => { const s = new THREE.Path(); pts.forEach(([x, y], i) => (i ? s.lineTo(x, -y) : s.moveTo(x, -y))); s.closePath(); return s; };

/** Shape coordinates are (x, -y) on the XY plane and extrude along +Z; turning the geometry gives world (x, height, y). */
function flat(shape, height, uvBox = null) {
  const g = new THREE.ShapeGeometry(shape);
  if (uvBox) {
    const pos = g.attributes.position;
    const uv = new Float32Array(pos.count * 2);
    for (let i = 0; i < pos.count; i += 1) { uv[2 * i] = (pos.getX(i) - uvBox.x) / uvBox.w; uv[2 * i + 1] = (pos.getY(i) - uvBox.y) / uvBox.h; }
    g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  }
  g.rotateX(-Math.PI / 2);
  g.translate(0, height, 0);
  return g;
}
function raised(shape, depth) {
  const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, steps: 1 });
  g.rotateX(-Math.PI / 2);
  return g;
}

/** A soft round mask for the floor glow (grey levels only, used as an alpha map). */
function glowTexture() {
  const c = document.createElement("canvas");
  c.width = 128; c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (let i = 0; i <= 8; i += 1) {
    const t = i / 8;
    const k = clamp((t - 0.1) / 0.9, 0, 1);
    const level = Math.round(255 * (0.3 + 0.7 * (1 - k * k * (3 - 2 * k))));
    grad.addColorStop(t, `rgb(${level},${level},${level})`);
  }
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.NoColorSpace;
  return tex;
}

const token = (name) => getComputedStyle(document.body).getPropertyValue(name).trim();
const colour = (name) => new THREE.Color(token(name));

/* ---------- build ---------- */

function build(root, data) {
  const canvas = $("[data-model-canvas]", root);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setClearColor(colour("--ctl-surface"), 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 2, 10, 20000);

  const floorColour = colour("--ctl-m-floor");
  const wallColour = colour("--ctl-m-wall");
  const dimColour = colour("--ctl-m-dim");
  const gold = colour("--ctl-accent");
  const mats = {
    slab: new THREE.MeshStandardMaterial({ color: colour("--ctl-m-slab"), roughness: 1, metalness: 0 }),
    floor: new THREE.MeshStandardMaterial({ color: floorColour, roughness: 1, metalness: 0 }),
    dim: new THREE.MeshStandardMaterial({ color: dimColour, roughness: 1, metalness: 0 }),
    wall: new THREE.MeshStandardMaterial({ color: wallColour, roughness: 1, metalness: 0 }),
    ring: new THREE.MeshBasicMaterial({ color: gold }),
  };
  const mask = glowTexture();
  const disposables = [mask, ...Object.values(mats), renderer];

  // soft ambient (sky and ground) plus one directional light
  const ambient = new THREE.HemisphereLight(new THREE.Color(1, 1, 1), dimColour.clone().multiplyScalar(0.8), 2.2);
  const sun = new THREE.DirectionalLight(new THREE.Color(1, 1, 1), 0.9);
  sun.position.set(-600, 1000, 500);
  scene.add(ambient, sun);

  const all = data.rooms.flatMap((r) => r.points);
  const minX = Math.min(...all.map((p) => p[0])) - PAD; const maxX = Math.max(...all.map((p) => p[0])) + PAD;
  const minY = Math.min(...all.map((p) => p[1])) - PAD; const maxY = Math.max(...all.map((p) => p[1])) + PAD;
  const centre = new THREE.Vector3((minX + maxX) / 2, 0, (minY + maxY) / 2);
  const half = { x: (maxX - minX) / 2, z: (maxY - minY) / 2 };
  sun.target.position.copy(centre);
  scene.add(sun.target);

  const slabGeo = new THREE.BoxGeometry(maxX - minX, SLAB, maxY - minY);
  const slab = new THREE.Mesh(slabGeo, mats.slab);
  slab.position.set(centre.x, -SLAB / 2, centre.z);
  scene.add(slab);
  disposables.push(slabGeo);

  const rooms = [];
  for (const room of data.rooms) {
    const live = Boolean(room.slug) && Boolean(roomOf(room.slug));  // a room the demo does not have is drawn like a space with no controls
    const outer = offsetPoly(room.points, WALL_HALF);
    const xs = room.points.map((p) => p[0]); const ys = room.points.map((p) => -p[1]);
    const box = { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
    const item = { slug: live ? room.slug : null, name: room.name, points: room.points, outer, mesh: [], centre: centroid(room.points), w: box.w, h: box.h, sig: "" };

    const floorGeo = flat(shapeOf(room.points), 0.3);
    scene.add(new THREE.Mesh(floorGeo, live ? mats.floor : mats.dim));
    disposables.push(floorGeo);

    const wallShape = shapeOf(outer);
    wallShape.holes.push(pathOf(room.points));
    const wallGeo = raised(wallShape, WALL_H);
    const wallMat = live ? mats.wall.clone() : mats.wall;
    const wall = new THREE.Mesh(wallGeo, wallMat);
    scene.add(wall);
    disposables.push(wallGeo);
    if (live) disposables.push(wallMat);
    item.wall = wallMat;

    if (live) {
      const glowGeo = flat(shapeOf(room.points), 0.6, box);
      const glowMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 1, 1), alphaMap: mask, transparent: true, opacity: 0, depthWrite: false });
      const glow = new THREE.Mesh(glowGeo, glowMat);
      glow.visible = false;
      scene.add(glow);
      disposables.push(glowGeo, glowMat);
      const ringShape = shapeOf(room.points);
      ringShape.holes.push(pathOf(offsetPoly(room.points, -5)));
      const ringGeo = flat(ringShape, 0.9);
      const ring = new THREE.Mesh(ringGeo, mats.ring);
      ring.visible = false;
      scene.add(ring);
      disposables.push(ringGeo);
      Object.assign(item, { glow, glowMat, ring });
    }
    rooms.push(item);
  }
  return { renderer, scene, camera, rooms, centre, half, disposables, canvas, mats, gold, wallColour };
}

/* ---------- the live instance ---------- */

class Model {
  constructor(root, data) {
    this.root = root;
    this.data = data;
    this.abort = new AbortController();
    Object.assign(this, build(root, data));
    this.live = this.rooms.filter((r) => r.slug);
    this.view = { az: 0, pol: 0, zoom: 1, pan: new THREE.Vector3() };
    this.touched = false;
    this.size = { w: 0, h: 0 };
    this.raf = 0;
    this.hover = null;
    this.tween = null;
    this.pts = new Map();
    this.drag = null;
    this.pinch = null;
    this.tmp = new THREE.Vector3();
    this.buildLabels();
    this.resize();
    this.view.az = this.homeAz();
    this.bind();
    this.paint(true);
    this.requestRender();
  }

  /* ----- labels (HTML, positioned from the 3D scene; real links so the keyboard works) ----- */

  buildLabels() {
    const host = $("[data-model-labels]", this.root);
    host.replaceChildren();
    this.labels = this.live.map((r) => {
      const a = document.createElement("a");
      a.className = "ctl-m-label";
      a.href = `?room=${r.slug}`;
      a.dataset.openRoom = r.slug;
      a.textContent = r.name;
      a.addEventListener("focus", () => this.setHover(r.slug), { signal: this.abort.signal });
      a.addEventListener("blur", () => this.setHover(null), { signal: this.abort.signal });
      host.append(a);
      return { el: a, room: r };
    });
    this.notes = (this.data.notes || []).map((n) => {
      const s = document.createElement("span");
      s.className = "ctl-m-note";
      s.textContent = n.text;
      s.setAttribute("aria-hidden", "true");
      host.append(s);
      return { el: s, x: n.x, z: n.y };
    });
  }

  /* ----- state: the room lights and the selected room ----- */

  paint(force = false) {
    const open = panelKey();
    let changed = false;
    for (const item of this.live) {
      const r = roomOf(item.slug);
      if (!r) continue;
      const [, tone] = status(r);
      const sel = open === `room:${item.slug}`;
      const sig = `${r.lights.on}|${r.lights.bright}|${r.lights.warmth}|${tone}|${sel}`;
      if (!force && sig === item.sig) continue;
      item.sig = sig;
      changed = true;
      const on = r.lights.on && r.lights.bright > 0;
      item.glow.visible = on;
      if (on) {
        const [R, G, B] = warmRgb(r.lights.warmth);
        item.glowMat.color.setRGB(R / 255, G / 255, B / 255, THREE.SRGBColorSpace);
        item.glowMat.opacity = 0.12 + 0.43 * (r.lights.bright / 100);
      }
      item.selected = sel;
      item.tone = tone;
      const label = this.labels.find((l) => l.room === item);
      if (label) {
        label.el.classList.toggle("is-selected", sel);
        label.el.classList.toggle("is-alert", tone === "danger");
        label.el.setAttribute("aria-label", `${item.name}. ${on ? `Lights ${r.lights.bright} percent, ${r.lights.warmth} kelvin.` : "Lights off."}${tone === "danger" ? " Alert." : ""}`);
      }
      this.applyHighlight(item);
    }
    if (changed) this.requestRender();
  }

  applyHighlight(item) {
    const on = item.selected || this.hover === item.slug;
    item.ring.visible = on;
    item.wall.color.copy(on ? this.gold : this.wallColour);
    const label = this.labels.find((l) => l.room === item);
    if (label) label.el.classList.toggle("is-hover", this.hover === item.slug);
  }

  setHover(slug) {
    if (slug === this.hover) return;
    const before = this.hover;
    this.hover = slug;
    for (const item of this.live) if (item.slug === before || item.slug === slug) this.applyHighlight(item);
    this.canvas.classList.toggle("is-hover", Boolean(slug));
    this.requestRender();
  }

  /* ----- camera ----- */

  homeAz() { return this.size.w / Math.max(1, this.size.h) < 0.95 ? Math.PI / 2 : 0; }

  placeCamera() {
    const { az, pol, zoom, pan } = this.view;
    const t = Math.tan((FOV * Math.PI) / 360);
    const aspect = this.size.w / Math.max(1, this.size.h);
    const c = Math.abs(Math.cos(az)); const s = Math.abs(Math.sin(az));
    const halfW = (c * this.half.x + s * this.half.z) * 1.04;
    const halfH = (s * this.half.x + c * this.half.z) * 1.04;
    const dist = Math.max(halfH / t, halfW / (t * aspect)) / zoom;
    this.dist = dist;
    const target = this.tmp.copy(this.centre).add(pan);
    const dir = new THREE.Vector3(Math.sin(pol) * Math.sin(az), Math.cos(pol), Math.sin(pol) * Math.cos(az));
    this.camera.position.copy(target).addScaledVector(dir, dist);
    const right = new THREE.Vector3(Math.cos(az), 0, -Math.sin(az));
    const forward = dir.clone().negate();
    this.camera.up.copy(right.cross(forward).normalize());
    this.camera.aspect = aspect;
    this.camera.near = dist * 0.05;
    this.camera.far = dist * 4;
    this.camera.updateProjectionMatrix();
    this.camera.lookAt(target);
    this.camera.updateMatrixWorld();
  }

  clampPan() {
    const k = 1 - 1 / Math.max(1, this.view.zoom);
    this.view.pan.x = clamp(this.view.pan.x, -this.half.x * k, this.half.x * k);
    this.view.pan.z = clamp(this.view.pan.z, -this.half.z * k, this.half.z * k);
  }

  resetView() {
    const to = { az: this.homeAz(), pol: 0, zoom: 1, pan: new THREE.Vector3() };
    this.touched = false;
    let da = to.az - this.view.az;
    da = Math.atan2(Math.sin(da), Math.cos(da));
    to.az = this.view.az + da;
    if (MOTION.matches) { Object.assign(this.view, to); this.requestRender(); return; }
    this.tween = { from: { az: this.view.az, pol: this.view.pol, zoom: this.view.zoom, pan: this.view.pan.clone() }, to, t0: performance.now(), ms: 420 };
    this.requestRender();
  }

  stepTween(now) {
    const tw = this.tween;
    const p = clamp((now - tw.t0) / tw.ms, 0, 1);
    const e = 1 - (1 - p) ** 3;
    const v = this.view;
    v.az = tw.from.az + (tw.to.az - tw.from.az) * e;
    v.pol = tw.from.pol + (tw.to.pol - tw.from.pol) * e;
    v.zoom = tw.from.zoom + (tw.to.zoom - tw.from.zoom) * e;
    v.pan.lerpVectors(tw.from.pan, tw.to.pan, e);
    if (p >= 1) this.tween = null;
  }

  /* ----- drawing, only when asked ----- */

  requestRender() { if (!this.raf && inst === this) this.raf = requestAnimationFrame((now) => this.draw(now)); }

  draw(now) {
    this.raf = 0;
    if (inst !== this) return;
    if (this.tween) this.stepTween(now);
    this.placeCamera();
    this.renderer.render(this.scene, this.camera);
    this.layoutLabels();
    $("[data-model-reset]", this.root).classList.toggle("is-home", this.isHome());
    if (this.tween) this.requestRender();
  }

  isHome() { return this.view.pol < 0.002 && this.view.zoom === 1 && this.view.pan.lengthSq() < 0.01 && Math.abs(Math.atan2(Math.sin(this.view.az - this.homeAz()), Math.cos(this.view.az - this.homeAz()))) < 0.002; }

  layoutLabels() {
    const { w, h } = this.size;
    const scale = h / 2 / (this.dist * Math.tan((FOV * Math.PI) / 360));
    const c = Math.abs(Math.cos(this.view.az)); const s = Math.abs(Math.sin(this.view.az));
    const v = new THREE.Vector3();
    for (const l of this.labels) {
      v.set(l.room.centre[0], 1, l.room.centre[1]).project(this.camera);
      l.el.style.transform = `translate(${((v.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((-v.y * 0.5 + 0.5) * h).toFixed(1)}px) translate(-50%, -50%)`;
      l.el.style.maxWidth = `${Math.max(40, (c * l.room.w + s * l.room.h) * scale - 2).toFixed(0)}px`;
    }
    for (const n of this.notes) {
      v.set(n.x, 0, n.z).project(this.camera);
      n.el.style.transform = `translate(${((v.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((-v.y * 0.5 + 0.5) * h).toFixed(1)}px) translate(-50%, -50%)`;
    }
  }

  resize() {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h || (w === this.size.w && h === this.size.h)) return;
    this.size = { w, h };
    this.renderer.setSize(w, h, false);
    if (!this.touched) this.view.az = this.homeAz();
    this.requestRender();
  }

  /* ----- picking: the point on the floor under the pointer, then which room outline holds it ----- */

  pick(clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    const x = ((clientX - r.left) / r.width) * 2 - 1;
    const y = -((clientY - r.top) / r.height) * 2 + 1;
    const origin = this.camera.position;
    const dir = new THREE.Vector3(x, y, 0.5).unproject(this.camera).sub(origin).normalize();
    if (Math.abs(dir.y) < 1e-6) return null;
    const t = (4 - origin.y) / dir.y;
    if (t < 0) return null;
    const px = origin.x + dir.x * t;
    const pz = origin.z + dir.z * t;
    const hit = this.live.find((item) => inside(item.outer, px, pz));
    return hit ? hit.slug : null;
  }

  /* ----- input ----- */

  bind() {
    const { signal } = this.abort;
    const cv = this.canvas;
    const onDown = (e) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      cv.setPointerCapture(e.pointerId);
      this.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.tween = null;
      if (this.pts.size === 1) {
        this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: 0, t0: e.timeStamp, pan: e.shiftKey };
      } else if (this.pts.size === 2) {
        const [a, b] = [...this.pts.values()];
        this.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, zoom: this.view.zoom, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
        if (this.drag) this.drag.moved = 999;
      }
    };
    const panBy = (dx, dy) => {
      const upp = (2 * this.dist * Math.tan((FOV * Math.PI) / 360)) / this.size.h;
      const az = this.view.az;
      const right = [Math.cos(az), -Math.sin(az)];
      const fwd = [-Math.sin(az), -Math.cos(az)];
      this.view.pan.x += (-dx * right[0] + dy * fwd[0]) * upp;
      this.view.pan.z += (-dx * right[1] + dy * fwd[1]) * upp;
      this.clampPan();
    };
    const onMove = (e) => {
      if (!this.pts.has(e.pointerId)) {
        if (e.pointerType === "mouse" && !e.buttons) this.setHover(this.pick(e.clientX, e.clientY));
        return;
      }
      this.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.pinch && this.pts.size >= 2) {
        const [a, b] = [...this.pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
        const mx = (a.x + b.x) / 2; const my = (a.y + b.y) / 2;
        this.view.zoom = clamp(this.pinch.zoom * (d / this.pinch.d), ZOOM[0], ZOOM[1]);
        panBy(mx - this.pinch.mx, my - this.pinch.my);
        this.pinch.mx = mx; this.pinch.my = my;
        this.touched = true;
        cv.classList.add("is-drag");
        this.requestRender();
        return;
      }
      const d = this.drag;
      if (!d || d.id !== e.pointerId) return;
      const dx = e.clientX - d.x; const dy = e.clientY - d.y;
      d.x = e.clientX; d.y = e.clientY;
      d.moved += Math.abs(dx) + Math.abs(dy);
      if (d.moved <= TAP_PX) return;
      this.touched = true;
      cv.classList.add("is-drag");
      if (d.pan || e.shiftKey) panBy(dx, dy);
      else {
        this.view.az -= dx * 0.007;
        this.view.pol = clamp(this.view.pol - dy * 0.006, 0, MAX_POLAR);
      }
      this.requestRender();
    };
    const onUp = (e) => {
      const d = this.drag;
      const wasOnly = this.pts.size === 1;
      this.pts.delete(e.pointerId);
      if (this.pts.size < 2) this.pinch = null;
      if (this.pts.size === 0) { cv.classList.remove("is-drag"); this.drag = null; }
      if (e.type === "pointerup" && d && d.id === e.pointerId && wasOnly && d.moved <= TAP_PX && e.timeStamp - d.t0 < 700) {
        const slug = this.pick(e.clientX, e.clientY);
        if (slug) openRoom(slug);
      }
    };
    const onWheel = (e) => {
      e.preventDefault();
      this.tween = null;
      this.view.zoom = clamp(this.view.zoom * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0016)), ZOOM[0], ZOOM[1]);
      this.clampPan();
      this.touched = true;
      this.requestRender();
    };
    cv.addEventListener("pointerdown", onDown, { signal });
    cv.addEventListener("pointermove", onMove, { signal });
    cv.addEventListener("pointerup", onUp, { signal });
    cv.addEventListener("pointercancel", onUp, { signal });
    cv.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && !this.pts.size) this.setHover(null); }, { signal });
    cv.addEventListener("wheel", onWheel, { passive: false, signal });
    cv.addEventListener("webglcontextlost", (e) => { e.preventDefault(); disposeOverview(); }, { signal });
    $("[data-model-reset]", this.root).addEventListener("click", () => this.resetView(), { signal });
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(cv);
    this.off = bus.on("lights-rendered", () => this.paint());
  }

  dispose() {
    this.abort.abort();
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    if (this.ro) this.ro.disconnect();
    if (this.off) this.off();
    for (const d of this.disposables) if (d && d.dispose) d.dispose();
    try { this.renderer.forceContextLoss(); } catch (e) { /* already gone */ }
    $("[data-model-labels]", this.root).replaceChildren();
  }
}

/* ---------- entry points (called by app.js) ---------- */

function showPlain() {
  const wrap = $("[data-plan]");
  if (wrap) wrap.classList.remove("is-3d");
  const root = $("[data-model]");
  if (root) root.hidden = true;
}

/** Show the 3D model on this page if it can run; otherwise the 2D plan stays. Safe to call again. */
export function mountOverview() {
  const root = $("[data-model]");
  const node = document.getElementById("ctl-plan3d");
  if (!root || !node) return;
  if (inst && inst.root === root && root.isConnected) { inst.resize(); inst.paint(true); return; }
  disposeOverview();
  if (MOTION.matches) return;  // reduced motion: the calm 2D plan
  root.hidden = false;
  $("[data-plan]").classList.add("is-3d");
  try {
    const data = JSON.parse(node.textContent);
    inst = new Model(root, data);
    inst.requestRender();
  } catch (e) {
    inst = null;  // no WebGL, or the model could not be built: the 2D plan is the fallback
    showPlain();
  }
}

export function disposeOverview() {
  if (!inst) return;
  const gone = inst;
  inst = null;
  gone.dispose();
  showPlain();
}

/** The running model (for checks and debugging in the console). */
export const currentModel = () => inst;
