/* The Gold Card in three.js (docs/design/GOLD-CARD-3D.md). Loaded lazily by scenes.js, only on capable desktops, over the CSS card.
 * Contract (IMMERSIVE 14.3): create(mount, { gsap, ScrollTrigger, tokens, card }) -> { ready, start, stop, dispose }.
 *  - `card` is the shared pose proxy that scenes.js tweens (ry, rx, turn, tiltX, tiltY, roll, bob, lift, drop, sheen, draw, line, relief, fade).
 *    This file only reads it, so the CSS card and the canvas are always in the same pose.
 *  - The swan, the engraved words and the back pattern are not downloaded: they are drawn from the same SVG paths the page already has
 *    (the CSS card's own swan) into canvas maps, turned into a normal map, a roughness map and a draw map, once, in idle slots.
 *  - Light is a warm studio built in code (PMREM), no environment file. Colours come from the CSS tokens, never from this file.
 *  - dispose() is idempotent: ticker, observers, listeners, every geometry, material, texture and the PMREM target, renderer, context, canvas.
 * Debug still: `?gc-export=1` with `data-gc-export` on the mount renders the rest pose (GOLD-CARD-3D 4.3) at 2560x1920 on espresso.
 */
import * as THREE from '../vendor/three/three.module.min.js';

const W = 85.6, H = 54, R = 3.18, BEV = 0.18, DEPTH = 0.44;       // millimetres: ISO ID-1
const FW = 1024, FH = 646, BW = 1024, BH = 646;                    // face and back map sizes
const D2R = Math.PI / 180;
// THE LOOK (one block to tune; 2026-10-23 contrast pass, see docs/design/GOLD-CARD-3D.md 7.5). The metal only shows what the studio gives it:
// dark walls = the deep bronze reflections, small very bright panels = the crisp highlights that sweep across as the card turns.
//   wall/floor/fill: the dark parts (multipliers of --color-gold-studio; fill = side, overhead and behind panels). Lower = deeper shadow, never 0 (never black).
//   key/strip/rim: the highlights (multipliers; the strip is the sweeping glint). Higher = brighter, crisper peaks.
//   face/edge/back/light: reflection strength per surface and the key light. exposure: tone mapping. mood/period/peak: Home only, the extra dim and brighten with the turn.
const LOOK = {
  hero: { wall: 0.2,  floor: 0.12, fill: 0.55, key: 5, strip: 14, rim: 12, exposure: 1,    face: 0.95, edge: 0.95, back: 0.85, light: 0.4,  mood: 0,    period: 36, peak: 0 },
  home: { wall: 0.12, floor: 0.08, fill: 0.4,  key: 4, strip: 12, rim: 10, exposure: 0.95, face: 0.9,  edge: 0.9,  back: 0.8,  light: 0.35, mood: 0.35, period: 36, peak: 2 },
};
const idle = (fn) => new Promise((resolve) => (window.requestIdleCallback ? requestIdleCallback(() => resolve(fn()), { timeout: 800 }) : setTimeout(() => resolve(fn()), 0)));

function roundedRect(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - r); s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2, false);
  s.lineTo(x + r, y + h); s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + r); s.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5, false);
  return s;
}

/** A face: the inset outline (the bevel sits outside it) with UVs 0..1 across it. */
function faceGeometry() {
  const g = new THREE.ShapeGeometry(roundedRect(W - 2 * BEV, H - 2 * BEV, R - BEV), 10);
  const pos = g.attributes.position, uv = g.attributes.uv, fw = W - 2 * BEV, fh = H - 2 * BEV;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) + fw / 2) / fw, (pos.getY(i) + fh / 2) / fh);
  return g;
}

/* ---------- maps (canvas, from the page's own SVG paths) ---------- */

function paths(mount) {
  return [...mount.querySelectorAll('.gc-swan .mark-line path')].map((p) => ({
    el: p, d: new Path2D(p.getAttribute('d')), m: (p.getAttribute('transform').match(/-?[\d.]+(?:e-?\d+)?/g) || []).map(Number), len: p.getTotalLength(),
  }));
}
const fillPaths = (ctx, list, base) => list.forEach(({ d, m }) => { ctx.setTransform(...base); ctx.transform(...m); ctx.fill(d); });

/** viewBox -2 -2 330 484 -> a face of `px` px per mm: the swan is 32 mm tall, 8 mm from the top, centred. */
function swanBase(ppm, cx) {
  const s = (32 * ppm) / 484;
  return [s, 0, 0, s, cx - 165 * s + 2 * s, 8 * ppm + 2 * s];
}

function mask(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#fff'; ctx.strokeStyle = '#fff';
  draw(ctx);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const rgba = ctx.getImageData(0, 0, w, h).data, out = new Float32Array(w * h);
  for (let i = 0; i < out.length; i++) out[i] = rgba[i * 4] / 255;
  return out;
}

/** Tracked text on a canvas (ctx.letterSpacing is not everywhere). */
function track(ctx, text, x, y, space, align = 'left') {
  const widths = [...text].map((ch) => ctx.measureText(ch).width + space);
  const total = widths.reduce((a, b) => a + b, 0) - space;
  let cx = align === 'right' ? x - total : align === 'center' ? x - total / 2 : x;
  [...text].forEach((ch, i) => { ctx.fillText(ch, cx, y); cx += widths[i]; });
}

function blur(src, w, h, r) {
  const tmp = new Float32Array(src.length), out = new Float32Array(src.length), k = 2 * r + 1;
  for (let y = 0; y < h; y++) {
    let acc = 0; const row = y * w;
    for (let x = -r; x <= r; x++) acc += src[row + Math.min(w - 1, Math.max(0, x))];
    for (let x = 0; x < w; x++) { tmp[row + x] = acc / k; acc += src[row + Math.min(w - 1, x + r + 1)] - src[row + Math.max(0, x - r)]; }
  }
  for (let x = 0; x < w; x++) {
    let acc = 0;
    for (let y = -r; y <= r; y++) acc += tmp[Math.min(h - 1, Math.max(0, y)) * w + x];
    for (let y = 0; y < h; y++) { out[y * w + x] = acc / k; acc += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x]; }
  }
  return out;
}

function canvasTexture(canvas, { color = false, aniso = 4 } = {}) {
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = aniso;
  t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter;
  return t;
}

/** Sobel on a height field -> a tangent-space normal map (strength in height units per pixel). */
function normalCanvas(height, w, h, strength) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d'), img = ctx.createImageData(w, h), d = img.data;
  const at = (x, y) => height[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const dx = (at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1) - at(x - 1, y - 1) - 2 * at(x - 1, y) - at(x - 1, y + 1)) * strength;
    const dy = (at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1) - at(x - 1, y - 1) - 2 * at(x, y - 1) - at(x + 1, y - 1)) * strength;
    const inv = 1 / Math.hypot(dx, dy, 1), i = (y * w + x) * 4;
    d[i] = (-dx * inv * 0.5 + 0.5) * 255; d[i + 1] = (dy * inv * 0.5 + 0.5) * 255; d[i + 2] = (inv * 0.5 + 0.5) * 255; d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

/** Roughness (green channel): field with a hairline brush, `smooth` areas polished, `rough` areas engraved. */
function roughCanvas(w, h, base, { smooth, rough, smoothV, roughV, dark = 0 }) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d'), img = ctx.createImageData(w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    const streak = (Math.random() - 0.5) * 0.016;
    for (let x = 0; x < w; x++) {
      const i = y * w + x, p = (i) * 4;
      let v = base + streak + (Math.random() - 0.5) * 0.006;
      if (smooth) v += (smoothV - base) * smooth[i];
      if (rough) v += (roughV - base) * rough[i];
      d[p] = 255; d[p + 1] = Math.max(0, Math.min(255, v * 255)); d[p + 2] = 255 * (1 - dark * (rough ? rough[i] : 0)); d[p + 3] = 255;   // blue = metalness: engraved areas are a little less metal, so they read darker, not as a lit rim
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}


/** Fine detail on the face, in mm on a face of `ppm` px per mm: guilloche (crossing fine waves, only in two wings either side of the swan),
 *  a groove 3 mm in from the edge, and micro text along the top. The same drawing is in guilloche.svg for the CSS card. */
function detail(ctx, ppm, { wings, groove, micro }) {
  const fw = W - 2 * BEV, fh = H - 2 * BEV;
  if (wings) {
    ctx.lineWidth = 0.1 * ppm;
    for (let fam = 0; fam < 2; fam++) for (let k = 0; k < 30; k++) {
      ctx.beginPath();
      for (let x = 4; x <= fw - 4; x += 0.5) {
        const y = 8 + k * 1.25 + 1.5 * Math.sin((x / 26) * Math.PI * 2 + k * 0.16 * (fam ? -1 : 1) + fam * 1.6);
        x === 4 ? ctx.moveTo(x * ppm, y * ppm) : ctx.lineTo(x * ppm, y * ppm);
      }
      ctx.stroke();
    }
  }
  if (groove) {
    ctx.lineWidth = 0.34 * ppm;
    const r = (R - BEV - 3) * ppm, x = 3 * ppm, y = 3 * ppm, w = (fw - 6) * ppm, h = (fh - 6) * ppm;
    ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.max(r, 1)); ctx.stroke();
  }
  if (micro) {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.textBaseline = 'alphabetic'; ctx.font = `500 ${1.15 * ppm}px Figtree`;
    track(ctx, 'BEYOND LUXURY  \u00B7  SPA 99  \u00B7  LONDON N4', fw / 2 * ppm, 5.6 * ppm, 0.42 * 1.15 * ppm, 'center');
  }
}

/* ---------- the module ---------- */

export function create(mount, { gsap, tokens, card }) {
  const tok = (name) => new THREE.Color(tokens(name));
  const look = LOOK[mount.dataset.goldCard] || LOOK.hero;
  const exporting = new URLSearchParams(location.search).has('gc-export') && mount.hasAttribute('data-gc-export');
  const box = mount.querySelector('.gc-gl');
  const disposables = [];
  const own = (o) => { disposables.push(o); return o; };
  let renderer = null, scene = null, camera = null, group = null, pivot = null, light = null, pmrem = null, studio = null;
  let canvas = null, io = null, ro = null, tick = null, mats = {};
  let inView = true, running = false, dead = false, shown = false;
  let lastKey = '', lastDrawKey = '', lastT = 0, slow = 0, dpr = 1, frames = 0;
  const swan = paths(mount);
  const maps = {};

  const camDistance = () => ((W / 0.72) * 0.75 / 2) / Math.tan(10 * D2R);

  /* --- face and back maps, one per idle slot --- */
  const fontsReady = () => Promise.all([document.fonts.load('600 40px Signika'), document.fonts.load('500 20px Figtree')]).catch(() => {});

  async function buildFace() {
    await fontsReady();
    const ppm = FW / (W - 2 * BEV);
    const swanMask = await idle(() => mask(FW, FH, (ctx) => fillPaths(ctx, swan, swanBase(ppm, FW / 2))));
    const textMask = await idle(() => mask(FW, FH, (ctx) => {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.textBaseline = 'alphabetic';
      ctx.font = `600 ${(2.4 / 0.7) * ppm}px Signika`;
      track(ctx, 'SPA 99', 6 * ppm, FH - 6 * ppm, 0.06 * (2.4 / 0.7) * ppm);
      ctx.font = `500 ${(1.6 / 0.7) * ppm}px Figtree`;
      track(ctx, 'GOLD', FW - 6 * ppm, FH - 6 * ppm, 0.24 * (1.6 / 0.7) * ppm, 'right');
    }));
    const fine = await idle(() => {
      const fw = W - 2 * BEV, wing = (x, y) => 1 - Math.max(0, Math.min(1, (x - 0.24 * fw) / (0.17 * fw))) * Math.max(0, Math.min(1, (0.76 * fw - x) / (0.17 * fw)));   // 1 in the wings, 0 behind the swan
      const lines = mask(FW, FH, (ctx) => detail(ctx, ppm, { wings: true })), edge = mask(FW, FH, (ctx) => detail(ctx, ppm, { groove: true })), micro = mask(FW, FH, (ctx) => detail(ctx, ppm, { micro: true }));
      for (let i = 0; i < lines.length; i++) lines[i] *= wing(((i % FW) / ppm), 0);
      return { lines, edge, micro };
    });
    // Two normal maps. The swan and the engraved words grow with `relief` (normalScale); the fine detail (edge groove, guilloche, micro text)
    // is the card's own finish, in the CSS card from the first frame, so it has its own map at a fixed strength (added in the shader, see buildScene).
    const height = await idle(() => {
      const raw = new Float32Array(swanMask.length);
      for (let i = 0; i < raw.length; i++) raw[i] = swanMask[i] - 0.22 * textMask[i];   // engraved words: a shallow cut; the read comes from the ink (metalness) map, so no lit outline
      return blur(raw, FW, FH, 2);
    });
    const fineHeight = await idle(() => {
      const thin = new Float32Array(swanMask.length);
      for (let i = 0; i < thin.length; i++) thin[i] = -0.3 * fine.edge[i] - 0.1 * fine.lines[i] - 0.1 * fine.micro[i];
      return blur(thin, FW, FH, 1);
    });
    maps.faceFine = canvasTexture(await idle(() => normalCanvas(fineHeight, FW, FH, 4.2)));
    own(maps.faceFine);
    maps.faceNormal = canvasTexture(await idle(() => normalCanvas(height, FW, FH, 4.2)));
    const rc = await idle(() => roughCanvas(FW, FH, 0.21, { smooth: blur(swanMask, FW, FH, 1), smoothV: 0.1, rough: blur(textMask.map((v, i) => Math.max(v, fine.micro[i])), FW, FH, 1), roughV: 0.3, dark: 0.95 }));
    maps.faceRough = canvasTexture(rc);
    own(maps.faceNormal); own(maps.faceRough);
  }

  async function buildBack() {
    const ppm = BW / (W - 2 * BEV);
    const pat = await idle(() => mask(BW, BH, (ctx) => {
      const s = (4 * ppm) / 484;                                    // each swan 4 mm tall
      for (let row = -1; row < H / 12 + 1; row++) for (let col = -1; col < W / 10 + 1; col++) {
        const x = (col + (row % 2 ? 0.5 : 0)) * 10 * ppm, y = row * 12 * ppm;
        if (y > 40 * ppm) continue;                                  // a clear band under the pattern for the engraved words
        fillPaths(ctx, swan, [s, 0, 0, s, x + 2 * s, y + 2 * s]);
      }
    }));
    const words = await idle(() => mask(BW, BH, (ctx) => {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.font = `500 ${(1.4 / 0.7) * ppm}px Figtree`;
      track(ctx, 'BEYOND LUXURY', BW / 2, BH - 6 * ppm, 0.2 * (1.4 / 0.7) * ppm, 'center');
    }));
    const height = await idle(() => {
      const raw = new Float32Array(pat.length);
      for (let i = 0; i < raw.length; i++) raw[i] = 0.5 * pat[i] - 0.12 * words[i];   // the swans are embossed (raised, a little lighter); the words are a shallow cut
      return blur(raw, BW, BH, 2);
    });
    maps.backNormal = canvasTexture(await idle(() => normalCanvas(height, BW, BH, 3.2)));
    maps.backRough = canvasTexture(await idle(() => roughCanvas(BW, BH, 0.42, { smooth: blur(pat, BW, BH, 2), smoothV: 0.2, rough: blur(words, BW, BH, 1), roughV: 0.3, dark: 0.9 })));
    own(maps.backNormal); own(maps.backRough);
  }

  /* --- the draw map (emissive): the line, redrawn only while it is drawing --- */
  const drawCanvas = document.createElement('canvas'); drawCanvas.width = FW; drawCanvas.height = FH;
  const dctx = drawCanvas.getContext('2d');
  function drawLine() {
    const key = card.draw.toFixed(3);
    if (key === lastDrawKey) return;
    lastDrawKey = key;
    const ppm = FW / (W - 2 * BEV), base = swanBase(ppm, FW / 2);
    dctx.setTransform(1, 0, 0, 1, 0, 0); dctx.clearRect(0, 0, FW, FH); dctx.fillStyle = '#000'; dctx.fillRect(0, 0, FW, FH);
    dctx.strokeStyle = '#fff'; dctx.lineCap = 'round'; dctx.lineJoin = 'round'; dctx.lineWidth = (0.35 * ppm) / base[0];
    swan.forEach(({ d, m, len }, i) => {
      const f = Math.max(0, Math.min(1, (card.draw * 0.7 - 0.1 * i) / 0.4));
      if (f <= 0) return;
      dctx.setTransform(...base); dctx.transform(...m);
      dctx.setLineDash(f >= 1 ? [] : [len * f, len * 2]);
      dctx.stroke(d);
    });
    maps.draw.needsUpdate = true;
  }

  /* --- the studio (environment) --- */
  function buildEnvironment() {
    studio = new THREE.Scene();
    const part = (w, h, hex, k, x, y, z) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: tok(hex).multiplyScalar(k) }));
      m.position.set(x, y, z); m.lookAt(0, 0, 0); studio.add(m);
    };
    studio.add(new THREE.Mesh(new THREE.BoxGeometry(10, 6, 10), new THREE.MeshBasicMaterial({ color: tok('--color-gold-studio').multiplyScalar(look.wall), side: THREE.BackSide })));   // warm walls: the face never meets black
    part(2.6, 0.9, '--color-led', look.key, -2.5, 2.4, 3);        // key softbox
    part(0.2, 5, '--color-gold-studio', look.strip, 0, 0, 4.5);         // the sheen strip
    part(0.15, 4, '--color-led', look.rim, 4, 0.5, -1);         // rim strip
    part(1.6, 4, '--color-gold-studio', 1.4 * look.fill, -4.6, 0, 0.5); part(1.6, 4, '--color-gold-studio', 1.4 * look.fill, 4.6, 0, 1);   // side fills: a soft panel is always in reach at grazing angles
    part(5, 5, '--color-gold-studio', 1.1 * look.fill, 0, 2.9, 0.5);  // overhead fill
    part(6, 3, '--color-gold-studio', 1.6 * look.fill, 0, 0, -4.6);   // behind: lights the back of the card
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(8, 8), new THREE.MeshBasicMaterial({ color: tok('--color-gold-studio').multiplyScalar(look.floor) }));
    floor.rotation.x = -Math.PI / 2; floor.position.y = -2.9; studio.add(floor);
    pmrem = new THREE.PMREMGenerator(renderer);
    const rt = pmrem.fromScene(studio, 0.02);
    scene.environment = rt.texture; scene.environmentIntensity = 1;
    own(rt);
    studio.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    pmrem.dispose(); pmrem = null; studio = null;
  }

  /* --- scene --- */
  function buildScene() {
    const gold = tok('--color-gold-metal').lerp(tok('--color-gold-light'), 0.6);   // champagne: lit by a neutral warm studio it stays soft gold (hue 33), not orange
    const rim = tok('--color-gold-metal').lerp(tok('--color-gold-light'), 0.3);
    const edgeGeo = own(new THREE.ExtrudeGeometry(roundedRect(W - 2 * BEV, H - 2 * BEV, R - BEV), { depth: DEPTH, bevelEnabled: true, bevelThickness: BEV, bevelSize: BEV, bevelSegments: 3, curveSegments: 10 }));
    edgeGeo.translate(0, 0, -DEPTH / 2);
    const zf = DEPTH / 2 + BEV + 0.004;
    maps.draw = own(canvasTexture(drawCanvas, { color: true }));
    mats.edge = own(new THREE.MeshPhysicalMaterial({ color: rim, metalness: 1, roughness: 0.2 }));
    mats.face = own(new THREE.MeshPhysicalMaterial({
      color: gold, metalness: 1, roughness: 1, anisotropy: 0.55, anisotropyRotation: Math.PI / 2, clearcoat: 0.35, clearcoatRoughness: 0.12,
      normalMap: maps.faceNormal, roughnessMap: maps.faceRough, metalnessMap: maps.faceRough, emissive: tok('--color-gold-light'), emissiveMap: maps.draw, emissiveIntensity: 0,
    }));
    const bronze = tok('--color-gold-deep').lerp(tok('--color-gold-metal'), 0.22);
    bronze.g += 0.03; bronze.b += 0.075;                                              // NeutralToneMapping takes ~0.04 off the weakest channel: a dark metal would go orange without this
    mats.back = own(new THREE.MeshPhysicalMaterial({
      color: bronze, metalness: 1, roughness: 1, envMapIntensity: look.back, clearcoat: 0.2, clearcoatRoughness: 0.3, normalMap: maps.backNormal, roughnessMap: maps.backRough, metalnessMap: maps.backRough,
    }));
    mats.face.onBeforeCompile = (shader) => {   // the fine detail is added on top of the relief map, whatever `relief` is
      shader.uniforms.fineMap = { value: maps.faceFine };
      shader.fragmentShader = shader.fragmentShader.replace('#include <common>', 'uniform sampler2D fineMap;\n#include <common>')
        .replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\n#ifdef USE_NORMALMAP_TANGENTSPACE\n\tvec3 fineN = texture2D( fineMap, vNormalMapUv ).xyz * 2.0 - 1.0;\n\tnormal = normalize( normal + tbn * vec3( fineN.xy / fineN.z, 0.0 ) );\n#endif');
    };
    Object.assign(mats.face, { envMap: scene.environment, envMapIntensity: look.face }); mats.back.envMap = mats.edge.envMap = scene.environment; mats.edge.envMapIntensity = look.edge;   // per-material intensity needs the map set on the material (three r163+)
    const faceGeo = own(faceGeometry());
    const front = new THREE.Mesh(faceGeo, mats.face); front.position.z = zf;
    const back = new THREE.Mesh(faceGeo, mats.back); back.rotation.y = Math.PI; back.position.z = -zf;
    const body = new THREE.Mesh(edgeGeo, mats.edge);
    group = new THREE.Group(); group.add(body, front, back);
    pivot = new THREE.Group(); pivot.add(group);
    scene.add(pivot);
    light = new THREE.DirectionalLight(tok('--color-led'), look.light);
    light.position.set(-30, 40, 120);
    scene.add(light);
  }

  /* --- frame --- */
  function pose() {
    const turn = card.ry + card.turn + card.tiltY, up = card.rx + card.tiltX;
    group.rotation.set(-up * D2R, turn * D2R, 0);
    pivot.rotation.z = -card.roll * D2R;
    pivot.position.y = -(card.bob / 100) * H;                      // lift and drop move the whole mount in CSS (gc.render), so the canvas moves with the card
    mats.face.emissiveIntensity = card.line * card.draw > 0 ? card.line * 1.15 : 0;
    const k = card.relief;
    mats.face.normalMap && mats.face.normalScale.set(k, k);
    const sweep = card.sheen * 68 * D2R;
    scene.environmentRotation.y = sweep;
    light.position.set(-30 * Math.cos(sweep) + 120 * Math.sin(sweep), 40, 120 * Math.cos(sweep) + 30 * Math.sin(sweep));
    if (look.mood) {
      // shadow and highlight: bright at `peak` degrees and every `period` after, darkest halfway between (Home: mid at rest, dark near -16 and 20, bright near 2)
      const glint = 0.5 + 0.5 * Math.cos(((turn - look.peak) * 2 * Math.PI) / look.period);
      const m = 1 - look.mood * (1 - glint);
      mats.face.envMapIntensity = look.face * m; mats.edge.envMapIntensity = look.edge * m; mats.back.envMapIntensity = look.back * m;
      light.intensity = look.light * m;
    }
    drawLine();
  }

  /** The canvas is wider than the card (1/0.72) and taller than a 4:3 frame, so the turn, tilt and float never reach its edge. The card stays 72% of the canvas width at any aspect. */
  function fit(aspect) {
    camera.aspect = aspect;
    camera.fov = 2 * Math.atan(W / 0.72 / aspect / 2 / camDistance()) / D2R;
    camera.updateProjectionMatrix();
  }

  function size() {
    const w = box.clientWidth || 1, h = box.clientHeight || 1;
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
    fit(w / h);
  }

  function render() {
    pose();
    renderer.render(scene, camera);
  }

  function loop(_, deltaMs) {
    if (!running || !inView || document.hidden || dead) return;
    const t = performance.now();
    const key = [card.ry, card.rx, card.turn, card.tiltX, card.tiltY, card.sheen, card.draw, card.line, card.relief, card.lift, card.drop, card.fade].map((v) => v.toFixed(3)).join();
    const moving = key !== lastKey;
    // Full rate while the pose changes (scroll, pointer, load); 30 fps when only the idle float moves.
    if (!moving && t - lastT < 32) return;
    lastKey = key; lastT = t;
    const t0 = performance.now();
    render();
    // If the machine is struggling (three slow frames in a row), drop the pixel ratio to 1.
    if (++frames > 6 && dpr > 1) { slow = performance.now() - t0 > 20 ? slow + 1 : 0; if (slow >= 3) { dpr = 1; size(); } }
  }

  /* --- the debug still --- */
  function exportStill() {
    card.ry = 0; card.rx = 0; card.turn = 0; card.tiltX = card.tiltY = 0; card.roll = 0; card.bob = 0; card.lift = card.drop = 0;
    card.sheen = 0.13; card.draw = 1; card.line = 0; card.relief = 1; card.fade = 1;
    renderer.setClearColor(tok('--color-espresso'), 1);
    renderer.setPixelRatio(1); renderer.setSize(2560, 1920, false);
    fit(4 / 3);
    render();
    window.__gcExport = canvas.toDataURL('image/png');
    canvas.toBlob((b) => { const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(b), download: 'gold-card-master.png' }); a.click(); });
  }

  /* --- lifecycle --- */
  const ready = (async () => {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance', preserveDrawingBuffer: exporting });
    canvas = renderer.domElement;
    renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = look.exposure; renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(20, 4 / 3, 100, 600);
    camera.position.set(0, 0, camDistance());
    canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); dispose(); });
    await buildFace(); if (dead) return;
    await buildBack(); if (dead) return;
    await idle(buildEnvironment); if (dead) return;
    await idle(buildScene); if (dead) return;
    box.append(canvas);
    mount.classList.add('has-gl');
    size();
    lastDrawKey = '';
    await idle(() => { render(); renderer.compile?.(scene, camera); render(); });
    if (dead) return;
    if (exporting) return exportStill();
    ro = new ResizeObserver(() => { if (!dead) { size(); lastKey = ''; } }); ro.observe(box);
    io = new IntersectionObserver(([e]) => { inView = e.isIntersecting; lastKey = ''; }, { rootMargin: '10% 0px' }); io.observe(mount);
    tick = loop; gsap.ticker.add(tick);
    running = true;
    // Hand-over: the canvas fades in over the CSS card (same proxy, same pose); the CSS card then rests under it.
    gsap.to(canvas, { opacity: 1, duration: parseFloat(getComputedStyle(mount).getPropertyValue('--duration-gl-in')) || 1.2, ease: 'soft', onComplete: () => { shown = true; if (!dead) { card.gl = true; mount.classList.add('is-gl'); } } });
  })();

  function dispose() {
    if (dead) return;
    dead = true; running = false;
    if (tick) gsap.ticker.remove(tick);
    io?.disconnect(); ro?.disconnect();
    if (canvas) gsap.killTweensOf(canvas);
    disposables.forEach((o) => o.dispose?.());
    mats = {}; Object.keys(maps).forEach((k) => maps[k]?.dispose?.());
    pmrem?.dispose();
    studio?.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    if (renderer) { renderer.dispose(); renderer.forceContextLoss(); }
    canvas?.remove();
    mount.classList.remove('has-gl', 'is-gl');
    card.gl = false; card.render?.();
  }

  return { ready, start() { running = !dead; }, stop() { running = false; }, dispose, get info() { return renderer?.info; } };
}
