/* Wet sauna (docs/design/VIRTUAL-TOUR.md 2.3). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Travertine steam room 4.5 x 4.0 (x -2.25..2.25, z -2..2): walls to 2.2 under a low barrel vault (crown 2.6), a single-tier bench in a U on the north, west and east walls with
 * its light underneath, the gold swan on the north wall, five small downlights, a bronze-framed glass door and sidelight in the south wall (the way back to the massage room), a bronze steam
 * outlet low in the front of the north bench with a plume coming out of it, and soft steam at knee height.
 * Kept warm and low: a little fog, light only from the downlights and under the bench. Animated (steam, fog breathing), 30 fps at rest. */

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), wrap = { wrap: true };

  /* ----- maps (2 of our own, plus the shared steam puff) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 3, ao: 2.2, joint: S / 2, jointY: S / 2 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.travertine(S >> 1, { seed: 9, joint: S >> 2, jointY: S >> 3 }), wrap);
  scene.environment = ctx.env('--color-travertine');

  /* ----- materials (stone pulled down a little so it reads as lit stone, not paper) ----- */
  const dim = new THREE.Color(0.8, 0.77, 0.74);
  const wall = K.std(dim, { r: 0.55, map: wallMap }), vaultM = K.std(dim, { r: 0.6, map: wallMap, side: THREE.BackSide }), floor = K.std(dim, { r: 0.3, map: floorMap });
  const bench = K.std(dim, { r: 0.35, map: wallMap });
  const led = K.basic('--color-led-warm');
  const bronze = K.std('--color-gold-shade', { r: 0.4, m: 0.8, envMapIntensity: 1.5 });
  const glass = K.std(K.col('--color-glass-bronze'), { r: 0.05, transparent: true, opacity: Math.max(0.2, K.alpha('--color-glass-bronze')), depthWrite: false, side: THREE.DoubleSide, envMapIntensity: 1.2 });
  const X0 = -2.25, X1 = 2.25, Z0 = -2, Z1 = 2, WH = 2.2, RY = 0.4, A = 2.25, D = 0.55, ZE = 1.05, L = ZE - Z0 - D, ZC = (ZE + Z0 + D) / 2;

  const ledLine = (pts, y, th = 0.016) => pts.forEach((a, i) => {            // an LED line along [x, z] points: small boxes, merged
    const b = pts[i + 1]; if (!b) return;
    const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz);
    K.box(len + 0.004, th, th, led, (a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2, { ry: Math.atan2(-dz, dx) });
  });

  /* ----- shell: floor, walls to 2.2, gables, the vault ----- */
  K.plane(4.5, 4, floor, 0, 0, 0, 'up', { tile: 2.4 });
  K.plane(4, WH, wall, X0, WH / 2, 0, 'e', { tile: 2.4 }); K.plane(4, WH, wall, X1, WH / 2, 0, 'w', { tile: 2.4 });
  K.plane(4.5, WH, wall, 0, WH / 2, Z0, 's', { tile: 2.4 });
  K.plane(2.55, WH, wall, -0.975, WH / 2, Z1, 'n', { tile: 2.4 }); K.plane(0.15, WH, wall, 2.175, WH / 2, Z1, 'n', { tile: 2.4 }); K.plane(1.8, WH - 2.1, wall, 1.2, 2.1 + (WH - 2.1) / 2, Z1, 'n', { tile: 2.4 });   // south wall round the glazing
  const gable = () => { const s = new THREE.Shape(); s.absellipse(0, 0, A, RY, 0, PI, false); return new THREE.ShapeGeometry(s, 32); };
  K.put(gable(), wall, { y: WH, z: Z0, tile: 2.4 }); K.put(gable(), wall, { y: WH, z: Z1, ry: PI, tile: 2.4 });
  const vg = new THREE.CylinderGeometry(A, A, 4, 40, 1, true, PI / 2, PI);   // half a cylinder along z, squashed to a low vault
  const fr = Array.from(vg.attributes.uv.array); vg.rotateX(PI / 2); vg.scale(1, RY / A, 1); vg.computeVertexNormals();
  const vp = vg.attributes.position, vu = vg.attributes.uv;
  for (let i = 0; i < vp.count; i++) vu.setXY(i, vp.getZ(i) / 2.4, fr[i * 2] * 4.8 / 2.4);    // veins run along the vault
  K.put(vg, vaultM, { y: WH });

  /* ----- the U bench: north, west and east arms, 0.55 deep, one tier (seat at 0.45) with a recessed core, a raised back, the light under the nose ----- */
  K.box(4.5, 0.33, D - 0.07, bench, 0, 0.165, Z0 + (D - 0.07) / 2, { tile: 2.4 }); K.box(4.5, 0.12, D, bench, 0, 0.39, Z0 + D / 2, { tile: 2.4 }); K.box(4.5, 0.45, 0.06, bench, 0, 0.675, Z0 + 0.03, { tile: 2.4 });
  [-1, 1].forEach((s) => {
    K.box(D - 0.07, 0.33, L, bench, s * (A - (D - 0.07) / 2), 0.165, ZC, { tile: 2.4 }); K.box(D, 0.12, L, bench, s * (A - D / 2), 0.39, ZC, { tile: 2.4 }); K.box(0.06, 0.45, L, bench, s * (A - 0.03), 0.675, ZC, { tile: 2.4 });
  });
  ledLine([[X1 - D + 0.075, ZE], [X1 - D + 0.075, Z0 + D - 0.075], [X0 + D - 0.075, Z0 + D - 0.075], [X0 + D - 0.075, ZE]], 0.322);       // under the seat nose, following the U
  K.glowPlane(4.2, 0.55, 0, 0.2, Z0 + D + 0.03, 's', 0.4); K.glowPlane(0.55, L, X0 + D + 0.03, 0.2, ZC, 'e', 0.35); K.glowPlane(0.55, L, X1 - D - 0.03, 0.2, ZC, 'w', 0.35);   // on the core
  K.glowPlane(4.0, 1.0, 0, 0.006, -1.0, 'up', 0.5); K.glowPlane(1.0, 2.4, -1.2, 0.006, 0.05, 'up', 0.45); K.glowPlane(1.0, 2.4, 1.2, 0.006, 0.05, 'up', 0.45);   // pools on the floor

  /* ----- the steam outlet: a bronze plate low in the front of the north bench, a short nozzle with a flared mouth, pointing into the room ----- */
  const NX = -0.7, NY = 0.2, NZ = Z0 + D - 0.07;
  K.put(new THREE.CylinderGeometry(0.09, 0.09, 0.015, 20), bronze, { x: NX, y: NY, z: NZ + 0.008, rx: PI / 2 });
  K.put(new THREE.CylinderGeometry(0.03, 0.03, 0.12, 14), bronze, { x: NX, y: NY, z: NZ + 0.07, rx: PI / 2 });
  K.put(new THREE.CylinderGeometry(0.055, 0.03, 0.05, 14, 1, true), bronze, { x: NX, y: NY, z: NZ + 0.155, rx: -PI / 2 });
  K.put(new THREE.CircleGeometry(0.05, 14), K.basic(K.col('--color-led-warm').clone().multiplyScalar(0.5)), { x: NX, y: NY, z: NZ + 0.178, rx: 0 });

  /* ----- the swan on the north wall: 0.45 tall, centre at 1.55, gold metal with a normal map ----- */
  const lock = ctx.logo('mark', { normal: tier === 'high' });
  if (lock) {
    const tx = (c) => T.tex(c, { color: false }), hh = 0.5;
    const mark = K.std('--color-gold-metal', { r: 0.3, m: 0.9, alphaMap: tx(lock.alpha), normalMap: lock.normal ? tx(lock.normal) : null, transparent: true, depthWrite: false, envMapIntensity: 1.8 });
    K.plane(hh * lock.aspect, hh, mark, 0, 1.55, Z0 + 0.01, 's');
  }

  /* ----- the glazing in the south wall: a fixed sidelight (x 0.3..1.2) and the door (x 1.2..2.1), bronze frames, a bar handle ----- */
  K.plane(0.9, 2.1, glass, 0.75, 1.05, Z1 - 0.02, 'n'); K.plane(0.9, 2.1, glass, 1.65, 1.05, Z1 - 0.02, 'n');
  [0.3, 1.2, 2.1].forEach((x) => K.box(0.04, 2.1, 0.06, bronze, x, 1.05, Z1 - 0.03));
  K.box(1.8, 0.04, 0.06, bronze, 1.2, 2.1, Z1 - 0.03); K.box(1.8, 0.04, 0.06, bronze, 1.2, 0.02, Z1 - 0.03);
  K.put(new THREE.CylinderGeometry(0.012, 0.012, 0.65, 10), bronze, { x: 1.32, y: 1.1, z: Z1 - 0.09 });
  K.put(new THREE.BoxGeometry(0.08, 0.03, 0.04), bronze, { x: 1.35, y: 1.9, z: Z1 - 0.03 }); K.put(new THREE.BoxGeometry(0.08, 0.03, 0.04), bronze, { x: 1.35, y: 0.3, z: Z1 - 0.03 });
  K.vista('--color-travertine', [1.2, Z1], 's', 1.9, 2.1, 1.2);               // the corridor beyond, lit in the next room's colour

  /* ----- downlights in the vault, each with a faint cone ----- */
  const vy = (x) => WH + RY * Math.sqrt(1 - (x / A) ** 2), cones = [];
  [[0, -1.1], [-1.1, 0.0], [1.1, 0.0], [0, 0.6], [-0.6, 1.4]].forEach(([x, z]) => {
    const y = vy(x) - 0.005, g = new THREE.CircleGeometry(0.04, 14);
    g.lookAt(new THREE.Vector3(-x / (A * A), -(y - WH) / (RY * RY), 0).normalize()); K.put(g, led, { x, y, z });
    const c = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.36, 1.0, 20, 1, true), new THREE.MeshBasicMaterial({ color: K.col('--color-led-warm'), transparent: true, opacity: 0.022, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    c.position.set(x, y - 0.5, z); c.renderOrder = 2; scene.add(c); cones.push(c);
  });
  K.flush();

  /* ----- light (2700K) and fog: warm, low, a little haze ----- */
  K.baseLight(0.22);
  K.light('--color-light-warm', 1.7, 3.8, 0, 2.4, -1.0); K.light('--color-light-warm', 1.7, 3.8, -1.1, 2.4, 0.2); K.light('--color-light-warm', 1.7, 3.8, 1.1, 2.4, 0.2);
  K.light('--color-light-warm', 1.3, 1.8, -0.4, 0.3, -1.2, true);              // bench glow (the strip itself stays lit on mobile)
  scene.fog = new THREE.FogExp2(K.col('--color-travertine-vein').clone().multiplyScalar(0.55), 0.035);

  /* ----- steam: soft camera-facing puffs. Ambient ones rise slowly from knee height (40 s each); the plume leaves the outlet, drifts out and up and thins (4 s each) ----- */
  const N = tier === 'high' ? 9 : tier === 'mobile' ? 6 : 3, J = tier === 'high' ? 7 : tier === 'mobile' ? 5 : 3, puff = T.shared('puff'), cream = K.tint('--color-cream', 0.7);
  const mk = (n, life, jet) => Array.from({ length: n }, (_, i) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: cream, map: puff, transparent: true, opacity: 0, depthWrite: false }));
    m.renderOrder = 3; m.frustumCulled = false; scene.add(m);
    m.onBeforeRender = (rd, sc, cam) => { m.rotation.y = Math.atan2(cam.position.x - m.position.x, cam.position.z - m.position.z); m.updateMatrixWorld(); };
    return { m, i, jet, life, off: i / n * life, cyc: -1, x: 0, y: 0, z: 0, s: 1, spin: 0, peak: 0.1 };
  });
  const steam = mk(N, 40, 0), plume = mk(J, 4, 1);
  function update(dt, t) {
    steam.forEach((p, i) => {
      const age = (t + p.off) % p.life, cyc = Math.floor((t + p.off) / p.life);
      if (cyc !== p.cyc) { const r = T.rng(i * 97 + cyc * 13 + 5); p.cyc = cyc; p.x = -1.6 + r() * 3.2; p.z = -1.2 + r() * 2.6; p.y = 0.2 + r() * 0.5; p.s = 1.5 + r() * 0.8; p.spin = (r() - 0.5) * 0.4; p.peak = 0.09 + r() * 0.06; }
      const k = age / p.life, fade = Math.min(1, k / 0.15) * Math.min(1, (1 - k) / 0.25);
      p.m.position.set(p.x + 0.01 * age, p.y + 0.015 * age, p.z); p.m.scale.set(p.s, p.s, 1); p.m.material.opacity = p.peak * fade;
      p.m.rotation.z = p.spin + age * 2 * PI / 180;
    });
    plume.forEach((p, i) => {
      const age = (t + p.off) % p.life, cyc = Math.floor((t + p.off) / p.life), k = age / p.life;
      if (cyc !== p.cyc) { const r = T.rng(i * 57 + cyc * 31 + 9); p.cyc = cyc; p.x = (r() - 0.5) * 0.12; p.z = 0.7 + r() * 0.4; p.y = 0.25 + r() * 0.3; p.spin = (r() - 0.5) * 0.8; p.peak = 0.2 + r() * 0.1; }
      p.m.position.set(NX + p.x * k, NY + 0.02 + p.y * k * k + 0.1 * k, NZ + 0.2 + p.z * k); const s = 0.14 + 0.7 * k; p.m.scale.set(s, s, 1);
      p.m.material.opacity = p.peak * Math.min(1, k / 0.1) * (1 - k) * (1 - k); p.m.rotation.z = p.spin * k;
    });
    scene.fog.density = 0.035 + 0.004 * Math.sin(t * 2 * PI / 20);
  }
  update(0, 1);

  return {
    view: { pos: [1.3, 1.55, 1.5], yaw: -31, pitch: -11 },     // from the door side: the swan wall, the bench and the steam outlet in frame
    exposure: 0.85, ambient: true, update,
    markers: [{ to: 'massage-room', at: [1.65, 1.1, Z1] }, { to: 'dry-sauna', at: [0.75, 1.1, Z1] }],
    tier(name) { if (name === 'low') { steam.forEach((p) => { if (p.i >= 3) p.m.visible = false; }); plume.forEach((p) => { if (p.i >= 3) p.m.visible = false; }); } },
  };
}
