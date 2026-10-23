/* Builder kit for tour rooms (docs/design/VIRTUAL-TOUR.md 2.0): the small helpers every room uses, so a room module stays short.
 * The engine makes one per room and hands it over as `ctx.K`. Static geometry is baked and merged per material when you call K.flush()
 * (so a room is a handful of draw calls); things that move or are instanced go through K.add().
 * Units are metres, y up, x east, z south. Every colour is a token name ('--color-sage') or a THREE.Color.
 * Lights are authored in the brief's units (intensity "2", distance "3"); LIGHT_GAIN turns them into three's physical units.
 *
 * SHARED LOOK DEFAULTS (every room inherits these; the lounge is the reference, tuned against .private/fal-renders/lounge.png):
 *   tone mapping   Linear (engine.js, no curve), default exposure 0.8 (DEFAULTS.exposure). Nothing glows by itself; colours above 1 clip.
 *   ambient        low and dark-footed: K.baseLight() = hemisphere sky --color-led over an espresso ground at 0.28, scene.environmentIntensity 0.3.
 *                  Rooms are lit by a few warm PRACTICALS (cove, downlight, sconce, LED under furniture) that pool, never by a flat fill.
 *   albedo         pale stone/cream surfaces are tinted to ~0.75-0.8 of the token (DEFAULTS.stone) so they sit under the light instead of clipping.
 *   self-lit       only LED lines, glass, windows and glow use K.basic/K.hot. K.hot(c) is a >1 colour that tone-maps to a white-hot core with a warm edge.
 *   grounding      K.shadow() under furniture, K.edge() along wall-floor junctions (the dark line where a floor meets a wall), ao baked into wall maps.
 *   water/tank     saturated blue is allowed only inside a tank; it is the brightest, most saturated thing in its room.
 */
import * as THREE from '../../vendor/three/three.module.min.js';
import { mergeGeometries } from '../../vendor/three/three.module.min.js';
import { tok, rgbOf, shared } from './textures.js';

export const LIGHT_GAIN = Math.PI;        // one number to tune every room's brightness together
export const DEFAULTS = { exposure: 0.8, hemi: 0.28, env: 0.3, stone: 0.78 };

export function makeKit(scene, { tier = 'high' } = {}) {
  const colours = {}, pending = new Map(), tmp = new THREE.Object3D();
  const maxLights = tier === 'high' ? 4 : 3;
  let lights = 0;

  const K = {
    THREE, scene, tier,
    /** Token (or Color) -> THREE.Color. */
    col(c) {
      if (c && c.isColor) return c;
      if (colours[c]) return colours[c];
      const [r, g, b] = rgbOf(c);
      return (colours[c] = new THREE.Color().setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace));
    },
    /** Alpha of an rgb(r g b / a) token (glass). */
    alpha: (name) => { const n = tok(name).match(/[\d.]+/g); return n && n.length > 3 ? +n[3] : 1; },

    /* ----- materials ----- */
    /** MeshStandardMaterial. o: r roughness, m metalness, plus any material option (map, normalMap, alphaMap, transparent, opacity, side ...). */
    std(c, { r = 0.8, m = 0, ...o } = {}) { return new THREE.MeshStandardMaterial({ color: K.col(c), roughness: r, metalness: m, ...o }); },
    /** Self-lit (LED strips, downlights, doorway glow): ignores lights. */
    basic(c, o = {}) { return new THREE.MeshBasicMaterial({ color: K.col(c), ...o }); },
    /** Additive glow: a soft radial halo (white map) tinted by colour. */
    glow(c = '--color-led-warm', a = 0.5) { return new THREE.MeshBasicMaterial({ color: K.col(c), map: shared('halo'), transparent: true, opacity: a, blending: THREE.AdditiveBlending, depthWrite: false }); },

    /* ----- static geometry (baked, merged by material at flush) ----- */
    /** Bake `geo` into the room. o: x y z (position), rx ry rz (radians), tile (metres per texture repeat: world-space UVs, so veins keep their scale across pieces). */
    put(geo, mat, { x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, tile = 0 } = {}) {
      tmp.position.set(x, y, z); tmp.rotation.set(rx, ry, rz); tmp.updateMatrix();
      geo.applyMatrix4(tmp.matrix);
      if (tile) K.worldUV(geo, tile);
      if (!pending.has(mat)) pending.set(mat, []);
      pending.get(mat).push(geo);
      return geo;
    },
    box(w, h, d, mat, x, y, z, o = {}) { return K.put(new THREE.BoxGeometry(w, h, d), mat, { x, y, z, ...o }); },
    /** A vertical or horizontal plane. face: 'n' 's' 'e' 'w' (the direction it faces) 'up' 'down'. */
    plane(w, h, mat, x, y, z, face = 's', o = {}) {
      const rot = { s: [0, 0], n: [0, Math.PI], e: [0, Math.PI / 2], w: [0, -Math.PI / 2], up: [-Math.PI / 2, 0], down: [Math.PI / 2, 0] }[face];
      return K.put(new THREE.PlaneGeometry(w, h), mat, { x, y, z, rx: rot[0], ry: rot[1], ...o });
    },
    /** Rounded-rectangle extrude, centred: pillows, cushions. w x h face, d thick, corner radius r, bevel b. */
    rbox(w, h, d, r = 0.05, b = 0.03) {
      const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
      s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0); s.lineTo(x + w, y + h - r); s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2);
      s.lineTo(x + r, y + h); s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI); s.lineTo(x, y + r); s.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
      const g = new THREE.ExtrudeGeometry(s, { depth: Math.max(0.001, d - 2 * b), bevelEnabled: true, bevelThickness: b, bevelSize: b, bevelSegments: 2, curveSegments: 5 });
      g.translate(0, 0, -(d - 2 * b) / 2);
      return g;
    },
    /** A ring sector standing on the floor, extruded up: sofas, curved benches. Angles in degrees in the x-z plane (0 = +x, 90 = +z). Centre cx, cz. */
    sector(r0, r1, a0, a1, h, cx = 0, cz = 0, y = 0, b = 0) {
      const pts = [], n = Math.max(8, Math.round(Math.abs(a1 - a0) / 4)), p = (r, a) => new THREE.Vector2(r * Math.cos(a * Math.PI / 180), -r * Math.sin(a * Math.PI / 180));
      for (let i = 0; i <= n; i++) pts.push(p(r1, a0 + (a1 - a0) * i / n));
      for (let i = n; i >= 0; i--) pts.push(p(r0, a0 + (a1 - a0) * i / n));
      const g = new THREE.ExtrudeGeometry(new THREE.Shape(pts), { depth: Math.max(0.001, h - 2 * b), bevelEnabled: b > 0, bevelThickness: b, bevelSize: b, bevelSegments: 2 });
      g.rotateX(-Math.PI / 2); g.translate(cx, y + b, cz);
      return g;
    },
    /** Self-lit LED strip as a thin box, optionally with a halo on a surface: halo = { w, h, x, y, z, face, a }. */
    led(w, h, d, x, y, z, halo, mat) {
      K.box(w, h, d, mat || (K.ledMat ||= K.basic('--color-led-warm')), x, y, z);
      if (halo) K.glowPlane(halo.w, halo.h, halo.x, halo.y, halo.z, halo.face || 'up', halo.a ?? 0.4, halo.c);
    },
    /** Additive halo plane (its own draw call; keep few). */
    glowPlane(w, h, x, y, z, face = 'up', a = 0.4, c) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), K.glow(c, a)), rot = { s: [0, 0], n: [0, Math.PI], e: [0, Math.PI / 2], w: [0, -Math.PI / 2], up: [-Math.PI / 2, 0], down: [Math.PI / 2, 0] }[face];
      m.position.set(x, y, z); m.rotation.set(rot[0], rot[1], 0); m.renderOrder = 2; scene.add(m); return m;
    },
    /** Self-lit but hot: colour pushed past 1 so the tone map clips the core to near white and leaves a warm edge (LED lines, filaments). */
    hot(c = '--color-led-warm', k = 1.9, o = {}) { return new THREE.MeshBasicMaterial({ color: K.col(c).clone().multiplyScalar(k), ...o }); },
    /** A pale surface colour scaled to DEFAULTS.stone (or k) so it does not clip under light. Returns a THREE.Color. */
    tint(c, k = DEFAULTS.stone) { return K.col(c).clone().multiplyScalar(k); },
    /** The dark line where a floor meets a wall: a soft strip on the floor from (x, z) running len along (ux, uz), spreading width toward (nx, nz). */
    edge(x, z, ux, uz, len, nx, nz, width = 0.5, a = 0.5, y = 0.003) {
      K.edgeMat ||= new THREE.MeshBasicMaterial({ map: shared('edge'), transparent: true, depthWrite: false, side: THREE.DoubleSide });
      const P = [[x, z], [x + ux * len, z + uz * len], [x + nx * width, z + nz * width], [x + ux * len + nx * width, z + uz * len + nz * width]];
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(P.flatMap((p) => [p[0], y, p[1]]), 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 1, 1], 2));
      g.setIndex([0, 1, 2, 1, 3, 2]);
      (K.edges ||= []).push(g); K.edgeA = a; return g;
    },
    /** Contact shadow under furniture: one soft espresso plane, just above the floor. */
    shadow(w, d, x, z, a = 0.42, y = 0.004) {
      K.shadowMat ||= new THREE.MeshBasicMaterial({ map: shared('shadow'), transparent: true, depthWrite: false, opacity: a });
      const g = new THREE.PlaneGeometry(w, d); g.rotateX(-Math.PI / 2); g.translate(x, y, z);
      (K.shadows ||= []).push(g);
    },

    /* ----- things that move, or are instanced ----- */
    add(obj, x, y, z) { if (x !== undefined) obj.position.set(x, y, z); scene.add(obj); return obj; },
    /** InstancedMesh: fn(i, o) positions the helper Object3D `o` for instance i. */
    inst(geo, mat, n, fn) {
      const m = new THREE.InstancedMesh(geo, mat, n);
      for (let i = 0; i < n; i++) { tmp.position.set(0, 0, 0); tmp.rotation.set(0, 0, 0); tmp.scale.set(1, 1, 1); fn(i, tmp); tmp.updateMatrix(); m.setMatrixAt(i, tmp.matrix); }
      m.instanceMatrix.needsUpdate = true; scene.add(m); return m;
    },

    /* ----- lights (the brief's authored units) ----- */
    /** PointLight; null (nothing made) over the tier's cap or when `optional` on a non-high tier. */
    light(c, intensity, distance, x, y, z, optional = false) {
      if (lights >= maxLights || (optional && tier !== 'high')) return null;
      lights++;
      const l = new THREE.PointLight(K.col(c), intensity * LIGHT_GAIN, distance, 2); l.position.set(x, y, z); scene.add(l); return l;
    },
    /** The shared ambient: dark-footed hemisphere. Call once per room. */
    baseLight(i = DEFAULTS.hemi) { return K.hemi('--color-led', '--color-espresso', i); },
    hemi(sky, ground, intensity) { const l = new THREE.HemisphereLight(K.col(sky), K.col(ground), intensity * LIGHT_GAIN); scene.add(l); return l; },

    /** A doorway you can see through: an open box beyond the wall opening, its back lit in the next room's main colour so the eye is drawn through.
     *  [x, z] = centre of the opening on the wall, face = which way you look through it ('e' 'w' 's' 'n'), w x h the opening, depth how far it runs, y0 its floor. */
    vista(color, [x, z], face, w, h, depth = 0.9, y0 = 0) {
      const [fx, fz] = { e: [1, 0], w: [-1, 0], s: [0, 1], n: [0, -1] }[face], px = Math.abs(fz), pz = Math.abs(fx), cy = y0 + h / 2, t = 0.02;
      const lit = K.basic(K.col(color).clone().multiplyScalar(1.15)), side = K.basic(K.col(color).clone().multiplyScalar(0.55));
      const dx = Math.abs(fx), dz = Math.abs(fz), mx = x + fx * depth / 2, mz = z + fz * depth / 2;
      K.box(dx * t + px * w, h, dz * t + pz * w, lit, x + fx * depth, cy, z + fz * depth);                 // back
      K.box(dx * depth + t * px, h, dz * depth + t * pz, side, mx + px * w / 2, cy, mz + pz * w / 2);       // sides
      K.box(dx * depth + t * px, h, dz * depth + t * pz, side, mx - px * w / 2, cy, mz - pz * w / 2);
      K.box(dx * depth + px * w, t, dz * depth + pz * w, side, mx, y0, mz);                                 // floor
      K.box(dx * depth + px * w, t, dz * depth + pz * w, side, mx, y0 + h, mz);                             // ceiling
    },

    /** Merge everything baked with put/box/plane into one mesh per material, and the contact shadows into one. Call once, at the end of build. */
    flush() {
      pending.forEach((geos, mat) => {
        const idx = geos.map((g) => g.index !== null);
        const list = idx.every(Boolean) ? geos : geos.map((g) => (g.index ? g.toNonIndexed() : g));
        list.forEach((g) => { for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k); if (!g.attributes.uv) g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2)); });
        const merged = list.length === 1 ? list[0] : mergeGeometries(list, false);
        if (merged) scene.add(new THREE.Mesh(merged, mat)); else list.forEach((g) => scene.add(new THREE.Mesh(g, mat)));
      });
      pending.clear();
      if (K.edges) { K.edgeMat.opacity = K.edgeA; const m = new THREE.Mesh(mergeGeometries(K.edges), K.edgeMat); m.renderOrder = 1; scene.add(m); K.edges = null; }
      if (K.shadows) { const m = new THREE.Mesh(mergeGeometries(K.shadows), K.shadowMat); m.renderOrder = 1; scene.add(m); K.shadows = null; }
    },

    /** World-space UVs for flat faces by normal (x-facing: z,y; z-facing: x,y; y-facing: x,z), `tile` metres per repeat. */
    worldUV(geo, tile) {
      const p = geo.attributes.position, n = geo.attributes.normal, uv = geo.attributes.uv;
      for (let i = 0; i < p.count; i++) {
        const ax = Math.abs(n.getX(i)), ay = Math.abs(n.getY(i)), az = Math.abs(n.getZ(i));
        if (ay >= ax && ay >= az) uv.setXY(i, p.getX(i) / tile, p.getZ(i) / tile);
        else if (ax >= az) uv.setXY(i, p.getZ(i) / tile, p.getY(i) / tile);
        else uv.setXY(i, p.getX(i) / tile, p.getY(i) / tile);
      }
      uv.needsUpdate = true;
    },
  };
  return K;
}
