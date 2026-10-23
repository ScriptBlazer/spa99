/* Dry sauna (docs/design/VIRTUAL-TOUR.md 2.2). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Interior 2.93 x 4.34 x 2.10 (x -1.46..1.46, z -2.17..2.17), glass front on the south side with a corridor beyond. Cedar boards, an L of pale aspen benches
 * (west and north), warm LED lines pooled on the wood, the heater with its stones in the north-east corner, the swan etched on the OUTSIDE face of the glass only.
 * Low, warm and moody on purpose: dark corners, light only where the LEDs and the heater put it. Static: it renders on demand. */

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), r = T.rng(21), wrap = { wrap: true };

  /* ----- maps (4 of our own) ----- */
  const wallMap = T.tex(T.planks(S, { n: 26, color: '--color-cedar', seed: 5, gap: 0.5 }), wrap); await ctx.idle();
  const aspenMap = T.tex(T.planks(S >> 1, { n: 4, color: '--color-aspen', seed: 8, gap: 0.3 }), wrap);
  const aspenAlong = aspenMap.clone(); aspenAlong.center.set(0.5, 0.5); aspenAlong.rotation = PI / 2; aspenAlong.needsUpdate = true;   // grain along x for the north bench
  const shadeMap = T.tex(T.planks(S >> 1, { n: 14, color: '--color-aspen-shade', seed: 9, gap: 0.45 }), wrap);
  scene.environment = ctx.env('--color-cedar');

  /* ----- materials ----- */
  const cedar = K.std(WHITE, { r: 0.85, map: wallMap }), aspen = K.std(WHITE, { r: 0.7, map: aspenMap }), aspenN = K.std(WHITE, { r: 0.7, map: aspenAlong });
  const skirt = K.std(WHITE, { r: 0.8, map: shadeMap }), walnut = K.std('--color-walnut', { r: 0.6 }), oak = K.std('--color-caramel', { r: 0.6 });
  const floor = K.std('--color-floor-stone', { r: 0.9 }), duck = K.std('--color-aspen-shade', { r: 0.85 });
  const tray = K.std('--color-walnut', { r: 0.5, m: 0.4 }), steel = K.std('--color-glass-bronze', { r: 0.3, m: 0.9 });
  const led = K.basic('--color-led-warm'), ledD = K.basic('--color-led-warm', { side: THREE.DoubleSide });
  const glassCol = K.col('--color-glass-bronze'), glassA = K.alpha('--color-glass-bronze');
  const glass = K.std(glassCol, { r: 0.05, transparent: true, opacity: Math.max(0.2, glassA), depthWrite: false, side: THREE.DoubleSide, envMapIntensity: 1.2 });
  const corr = K.std(K.col('--color-travertine').clone().multiplyScalar(0.5), { r: 0.8 });
  const lit = K.basic(K.col('--color-travertine').clone().multiplyScalar(0.9));
  const X0 = -1.46, X1 = 1.46, Z0 = -2.17, Z1 = 2.17, H = 2.1;

  /* an LED line along a polyline of [x, z] points: small boxes, merged (no tube class in the vendored build) */
  const ledLine = (pts, y, th = 0.016, mat = led) => pts.forEach((a, i) => {
    const b = pts[i + 1]; if (!b) return;
    const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz);
    K.box(len + 0.004, th, th, mat, (a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2, { ry: Math.atan2(-dz, dx) });
  });
  const rim = (inset, rad) => {                                              // west wall, round the north-west corner, along the north wall
    const wx = X0 + inset, nz = Z0 + inset, pts = [];
    for (let z = 1.4; z > Z0 + rad + inset; z -= 0.4) pts.push([wx, z]);
    for (let i = 0; i <= 8; i++) { const t = i / 8 * PI / 2; pts.push([wx + rad - rad * Math.cos(t), nz + rad - rad * Math.sin(t)]); }
    for (let x = wx + rad + 0.4; x < 1.2; x += 0.4) pts.push([x, nz]);
    pts.push([1.2, nz]); return pts;
  };

  /* ----- shell ----- */
  K.plane(2.93, 4.34, floor, 0, 0, 0, 'up');
  for (let i = 0; i < 28; i++) K.box(0.09, 0.02, 4.3, duck, X0 + 0.07 + i * 0.1, 0.012, 0, { tile: 1 });          // duckboard slats
  K.plane(4.34, H, cedar, X0, H / 2, 0, 'e', { tile: 2.34 }); K.plane(4.34, H, cedar, X1, H / 2, 0, 'w', { tile: 2.34 });
  K.plane(2.93, H, cedar, 0, H / 2, Z0, 's', { tile: 2.34 }); K.plane(2.93, 4.34, cedar, 0, H, 0, 'down', { tile: 2.34 });
  for (let i = 0; i < 2; i++) K.box(0.04, 0.04, 4.3, cedar, i ? 1.44 : -1.44, H - 0.02, 0, { tile: 2.34 });       // ceiling edge battens

  /* ----- the glass front (south): fixed panel, door opening, door leaf swung flat against the east wall ----- */
  K.plane(2.01, H, glass, -0.455, H / 2, Z1, 's');
  K.plane(0.7, 2.04, glass, 1.215, 1.05, 1.82, 'e');
  [[X0 + 0.03, 0.06], [0.55, 0.05], [1.25, 0.05], [X1 - 0.03, 0.06]].forEach(([x, w]) => K.box(w, H, 0.06, walnut, x, H / 2, Z1));
  K.box(2.93, 0.06, 0.06, walnut, 0, H - 0.03, Z1); K.box(2.93, 0.05, 0.06, walnut, 0, 0.025, Z1);
  K.put(new THREE.CylinderGeometry(0.014, 0.014, 0.9, 10), steel, { x: 1.18, y: 1.0, z: 1.52 });
  K.put(new THREE.BoxGeometry(0.06, 0.08, 0.02), steel, { x: 0.57, y: 1.9, z: Z1 }); K.put(new THREE.BoxGeometry(0.06, 0.08, 0.02), steel, { x: 0.57, y: 0.3, z: Z1 });
  const lock = ctx.logo('mark', { normal: false });
  if (lock) {                                                                // the swan: outside face only (front-facing plane looking south), so it is never seen mirrored
    const hh = 0.95, m = new THREE.MeshBasicMaterial({ color: K.col('--color-cream'), alphaMap: T.tex(lock.alpha, { color: false }), transparent: true, opacity: 0.85, depthWrite: false });
    const sw = new THREE.Mesh(new THREE.PlaneGeometry(hh * lock.aspect, hh), m); sw.position.set(-0.45, 1.25, Z1 + 0.012); sw.renderOrder = 3; scene.add(sw);
  }

  /* ----- the corridor beyond the glass (the settle starts out here) ----- */
  K.plane(4, 2.63, corr, 0, 0, 3.485, 'up'); K.plane(4, 2.63, corr, 0, 2.4, 3.485, 'down');
  K.plane(2.63, 2.4, corr, -2, 1.2, 3.485, 'e', {}); K.plane(2.63, 2.4, corr, 2, 1.2, 3.485, 'w', {});
  K.plane(4, 2.4, lit, 0, 1.2, 4.8, 'n');
  K.plane(0.54, 2.4, corr, -1.73, 1.2, Z1, 's'); K.plane(0.54, 2.4, corr, 1.73, 1.2, Z1, 's'); K.plane(2.93, 0.3, corr, 0, 2.25, Z1, 's');

  /* ----- benches: L along the west and north walls. Lower seat 0.45, upper 0.90, 0.6 deep each ----- */
  const slat = (x0, x1, z0, z1, top, alongZ) => {                            // seat slats 0.09 wide, 0.012 gaps
    const depth = alongZ ? x1 - x0 : z1 - z0, n = Math.round(depth / 0.102), w = depth / n - 0.012;
    for (let i = 0; i < n; i++) {
      const c = (alongZ ? x0 : z0) + (i + 0.5) * depth / n;
      if (alongZ) K.box(w, 0.03, z1 - z0, aspen, c, top - 0.015, (z0 + z1) / 2, { tile: 0.9 }); else K.box(x1 - x0, 0.03, w, aspenN, (x0 + x1) / 2, top - 0.015, c, { tile: 0.9 });
    }
  };
  const block = (x0, x1, z0, z1, top) => K.box(x1 - x0 - 0.02, top - 0.03, z1 - z0 - 0.02, skirt, (x0 + x1) / 2, (top - 0.03) / 2, (z0 + z1) / 2, { tile: 0.9 });
  const WE = -0.86, WL = -0.26;
  block(X0, WE, Z0, 1.45, 0.9); slat(X0, WE, Z0, 1.45, 0.9, true);                     // west, upper
  block(WE, WL, -1.57, 1.45, 0.45); slat(WE, WL, -1.57, 1.45, 0.45, true);              // west, lower
  block(WE, 0.55, Z0, -1.57, 0.9); slat(WE, 0.55, Z0, -1.57, 0.9, false);               // north, upper
  block(WL, 0.55, -1.57, -0.97, 0.45); slat(WL, 0.55, -1.57, -0.97, 0.45, false);       // north, lower
  for (let i = 0; i < 4; i++) {                                                          // backrest slats above the upper benches, 0.95 to 1.40
    K.box(0.04, 0.09, 3.5, aspen, X0 + 0.02, 1.0 + i * 0.14, -0.3, { tile: 0.9 }); K.box(2.3, 0.09, 0.04, aspenN, 0.1 - 0.18, 1.0 + i * 0.14, Z0 + 0.02, { tile: 0.9 });
  }
  K.box(0.6, 0.9, 0.04, walnut, (X0 + WE) / 2, 0.45, 1.47); K.box(0.6, 0.45, 0.04, walnut, (WE + WL) / 2, 0.225, 1.47);            // bench ends
  K.box(0.04, 0.9, 0.6, walnut, 0.57, 0.45, -1.87); K.box(0.04, 0.45, 0.6, walnut, 0.57, 0.225, -1.27);

  /* LED lines: under each seat lip, a light line on the west and north walls at 1.75, a curved cove line on the ceiling, and a halo for each */
  K.led(0.014, 0.014, 3.62, WE - 0.005, 0.84, -0.36, { w: 3.62, h: 0.55, x: WE + 0.01, y: 0.63, z: -0.36, face: 'e', a: 0.45 });
  K.led(0.014, 0.014, 3.0, WL - 0.005, 0.39, -0.06, { w: 0.7, h: 3.0, x: WL + 0.25, y: 0.008, z: -0.06, face: 'up', a: 0.4 });
  K.led(1.4, 0.014, 0.014, -0.15, 0.84, -1.575, { w: 1.4, h: 0.55, x: -0.15, y: 0.63, z: -1.56, face: 's', a: 0.45 });
  K.led(0.8, 0.014, 0.014, 0.15, 0.39, -0.975, { w: 0.9, h: 0.7, x: 0.15, y: 0.008, z: -0.7, face: 'up', a: 0.4 });
  ledLine(rim(0.03, 0.4), 1.75); ledLine(rim(0.12, 0.7), H - 0.04, 0.014, ledD);
  K.glowPlane(3.9, 0.9, X0 + 0.01, 1.7, -0.1, 'e', 0.4); K.glowPlane(2.5, 0.9, 0.0, 1.7, Z0 + 0.01, 's', 0.4);
  K.shadow(1.2, 4.0, -0.5, -0.2, 0.45); K.shadow(1.3, 0.9, 0.1, -1.3, 0.4);

  /* downlights: two self-lit discs in the ceiling */
  [[-0.3, -0.4], [0.35, 1.0]].forEach(([x, z]) => K.put(new THREE.CircleGeometry(0.04, 14), led, { x, y: H - 0.003, z, rx: PI / 2 }));

  /* ----- the heater, north-east corner: oak frame, a tray, stones ----- */
  const HX = 1.0, HZ = -1.4;
  [[-0.28, -0.22], [0.28, -0.22], [-0.28, 0.22], [0.28, 0.22]].forEach(([x, z]) => K.box(0.045, 0.74, 0.045, oak, HX + x, 0.37, HZ + z));
  K.box(0.62, 0.04, 0.52, oak, HX, 0.72, HZ); K.box(0.62, 0.04, 0.52, oak, HX, 0.2, HZ); K.box(0.58, 0.05, 0.48, tray, HX, 0.765, HZ);
  [[0, -0.24, 0.6, 0.03], [0, 0.24, 0.6, 0.03], [-0.29, 0, 0.03, 0.5], [0.29, 0, 0.03, 0.5]].forEach(([x, z, w, d]) => K.box(w, 0.07, d, tray, HX + x, 0.8, HZ + z));
  K.shadow(0.95, 0.85, HX, HZ, 0.5);
  const nS = tier === 'high' ? 80 : 50, dark = K.col('--color-stone-dark'), pale = K.col('--color-stone');
  const stones = K.inst(new THREE.SphereGeometry(1, 5, 4), K.std(WHITE, { r: 0.85, m: 0.05 }), nS, (i, o) => {
    const a = r() * 6.28, rr = Math.sqrt(r()), sx = 0.2 * rr * Math.cos(a), sz = 0.17 * rr * Math.sin(a), k = 0.04 + r() * 0.03;
    o.position.set(HX + sx, 0.81 + 0.06 * (1 - rr * rr) + k * 0.4, HZ + sz); o.rotation.set(r() * 3, r() * 3, r() * 3); o.scale.set(k * (1 + r() * 0.4), k * 0.8, k * (1 + r() * 0.3));
  });
  for (let i = 0; i < nS; i++) stones.setColorAt(i, dark.clone().lerp(pale, r() * r()));
  stones.instanceColor.needsUpdate = true;
  K.glowPlane(0.5, 0.42, HX, 0.835, HZ, 'up', 0.3, '--color-heater-glow');
  await ctx.idle();

  K.flush();

  /* ----- light (2700K): low and pooled; hemisphere kept dim so the corners stay dark ----- */
  K.hemi('--color-led', '--color-floor-stone', 0.32);
  K.light('--color-light-warm', 2.2, 2.6, -1.2, 1.7, 0.6);                   // backrest wash, west
  K.light('--color-light-warm', 2.2, 2.6, -0.2, 1.7, -1.9);                  // backrest wash, north
  K.light('--color-heater-glow', 0.8, 1.4, HX, 0.85, HZ);                    // the low light in the stones
  K.light('--color-light-warm', 1.0, 2, -0.6, 0.35, 0, true);                // under the lower bench (dropped on the mobile tier)

  return {
    view: { pos: [0.75, 1.6, 1.3], yaw: -25, pitch: -10 },
    exposure: 0.9,
    arrive: { pos: [0.75, 1.6, 3.55], yaw: 0, pitch: -1, ms: 2400, input: 1200 },     // from the corridor, through the open door, then the turn down the benches
    markers: [{ to: 'wet-sauna', at: [0.9, 1.1, Z1] }, { to: 'lounge', at: [-1.1, 1.1, Z1] }],
  };
}
