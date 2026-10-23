/* Canvas texture generators for the virtual tour (docs/design/VIRTUAL-TOUR.md 2.0 and 2.6). Nothing is downloaded: every map is drawn at runtime
 * from the CSS tokens and, for the logo, from the SVG paths the page already carries in #tour-logos (never redrawn).
 * Each generator returns a canvas (cheap to test); `tex(canvas, opts)` turns one into a THREE.CanvasTexture.
 * Call them from a room's build() with `await ctx.idle()` between the heavy ones (each is well under 50 ms at 512, about 40 ms at 1024).
 * Colours are token names ('--color-travertine'); they are read with getComputedStyle, so a token change is a look change.
 */
import * as THREE from '../../vendor/three/three.module.min.js';

/* ---------- colour helpers ---------- */
const root = () => document.documentElement;
const tokCache = new Map();    // one getComputedStyle per token (it ran thousands of times inside the drawing loops); a token change needs a reload
export const tok = (name) => { let v = tokCache.get(name); if (v === undefined) { v = getComputedStyle(root()).getPropertyValue(name).trim(); if (v) tokCache.set(name, v); } return v; };
export const rgbOf = (c) => {
  const s = c.startsWith('--') ? tok(c) : c;
  const m = s.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})/i);
  if (m) return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  const n = s.match(/[\d.]+/g) || [0, 0, 0];
  return [+n[0], +n[1], +n[2]];
};
export const rgba = (c, a = 1) => { const [r, g, b] = rgbOf(c); return `rgba(${r | 0},${g | 0},${b | 0},${a})`; };
/** Mix two colours (token names or hex), t = 0 gives a, 1 gives b. Returns "rgb(...)". */
export const mix = (a, b, t) => { const x = rgbOf(a), y = rgbOf(b); return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(',')})`; };

/** Seeded random (mulberry32) so a room looks the same on every visit. */
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** Generated canvases are kept between rooms (key = generator + args): a room that asks for the same slab as the last one pays nothing. Treat the result as read-only. */
const made = new Map();
export function memo(key, make) { const k = key.join('|'); if (!made.has(k)) { if (made.size > 14) made.delete(made.keys().next().value); made.set(k, make()); } return made.get(k); }

export function canvas(w, h = w) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  return [c, c.getContext('2d')];
}

/** Canvas -> texture. color: sRGB colour map (false for masks and normals). repeat: [u, v]. shared: kept by the engine between rooms. */
export function tex(c, { color = true, repeat, wrap = false, aniso = 4, shared = false } = {}) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = aniso;
  if (wrap || repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; if (repeat) t.repeat.set(repeat[0], repeat[1]); }
  t.userData.shared = shared;
  return t;
}

const cache = {};
/** Tiny shared maps: halo (white radial, for additive glow), shadow (espresso radial, for contact shadows), puff (cream, steam), ray (white vertical beam). */
export function shared(kind) {
  if (cache[kind]) return cache[kind];
  const [c, x] = kind === 'ray' ? canvas(32, 128) : canvas(kind === 'puff' ? 256 : 128);
  const s = c.width, g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  if (kind === 'halo') { g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.35, 'rgba(255,255,255,0.45)'); g.addColorStop(1, 'rgba(255,255,255,0)'); }
  if (kind === 'edge') { const e = '--color-espresso', l = x.createLinearGradient(0, s, 0, 0); l.addColorStop(0, rgba(e, 1)); l.addColorStop(0.4, rgba(e, 0.35)); l.addColorStop(1, rgba(e, 0)); x.fillStyle = l; x.fillRect(0, 0, s, s); return (cache[kind] = tex(c, { shared: true })); }
  if (kind === 'shadow') { const e = '--color-espresso'; g.addColorStop(0, rgba(e, 1)); g.addColorStop(0.55, rgba(e, 0.55)); g.addColorStop(1, rgba(e, 0)); }
  if (kind === 'puff') {
    const r = rng(7), cream = '--color-cream';
    for (let i = 0; i < 9; i++) {
      const px = s * (0.3 + r() * 0.4), py = s * (0.3 + r() * 0.4), pr = s * (0.16 + r() * 0.14), q = x.createRadialGradient(px, py, 0, px, py, pr);
      q.addColorStop(0, rgba(cream, 0.5)); q.addColorStop(1, rgba(cream, 0)); x.fillStyle = q; x.fillRect(0, 0, s, s);
    }
  } else if (kind === 'ray') {                                      // a soft vertical beam: fades down, soft at both sides
    const v = x.createLinearGradient(0, 0, 0, 128); v.addColorStop(0, 'rgba(255,255,255,1)'); v.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = v; x.fillRect(0, 0, 32, 128);
    const h = x.createLinearGradient(0, 0, 32, 0); h.addColorStop(0, 'rgba(0,0,0,0)'); h.addColorStop(0.5, 'rgba(0,0,0,1)'); h.addColorStop(1, 'rgba(0,0,0,0)');
    x.globalCompositeOperation = 'destination-in'; x.fillStyle = h; x.fillRect(0, 0, 32, 128);
  } else { x.fillStyle = g; x.fillRect(0, 0, s, s); }
  return (cache[kind] = tex(c, { color: kind !== 'halo' && kind !== 'ray', shared: true }));
}

/* ---------- stone ---------- */

/** Travertine: horizontal veins that tile left to right. ao = wall height in metres (bakes the dark band toward floor and ceiling, 2.0);
 *  joint = px between slab joints (0 none); jointY the same across. seed: wall and floor use different ones. */
export function travertine(S, { seed = 1, ao = 0, joint = 0, jointY = 0 } = {}) {
  return memo(['travertine', S, seed, ao, joint, jointY], () => {
    const [c, x] = canvas(S), r = rng(seed), base = '--color-travertine', vein = '--color-travertine-vein', e = '--color-espresso';
    x.fillStyle = tok(base); x.fillRect(0, 0, S, S);
    /* soft cloudy tone: tileable value noise, stretched sideways so the clouds lie in long horizontal drifts */
    const cloud = (nx, ny, warm, cool, amt) => {
      const g = Array.from({ length: ny }, () => Array.from({ length: nx }, r)), W = 128, [n, nc] = canvas(W), img = nc.createImageData(W, W), d = img.data, sm = (t) => t * t * (3 - 2 * t);
      const [wr, wg, wb] = rgbOf(warm), [cr, cg, cb] = rgbOf(cool);
      for (let j = 0; j < W; j++) for (let i = 0; i < W; i++) {
        const u = i / W * nx, v = j / W * ny, i0 = Math.floor(u), j0 = Math.floor(v), fu = sm(u - i0), fv = sm(v - j0), q = (a, b) => g[b % ny][a % nx];
        const t = q(i0, j0) * (1 - fu) * (1 - fv) + q(i0 + 1, j0) * fu * (1 - fv) + q(i0, j0 + 1) * (1 - fu) * fv + q(i0 + 1, j0 + 1) * fu * fv, k = (j * W + i) * 4;
        const dark = Math.max(0, t - 0.5) * 2, light = Math.max(0, 0.5 - t) * 2;
        d[k] = dark > light ? wr : cr; d[k + 1] = dark > light ? wg : cg; d[k + 2] = dark > light ? wb : cb; d[k + 3] = Math.max(dark, light) * 255 * amt;
      }
      nc.putImageData(img, 0, 0); x.imageSmoothingQuality = 'high'; x.drawImage(n, 0, 0, S, S);
    };
    cloud(3, 5, vein, '--color-cream', 0.55); cloud(6, 14, vein, '--color-cream', 0.3); cloud(10, 34, vein, '--color-cream', 0.16);
    for (let i = 0; i < 12; i++) {                                    // faint, irregular horizontal banding
      const y = r() * S, h = S * (0.004 + r() * 0.02), g = x.createLinearGradient(0, y - h, 0, y + h), col = r() > 0.5 ? vein : '--color-cream';
      g.addColorStop(0, rgba(col, 0)); g.addColorStop(0.5, rgba(col, 0.05 + r() * 0.07)); g.addColorStop(1, rgba(col, 0));
      x.fillStyle = g; x.fillRect(0, y - h, S, h * 2);
    }
    x.lineCap = 'round';
    for (let i = 0; i < 26; i++) {                                    // hairlines: very faint, broken, not continuous across the slab
      const y0 = r() * S, x0 = r() * S, len = S * (0.1 + r() * 0.3), a1 = 1 + r() * 3, k1 = 1 + ((r() * 3) | 0), p1 = r() * 6.28;
      x.beginPath(); for (let px = 0; px <= len; px += 12) { const y = y0 + a1 * Math.sin(k1 * px / len * 3 + p1); px ? x.lineTo((x0 + px) % S, y) : x.moveTo(x0, y); }
      x.strokeStyle = rgba(vein, 0.05 + r() * 0.08); x.lineWidth = 0.5 + r() * (S / 800); x.stroke();
    }
    for (let i = 0; i < S * 0.5; i++) {                               // pits and small voids, mostly elongated along the bedding
      const px = r() * S, py = r() * S, w = 0.6 + r() * (r() > 0.9 ? 7 : 2), h = 0.4 + r() * 0.9;
      x.fillStyle = rgba(r() > 0.3 ? vein : e, 0.15 + r() * 0.3); x.beginPath(); x.ellipse(px, py, w, h, 0, 0, 6.3); x.fill();
      x.fillStyle = rgba('--color-cream', 0.12); x.beginPath(); x.ellipse(px, py + h + 0.6, w, 0.4, 0, 0, 6.3); x.fill();
    }
    x.strokeStyle = rgba(vein, 0.45); x.lineWidth = 1.2;
    if (joint) for (let px = 0; px < S; px += joint) { x.beginPath(); x.moveTo(px, 0); x.lineTo(px, S); x.stroke(); }
    if (jointY) for (let py = 0; py < S; py += jointY) { x.beginPath(); x.moveTo(0, py); x.lineTo(S, py); x.stroke(); }
    if (ao) {
      const b = x.createLinearGradient(0, S, 0, S * (1 - 0.3 / ao)), t = x.createLinearGradient(0, 0, 0, S * (0.2 / ao));
      b.addColorStop(0, rgba(e, 0.32)); b.addColorStop(1, rgba(e, 0)); t.addColorStop(0, rgba(e, 0.18)); t.addColorStop(1, rgba(e, 0));
      x.fillStyle = b; x.fillRect(0, 0, S, S); x.fillStyle = t; x.fillRect(0, 0, S, S);
    }
    return c;
  });
}

/* ---------- wood ---------- */

/** Oak: grain runs down the canvas. tone: a colour token ('--color-caramel', '--color-walnut'); planks: boards across (0 = one sheet). */
export function oak(S, { seed = 2, tone = '--color-caramel', planks = 0, lift = 0 } = {}) {
  return memo(['oak', S, seed, tone, planks, lift], () => {
  const [c, x] = canvas(S), r = rng(seed);
  x.fillStyle = lift ? mix(tone, '--color-cream', lift) : tok(tone); x.fillRect(0, 0, S, S);
  const n = planks || 1, w = S / n;
  for (let i = 0; i < n; i++) {
    x.fillStyle = r() > 0.5 ? rgba('--color-espresso', r() * 0.1) : rgba('--color-cream', r() * 0.07); x.fillRect(i * w, 0, w, S);
    for (let k = 0; k < 26 * (w / 64 + 1); k++) {
      const gx = i * w + r() * w, wob = r() * 3, ph = r() * 6;
      x.beginPath(); x.moveTo(gx, 0);
      for (let y = 0; y <= S; y += 32) x.lineTo(gx + Math.sin(y / S * 6.28 + ph) * wob, y);
      x.strokeStyle = r() > 0.5 ? rgba('--color-espresso', 0.05 + r() * 0.12) : rgba('--color-cream', 0.03 + r() * 0.06); x.lineWidth = 0.5 + r() * 1.5; x.stroke();
    }
    if (planks) { x.fillStyle = rgba('--color-espresso', 0.5); x.fillRect(i * w, 0, 1.5, S); }
  }
  return c;
  });
}

/** Boards (sauna walls, ceiling, benches): n boards across, each slightly different, dark gaps. */
export function planks(S, { n = 8, color = '--color-cedar', seed = 3, gap = 0.45 } = {}) {
  return memo(['planks', S, n, color, seed, gap], () => {
  const [c, x] = canvas(S), r = rng(seed), w = S / n;
  for (let i = 0; i < n; i++) {
    x.fillStyle = r() > 0.5 ? mix(color, '--color-espresso', r() * 0.12) : mix(color, '--color-cream', r() * 0.08); x.fillRect(i * w, 0, w, S);
    for (let k = 0; k < 10; k++) {
      const gx = i * w + r() * w; x.beginPath(); x.moveTo(gx, 0);
      for (let y = 0; y <= S; y += 64) x.lineTo(gx + Math.sin(y / S * 9 + k) * 1.4, y);
      x.strokeStyle = rgba('--color-espresso', 0.05 + r() * 0.1); x.lineWidth = 0.6 + r(); x.stroke();
    }
    x.fillStyle = rgba('--color-espresso', gap); x.fillRect(i * w, 0, Math.max(1.5, S / 300), S);
  }
  return c;
  });
}

/** Fluted panelling: n vertical flutes, each shaded across its width. */
export function slats(S, { n = 24, tone = '--color-caramel' } = {}) {
  return memo(['slats', S, n, tone], () => {
  const [c, x] = canvas(S), w = S / n;
  for (let i = 0; i < n; i++) {
    const g = x.createLinearGradient(i * w, 0, (i + 1) * w, 0);
    g.addColorStop(0, mix(tone, '--color-espresso', 0.38)); g.addColorStop(0.3, mix(tone, '--color-cream', 0.08)); g.addColorStop(0.7, tok(tone)); g.addColorStop(1, mix(tone, '--color-espresso', 0.5));
    x.fillStyle = g; x.fillRect(i * w, 0, w + 1, S);
  }
  return c;
  });
}

/* ---------- soft things ---------- */

export function moss(S, seed = 4) {
  const [c, x] = canvas(S), r = rng(seed);
  x.fillStyle = mix('--color-moss', '--color-espresso', 0.25); x.fillRect(0, 0, S, S);
  for (let i = 0; i < S * 14; i++) {
    const t = r(); x.fillStyle = t < 0.3 ? mix('--color-moss', '--color-espresso', 0.4) : t < 0.8 ? tok('--color-moss') : mix('--color-moss', '--color-gold', 0.28);
    x.globalAlpha = 0.45 + r() * 0.4; x.beginPath(); x.arc(r() * S, r() * S, 1 + r() * (S / 90), 0, 6.3); x.fill();
  }
  x.globalAlpha = 1;
  return c;
}

/** Tufted pad: a grid of buttons with soft folds between them. */
export function quilting(S, { cells = 6 } = {}) {
  const [c, x] = canvas(S), w = S / cells, e = '--color-espresso';
  x.fillStyle = tok('--color-cream-raised'); x.fillRect(0, 0, S, S);
  for (let i = 0; i < cells; i++) for (let j = 0; j < cells; j++) {
    const cx = (i + 0.5) * w, cy = (j + 0.5) * w, g = x.createRadialGradient(cx, cy, 0, cx, cy, w * 0.75);
    g.addColorStop(0, rgba(e, 0.22)); g.addColorStop(0.12, rgba(e, 0.06)); g.addColorStop(0.55, rgba(e, 0)); g.addColorStop(1, rgba(e, 0.1));
    x.fillStyle = g; x.fillRect(i * w, j * w, w, w);
  }
  return c;
}

/** Round rug: fine ring grooves. */
export function rings(S) {
  const [c, x] = canvas(S), h = S / 2;
  x.fillStyle = tok('--color-cream'); x.fillRect(0, 0, S, S);
  for (let r = 4; r < h; r += 5) { x.strokeStyle = rgba('--color-caramel', 0.22 + 0.1 * Math.sin(r)); x.lineWidth = 1.6; x.beginPath(); x.arc(h, h, r, 0, 6.3); x.stroke(); }
  return c;
}

/* ---------- the reef ---------- */

/** The back of the tank: a deep blue water column with light rays, dark rock, colourful coral clusters, kelp and sand.
 *  TANK-ONLY palette (derived from the lounge render; the one place saturated colour is allowed). Far things fade toward the water blue. */
export const REEF = { top: '#3FA9F0', mid: '#1670C8', deep: '#07295E', rock: '#10264A', sand: '#C9B08A',
  coral: ['#8E4CC9', '#E8742A', '#F2C230', '#E24F8B', '#F3EEE2', '#4FB8D8'], green: ['#3E9A3A', '#7BB83A', '#2A6E3A'] };
export function reef(W, H, seed = 5) {
  const [c, x] = canvas(W, H), r = rng(seed), U = H / 512, water = REEF.mid;
  const g = x.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, REEF.top); g.addColorStop(0.35, REEF.mid); g.addColorStop(0.8, mix(REEF.mid, REEF.deep, 0.6)); g.addColorStop(1, REEF.deep);
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  x.globalCompositeOperation = 'screen';                            // light rays from above, slanting
  for (let i = 0; i < 9; i++) {
    const sx = r() * W * 1.1, w = (30 + r() * 80) * U, len = H * (0.55 + r() * 0.4), sl = (0.12 + r() * 0.18) * len, rg = x.createLinearGradient(0, 0, 0, len);
    rg.addColorStop(0, `rgba(160,220,255,${0.22 + r() * 0.16})`); rg.addColorStop(1, 'rgba(160,220,255,0)');
    x.fillStyle = rg; x.beginPath(); x.moveTo(sx, 0); x.lineTo(sx + w, 0); x.lineTo(sx + w - sl + w * 0.6, len); x.lineTo(sx - sl - w * 0.2, len); x.fill();
  }
  x.globalCompositeOperation = 'source-over';
  const fog = (col, d) => mix(col, water, d);
  const mound = (cx, base, w, h, col) => {
    x.fillStyle = col; x.beginPath(); x.moveTo(cx - w, base);
    for (let i = 0; i <= 10; i++) x.lineTo(cx - w + (i / 10) * w * 2, base - h * Math.sin(i / 10 * Math.PI) * (0.65 + r() * 0.35));
    x.lineTo(cx + w, base); x.fill();
  };
  const branch = (px, py, ang, len, wd, col, d) => {
    if (len < 3 * U || d > 5) return;
    const nx = px + Math.cos(ang) * len, ny = py + Math.sin(ang) * len;
    x.strokeStyle = col; x.lineWidth = wd; x.lineCap = 'round'; x.beginPath(); x.moveTo(px, py); x.lineTo(nx, ny); x.stroke();
    if (d > 2) { x.fillStyle = mix(col, '#FFFFFF', 0.25); x.beginPath(); x.arc(nx, ny, wd * 0.9, 0, 6.3); x.fill(); }
    branch(nx, ny, ang - 0.35 - r() * 0.3, len * 0.74, wd * 0.74, col, d + 1); branch(nx, ny, ang + 0.35 + r() * 0.3, len * 0.74, wd * 0.74, col, d + 1);
  };
  const brain = (cx, cy, rad, col) => {                             // a rounded coral head with polyps
    const gr = x.createRadialGradient(cx - rad * 0.3, cy - rad * 0.4, 0, cx, cy, rad); gr.addColorStop(0, mix(col, '#FFFFFF', 0.35)); gr.addColorStop(1, mix(col, REEF.deep, 0.35));
    x.fillStyle = gr; x.beginPath(); x.ellipse(cx, cy, rad, rad * 0.7, 0, 0, 6.3); x.fill();
    x.fillStyle = mix(col, '#FFFFFF', 0.5); for (let k = 0; k < 16; k++) { const a = r() * 6.3, d = Math.sqrt(r()) * 0.85; x.beginPath(); x.arc(cx + Math.cos(a) * rad * d, cy + Math.sin(a) * rad * 0.65 * d, U * (1.5 + r() * 2.5), 0, 6.3); x.fill(); }
  };
  const fan = (cx, by, h, col) => { x.strokeStyle = col; x.lineWidth = 1.6 * U; for (let k = -8; k <= 8; k++) { x.beginPath(); x.moveTo(cx, by); x.quadraticCurveTo(cx + k * h * 0.06, by - h * 0.6, cx + k * h * 0.1, by - h * (0.85 - Math.abs(k) * 0.02)); x.stroke(); } };
  const kelp = (gx, by, gh, col, wd) => { const sway = (r() - 0.5) * 80 * U; x.strokeStyle = col; x.lineWidth = wd; x.lineCap = 'round'; x.beginPath(); x.moveTo(gx, by); x.bezierCurveTo(gx + sway * 0.1, by - gh * 0.4, gx + sway, by - gh * 0.7, gx + sway * 0.6, by - gh); x.stroke(); };
  for (let layer = 0; layer < 3; layer++) {                         // far, middle, near
    const d = 0.62 - layer * 0.3, base = H * (0.66 + layer * 0.13), count = 6 + layer * 3, k = 1 + layer * 0.55;
    for (let i = 0; i < count; i++) {
      const cx = (i + r() * 0.8) / count * W, size = (50 + r() * 80) * U * k;
      mound(cx, base + 30 * U, size * 1.2, size * (0.6 + r() * 0.6), fog(REEF.rock, d * 0.7));
      const hue = REEF.coral[(r() * REEF.coral.length) | 0], t = r();
      if (t < 0.4) branch(cx, base - size * 0.1, -Math.PI / 2 + (r() - 0.5) * 0.5, size * 0.5, 7 * U * k, fog(hue, d), 0);
      else if (t < 0.8) { brain(cx, base - size * 0.25, size * 0.5, fog(hue, d)); brain(cx + size * 0.55, base - size * 0.1, size * 0.3, fog(REEF.coral[(r() * 6) | 0], d)); }
      else fan(cx, base, size * 0.9, fog(hue, d));
    }
    for (let i = 0; i < 14; i++) kelp(r() * W, H * (0.86 + layer * 0.04), (50 + r() * 120) * U * k, fog(REEF.green[(r() * 3) | 0], d * 0.7), (3 + r() * 3) * U * k);
  }
  const s = x.createLinearGradient(0, H * 0.9, 0, H);
  s.addColorStop(0, 'rgba(201,176,138,0)'); s.addColorStop(1, mix(REEF.sand, REEF.deep, 0.55)); x.fillStyle = s; x.fillRect(0, H * 0.9, W, H * 0.1);
  const vg = x.createRadialGradient(W / 2, H * 0.45, H * 0.45, W / 2, H * 0.5, W * 0.62); vg.addColorStop(0, 'rgba(7,41,94,0)'); vg.addColorStop(1, 'rgba(7,41,94,0.5)'); x.fillStyle = vg; x.fillRect(0, 0, W, H);
  return c;
}

/** Tileable caustic cells (cellular noise, bright where cells meet). White on black; the shader scrolls two copies. */
export function caustics(S = 128, seed = 6) {
  const [c, x] = canvas(S), r = rng(seed), N = 5, cell = S / N, pts = [];
  for (let i = 0; i < N * N; i++) pts.push([(i % N + r()) * cell, (((i / N) | 0) + r()) * cell]);
  const img = x.createImageData(S, S), d = img.data;
  for (let py = 0; py < S; py++) for (let px = 0; px < S; px++) {
    const ci = (px / cell) | 0, cj = (py / cell) | 0; let f1 = 1e9, f2 = 1e9;
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      const ii = (ci + di + N) % N, jj = (cj + dj + N) % N, p = pts[jj * N + ii];
      const ox = (ci + di < 0 ? -S : ci + di >= N ? S : 0), oy = (cj + dj < 0 ? -S : cj + dj >= N ? S : 0);
      const dist = Math.hypot(px - (p[0] + ox), py - (p[1] + oy));
      if (dist < f1) { f2 = f1; f1 = dist; } else if (dist < f2) f2 = dist;
    }
    const e = Math.max(0, 1 - (f2 - f1) / (cell * 0.22)), v = e * e * e * 255, k = (py * S + px) * 4;
    d[k] = d[k + 1] = d[k + 2] = v; d[k + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  return c;
}

/** Fish atlas, 512 x 256: 128 x 64 cells, 6 species. Species s uses row s>>1 and columns (s&1)*2 + frame (the frame is the tail wobble). Fish face right. */
export function fish() {
  const [c, x] = canvas(512, 256);
  const species = [                                                   // saturated tank fish, from the render: clownfish, blue tang, yellow tang, cyan, magenta, butterfly
    { body: '#FF6A10', fin: '#FF8A2A', stripe: '#FFFFFF' },
    { body: '#1E56E0', fin: '#FFD21E' },
    { body: '#FFD81E', fin: '#FFE866' },
    { body: '#6FD3EE', fin: '#2D8FD0', stripe: '#FFFFFF' },
    { body: '#B040D8', fin: '#FFD21E' },
    { body: '#FFB020', fin: '#2A5EE0', stripe: '#1B1B2A' },
  ];
  species.forEach((sp, s) => {
    for (let f = 0; f < 2; f++) {
      const ox = ((s & 1) * 2 + f) * 128, oy = (s >> 1) * 64, cx = ox + 54, cy = oy + 32, sw = f ? 7 : -7;
      x.fillStyle = sp.fin; x.beginPath(); x.moveTo(cx - 34, cy); x.lineTo(cx - 62, cy - 20 + sw); x.lineTo(cx - 58, cy + sw * 0.2); x.lineTo(cx - 62, cy + 20 + sw); x.fill();
      x.beginPath(); x.moveTo(cx - 8, cy - 18); x.quadraticCurveTo(cx + 8, cy - 34, cx + 24, cy - 15); x.fill();
      x.fillStyle = sp.body; x.beginPath(); x.ellipse(cx, cy, 40, 20, 0, 0, 6.3); x.fill();
      if (sp.stripe) { x.fillStyle = sp.stripe; [-14, 8].forEach((o) => { x.beginPath(); x.ellipse(cx + o, cy, 4, 18, 0, 0, 6.3); x.fill(); }); }
      x.fillStyle = '#10182A'; x.beginPath(); x.arc(cx + 24, cy - 4, 3.2, 0, 6.3); x.fill();
    }
  });
  return c;
}

/* ---------- the logo, from the page's own SVG ---------- */

const parseT = (t) => { const m = []; (t || '').replace(/(matrix|translate|scale)\(([^)]+)\)/g, (_, k, v) => { const n = v.split(/[ ,]+/).map(Number); m.push(k === 'matrix' ? n : k === 'scale' ? [n[0], 0, 0, n[n.length > 1 ? 1 : 0], 0, 0] : [1, 0, 0, 1, n[0], n[1] || 0]); }); return m; };   // scale() matters: the "SPA 99" letters sit in scaled groups

/** Reads every path of an inline SVG (viewBox plus the transforms on the path and its groups) into drawable items. */
function svgPaths(svg) {
  const vb = svg.getAttribute('viewBox').split(/[ ,]+/).map(Number);
  const items = [...svg.querySelectorAll('path')].map((p) => {
    const chain = []; for (let n = p; n && n !== svg; n = n.parentNode) chain.unshift(...parseT(n.getAttribute?.('transform')));
    return { d: new Path2D(p.getAttribute('d')), chain };
  });
  return { vb, items };
}

function blur(src, w, h, rad) {                                      // two box passes on a float field
  const tmp = new Float32Array(src.length), out = new Float32Array(src.length), k = 2 * rad + 1;
  for (let y = 0; y < h; y++) { let a = 0; const o = y * w; for (let i = -rad; i <= rad; i++) a += src[o + Math.min(w - 1, Math.max(0, i))]; for (let i = 0; i < w; i++) { tmp[o + i] = a / k; a += src[o + Math.min(w - 1, i + rad + 1)] - src[o + Math.max(0, i - rad)]; } }
  for (let i = 0; i < w; i++) { let a = 0; for (let y = -rad; y <= rad; y++) a += tmp[Math.min(h - 1, Math.max(0, y)) * w + i]; for (let y = 0; y < h; y++) { out[y * w + i] = a / k; a += tmp[Math.min(h - 1, y + rad + 1) * w + i] - tmp[Math.max(0, y - rad) * w + i]; } }
  return out;
}

/** Mask of a logo: { alpha, normal, halo: canvases, aspect: width / height }. kind: 'mark' (the swan, #tour-mark) or 'stacked' (swan above SPA 99, #tour-logo-stacked).
 *  px = height of the alpha mask (1024 desktop, 512 phone). alpha: white logo on black (use as alphaMap, it reads green). normal: tangent-space bump from the blurred mask.
 *  halo: the blurred mask on a transparent canvas (additive glow behind the lockup). The swan on the dry sauna glass uses alpha only. */
export function logo(kind, px, { normal = true, halo = false } = {}) {
  const svg = document.querySelector(kind === 'mark' ? '#tour-mark svg' : '#tour-logo-stacked svg');
  if (!svg) return null;
  const { vb, items } = svgPaths(svg), h = px, w = Math.round(px * vb[2] / vb[3]), s = h / vb[3];
  const [a, x] = canvas(w, h);
  x.fillStyle = '#000'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff';
  items.forEach(({ d, chain }) => { x.setTransform(s, 0, 0, s, -vb[0] * s, -vb[1] * s); chain.forEach((m) => x.transform(...m)); x.fill(d); });
  x.setTransform(1, 0, 0, 1, 0, 0);
  const out = { alpha: a, aspect: w / h };
  if (normal || halo) {
    const hw = w >> 1, hh = h >> 1, [sm, sx] = canvas(hw, hh); sx.drawImage(a, 0, 0, hw, hh);
    const rgba8 = sx.getImageData(0, 0, hw, hh).data, field = new Float32Array(hw * hh);
    for (let i = 0; i < field.length; i++) field[i] = rgba8[i * 4] / 255;
    if (normal) {
      const f = blur(field, hw, hh, Math.max(1, hh / 256)), [n, nx] = canvas(hw, hh), img = nx.createImageData(hw, hh), d = img.data, at = (i, j) => f[Math.min(hh - 1, Math.max(0, j)) * hw + Math.min(hw - 1, Math.max(0, i))];
      for (let j = 0; j < hh; j++) for (let i = 0; i < hw; i++) {
        const dx = (at(i + 1, j) - at(i - 1, j)) * 6, dy = (at(i, j + 1) - at(i, j - 1)) * 6, inv = 1 / Math.hypot(dx, dy, 1), k = (j * hw + i) * 4;
        d[k] = (-dx * inv * 0.5 + 0.5) * 255; d[k + 1] = (dy * inv * 0.5 + 0.5) * 255; d[k + 2] = (inv * 0.5 + 0.5) * 255; d[k + 3] = 255;
      }
      nx.putImageData(img, 0, 0); out.normal = n;
    }
    if (halo) {
      const f = blur(blur(field, hw, hh, Math.max(2, hh / 40)), hw, hh, Math.max(2, hh / 40)), [hc, hx] = canvas(hw, hh), img = hx.createImageData(hw, hh), d = img.data;
      for (let i = 0; i < f.length; i++) { d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = 255; d[i * 4 + 3] = Math.min(255, f[i] * 255 * 3.2); }
      hx.putImageData(img, 0, 0); out.halo = hc;
    }
  }
  return out;
}
