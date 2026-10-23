/* Gym (docs/design/VIRTUAL-TOUR.md 2.5, round 2: furnished). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 7.0 x 8.0 x 2.8 (x -3.5..3.5, z -5..3). West: smoked oak panels with the gold stacked lockup, a rubber floor zone with the free weights (dumbbell rack, power rack
 * with a barbell, two adjustable benches, kettlebells, plates, a cable machine at the north wall). East: a night window, three treadmills in a row facing it, two exercise
 * bikes and a rower. North: mirrors, and in the middle a short passage whose back wall has one door on to the kitchenette (then the massage room, then the saunas). The way in is the
 * lounge door in the south wall (x 1.0). Everything repeated is instanced or merged per material, so the room stays at about 30 draw calls. */

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
  // passage: side walls, back wall with one door (to the kitchenette, x 0), ceiling
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

  /* ----- east wall: a night window (dark glass, walnut mullions) the treadmills face ----- */
  K.plane(5.6, 1.4, glass, 3.49, 1.55, -1.6, 'w');
  for (let i = 0; i < 5; i++) K.box(0.05, 1.5, 0.06, walnut, 3.48, 1.55, -4.4 + i * 1.4);
  K.box(0.05, 0.06, 5.7, walnut, 3.48, 2.27, -1.6); K.box(0.05, 0.06, 5.7, walnut, 3.48, 0.84, -1.6);
  K.glowPlane(5.6, 1.4, 3.45, 1.55, -1.6, 'w', 0.12);

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
  [-3.7, -2.55, -1.4].forEach((z) => treadmill(2.5, z));

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
  bike(2.65, -0.15); bike(2.65, 0.75);

  // rower
  const rower = (x, z) => {
    const m = at(x, z, 0);
    m.box(2.0, 0.05, 0.1, steel, 0, 0.26, 0); m.box(0.06, 0.26, 0.5, iron, -0.9, 0.13, 0); m.box(0.06, 0.26, 0.5, iron, 0.55, 0.13, 0);
    m.box(0.3, 0.06, 0.26, padM, -0.3, 0.33, 0); m.cyl(0.24, 0.14, iron, 0.85, 0.5, 0, 'z', 18);
    [-0.2, 0.2].forEach((s) => m.box(0.3, 0.02, 0.1, steel, 0.55, 0.42, s));
    m.box(0.03, 0.5, 0.03, steel, 0.95, 0.85, 0); m.box(0.05, 0.04, 0.4, steel, 0.95, 1.1, 0); m.box(0.03, 0.12, 0.22, iron, 1.0, 0.95, 0); m.box(0.005, 0.07, 0.16, screen, 0.98, 0.95, 0);
    K.shadow(2.3, 0.8, x, z, 0.38);
  };
  rower(2.4, 1.95);

  // rubber floor zone for the free weights
  K.put(new THREE.PlaneGeometry(2.65, 7.4).rotateX(-PI / 2), rubber, { x: -2.125, y: 0.006, z: -1.1 });

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

  // power rack with a loaded barbell, on a platform
  {
    const m = at(-1.9, -2.4, -PI / 2);
    m.box(1.7, 0.03, 2.4, rubber, 0, 0.02, 0);
    [-0.55, 0.55].forEach((lx) => [-0.6, 0.6].forEach((lz) => m.box(0.07, 2.2, 0.07, iron, lx, 1.1, lz)));
    [-0.6, 0.6].forEach((lz) => m.box(1.19, 0.07, 0.07, iron, 0, 2.2, lz)); [-0.55, 0.55].forEach((lx) => m.box(0.07, 0.07, 1.27, iron, lx, 2.2, 0));
    [-0.55, 0.55].forEach((lx) => [-0.6, 0.6].forEach((lz) => m.box(0.12, 0.05, 0.1, steel, lx, 1.32, lz)));
    [-0.6, 0.6].forEach((lz) => m.box(1.19, 0.05, 0.05, iron, 0, 0.45, lz));
    m.cyl(0.016, 2.2, steel, 0, 1.38, 0, 'z', 8);
    [-1, 1].forEach((s) => { [0.7, 0.76].forEach((lz) => m.cyl(0.22, 0.05, iron, 0, 1.38, s * lz, 'z', 20)); m.cyl(0.03, 0.04, steel, 0, 1.38, s * 0.82, 'z', 8); });
    K.shadow(1.9, 2.2, -1.9, -2.4, 0.4);
  }

  // two adjustable benches, heads to the wall: one inclined, one flat
  const bench = (x, z, tilt) => {
    const m = at(x, z, PI);
    m.box(0.5, 0.08, 0.3, padM, -0.2, 0.46, 0); m.box(1.2, 0.05, 0.06, iron, 0.05, 0.33, 0);
    m.box(0.05, 0.05, 0.5, iron, -0.5, 0.03, 0); m.box(0.05, 0.05, 0.5, iron, 0.6, 0.03, 0);
    m.box(0.05, 0.3, 0.05, iron, -0.45, 0.18, 0); m.box(0.05, 0.3, 0.05, iron, 0.55, 0.18, 0);
    const [bx, bz] = m.wp(0.12 + 0.36 * Math.cos(tilt), 0);                                                 // the back pad hinges at the seat and rises toward the head
    K.put(new THREE.BoxGeometry(0.72, 0.08, 0.3), padM, { x: bx, y: 0.46 + 0.36 * Math.sin(tilt), z: bz, ry: PI, rz: tilt });
    if (tilt) m.box(0.04, 0.3, 0.04, iron, 0.4, 0.3, 0, { rz: -0.5 });
    K.shadow(1.5, 0.7, x, z, 0.36);
  };
  bench(-1.55, 0.3, 0.7); bench(-1.55, 1.6, 0);

  // kettlebells: a low rack on the west wall (five) and three on the floor, bodies instanced, handles merged
  {
    const m = at(-3.2, 1.2, 0), kb = [];
    m.box(0.5, 0.04, 1.5, iron, 0, 0.25, 0); [-0.7, 0.7].forEach((lz) => [-0.22, 0.22].forEach((lx) => m.box(0.04, 0.25, 0.04, iron, lx, 0.125, lz)));
    for (let i = 0; i < 5; i++) kb.push([-3.2, 0.25 + 0.02 + 0.105, 1.2 - 0.6 + i * 0.3]);
    [[-2.7, 2.4], [-2.4, 2.5], [-2.05, 2.4]].forEach(([x, z]) => kb.push([x, 0.105 + 0.006, z]));
    const handle = (x, y, z) => K.put(new THREE.TorusGeometry(0.06, 0.016, 6, 14), steel, { x, y: y + 0.17, z, ry: PI / 2 });
    kb.forEach(([x, y, z]) => handle(x, y, z));
    K.inst(new THREE.SphereGeometry(0.105, 14, 10), iron, kb.length, (i, o) => o.position.set(...kb[i]));
    K.shadow(0.8, 1.8, -3.15, 1.2, 0.38);
  }

  // plates: two stacks on the floor by the rack (instanced discs of two sizes)
  {
    const pl = [], st = (x, z, n, sc) => { for (let i = 0; i < n; i++) pl.push([x, 0.012 + i * 0.03, z, sc]); };
    st(-0.95, -4.0, 5, 1.0); st(-0.95, -3.45, 4, 0.82);
    K.inst(new THREE.CylinderGeometry(0.225, 0.225, 0.028, 22), iron, pl.length, (i, o) => { o.position.set(pl[i][0], pl[i][1], pl[i][2]); o.scale.set(pl[i][3], 1, pl[i][3]); });
    K.shadow(1.1, 1.8, -0.95, -3.7, 0.4);
  }

  // cable machine at the north wall: two uprights, beam, weight stacks, pulleys, cables, two handles (front faces south)
  {
    const m = at(-2.4, -4.55, -PI / 2);
    [-0.65, 0.65].forEach((lz) => { m.box(0.08, 2.3, 0.08, iron, 0.1, 1.15, lz); m.box(0.8, 0.04, 0.12, iron, 0, 0.02, lz); m.box(0.3, 1.2, 0.3, iron, -0.25, 0.65, lz * 0.9); m.box(0.28, 0.9, 0.02, steel, -0.09, 0.62, lz * 0.9); });
    m.box(0.1, 0.08, 1.38, iron, 0.1, 2.3, 0);
    [-0.65, 0.65].forEach((lz) => [2.2, 0.35].forEach((ly) => m.cyl(0.07, 0.03, steel, 0.17, ly, lz, 'z', 14)));
    [-0.65, 0.65].forEach((lz) => m.cyl(0.004, 1.85, steel, 0.17, 1.28, lz, 'y', 4));
    [-0.65, 0.65].forEach((lz) => m.box(0.03, 0.03, 0.2, steel, 0.17, 0.35, lz));
    K.shadow(1.1, 1.8, -2.35, -4.4, 0.4);
  }
  K.flush();

  /* ----- doorways seen through: the lounge (south) and, at the far end, the kitchenette ----- */
  K.vista('--color-travertine', [1.0, 3], 's', 1.0, 2.2, 1.0);
  K.vista('--color-travertine', [0, -6.2], 'n', 1.0, 2.2, 0.9);                  // far end: the kitchenette
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
    markers: [{ to: 'lounge', at: [1.0, 1.1, 2.95] }, { to: 'kitchenette', at: [0, 1.1, -6.15] }],
  };
}
