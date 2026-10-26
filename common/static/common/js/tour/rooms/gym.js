/* Gym (docs/design/VIRTUAL-TOUR.md 2.5; 2026-10-26 Moishe: a much smaller gym). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 5.6 x 5.8 x 2.6 (x -2.8..2.8, z -3.6..2.2). West: smoked oak panels with the gold stacked lockup and a dumbbell rack on a rubber mat, and a deadlift platform with a loaded bar. Middle: a bench press (bench, rack, barbell). East: a walnut panel with a
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
  const iron = K.std(K.col('--color-iron').clone().multiplyScalar(1.5), { r: 0.45, m: 0.6 }), padM = K.std(K.col('--color-caramel').clone().multiplyScalar(0.5), { r: 0.6 }), steel = K.std('--color-text-muted-inverse', { r: 0.35, m: 0.9 });
  const rubber = K.std('--color-iron', { r: 0.95 }), glass = K.basic(K.col('--color-iron').clone().multiplyScalar(0.9)), screen = K.hot('--color-led-warm', 1.3), walnut = K.std('--color-walnut', { r: 0.6 });
  const gold = K.std('--color-gold-metal', { r: 0.3, m: 0.9, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.14, envMapIntensity: 1.8 });

  /* ----- shell: floor, walls, mirrors, dropped ceiling with cove ----- */
  const XW = 2.8, Z0 = -3.6, Z1 = 2.2, H = 2.6, W = XW * 2, D = Z1 - Z0, ZC = (Z0 + Z1) / 2, PZ = Z0 - 0.6;      // 5.6 x 5.8 x 2.6; the passage runs 1.2 further north
  K.plane(W, D, floor, 0, 0, ZC, 'up', { tile: 1.44 });
  K.plane(2.4, 1.2, floor, 0, 0, PZ, 'up', { tile: 1.44 });                                                 // the passage floor
  for (const s of [-1, 1]) {                                                                                // north, around the mirrors
    K.plane(1.6, H, wall, s * 2.0, H / 2, Z0, 's');
    for (const d of [-0.4, 0.4]) K.plane(0.78, 1.4, mirror, s * 2.0 + d, 1.7, Z0 + 0.01, 's');
  }
  K.plane(D, H, wall, -XW, H / 2, ZC, 'e');                                                                 // west, behind the panels
  K.plane(D, H, wall, XW, H / 2, ZC, 'w');                                                                  // east, behind the window
  K.plane(3.3, H, wall, -1.15, H / 2, Z1, 'n'); K.plane(1.3, H, wall, 2.15, H / 2, Z1, 'n'); K.plane(1.0, H - 2.2, wall, 1.0, (H + 2.2) / 2, Z1, 'n');   // south, around the lounge door at x 1.0
  // passage: side walls, back wall with one door (to the massage room, x 0), ceiling
  K.plane(1.2, H, wall, -1.2, H / 2, PZ, 'e'); K.plane(1.2, H, wall, 1.2, H / 2, PZ, 'w');
  const PB = Z0 - 1.2;
  K.plane(0.7, 2.2, wall, -0.85, 1.1, PB, 's'); K.plane(0.7, 2.2, wall, 0.85, 1.1, PB, 's'); K.plane(2.4, H - 2.2, wall, 0, (H + 2.2) / 2, PB, 's');
  K.plane(2.4, 1.2, ceil, 0, H, PZ, 'down'); K.plane(2.4, 0.5, ledD, 0, H - 0.25, Z0 - 0.001, 's');
  K.box(0.08, 2.25, 0.1, walnut, -0.5, 1.125, PB + 0.05); K.box(0.08, 2.25, 0.1, walnut, 0.5, 1.125, PB + 0.05); K.box(1.08, 0.06, 0.1, walnut, 0, 2.23, PB + 0.05);
  K.glowPlane(1.6, 1.0, 0, 0.007, PZ, 'up', 0.35);

  const rect = (x0, z0, x1, z1) => [[x0, z0], [x1, z0], [x1, z1], [x0, z1]].map((p) => new THREE.Vector2(p[0], p[1]));
  const outer = new THREE.Shape(rect(-XW, Z0, XW, Z1)); outer.holes.push(new THREE.Path(rect(-XW + 0.4, Z0 + 0.4, XW - 0.4, Z1 - 0.4)));
  const ceilG = new THREE.ShapeGeometry(outer); ceilG.rotateX(PI / 2); K.put(ceilG, ceil, { y: H });          // the raised ring, with the cove in it
  K.plane(W - 0.8, D - 0.8, ceil, 0, H - 0.15, ZC, 'down');                                                 // the dropped middle
  K.plane(W - 0.8, 0.15, ledD, 0, H - 0.075, Z0 + 0.4, 's'); K.plane(W - 0.8, 0.15, ledD, 0, H - 0.075, Z1 - 0.4, 'n');   // its lit lip, facing out into the ring
  K.plane(D - 0.8, 0.15, ledD, -XW + 0.4, H - 0.075, ZC, 'w'); K.plane(D - 0.8, 0.15, ledD, XW - 0.4, H - 0.075, ZC, 'e');
  K.glowPlane(W, 0.8, 0, H - 0.01, Z0 + 0.2, 'down', 0.42); K.glowPlane(W, 0.8, 0, H - 0.01, Z1 - 0.2, 'down', 0.42);
  K.glowPlane(0.8, D, -XW + 0.2, H - 0.01, ZC, 'down', 0.42); K.glowPlane(0.8, D, XW - 0.2, H - 0.01, ZC, 'down', 0.42);
  [-2.6, -0.7, 1.2].forEach((z) => [-1.4, 1.4].forEach((x) => K.put(new THREE.CircleGeometry(0.05, 12), led, { x, y: H - 0.155, z, rx: PI / 2 })));

  /* ----- west wall: four smoked oak panels (reveals between), the lockup on the third ----- */
  const PW = D / 4;
  for (let i = 0; i < 4; i++) K.box(0.06, H - 0.2, PW - 0.02, panel, -XW + 0.03, (H - 0.2) / 2, Z0 + PW * (i + 0.5), { tile: 1.5 });
  if (lock) {
    const tx = (c) => T.tex(c, { color: false }), lh = 1.25;
    const mark = K.std('--color-gold-metal', { r: 0.3, m: 0.9, alphaMap: tx(lock.alpha), normalMap: tx(lock.normal), transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.16, envMapIntensity: 1.8 });
    K.plane(lh * lock.aspect, lh, mark, -XW + 0.075, 1.5, Z0 + PW * 2.5, 'e');
  }

  /* ----- east wall: a walnut panel with the wall screen (off) the treadmill and the bike face, then a shorter night window to the south ----- */
  K.box(0.05, H - 0.2, 2.5, panel, XW - 0.03, (H - 0.2) / 2, -1.85, { tile: 1.5 });
  K.box(0.04, 1.18, 2.18, iron, XW - 0.075, 1.65, -1.85);
  const tv = K.std(K.col('--color-iron').clone().multiplyScalar(0.55), { r: 0.12, m: 0.5, envMapIntensity: 1.2 });
  K.plane(2.1, 1.1, tv, XW - 0.095, 1.65, -1.85, 'w');
  K.plane(2.2, 1.3, glass, XW - 0.01, 1.45, 0.95, 'w');
  for (const z of [-0.15, 0.95, 2.05]) K.box(0.05, 1.3, 0.06, walnut, XW - 0.02, 1.45, z);
  K.box(0.05, 0.06, 2.3, walnut, XW - 0.02, 2.1, 0.95); K.box(0.05, 0.06, 2.3, walnut, XW - 0.02, 0.8, 0.95);
  K.glowPlane(2.2, 1.3, XW - 0.05, 1.45, 0.95, 'w', 0.12);

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
  treadmill(1.75, -2.7);

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
  bike(2.0, -1.0);

  // a rubber mat under the dumbbell rack
  K.put(new THREE.PlaneGeometry(1.2, 2.4).rotateX(-PI / 2), rubber, { x: -2.2, y: 0.006, z: -2.4 });

  // dumbbell rack on the west wall: two shelves, twelve dumbbells (heads instanced)
  {
    const RX = -XW + 0.35, RZ = -2.4, m = at(RX, RZ, 0), heads = [];
    [-0.9, 0, 0.9].forEach((lz) => [-0.25, 0.25].forEach((lx) => m.box(0.05, 0.95, 0.05, iron, lx, 0.475, lz)));
    [0.45, 0.8].forEach((ly) => m.box(0.6, 0.04, 1.9, iron, 0, ly, 0));
    [0.45, 0.8].forEach((ly) => { for (let i = 0; i < 6; i++) { const lz = -0.75 + i * 0.3; m.cyl(0.012, 0.3, steel, 0, ly + 0.085, lz, 'x', 8); [-0.14, 0.14].forEach((lx) => heads.push([RX + lx, ly + 0.085, RZ + lz])); } });
    const hg = new THREE.CylinderGeometry(0.055, 0.055, 0.07, 14); hg.rotateZ(PI / 2);
    K.inst(hg, iron, heads.length, (i, o) => o.position.set(...heads[i]));
    K.shadow(0.9, 2.2, RX + 0.1, RZ, 0.4);
  }

  // a loaded barbell along local x at height y, z: the bar, its sleeves, and plate pairs ([offset from the centre, radius]) on both ends, with collars
  const barbell = (m, y, z, plates) => {
    m.cyl(0.014, 2.2, steel, 0, y, z, 'x', 8);
    plates.forEach(([o, r]) => [-1, 1].forEach((s) => m.cyl(r, 0.04, iron, s * o, y, z, 'x', 18)));
    [-1, 1].forEach((s) => { m.cyl(0.025, 0.4, steel, s * 0.95, y, z, 'x', 8); m.cyl(0.03, 0.03, steel, s * (plates[plates.length - 1][0] + 0.05), y, z, 'x', 8); });
  };

  // bench press: a flat padded bench, two rack uprights with J-hooks at the head end, a loaded bar on the hooks, a rubber mat
  {
    const BX = -0.6, UZ = -1.2, m = at(BX, 0, 0), HY = 1.15;
    K.put(new THREE.PlaneGeometry(2.2, 2.0).rotateX(-PI / 2), rubber, { x: BX, y: 0.008, z: -0.4 });
    m.box(0.3, 0.08, 1.25, padM, 0, 0.44, -0.375); m.box(0.1, 0.05, 1.1, iron, 0, 0.375, -0.375);                  // pad and its frame
    [-0.85, 0.1].forEach((z) => { m.box(0.05, 0.36, 0.05, iron, 0, 0.2, z); m.box(0.55, 0.05, 0.06, iron, 0, 0.025, z); });
    [-0.55, 0.55].forEach((x) => {
      m.box(0.05, 1.35, 0.05, iron, x, 0.675, UZ); m.box(0.06, 0.05, 0.9, iron, x, 0.025, UZ);                      // upright and its foot
      m.box(0.05, 0.04, 0.1, steel, x, HY - 0.03, UZ + 0.05);                                                       // J-hook
    });
    m.box(1.15, 0.04, 0.04, iron, 0, 1.3, UZ);
    barbell(m, HY + 0.02, UZ + 0.1, [[0.7, 0.22], [0.75, 0.22], [0.8, 0.15]]);
    K.shadow(2.0, 1.8, BX, -0.5, 0.35);
  }

  // deadlift platform: oak centre between two rubber ends, a loaded barbell lying on it
  {
    const PX = -1.55, PZc = 1.25, m = at(PX, PZc, 0), TOP = 0.06;
    [-0.9, 0.9].forEach((x) => m.box(0.6, TOP, 1.15, rubber, x, TOP / 2, 0)); m.box(1.2, TOP + 0.003, 1.15, panel, 0, TOP / 2, 0, { tile: 1.5 });
    barbell(m, TOP + 0.225, 0, [[0.68, 0.225], [0.72, 0.225], [0.76, 0.225], [0.8, 0.14]]);
    K.shadow(2.8, 1.5, PX, PZc, 0.35);
  }

  K.flush();

  /* ----- doorways seen through: the lounge (south) and, at the far end, the massage room ----- */
  K.vista('--color-travertine', [1.0, Z1], 's', 1.0, 2.2, 1.0);
  K.vista('--color-travertine', [0, PB], 'n', 1.0, 2.2, 0.9);                    // far end: the massage room
  K.edge(-XW, Z1, 0, -1, D, 1, 0, 0.5, 0.5); K.edge(XW, Z1, 0, -1, D, -1, 0, 0.5, 0.5);

  /* ----- light (2700K), lifted so the room never goes black ----- */
  K.hemi('--color-led', '--color-walnut', 0.5);
  K.light('--color-light-warm', 4, 6, 0, 2.4, -1.9);
  K.light('--color-light-warm', 4, 6, 0, 2.4, 0.9);
  K.light('--color-light-warm', 2, 2.5, -1.9, 2.2, Z0 + PW * 2.5, true);
  K.light('--color-light-warm', 1.6, 3, 0, 2.2, PB + 0.6, true);

  return {
    view: { pos: [1.9, 1.6, 1.7], yaw: -26, pitch: -8 },
    exposure: 1.0,
    markers: [{ to: 'lounge', at: [1.0, 1.1, Z1 - 0.05] }, { to: 'massage-room', at: [0, 1.1, PB + 0.05] }],
  };
}
