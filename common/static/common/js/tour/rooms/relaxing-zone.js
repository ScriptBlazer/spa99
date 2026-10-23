/* Relaxing zone (docs/design/VIRTUAL-TOUR.md 2.4). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 3.6 x 8.0 x 2.7 (x -1.8..1.8, z -4..4): travertine walls with vertical LED lines on the east wall, an oak pilaster with round moss panels on the west,
 * a coffered ceiling with an LED cove, six cushioned loungers on curved oak frames, the backlit gold stacked lockup on the east wall, and (round 2) a TV on the west wall facing the loungers. */

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), r = T.rng(21);
  const wrap = { wrap: true };

  /* ----- maps (6 of our own, plus the lockup's) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 5, ao: 3, joint: S / 2, jointY: S / 2 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.travertine(S, { seed: 12, joint: S / 2, jointY: S / 4 }), wrap); await ctx.idle();
  const oakMap = T.tex(T.oak(S >> 1, { seed: 7 }), wrap);
  const mossMap = T.tex(T.moss(S >> 1, 8), wrap);
  const quiltMap = T.tex(T.quilting(S >> 1, { cells: 4 }), wrap); await ctx.idle();
  const lock = ctx.logo('stacked', { normal: true, halo: true });
  scene.environment = ctx.env('--color-travertine');

  /* ----- materials ----- */
  const wall = K.std(WHITE, { r: 0.6, map: wallMap }), floor = K.std(WHITE, { r: 0.35, map: floorMap }), ceil = K.std('--color-cream', { r: 1 });
  const oak = K.std(WHITE, { r: 0.55, map: oakMap }), moss = K.std(WHITE, { r: 1, map: mossMap });
  const pad = K.std(WHITE, { r: 0.9, map: quiltMap }), cream = K.std('--color-cream-raised', { r: 0.9 }), throwM = K.std('--color-caramel', { r: 1 });
  const led = K.basic('--color-led-warm'), ledD = K.basic('--color-led-warm', { side: THREE.DoubleSide });
  const gold = K.std('--color-gold-metal', { r: 0.35, m: 0.85, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.16, envMapIntensity: 1.8, side: THREE.DoubleSide });

  /* ----- shell: floor, walls (one doorway), coffered ceiling ----- */
  K.plane(3.6, 8, floor, 0, 0, 0, 'up', { tile: 2.4 });
  K.plane(3.6, 2.7, wall, 0, 1.35, -4, 's', { tile: 2.4 });
  K.plane(8, 2.7, wall, 1.8, 1.35, 0, 'w', { tile: 2.4 });                                              // east, the lockup wall
  K.plane(8, 2.7, wall, -1.8, 1.35, 0, 'e', { tile: 2.4 });                                              // west: plain wall (round 2: no gym doorway; the TV hangs here)
  K.plane(1.3, 2.7, wall, -1.15, 1.35, 4, 'n', { tile: 2.4 }); K.plane(1.3, 2.7, wall, 1.15, 1.35, 4, 'n', { tile: 2.4 });
  K.plane(1.0, 0.5, wall, 0, 2.45, 4, 'n', { tile: 2.4 });                                               // south: the lounge doorway at x 0

  const hole = [[-1.2, -3.4], [1.2, -3.4], [1.2, 3.4], [-1.2, 3.4]].map((p) => new THREE.Vector2(p[0], p[1]));
  const outer = new THREE.Shape([[-1.8, -4], [1.8, -4], [1.8, 4], [-1.8, 4]].map((p) => new THREE.Vector2(p[0], p[1])));
  outer.holes.push(new THREE.Path(hole));
  const ceilG = new THREE.ShapeGeometry(outer); ceilG.rotateX(PI / 2); K.put(ceilG, ceil, { y: 2.7 });
  K.plane(2.4, 6.8, ceil, 0, 2.85, 0, 'down');
  K.plane(2.4, 0.15, ledD, 0, 2.775, -3.4, 's'); K.plane(2.4, 0.15, ledD, 0, 2.775, 3.4, 'n');          // the coffer's lit lip, facing in
  K.plane(6.8, 0.15, ledD, -1.2, 2.775, 0, 'e'); K.plane(6.8, 0.15, ledD, 1.2, 2.775, 0, 'w');
  K.glowPlane(2.4, 6.8, 0, 2.84, 0, 'down', 0.22);
  [-2.4, 0, 2.4].forEach((z) => [-0.6, 0.6].forEach((x) => K.put(new THREE.CircleGeometry(0.05, 12), led, { x, y: 2.845, z, rx: PI / 2 })));

  /* ----- east wall: vertical LED lines (lit, with a halo each) ----- */
  [-3.0, -1.8, 0.6, 1.8].forEach((z) => K.led(0.015, 2.7, 0.012, 1.79, 1.35, z, { w: 0.5, h: 2.7, x: 1.785, y: 1.35, z, face: 'w', a: 0.3 }, led));

  /* ----- west wall: the oak pilaster (z -2.8..-0.6) and three round moss panels in thin oak rings ----- */
  K.box(0.25, 2.7, 2.2, oak, -1.675, 1.35, -1.7, { tile: 1.2 });
  [[-2.4, 0.30], [-1.7, 0.28], [-1.0, 0.26]].forEach(([z, rad]) => {
    K.put(new THREE.CircleGeometry(rad, 36), moss, { x: -1.545, y: 1.4, z, ry: PI / 2 });
    K.put(new THREE.TorusGeometry(rad + 0.012, 0.014, 6, 36), oak, { x: -1.54, y: 1.4, z, ry: PI / 2, tile: 0.5 });
  });
  K.glowPlane(0.9, 2.2, -1.5, 1.4, -1.7, 'e', 0.12);

  /* ----- west wall: the TV (round 2), 65 inch, slim black frame, dark screen with a faint warm reflection and no picture, facing the loungers ----- */
  {
    const c = document.createElement('canvas'); c.width = 256; c.height = 144; const g = c.getContext('2d');
    g.fillStyle = T.mix('--color-iron', '--color-espresso', 0.5); g.fillRect(0, 0, 256, 144);
    const sheen = g.createLinearGradient(0, 0, 256, 144);
    sheen.addColorStop(0, T.rgba('--color-light-warm', 0.0)); sheen.addColorStop(0.3, T.rgba('--color-light-warm', 0.16)); sheen.addColorStop(0.55, T.rgba('--color-light-warm', 0.03)); sheen.addColorStop(1, T.rgba('--color-light-warm', 0));
    g.fillStyle = sheen; g.fillRect(0, 0, 256, 144);
    const glow = g.createRadialGradient(200, 30, 4, 200, 30, 90); glow.addColorStop(0, T.rgba('--color-led-warm', 0.1)); glow.addColorStop(1, T.rgba('--color-led-warm', 0));
    g.fillStyle = glow; g.fillRect(0, 0, 256, 144);
    const tvZ = 1.7, tvY = 1.4, tw = 1.44, th = 0.81;
    K.box(0.04, th + 0.05, tw + 0.05, K.std('--color-iron', { r: 0.35, m: 0.5 }), -1.76, tvY, tvZ);                                 // slim black frame
    K.plane(tw, th, K.basic(new THREE.Color(1, 1, 1), { map: T.tex(c) }), -1.737, tvY, tvZ, 'e');                                  // the screen
  }

  /* ----- the lockup: backlit gold stacked logo on the east wall ----- */
  if (lock) {
    const tx = (c, o) => T.tex(c, o || { color: false }), lh = 1.25;
    const mark = K.std('--color-gold-metal', { r: 0.35, m: 0.85, alphaMap: tx(lock.alpha), normalMap: tx(lock.normal), transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.2, envMapIntensity: 1.8 });
    K.plane(lh * lock.aspect, lh, mark, 1.775, 1.9, -0.6, 'w');
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(lh * lock.aspect * 1.7, lh * 1.5), new THREE.MeshBasicMaterial({ color: K.col('--color-light-warm'), map: tx(lock.halo, {}), transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false }));
    halo.position.set(1.765, 1.9, -0.6); halo.rotation.y = -PI / 2; halo.renderOrder = 2; scene.add(halo);
  }

  /* ----- loungers: S-curve oak side frames, quilted pad, bolster, folded caramel throw. Local x runs foot (-) to head (+). ----- */
  const sm = (a, b, u) => { const t = Math.min(1, Math.max(0, (u - a) / (b - a))); return t * t * (3 - 2 * t); };
  const yc = (u) => 0.40 - 0.10 * sm(-0.5, -0.85, u) + 0.40 * sm(0, 0.85, u);
  const us = []; for (let i = 0; i <= 20; i++) us.push(-0.85 + i * 0.085);
  const band = (lo, hi) => new THREE.Shape([...us.map((u) => new THREE.Vector2(u, yc(u) + hi)), ...us.slice().reverse().map((u) => new THREE.Vector2(u, yc(u) + lo))]);
  const ext = (shape, depth, bev) => { const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: bev > 0, bevelThickness: bev, bevelSize: bev, bevelSegments: 2, curveSegments: 4 }); g.translate(0, 0, -depth / 2); return g; };
  const lounger = (x, z, ry) => {
    const o = { x, z, ry };
    [-0.32, 0.32].forEach((s) => { K.put(ext(band(-0.09, 0), 0.04, 0).translate(0, 0, s), oak, { ...o, tile: 0.8 }); });
    [-0.55, 0.25].forEach((u) => {
      const h = yc(u) - 0.09;
      [-0.32, 0.32].forEach((s) => K.put(new THREE.BoxGeometry(0.05, h, 0.04).translate(u, h / 2, s), oak, { ...o, tile: 0.8 }));
      K.put(new THREE.BoxGeometry(0.04, 0.04, 0.64).translate(u, h * 0.6, 0), oak, { ...o, tile: 0.8 });
    });
    K.put(ext(band(0.03, 0.11), 0.58, 0.02), pad, { ...o, tile: 0.6 });
    K.put(new THREE.CylinderGeometry(0.1, 0.1, 0.58, 14).rotateX(PI / 2).translate(0.6, yc(0.6) + 0.22, 0), cream, o);
    K.put(new THREE.BoxGeometry(0.45, 0.06, 0.3).rotateY((r() - 0.5) * 0.2).translate(-0.3, 0.40 + 0.15, 0), throwM, o);
    K.shadow(2.1, 0.95, x, z, 0.38);
  };
  [-3.0, -1.85, -0.7, 0.45, 1.6, 2.75].forEach((z) => lounger(0.45, z, 0.26));
  K.flush();

  /* ----- doorway seen through: the lounge (travertine) ----- */
  K.vista('--color-travertine', [0, 4], 's', 1.0, 2.2, 1.0);

  /* ----- light (2700K) ----- */
  K.hemi('--color-led', '--color-caramel', 0.45);
  K.light('--color-light-warm', 3, 5, 0, 2.55, -1.5);
  K.light('--color-light-warm', 3, 5, 0, 2.55, 2.0);
  K.light('--color-light-warm', 1.5, 2, 1.55, 1.9, -0.6, true);

  return {
    view: { pos: [-0.6, 1.6, 3.4], yaw: 10, pitch: -8 },
    exposure: 0.92,
    markers: [{ to: 'lounge', at: [0, 1.1, 3.95] }],
  };
}
