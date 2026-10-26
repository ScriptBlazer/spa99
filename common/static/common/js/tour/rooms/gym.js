/* Gym (docs/design/VIRTUAL-TOUR.md 2.5; 2026-10-26 Moishe: a much smaller gym). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 7.0 x 8.0 x 2.8 (x -3.5..3.5, z -5..3). West: smoked oak panels with the gold stacked lockup and one dumbbell rack on a rubber mat. East: a walnut panel with a
 * wall screen (off), one treadmill and one exercise bike facing it, and a shorter night window to the south. North: mirrors, and in the middle a short passage whose
 * back wall has one door on to the massage room (then the kitchenette, the relaxing zone and the saunas). The way in is the lounge door in the south wall (x 1.0). */

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
  const iron = K.std(K.col('--color-iron').clone().multiplyScalar(1.5), { r: 0.45, m: 0.6 }), padM = K.std('--color-walnut', { r: 0.6 }), steel = K.std('--color-text-muted-inverse', { r: 0.35, m: 0.9 });
  const rubber = K.std('--color-iron', { r: 0.95 }), glass = K.basic(K.col('--color-iron').clone().multiplyScalar(0.9)), screen = K.hot('--color-led-warm', 1.3), walnut = K.std('--color-walnut', { r: 0.6 });
  const gold = K.std('--color-gold-metal', { r: 0.3, m: 0.9, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.14, envMapIntensity: 1.8 });

  /* ----- shell: floor, walls, mirrors, dropped ceiling with cove ----- */
  const Z0 = -5, ZC = -1, D = 8;
  K.plane(7, D, floor, 0, 0, ZC, 'up', { tile: 1.44 });
  K.plane(2.4, 1.2, floor, 0, 0, -5.6, 'up', { tile: 1.44 });                                               // the passage floor
  K.plane(2.3, 1.0, wall, -2.35, 0.5, Z0, 's'); K.plane(2.3, 1.0, wall, 2.35, 0.5, Z0, 's');                // north, around the mirrors
  K.plane(7, 0.2, wall, 0, 2.7, Z0, 's'); K.plane(2.3, 0.4, wall, -2.35, 2.4, Z0, 's'); K.plane(2.3, 0.4, wall, 2.35, 2.4, Z0, 's');
  for (const cx of [-2.35, 2.35]) for (const d of [-0.575, 0.575]) K.plane(1.14, 1.4, mirror, cx + d, 1.7, Z0 + 0.01, 's');
  K.plane(2.3, 1.4, wall, -2.35, 1.7, Z0 + 0.001, 's'); K.plane(2.3, 1.4, wall, 2.35, 1.7, Z0 + 0.001, 's');   // dark joint backing, behind the mirrors
  K.plane(8, 2.8, wall, -3.5, 1.4, ZC, 'e');                                                                // west, behind the panels
  K.plane(8, 2.8, wall, 3.5, 1.4, ZC, 'w');                                                                 // east, behind the window
  K.plane(4.0, 2.8, wall, -1.5, 1.4, 3, 'n'); K.plane(2.0, 2.8, wall, 2.5, 1.4, 3, 'n'); K.plane(1.0, 0.6, wall, 1.0, 2.5, 3, 'n');   // south, around the lounge door at x 1.0
  // passage: side walls, back wall with one door (to the massage room, x 0), ceiling
  K.plane(1.2, 2.8, wall, -1.2, 1.4, -5.6, 'e'); K.plane(1.2, 2.8, wall, 1.2, 1.4, -5.6, 'w');
  K.plane(0.7, 2.2, wall, -0.85, 1.1, -6.2, 's'); K.plane(0.7, 2.2, wall, 0.85, 1.1, -6.2, 's'); K.plane(2.4, 0.6, wall, 0, 2.5, -6.2, 's');
  K.plane(2.4, 1.2, ceil, 0, 2.8, -5.6, 'down'); K.plane(2.4, 0.5, ledD, 0, 2.55, -5.0 - 0.001, 's');
  K.box(0.08, 2.25, 0.1, walnut, -0.5, 1.125, -6.15); K.box(0.08, 2.25, 0.1, walnut, 0.5, 1.125, -6.15); K.box(1.08, 0.06, 0.1, walnut, 0, 2.23, -6.15);
  K.glowPlane(1.6, 1.0, 0, 0.007, -5.6, 'up', 0.35);

  const rect = (x0, z0, x1, z1) => [[x0, z0], [x1, z0], [x1, z1], [x0, z1]].map((p) => new THREE.Vector2(p[0], p[1]));
  const outer = new THREE.Shape(rect(-3.5, Z0, 3.5, 3)); outer.holes.push(new THREE.Path(rect(-3.1, -4.6, 3.1, 2.6)));
  const ceilG = new THREE.ShapeGeometry(outer); ceilG.rotateX(PI / 2); K.put(ceilG, ceil, { y: 2.8 });      // the raised ring, with the cove in it
  K.plane(6.2, 7.2, ceil, 0, 2.65, -1, 'down');                                                             // the dropped middle
  K.plane(6.2, 0.15, ledD, 0, 2.725, -4.6, 's'); K.plane(6.2, 0.15, ledD, 0, 2.725, 2.6, 'n');            // its lit lip, facing out into the ring
  K.plane(7.2, 0.15, ledD, -3.1, 2.725, -1, 'w'); K.plane(7.2, 0.15, ledD, 3.1, 2.725, -1, 'e');
  K.glowPlane(7, 0.8, 0, 2.79, -4.8, 'down', 0.42); K.glowPlane(7, 0.8, 0, 2.79, 2.8, 'down', 0.42);
  K.glowPlane(0.8, 7.2, -3.3, 2.79, -1, 'down', 0.42); K.glowPlane(0.8, 7.2, 3.3, 2.79, -1, 'down', 0.42);
  [-3.6, -1.2, 1.2].forEach((z) => [-1.6, 1.6].forEach((x) => K.put(new THREE.CircleGeometry(0.05, 12), led, { x, y: 2.645, z, rx: PI / 2 })));

  /* ----- west wall: six smoked oak panels (reveals between), the lockup on the fourth ----- */
  for (let i = 0; i < 6; i++) K.box(0.06, 2.6, 1.13, panel, -3.47, 1.3, -4.135 + 1.14 * i, { tile: 1.5 });
  if (lock) {
    const tx = (c) => T.tex(c, { color: false }), lh = 1.3;
    const mark = K.std('--color-gold-metal', { r: 0.3, m: 0.9, alphaMap: tx(lock.alpha), normalMap: tx(lock.normal), transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.16, envMapIntensity: 1.8 });
    K.plane(lh * lock.aspect, lh, mark, -3.425, 1.55, -0.715, 'e');
  }

  /* ----- east wall: a walnut panel with the wall screen (off) the treadmill and the bike face, then a shorter night window to the south ----- */
  K.box(0.05, 2.6, 2.4, panel, 3.47, 1.3, -2.3, { tile: 1.5 });
  K.box(0.04, 0.98, 1.68, iron, 3.43, 1.7, -2.3);
  const tv = K.std(K.col('--color-iron').clone().multiplyScalar(0.55), { r: 0.12, m: 0.5, envMapIntensity: 1.2 });
  K.plane(1.6, 0.9, tv, 3.405, 1.7, -2.3, 'w');
  K.plane(3.2, 1.4, glass, 3.49, 1.55, 1.0, 'w');
  for (const z of [-0.6, 1.0, 2.6]) K.box(0.05, 1.5, 0.06, walnut, 3.48, 1.55, z);
  K.box(0.05, 0.06, 3.3, walnut, 3.48, 2.27, 1.0); K.box(0.05, 0.06, 3.3, walnut, 3.48, 0.84, 1.0);
  K.glowPlane(3.2, 1.4, 3.45, 1.55, 1.0, 'w', 0.12);

  /* ----- machine helpers: a part is placed in a machine's local frame (local +x is its front), then turned by `a` about the vertical at (ox, oz) ----- */
  const at = (ox, oz, a) => {
    const c = Math.cos(a), s = Math.sin(a), wp = (lx, lz) => [ox + lx * c + lz * s, oz - lx * s + lz * c];
    return {
      box(w, h, d, m, lx, ly, lz, o = {}) { const [x, z] = wp(lx, lz); return K.put(new THREE.BoxGeometry(w, h, d), m, { x, y: ly, z, ry: a, ...o }); },
      cyl(r, len, m, lx, ly, lz, ax = 'z', seg = 12) {                                                     // cylinder along local axis x, y or z
        const g = new THREE.CylinderGeometry(r, r, len, seg); if (ax === 'x') g.rotateZ(PI / 2); else if (ax === 'z') g.rotateX(PI / 2);
        const [x, z] = wp(lx, lz); return K.put(g, m, { x, y: ly, z, ry: a });
      },
      wp,
    };
  };

  // treadmill: deck, belt, rails, two uprights, console with a lit display facing the runner
  const treadmill = (x, z) => {
    const m = at(x, z, 0);
    m.box(1.7, 0.12, 0.75, iron, 0, 0.2, 0); m.box(1.5, 0.025, 0.6, rubber, -0.02, 0.27, 0);
    [-0.37, 0.37].forEach((s) => { m.box(1.7, 0.05, 0.04, steel, 0, 0.3, s); m.box(0.045, 1.0, 0.045, iron, 0.7, 0.78, s * 0.92); m.box(0.55, 0.03, 0.03, steel, 0.45, 1.05, s * 0.92); });
    m.box(0.12, 0.24, 0.66, iron, 0.74, 1.22, 0); m.box(0.01, 0.12, 0.4, screen, 0.675, 1.24, 0); m.box(0.1, 0.05, 0.7, iron, 0.74, 1.05, 0);
    K.shadow(2.0, 1.0, x, z, 0.4);
  };
  treadmill(2.3, -2.9);

  // upright bike
  const bike = (x, z) => {
    const m = at(x, z, 0);
    m.cyl(0.24, 0.1, iron, 0.32, 0.42, 0, 'z', 18); m.cyl(0.015, 0.5, steel, 0.12, 0.3, 0, 'z', 8);
    [-0.2, 0.2].forEach((s) => m.box(0.2, 0.03, 0.09, steel, 0.12, 0.3, s));
    m.box(0.1, 0.05, 0.62, iron, 0.55, 0.03, 0); m.box(0.1, 0.05, 0.5, iron, -0.35, 0.03, 0);
    m.box(0.05, 0.7, 0.05, iron, -0.2, 0.4, 0); m.box(0.3, 0.07, 0.2, padM, -0.24, 1.0, 0);
    m.box(0.05, 0.75, 0.05, iron, 0.46, 0.62, 0); m.box(0.07, 0.04, 0.5, steel, 0.46, 1.1, 0); m.box(0.06, 0.12, 0.2, iron, 0.5, 1.2, 0); m.box(0.005, 0.07, 0.15, screen, 0.465, 1.2, 0);
    m.box(0.05, 0.05, 0.05, iron, 0.2, 0.55, 0); m.box(0.05, 0.9, 0.05, iron, 0.0, 0.5, 0);
    K.shadow(1.3, 0.8, x, z, 0.4);
  };
  bike(2.5, -1.6);

  // a rubber mat under the dumbbell rack
  K.put(new THREE.PlaneGeometry(1.4, 2.8).rotateX(-PI / 2), rubber, { x: -2.8, y: 0.006, z: -2.8 });

  // dumbbell rack on the west wall: two shelves, twelve dumbbells (heads instanced)
  {
    const m = at(-3.15, -2.8, 0), heads = [];
    [-0.9, 0, 0.9].forEach((lz) => [-0.25, 0.25].forEach((lx) => m.box(0.05, 0.95, 0.05, iron, lx, 0.475, lz)));
    [0.45, 0.8].forEach((ly) => m.box(0.6, 0.04, 1.9, iron, 0, ly, 0));
    [0.45, 0.8].forEach((ly) => { for (let i = 0; i < 6; i++) { const lz = -0.75 + i * 0.3; m.cyl(0.012, 0.3, steel, 0, ly + 0.085, lz, 'x', 8); [-0.14, 0.14].forEach((lx) => heads.push([-3.15 + lx, ly + 0.085, -2.8 + lz])); } });
    const hg = new THREE.CylinderGeometry(0.055, 0.055, 0.07, 14); hg.rotateZ(PI / 2);
    K.inst(hg, iron, heads.length, (i, o) => o.position.set(...heads[i]));
    K.shadow(0.9, 2.2, -3.0, -2.8, 0.4);
  }

  K.flush();

  /* ----- doorways seen through: the lounge (south) and, at the far end, the massage room ----- */
  K.vista('--color-travertine', [1.0, 3], 's', 1.0, 2.2, 1.0);
  K.vista('--color-travertine', [0, -6.2], 'n', 1.0, 2.2, 0.9);                  // far end: the massage room
  K.edge(-3.5, 3, 0, -1, 8, 1, 0, 0.5, 0.5); K.edge(3.5, 3, 0, -1, 8, -1, 0, 0.5, 0.5);

  /* ----- light (2700K), lifted so the room never goes black ----- */
  K.hemi('--color-led', '--color-walnut', 0.5);
  K.light('--color-light-warm', 4, 6, 0, 2.6, -3.0);
  K.light('--color-light-warm', 4, 6, 0, 2.6, 1.0);
  K.light('--color-light-warm', 2, 2.5, -2.6, 2.3, -0.5, true);
  K.light('--color-light-warm', 1.6, 3, 0, 2.3, -5.6, true);

  return {
    view: { pos: [1.0, 1.6, 2.4], yaw: -10, pitch: -3 },
    exposure: 1.0,
    markers: [{ to: 'lounge', at: [1.0, 1.1, 2.95] }, { to: 'massage-room', at: [0, 1.1, -6.15] }],
  };
}
