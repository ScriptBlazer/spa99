/* Gym (docs/design/VIRTUAL-TOUR.md 2.5). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 7.0 x 6.0 x 2.8 (x -3.5..3.5, z -3..3): smoked oak panel wall with the gold stacked lockup (west), a mirror wall (north), a dropped ceiling with an
 * LED cove, dark oak floor, and a few machines as simple shapes: dumbbell rack, bench, cable tower, treadmill. Dark, but lifted. */

export async function build(scene, ctx) {
  const { THREE, K, T, S } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1);
  const wrap = { wrap: true };

  /* ----- maps (3 of our own, plus the lockup's) ----- */
  const floorMap = T.tex(T.oak(S, { seed: 31, tone: '--color-walnut', planks: 8, lift: 0.14 }), wrap); await ctx.idle();
  const panelMap = T.tex(T.oak(S >> 1, { seed: 33, tone: '--color-walnut', lift: 0.1 }), wrap); await ctx.idle();
  const lock = ctx.logo('stacked', { normal: true });
  scene.environment = ctx.env('--color-caramel');

  /* ----- materials ----- */
  const floor = K.std(WHITE, { r: 0.5, map: floorMap }), panel = K.std(WHITE, { r: 0.6, map: panelMap }), wall = K.std('--color-espresso-raised', { r: 0.8 });
  const ceil = K.std(K.col('--color-travertine').clone().multiplyScalar(0.55), { r: 1 }), led = K.basic('--color-led-warm'), ledD = K.basic('--color-led-warm', { side: THREE.DoubleSide });
  const mirror = K.std(K.col('--color-caramel').clone().multiplyScalar(0.6), { r: 0.08, m: 1, envMapIntensity: 1.3 });
  const iron = K.std('--color-iron', { r: 0.45, m: 0.6 }), padM = K.std('--color-espresso', { r: 0.6 }), steel = K.std('--color-text-muted-inverse', { r: 0.35, m: 0.9 });
  const gold = K.std('--color-gold-metal', { r: 0.3, m: 0.9, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.14, envMapIntensity: 1.8 });

  /* ----- shell: floor, walls (two doorways), mirrors, dropped ceiling with cove ----- */
  K.plane(7, 6, floor, 0, 0, 0, 'up', { tile: 1.44 });
  K.plane(7, 1.0, wall, 0, 0.5, -3, 's'); K.plane(7, 0.4, wall, 0, 2.6, -3, 's');                          // north, around the mirrors
  const mw = (7 - 0.012) / 3;
  for (let i = 0; i < 3; i++) K.plane(mw, 1.4, mirror, -3.5 + mw / 2 + i * (mw + 0.006), 1.7, -2.99, 's');
  K.plane(7, 1.4, wall, 0, 1.7, -3.001, 's');                                                          // dark joint backing, behind the mirrors
  K.plane(6, 2.8, wall, -3.5, 1.4, 0, 'e');                                                                // west, behind the panels
  K.plane(3.3, 2.8, wall, 3.5, 1.4, -1.35, 'w'); K.plane(1.7, 2.8, wall, 3.5, 1.4, 2.15, 'w'); K.plane(1.0, 0.6, wall, 3.5, 2.5, 0.8, 'w');   // east: doorway at z 0.8
  K.plane(4, 2.8, wall, -1.5, 1.4, 3, 'n'); K.plane(2, 2.8, wall, 2.5, 1.4, 3, 'n'); K.plane(1.0, 0.6, wall, 1.0, 2.5, 3, 'n');               // south: doorway at x 1.0

  const rect = (x0, z0, x1, z1) => [[x0, z0], [x1, z0], [x1, z1], [x0, z1]].map((p) => new THREE.Vector2(p[0], p[1]));
  const outer = new THREE.Shape(rect(-3.5, -3, 3.5, 3)); outer.holes.push(new THREE.Path(rect(-3.1, -2.6, 3.1, 2.6)));
  const ceilG = new THREE.ShapeGeometry(outer); ceilG.rotateX(PI / 2); K.put(ceilG, ceil, { y: 2.8 });      // the raised ring, with the cove in it
  K.plane(6.2, 5.2, ceil, 0, 2.65, 0, 'down');                                                              // the dropped middle
  K.plane(6.2, 0.15, ledD, 0, 2.725, -2.6, 's'); K.plane(6.2, 0.15, ledD, 0, 2.725, 2.6, 'n');            // its lit lip, facing out into the ring
  K.plane(5.2, 0.15, ledD, -3.1, 2.725, 0, 'w'); K.plane(5.2, 0.15, ledD, 3.1, 2.725, 0, 'e');
  K.glowPlane(7, 0.8, 0, 2.79, -2.8, 'down', 0.42); K.glowPlane(7, 0.8, 0, 2.79, 2.8, 'down', 0.42);
  K.glowPlane(0.8, 5.2, -3.3, 2.79, 0, 'down', 0.42); K.glowPlane(0.8, 5.2, 3.3, 2.79, 0, 'down', 0.42);
  [-1.8, 0, 1.8].forEach((z) => [-1.6, 1.6].forEach((x) => K.put(new THREE.CircleGeometry(0.05, 12), led, { x, y: 2.645, z, rx: PI / 2 })));

  /* ----- west wall: three tall smoked oak panels (3 mm reveals), the lockup on the middle one ----- */
  [-1.633, -0.5, 0.633].forEach((z) => K.box(0.06, 2.6, 1.13, panel, -3.47, 1.3, z, { tile: 1.5 }));
  if (lock) {
    const tx = (c) => T.tex(c, { color: false }), lh = 1.3;
    const mark = K.std('--color-gold-metal', { r: 0.3, m: 0.9, alphaMap: tx(lock.alpha), normalMap: tx(lock.normal), transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.16, envMapIntensity: 1.8 });
    K.plane(lh * lock.aspect, lh, mark, -3.425, 1.55, -0.5, 'e');
  }

  /* ----- machines: simple shapes ----- */
  const bx = (w, h, d, m, x, y, z) => K.box(w, h, d, m, x, y, z);
  // dumbbell rack (-0.5, -2.4): uprights, two shelves, ten dumbbells lying along z
  [-1.4, -0.5, 0.4].forEach((x) => [-2.65, -2.15].forEach((z) => bx(0.05, 0.95, 0.05, iron, x, 0.475, z)));
  [0.5, 0.88].forEach((y) => bx(1.9, 0.04, 0.55, iron, -0.5, y, -2.4));
  for (let i = 0; i < 10; i++) {
    const x = -1.2 + (i % 5) * 0.4 + (i % 5 > 2 ? 0.0 : 0), y = i < 5 ? 0.5 + 0.02 + 0.06 : 0.88 + 0.02 + 0.06;
    K.put(new THREE.CylinderGeometry(0.015, 0.015, 0.34, 8), steel, { x, y, z: -2.4, rx: PI / 2 });
    [-0.14, 0.14].forEach((dz) => K.put(new THREE.CylinderGeometry(0.06, 0.06, 0.07, 14), iron, { x, y, z: -2.4 + dz, rx: PI / 2 }));
  }
  // flat bench (0, -1.4)
  bx(0.32, 0.09, 1.25, padM, 0, 0.47, -1.4); bx(0.06, 0.04, 1.2, iron, 0, 0.4, -1.4);
  [-0.55, 0.55].forEach((dz) => { bx(0.5, 0.04, 0.05, iron, 0, 0.02, -1.4 + dz); bx(0.05, 0.4, 0.05, iron, 0, 0.2, -1.4 + dz); });
  // cable tower (2.6, -1.6): two uprights, beam, pulleys, weight stack, cables
  [2.0, 3.2].forEach((x) => { bx(0.08, 2.3, 0.08, iron, x, 1.15, -1.6); bx(0.12, 0.04, 0.9, iron, x, 0.02, -1.6); });
  bx(1.28, 0.08, 0.1, iron, 2.6, 2.3, -1.6); bx(0.34, 1.2, 0.3, iron, 2.0 + 0.0, 0.7, -1.9); bx(0.28, 0.9, 0.04, steel, 2.0, 0.65, -1.74);
  [[2.0, 2.2], [2.0, 0.3], [3.2, 2.2], [3.2, 0.3]].forEach(([x, y]) => K.put(new THREE.CylinderGeometry(0.07, 0.07, 0.03, 16), steel, { x, y, z: -1.6, rx: PI / 2 }));
  [2.0, 3.2].forEach((x) => K.put(new THREE.CylinderGeometry(0.004, 0.004, 1.9, 4), steel, { x: x + 0.06, y: 1.25, z: -1.6 }));
  // treadmill (-1.3, 2.3), console to the north
  bx(0.7, 0.12, 1.7, iron, -1.3, 0.22, 2.3); bx(0.6, 0.02, 1.5, padM, -1.3, 0.29, 2.3);
  [-0.37, 0.37].forEach((dx) => { bx(0.04, 0.05, 1.7, iron, -1.3 + dx, 0.35, 2.3); bx(0.04, 1.1, 0.04, iron, -1.3 + dx, 0.8, 1.5); });
  bx(0.62, 0.2, 0.08, iron, -1.3, 1.3, 1.5);
  K.shadow(1.1, 2.0, -1.3, 2.3, 0.4); K.shadow(2.1, 0.9, -0.5, -2.4, 0.4); K.shadow(0.8, 1.6, 0, -1.4, 0.35); K.shadow(1.8, 1.3, 2.6, -1.7, 0.4);
  K.flush();

  /* ----- doorways seen through: lounge (south), relaxing zone (east) ----- */
  K.vista('--color-travertine', [1.0, 3], 's', 1.0, 2.2, 1.0);
  K.vista('--color-travertine', [3.5, 0.8], 'e', 1.0, 2.2, 1.0);

  /* ----- light (2700K), lifted so the room never goes black ----- */
  K.hemi('--color-led', '--color-walnut', 0.5);
  K.light('--color-light-warm', 4, 6, 0, 2.6, -1.0);
  K.light('--color-light-warm', 4, 6, 0, 2.6, 1.8);
  K.light('--color-light-warm', 2, 2.5, -2.6, 2.3, -0.5, true);

  return {
    view: { pos: [1.5, 1.6, 2.2], yaw: -38, pitch: -4 },
    exposure: 1.0,
    markers: [{ to: 'lounge', at: [1.0, 1.1, 2.95] }, { to: 'relaxing-zone', at: [3.45, 1.1, 0.8] }],
  };
}
