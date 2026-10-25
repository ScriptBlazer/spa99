/* Dry sauna (docs/design/VIRTUAL-TOUR.md 2.2). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Interior 4.5 x 4.0 x 2.6 (x -2.25..2.25, z -2..2), glass front on the south side with a corridor beyond (the door back to the relaxing zone). Cedar boards, a U of two-tier pale aspen
 * benches on the west, north and east walls (one instanced mesh of boards), warm LED lines under every bench lip and in a curved ceiling cove, the swan etched on the OUTSIDE
 * face of the glass only. The stove stands against the east wall: dark stone cladding, a glowing coal window, hot stones on top; a wooden bucket with a ladle holds coals and stones.
 * Low, warm and moody on purpose. Animated only by the fire's slow flicker (30 fps at rest). */

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), r = T.rng(21), wrap = { wrap: true };

  /* ----- maps (1 of our own: the cedar boards) ----- */
  const wallMap = T.tex(T.planks(S, { n: 26, color: '--color-cedar', seed: 5, gap: 0.5 }), wrap); await ctx.idle();
  scene.environment = ctx.env('--color-cedar');

  /* ----- materials ----- */
  const cedar = K.std(WHITE, { r: 0.85, map: wallMap }), board = K.std(WHITE, { r: 0.7 }), skirt = K.std('--color-aspen-shade', { r: 0.8 });
  const walnut = K.std('--color-walnut', { r: 0.6 }), oak = K.std('--color-caramel', { r: 0.6 }), floor = K.std('--color-floor-stone', { r: 0.9 }), duck = K.std('--color-aspen-shade', { r: 0.85 });
  const steel = K.std('--color-glass-bronze', { r: 0.3, m: 0.9 }), rock = K.std('--color-stone-dark', { r: 0.92 }), mortar = K.std(K.col('--color-stone-dark').clone().multiplyScalar(0.55), { r: 1 });
  const led = K.basic('--color-led-warm'), ledD = K.basic('--color-led-warm', { side: THREE.DoubleSide }), fire = K.hot('--color-heater-glow', 1.25), fireBase = fire.color.clone();
  const glassCol = K.col('--color-glass-bronze'), glassA = K.alpha('--color-glass-bronze');
  const glass = K.std(glassCol, { r: 0.05, transparent: true, opacity: Math.max(0.2, glassA), depthWrite: false, side: THREE.DoubleSide, envMapIntensity: 1.2 });
  const corr = K.std(K.col('--color-travertine').clone().multiplyScalar(0.5), { r: 0.8 }), lit = K.basic(K.col('--color-travertine').clone().multiplyScalar(0.9));
  const X0 = -2.25, X1 = 2.25, Z0 = -2, Z1 = 2, H = 2.6;

  /* an LED line along a polyline of [x, z] points: small boxes, merged (no tube class in the vendored build) */
  const ledLine = (pts, y, th = 0.016, mat = led) => pts.forEach((a, i) => {
    const b = pts[i + 1]; if (!b) return;
    const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz);
    K.box(len + 0.004, th, th, mat, (a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2, { ry: Math.atan2(-dz, dx) });
  });
  const cove = (d, rad, y, mat) => {                                         // east wall, round the north-east corner, along the north wall, round the north-west corner, down the west wall
    const e = X1 - d, w = X0 + d, n = Z0 + d, pts = [[e, 1.2]];
    for (let i = 0; i <= 8; i++) { const t = i / 8 * PI / 2; pts.push([e - rad + rad * Math.cos(t), n + rad - rad * Math.sin(t)]); }
    for (let i = 0; i <= 8; i++) { const t = i / 8 * PI / 2; pts.push([w + rad - rad * Math.sin(t), n + rad - rad * Math.cos(t)]); }
    pts.push([w, 1.2]); ledLine(pts, y, 0.016, mat);
  };

  /* ----- shell ----- */
  K.plane(4.5, 4, floor, 0, 0, 0, 'up');
  for (let i = 0; i < 46; i++) K.box(0.09, 0.02, 3.96, duck, X0 + 0.07 + i * 0.1, 0.012, 0, { tile: 1 });          // duckboard slats
  K.plane(4, H, cedar, X0, H / 2, 0, 'e', { tile: 2.6 }); K.plane(4, H, cedar, X1, H / 2, 0, 'w', { tile: 2.6 });
  K.plane(4.5, H, cedar, 0, H / 2, Z0, 's', { tile: 2.6 }); K.plane(4.5, 4, cedar, 0, H, 0, 'down', { tile: 2.6 });
  for (let i = 0; i < 2; i++) K.box(0.04, 0.04, 3.96, cedar, i ? 2.23 : -2.23, H - 0.02, 0, { tile: 2.6 });       // ceiling edge battens

  /* ----- the glass front (south): fixed panel, door opening (x 1.35..2.05), door leaf swung back along the opening's west edge ----- */
  K.plane(3.6, H, glass, -0.45, H / 2, Z1, 's'); K.plane(0.2, H, glass, 2.15, H / 2, Z1, 's'); K.plane(0.7, 2.04, glass, 1.4, 1.05, 1.65, 'e');
  [[X0 + 0.03, 0.06], [1.35, 0.05], [2.05, 0.05], [X1 - 0.03, 0.06]].forEach(([x, w]) => K.box(w, H, 0.06, walnut, x, H / 2, Z1));
  K.box(4.5, 0.06, 0.06, walnut, 0, H - 0.03, Z1); K.box(4.5, 0.05, 0.06, walnut, 0, 0.025, Z1);
  K.put(new THREE.CylinderGeometry(0.014, 0.014, 0.9, 10), steel, { x: 1.37, y: 1.0, z: 1.4 });
  K.put(new THREE.BoxGeometry(0.06, 0.08, 0.02), steel, { x: 1.7, y: 2.3, z: Z1 }); K.put(new THREE.BoxGeometry(0.06, 0.08, 0.02), steel, { x: 1.7, y: 0.3, z: Z1 });
  const lock = ctx.logo('mark', { normal: false });
  if (lock) {                                                                // the swan: outside face only (front-facing plane looking south), so it is never seen mirrored
    const hh = 1.05, m = new THREE.MeshBasicMaterial({ color: K.col('--color-cream'), alphaMap: T.tex(lock.alpha, { color: false }), transparent: true, opacity: 0.85, depthWrite: false });
    const sw = new THREE.Mesh(new THREE.PlaneGeometry(hh * lock.aspect, hh), m); sw.position.set(-0.45, 1.3, Z1 + 0.012); sw.renderOrder = 3; scene.add(sw);
  }

  /* ----- the corridor beyond the glass (the settle starts out here) ----- */
  K.plane(5, 2.6, corr, 0, 0, 3.3, 'up'); K.plane(5, 2.6, corr, 0, H, 3.3, 'down');
  K.plane(2.6, H, corr, -2.5, H / 2, 3.3, 'e'); K.plane(2.6, H, corr, 2.5, H / 2, 3.3, 'w');
  K.plane(5, H, lit, 0, H / 2, 4.6, 'n');
  K.plane(0.25, H, corr, -2.375, H / 2, Z1, 's'); K.plane(0.25, H, corr, 2.375, H / 2, Z1, 's');

  /* ----- benches: a U on the west, north and east walls. Two tiers 0.6 deep: upper seat 0.90 (against the wall), lower 0.45. Boards are one instanced mesh ----- */
  const bd = [], add = (cx, cy, cz, sx, sy, sz) => bd.push([cx, cy, cz, sx, sy, sz]);
  const seat = (x0, x1, z0, z1, top, alongZ) => {                            // seat boards 0.088 wide, 0.012 gaps, 0.03 thick
    const depth = alongZ ? x1 - x0 : z1 - z0, n = Math.round(depth / 0.1), w = depth / n - 0.012;
    for (let i = 0; i < n; i++) { const c = (alongZ ? x0 : z0) + (i + 0.5) * depth / n; if (alongZ) add(c, top - 0.015, (z0 + z1) / 2, w, 0.03, z1 - z0); else add((x0 + x1) / 2, top - 0.015, c, x1 - x0, 0.03, w); }
  };
  const block = (x0, x1, z0, z1, top) => K.box(x1 - x0 - 0.02, top - 0.03, z1 - z0 - 0.02, skirt, (x0 + x1) / 2, (top - 0.03) / 2, (z0 + z1) / 2);
  const lip = (x, z, y, len, alongZ, hx, hz, hy) => {                        // an LED under a seat edge and its pool of light
    if (alongZ) { K.led(0.014, 0.014, len, x, y, z); K.glowPlane(0.7, len + 0.3, hx, hy, hz, 'up', 0.38); } else { K.led(len, 0.014, 0.014, x, y, z); K.glowPlane(len + 0.3, 0.7, hx, hy, hz, 'up', 0.38); }
  };
  seat(X0, X1, Z0, -1.4, 0.9, false); block(X0, X1, Z0, -1.4, 0.9); seat(-1.05, 1.05, -1.4, -0.8, 0.45, false); block(-1.05, 1.05, -1.4, -0.8, 0.45);
  lip(0, -1.405, 0.84, 3.3, false, 0, -1.1, 0.456); lip(0, -0.805, 0.39, 2.1, false, 0, -0.45, 0.008);
  for (const [s, zE] of [[-1, 0.9], [1, -0.2]]) {                            // west bench runs to z 0.9; the east one stops at -0.2 for the stove
    const len = zE + 1.4, zc = (zE - 1.4) / 2, a = Math.min(s * 2.25, s * 1.65), b = Math.max(s * 2.25, s * 1.65), c = Math.min(s * 1.65, s * 1.05), d = Math.max(s * 1.65, s * 1.05);
    seat(a, b, -1.4, zE, 0.9, true); block(a, b, -1.4, zE, 0.9); seat(c, d, -1.4, zE, 0.45, true); block(c, d, -1.4, zE, 0.45);
    lip(s * 1.655, zc, 0.84, len, true, s * 1.37, zc, 0.456); lip(s * 1.055, zc, 0.39, len, true, s * 0.72, zc, 0.008);
    K.box(0.6, 0.9, 0.04, walnut, s * 1.95, 0.45, zE + 0.02); K.box(0.6, 0.45, 0.04, walnut, s * 1.35, 0.225, zE + 0.02);
    for (let i = 0; i < 4; i++) add(s * 2.23, 1.0 + i * 0.14, (zE - 2) / 2, 0.04, 0.09, zE + 2);        // backrest boards, 0.95 to 1.4
  }
  for (let i = 0; i < 4; i++) add(0, 1.0 + i * 0.14, Z0 + 0.02, 4.46, 0.09, 0.04);
  const bt = K.col('--color-aspen'), bs = K.col('--color-aspen-shade');
  const boards = K.inst(new THREE.BoxGeometry(1, 1, 1), board, bd.length, (i, o) => { const q = bd[i]; o.position.set(q[0], q[1], q[2]); o.scale.set(q[3], q[4], q[5]); });
  bd.forEach((q, i) => boards.setColorAt(i, bt.clone().lerp(bs, r() * 0.5)));
  boards.instanceColor.needsUpdate = true;

  /* LED lines: a light line on the three walls at 1.8, a curved cove line on the ceiling, and a halo for each wall */
  cove(0.03, 0.4, 1.8); cove(0.12, 0.7, H - 0.04, ledD);
  K.glowPlane(3.9, 0.9, X0 + 0.01, 1.75, -0.1, 'e', 0.4); K.glowPlane(4.4, 0.9, 0, 1.75, Z0 + 0.01, 's', 0.4); K.glowPlane(2.4, 0.9, X1 - 0.01, 1.75, -1.0, 'w', 0.35);
  K.shadow(1.4, 3.3, -1.5, -0.3, 0.45); K.shadow(2.5, 1.2, 0, -1.4, 0.4); K.shadow(1.4, 2.2, 1.5, -1.0, 0.4);
  [[-1.0, -0.6], [0.3, 0.6], [1.0, -0.6]].forEach(([x, z]) => K.put(new THREE.CircleGeometry(0.04, 14), led, { x, y: H - 0.003, z, rx: PI / 2 }));

  /* ----- the stove, against the east wall, facing west: dark stone cladding on a steel plinth, a coal window, a basket of stones on top ----- */
  const HX = 1.9, HZ = 0.5;
  K.box(0.6, 0.78, 0.8, rock, HX, 0.41, HZ); K.box(0.64, 0.04, 0.84, steel, HX, 0.02, HZ);
  [0.24, 0.44, 0.64].forEach((y) => K.box(0.61, 0.012, 0.81, mortar, HX, y, HZ));                       // courses of stone
  K.box(0.012, 0.78, 0.012, mortar, HX - 0.3, 0.41, HZ - 0.13); K.box(0.012, 0.78, 0.012, mortar, HX - 0.3, 0.41, HZ + 0.15);
  [[0, -0.4, 0.64, 0.04], [0, 0.4, 0.64, 0.04], [-0.3, 0, 0.04, 0.84], [0.3, 0, 0.04, 0.84]].forEach(([x, z, w, d]) => K.box(w, 0.06, d, steel, HX + x, 0.83, HZ + z));    // basket rim
  K.box(0.04, 0.04, 0.56, steel, HX - 0.3, 0.17, HZ); K.box(0.04, 0.04, 0.56, steel, HX - 0.3, 0.49, HZ); K.box(0.04, 0.36, 0.04, steel, HX - 0.3, 0.33, HZ - 0.28); K.box(0.04, 0.36, 0.04, steel, HX - 0.3, 0.33, HZ + 0.28);   // coal window frame
  K.plane(0.52, 0.3, fire, HX - 0.303, 0.33, HZ, 'w');                                                     // the coals, white-hot core
  K.shadow(1.1, 1.2, HX - 0.1, HZ, 0.5);
  const fglow = [K.glowPlane(1.0, 0.7, HX - 0.34, 0.33, HZ, 'w', 0.6, '--color-heater-glow'), K.glowPlane(1.1, 1.3, HX - 0.8, 0.01, HZ, 'up', 0.35, '--color-heater-glow'), K.glowPlane(0.6, 0.7, HX, 0.9, HZ, 'up', 0.35, '--color-heater-glow')];

  /* the bucket: oak staves, steel hoops, a rope handle, coals and stones inside (the ladle lies beside it) */
  const BX = 1.15, BZ = 1.0;
  K.put(new THREE.CylinderGeometry(0.19, 0.16, 0.34, 14, 1, true), K.std('--color-caramel', { r: 0.6, side: THREE.DoubleSide }), { x: BX, y: 0.18, z: BZ });
  K.put(new THREE.CircleGeometry(0.16, 12), walnut, { x: BX, y: 0.03, z: BZ, rx: -PI / 2 });
  [0.07, 0.28].forEach((y) => K.put(new THREE.CylinderGeometry(0.19 - (0.34 - y) * 0.088 + 0.004, 0.19 - (0.34 - y) * 0.088 + 0.004, 0.02, 14, 1, true), steel, { x: BX, y: y + 0.01, z: BZ }));
  K.put(new THREE.TorusGeometry(0.17, 0.008, 5, 14, PI), walnut, { x: BX, y: 0.35, z: BZ, rx: 0 });
  K.put(new THREE.CylinderGeometry(0.012, 0.012, 0.5, 6), oak, { x: BX + 0.55, y: 0.016, z: BZ, rz: PI / 2 });
  K.put(new THREE.SphereGeometry(0.05, 8, 5, 0, 2 * PI, 0, PI / 2), oak, { x: BX + 0.28, y: 0.05, z: BZ, rx: PI });
  K.shadow(0.6, 0.6, BX, BZ, 0.4);

  /* stones (heater top and bucket) and embers (coal window and bucket): two instanced meshes, flickered in update() */
  const nS = tier === 'high' ? 70 : 46, nB = 12, dark = K.col('--color-stone-dark'), pale = K.col('--color-stone');
  const stones = K.inst(new THREE.SphereGeometry(1, 5, 4), K.std(WHITE, { r: 0.85, m: 0.05 }), nS + nB, (i, o) => {
    const a = r() * 6.28, rr = Math.sqrt(r()), k = 0.04 + r() * 0.03, B = i >= nS, R = B ? 0.11 : 0.27;
    const px = (B ? BX : HX) + (B ? R : 0.4 * R) * rr * Math.cos(a), pz = (B ? BZ : HZ) + (B ? R : 1.2 * R) * rr * Math.sin(a), py = B ? 0.27 + 0.03 * (1 - rr * rr) : 0.86 + 0.06 * (1 - rr * rr);
    o.position.set(px, py, pz); o.rotation.set(r() * 3, r() * 3, r() * 3); o.scale.set(k * (1 + r() * 0.4), k * 0.8, k * (1 + r() * 0.3));
  });
  for (let i = 0; i < nS + nB; i++) stones.setColorAt(i, dark.clone().lerp(pale, r() * r() * 0.8));
  stones.instanceColor.needsUpdate = true;
  const nE = 20, coalMat = K.basic(WHITE), hotC = K.col('--color-heater-glow');
  const coals = K.inst(new THREE.SphereGeometry(1, 5, 4), coalMat, nE, (i, o) => {
    const B = i >= 14, k = 0.03 + r() * 0.025;
    if (B) o.position.set(BX + (r() - 0.5) * 0.18, 0.285, BZ + (r() - 0.5) * 0.18); else o.position.set(HX - 0.31, 0.2 + r() * 0.26, HZ + (r() - 0.5) * 0.44);
    o.rotation.set(r() * 3, r() * 3, r() * 3); o.scale.set(k, k * 0.8, k);
  });
  for (let i = 0; i < nE; i++) coals.setColorAt(i, hotC.clone().multiplyScalar(i % 3 ? 0.6 + r() * 0.6 : 1.4));
  coals.instanceColor.needsUpdate = true;
  await ctx.idle();

  K.flush();

  /* ----- light (2700K): low and pooled; hemisphere kept dim so the corners stay dark ----- */
  K.hemi('--color-led', '--color-floor-stone', 0.32);
  K.light('--color-light-warm', 2.2, 3.6, -1.3, 1.75, 0.3);                  // backrest wash, west
  K.light('--color-light-warm', 2.2, 3.6, 0.3, 1.75, -1.8);                  // backrest wash, north
  const fl = K.light('--color-heater-glow', 1.0, 2.6, HX - 0.5, 0.6, HZ), fl0 = fl ? fl.intensity : 0;   // the light of the fire
  K.light('--color-light-warm', 1.0, 2.4, -0.6, 0.35, 0, true);              // under the lower bench (dropped on the mobile tier)

  function update(dt, t) {                                                    // slow, uneven flicker: three sines out of step, never a blink
    const f = 0.88 + 0.07 * Math.sin(t * 5.3) + 0.04 * Math.sin(t * 11.7 + 1) + 0.03 * Math.sin(t * 19.1 + 2);
    fire.color.copy(fireBase).multiplyScalar(f); coalMat.color.setScalar(0.8 + (f - 0.88) * 2.5);
    fglow[0].material.opacity = 0.6 * f; fglow[1].material.opacity = 0.35 * f; fglow[2].material.opacity = 0.35 * f; if (fl) fl.intensity = fl0 * (0.85 + (f - 0.88) * 1.6);
  }
  update(0, 1);

  return {
    view: { pos: [-0.6, 1.6, 1.7], yaw: 42, pitch: -12 },
    exposure: 0.9, ambient: true, update,
    arrive: { pos: [1.7, 1.6, 4.35], yaw: 0, pitch: -1, ms: 2400, input: 1200 },     // from the corridor, through the open door, then the turn toward the benches and the stove
    markers: [{ to: 'relaxing-zone', at: [1.7, 1.1, Z1] }],
  };
}
