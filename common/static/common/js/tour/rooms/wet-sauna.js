/* Wet sauna (docs/design/VIRTUAL-TOUR.md 2.3). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Travertine steam room 2.4 x 3.2 (x -1.2..1.2, z -1.6..1.6): walls to 2.25 under a low barrel vault (crown 2.91), a curved L bench on the north and west walls with its
 * light underneath, the gold swan on the north wall, four small downlights, a bronze-framed glass door and sidelight in the east wall, and soft steam at knee height.
 * Kept warm and low: a little fog, light only from the downlights and under the bench. Animated (steam, fog breathing), 30 fps at rest. */

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), wrap = { wrap: true };

  /* ----- maps (2 of our own, plus the shared steam puff) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 3, ao: 2.25, joint: S / 2, jointY: S / 2 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.travertine(S >> 1, { seed: 9, joint: S >> 2, jointY: S >> 3 }), wrap);
  scene.environment = ctx.env('--color-travertine');

  /* ----- materials (stone pulled down a little so it reads as lit stone, not paper) ----- */
  const dim = new THREE.Color(0.8, 0.77, 0.74);
  const wall = K.std(dim, { r: 0.55, map: wallMap }), vaultM = K.std(dim, { r: 0.6, map: wallMap, side: THREE.BackSide }), floor = K.std(dim, { r: 0.3, map: floorMap });
  const bench = K.std(dim, { r: 0.35, map: wallMap });
  const led = K.basic('--color-led-warm');
  const bronze = K.std('--color-gold-shade', { r: 0.4, m: 0.8, envMapIntensity: 1.5 });
  const glass = K.std(K.col('--color-glass-bronze'), { r: 0.05, transparent: true, opacity: Math.max(0.2, K.alpha('--color-glass-bronze')), depthWrite: false, side: THREE.DoubleSide, envMapIntensity: 1.2 });
  const X0 = -1.2, X1 = 1.2, Z0 = -1.6, Z1 = 1.6, WH = 2.25, RY = 0.66;

  const ledLine = (pts, y, th = 0.016) => pts.forEach((a, i) => {            // an LED line along [x, z] points: small boxes, merged
    const b = pts[i + 1]; if (!b) return;
    const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz);
    K.box(len + 0.004, th, th, led, (a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2, { ry: Math.atan2(-dz, dx) });
  });

  /* ----- shell: floor, walls to 2.25, gables, the vault ----- */
  K.plane(2.4, 3.2, floor, 0, 0, 0, 'up', { tile: 2.4 });
  K.plane(3.2, WH, wall, X0, WH / 2, 0, 'e', { tile: 2.4 });
  K.plane(2.4, WH, wall, 0, WH / 2, Z0, 's', { tile: 2.4 }); K.plane(2.4, WH, wall, 0, WH / 2, Z1, 'n', { tile: 2.4 });
  K.plane(1.1, WH, wall, X1, WH / 2, -1.05, 'w', { tile: 2.4 }); K.plane(0.2, WH, wall, X1, WH / 2, 1.5, 'w', { tile: 2.4 });   // east wall round the glazing
  K.plane(1.9, WH - 2.1, wall, X1, 2.1 + (WH - 2.1) / 2, 0.45, 'w', { tile: 2.4 });
  const gable = () => { const s = new THREE.Shape(); s.absellipse(0, 0, 1.2, RY, 0, PI, false); return new THREE.ShapeGeometry(s, 24); };
  K.put(gable(), wall, { y: WH, z: Z0, tile: 2.4 }); K.put(gable(), wall, { y: WH, z: Z1, ry: PI, tile: 2.4 });
  const vg = new THREE.CylinderGeometry(1.2, 1.2, 3.2, 36, 1, true, PI / 2, PI);   // half a cylinder along z, squashed to a low vault
  const fr = Array.from(vg.attributes.uv.array); vg.rotateX(PI / 2); vg.scale(1, RY / 1.2, 1); vg.computeVertexNormals();
  const vp = vg.attributes.position, vu = vg.attributes.uv;
  for (let i = 0; i < vp.count; i++) vu.setXY(i, vp.getZ(i) / 2.4, fr[i * 2] * 3.4 / 2.4);    // veins run along the vault
  K.put(vg, vaultM, { y: WH });

  /* ----- the curved L bench: north and west arms, 0.55 deep, a rounded nose on the west arm, inner corner radius 0.6 ----- */
  const outline = (i) => {                                                   // [x, z] points; `front` is the visible edge (for the light under it)
    const front = [[X1, -1.05 - i], [-0.05, -1.05 - i]], R = 0.6 + i, rn = 0.275 - i;
    for (let k = 1; k <= 8; k++) { const a = (-90 - 90 * k / 8) * PI / 180; front.push([-0.05 + R * Math.cos(a), -0.45 + R * Math.sin(a)]); }
    front.push([-0.65 - i, 0.75]);
    for (let k = 1; k <= 12; k++) { const a = PI * k / 12; front.push([-0.925 + rn * Math.cos(a), 0.75 + rn * Math.sin(a)]); }
    return { front, all: [[X0, Z0], [X1, Z0], ...front, [X0, Z0]] };
  };
  const extrude = (pts, depth, y, b) => {
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(pts.map((p) => new THREE.Vector2(p[0], -p[1]))), { depth, bevelEnabled: b > 0, bevelThickness: b, bevelSize: b, bevelSegments: 3, curveSegments: 4 });
    g.rotateX(-PI / 2); g.translate(0, y + b, 0); return g;
  };
  K.put(extrude(outline(0.07).all, 0.33, 0, 0), bench, { tile: 2.4 });        // the recessed core
  K.put(extrude(outline(0).all, 0.06, 0.33, 0.03), bench, { tile: 2.4 });     // the seat slab with its rounded nose, 0.33 to 0.45
  K.box(2.4, 0.45, 0.06, bench, 0, 0.675, Z0 + 0.03, { tile: 2.4 }); K.box(0.06, 0.45, 2.35, bench, X0 + 0.03, 0.675, -0.425, { tile: 2.4 });   // the raised back
  const under = outline(0.075).front; ledLine(under, 0.322);                  // the light under the seat nose, following the L
  K.glowPlane(2.4, 0.5, 0.2, 0.2, -1.11, 's', 0.4); K.glowPlane(2.1, 0.5, -0.71, 0.2, 0.0, 'e', 0.35);     // on the core
  K.glowPlane(2.6, 1.0, 0.0, 0.006, -0.55, 'up', 0.5); K.glowPlane(1.0, 2.2, -0.4, 0.006, 0.1, 'up', 0.45); K.glowPlane(1.0, 0.9, -0.85, 0.006, 1.0, 'up', 0.35);   // pools on the floor

  /* ----- the swan on the north wall: 0.45 tall, centre at 1.55, gold metal with a normal map ----- */
  const lock = ctx.logo('mark', { normal: tier === 'high' });
  if (lock) {
    const tx = (c) => T.tex(c, { color: false }), hh = 0.45;
    const mark = K.std('--color-gold-metal', { r: 0.3, m: 0.9, alphaMap: tx(lock.alpha), normalMap: lock.normal ? tx(lock.normal) : null, transparent: true, depthWrite: false, envMapIntensity: 1.8 });
    K.plane(hh * lock.aspect, hh, mark, 0, 1.55, Z0 + 0.01, 's');
  }

  /* ----- the glazing in the east wall: a fixed sidelight (z -0.5..0.6) and the door (z 0.6..1.4), bronze frames, a bar handle ----- */
  K.plane(1.1, 2.1, glass, X1 - 0.02, 1.05, 0.05, 'w'); K.plane(0.8, 2.1, glass, X1 - 0.02, 1.05, 1.0, 'w');
  [-0.5, 0.6, 1.4].forEach((z) => K.box(0.06, 2.1, 0.04, bronze, X1 - 0.03, 1.05, z));
  K.box(0.06, 0.04, 1.94, bronze, X1 - 0.03, 2.1, 0.45); K.box(0.06, 0.04, 1.94, bronze, X1 - 0.03, 0.02, 0.45);
  K.put(new THREE.CylinderGeometry(0.012, 0.012, 0.65, 10), bronze, { x: X1 - 0.09, y: 1.1, z: 1.27 });
  K.put(new THREE.BoxGeometry(0.03, 0.08, 0.04), bronze, { x: X1 - 0.03, y: 1.9, z: 0.62 }); K.put(new THREE.BoxGeometry(0.03, 0.08, 0.04), bronze, { x: X1 - 0.03, y: 0.3, z: 0.62 });
  K.vista('--color-travertine', [X1, 0.45], 'e', 1.9, 2.1, 1.2);               // the corridor beyond, lit in the next room's colour

  /* ----- downlights in the vault, each with a faint cone ----- */
  const vy = (x) => WH + RY * Math.sqrt(1 - (x / 1.2) ** 2), cones = [];
  [[0, -0.6], [-0.55, 0.3], [0.55, 0.3], [0, 0.9]].forEach(([x, z]) => {
    const y = vy(x) - 0.005, g = new THREE.CircleGeometry(0.04, 14);
    g.lookAt(new THREE.Vector3(-x / 1.44, -(y - WH) / (RY * RY), 0).normalize()); K.put(g, led, { x, y, z });
    const c = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.36, 1.0, 20, 1, true), new THREE.MeshBasicMaterial({ color: K.col('--color-led-warm'), transparent: true, opacity: 0.09, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    c.position.set(x, y - 0.5, z); c.renderOrder = 2; scene.add(c); cones.push(c);
  });
  K.flush();

  /* ----- light (2700K) and fog: warm, low, a little haze ----- */
  K.baseLight(0.22);
  K.light('--color-light-warm', 1.6, 3, 0, 2.6, -0.6); K.light('--color-light-warm', 1.6, 3, -0.55, 2.5, 0.3); K.light('--color-light-warm', 1.6, 3, 0.55, 2.5, 0.3);
  K.light('--color-light-warm', 1.3, 1.5, -0.4, 0.3, -0.9, true);              // bench glow (the strip itself stays lit on mobile)
  scene.fog = new THREE.FogExp2(K.col('--color-travertine-vein').clone().multiplyScalar(0.55), 0.035);

  /* ----- steam: soft camera-facing puffs rising slowly from knee height, 40 s each ----- */
  const N = tier === 'high' ? 8 : tier === 'mobile' ? 5 : 3, LIFE = 40, puff = T.shared('puff'), cream = K.tint('--color-cream', 0.7);
  const steam = Array.from({ length: N }, (_, i) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: cream, map: puff, transparent: true, opacity: 0, depthWrite: false }));
    m.renderOrder = 3; m.frustumCulled = false; scene.add(m);
    m.onBeforeRender = (rd, sc, cam) => { m.rotation.y = Math.atan2(cam.position.x - m.position.x, cam.position.z - m.position.z); m.updateMatrixWorld(); };
    return { m, off: i / N * LIFE, cyc: -1, x: 0, y: 0, z: 0, s: 1, spin: 0, peak: 0.1 };
  });
  function update(dt, t) {
    steam.forEach((p, i) => {
      const age = (t + p.off) % LIFE, cyc = Math.floor((t + p.off) / LIFE);
      if (cyc !== p.cyc) { const r = T.rng(i * 97 + cyc * 13 + 5); p.cyc = cyc; p.x = -0.9 + r() * 1.4; p.z = -1.2 + r() * 2.0; p.y = 0.2 + r() * 0.5; p.s = 1.5 + r() * 0.8; p.spin = (r() - 0.5) * 0.4; p.peak = 0.09 + r() * 0.06; }
      const k = age / LIFE, fade = Math.min(1, k / 0.15) * Math.min(1, (1 - k) / 0.25);
      p.m.position.set(p.x + 0.01 * age, p.y + 0.015 * age, p.z); p.m.scale.set(p.s, p.s, 1); p.m.material.opacity = p.peak * fade;
      p.m.rotation.z = p.spin + age * 2 * PI / 180;
    });
    scene.fog.density = 0.035 + 0.004 * Math.sin(t * 2 * PI / 20);
  }
  update(0, 1);

  return {
    view: { pos: [0.95, 1.55, 1.35], yaw: -36, pitch: -12 },     // from the door side: the swan wall and both arms of the L bench in frame
    exposure: 0.85, ambient: true, update,
    markers: [{ to: 'relaxing-zone', at: [X1, 1.1, 1.0] }, { to: 'lounge', at: [X1, 1.1, -0.15] }],
    tier(name) { if (name === 'low') steam.forEach((p, i) => { if (i >= 3) p.m.visible = false; }); },
  };
}
