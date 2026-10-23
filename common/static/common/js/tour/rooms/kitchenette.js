/* Kitchenette (round 2 addition; look from .private/fal-renders/kitchenette.png). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Interior 4.4 x 5.0 x 2.7 (x -2.2..2.2, z -2.5..2.5). The counter runs along the north wall: walnut cabinets, a travertine top and splashback, a bronze built-in coffee machine and tap,
 * one open oak shelf of cream cups (one instanced mesh), the gold swan on the walnut panel above, a warm LED wash under the ceiling. Two low caramel bouclé chairs round a travertine table
 * under a frosted pendant. Cream fluted panelling low on the other walls. Doorways: south (back to the gym), east (on to the massage room). */

export async function build(scene, ctx) {
  const { THREE, K, T, S } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), wrap = { wrap: true };

  /* ----- maps (4 of our own) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 9, ao: 3, joint: S / 2, jointY: S / 2 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.travertine(S, { seed: 14, joint: S / 2, jointY: S / 4 }), wrap); await ctx.idle();
  const walnutMap = T.tex(T.oak(S >> 1, { seed: 3, tone: '--color-walnut' }), wrap);
  const flutedMap = T.tex(T.slats(S >> 1, { n: 32, tone: '--color-cream' }), wrap);
  scene.environment = ctx.env('--color-travertine');

  /* ----- materials ----- */
  const wall = K.std(WHITE, { r: 0.6, map: wallMap }), floor = K.std(WHITE, { r: 0.35, map: floorMap }), ceil = K.std('--color-cream', { r: 1 });
  const walnut = K.std(WHITE, { r: 0.55, map: walnutMap }), fluted = K.std(WHITE, { r: 0.8, map: flutedMap }), oak = K.std('--color-caramel', { r: 0.6 });
  const stone = K.std('--color-travertine', { r: 0.45 }), cup = K.std('--color-cream-raised', { r: 0.5 }), boucle = K.std('--color-caramel', { r: 1 });
  const bronze = K.std('--color-glass-bronze', { r: 0.3, m: 0.9 }), dark = K.std('--color-iron', { r: 0.25, m: 0.4 }), line = K.basic('--color-espresso');
  const led = K.basic('--color-led-warm'), lamp = K.hot('--color-light-warm', 1.1);
  const X0 = -2.2, X1 = 2.2, Z0 = -2.5, Z1 = 2.5, H = 2.7, DW = 0.9;

  /* ----- shell: floor, ceiling, walls (two doorways), low fluted panelling ----- */
  K.plane(4.4, 5, floor, 0, 0, 0, 'up', { tile: 2.4 }); K.plane(4.4, 5, ceil, 0, H, 0, 'down');
  K.plane(3.7, H, walnut, -0.35, H / 2, Z0, 's', { tile: 1.4 }); K.plane(0.7, H, wall, 1.85, H / 2, Z0, 's', { tile: 2.4 });   // north: walnut behind the counter
  K.plane(5, H, wall, X0, H / 2, 0, 'e', { tile: 2.4 }); K.plane(5, 1.0, fluted, X0 + 0.01, 0.5, 0, 'e', { tile: 0.8 });
  const wallDoor = (face, fixed, a, b, c) => {                                                  // a..b wall run, door centred on c: the pieces, the lintel and the panelling
    const d0 = c - DW / 2, d1 = c + DW / 2, put = (u0, u1, y0, y1, m, o = 0) => {
      const w = u1 - u0, h = y1 - y0, u = (u0 + u1) / 2, y = (y0 + y1) / 2, tile = m === fluted ? 0.8 : 2.4;
      if (face === 'w') K.plane(w, h, m, fixed - o, y, u, 'w', { tile }); else K.plane(w, h, m, u, y, fixed - o, 'n', { tile });
    };
    put(a, d0, 0, H, wall); put(d1, b, 0, H, wall); put(d0, d1, 2.1, H, wall);
    put(a, d0, 0, 1.0, fluted, 0.01); put(d1, b, 0, 1.0, fluted, 0.01);
  };
  wallDoor('w', X1, Z0, Z1, -0.9);                                                               // east wall (faces west), door to the massage room
  wallDoor('n', Z1, X0, X1, -1.0);                                                               // south wall (faces north), door back to the gym
  K.vista('--color-travertine', [X1, -0.9], 'e', DW, 2.1, 1.0); K.vista('--color-travertine', [-1.0, Z1], 's', DW, 2.1, 1.0);
  [[X1 - 0.01, -0.9], [-1.0, Z1 - 0.01]].forEach(([x, z], i) => K.box(i ? DW : 0.012, 0.012, i ? 0.012 : DW, led, x, 2.1, z));

  /* ----- the counter wall ----- */
  K.box(3.1, 0.88, 0.58, walnut, -0.65, 0.44, Z0 + 0.29, { tile: 1.4 });                       // base cabinets x -2.2..0.9
  K.box(3.1, 0.04, 0.62, stone, -0.65, 0.9, Z0 + 0.31);                                          // travertine top
  K.plane(2.25, 0.5, stone, -0.275, 1.17, Z0 + 0.005, 's');                                      // splashback
  K.box(0.62, 2.4, 0.6, walnut, 1.2, 1.2, Z0 + 0.3, { tile: 1.4 });                              // tall unit x 0.9..1.5
  [-1.0, -0.2].forEach((x) => K.box(0.006, 0.84, 0.01, line, x, 0.44, Z0 + 0.585));              // door and drawer joints on the cabinet fronts
  [0.3, 0.58].forEach((y) => K.box(0.8, 0.006, 0.01, line, -0.6, y, Z0 + 0.585));
  K.box(0.006, 1.6, 0.01, line, 0.9, 1.7, Z0 + 0.585); K.box(0.58, 0.006, 0.01, line, 1.2, 1.45, Z0 + 0.603);
  K.box(3.1, 0.04, 0.26, oak, -0.65, 1.55, Z0 + 0.13);                                           // the open oak shelf
  /* coffee machine: bronze frame, black glass front, small display and spout; tap and sink */
  K.box(0.62, 0.46, 0.46, bronze, -1.75, 1.17, Z0 + 0.25); K.box(0.54, 0.38, 0.02, dark, -1.75, 1.17, Z0 + 0.49);
  K.box(0.08, 0.1, 0.04, bronze, -1.75, 1.2, Z0 + 0.47); K.box(0.16, 0.02, 0.01, led, -1.75, 1.34, Z0 + 0.5);
  K.put(new THREE.CylinderGeometry(0.012, 0.012, 0.3, 10), bronze, { x: -0.3, y: 1.07, z: Z0 + 0.18 });
  K.put(new THREE.CylinderGeometry(0.012, 0.012, 0.16, 10).rotateZ(PI / 2), bronze, { x: -0.3, y: 1.22, z: Z0 + 0.25, ry: PI / 2 });
  K.plane(0.5, 0.34, dark, -0.3, 0.922, Z0 + 0.34, 'up');                                       // the sink, flush
  /* cups: one instanced mesh of cups, one of handles */
  const nCup = 13, cupX = (i) => -2.05 + i * 0.205;
  K.inst(new THREE.CylinderGeometry(0.04, 0.032, 0.08, 12).translate(0, 0.04, 0), cup, nCup, (i, o) => o.position.set(cupX(i), 1.57, Z0 + 0.13));
  K.inst(new THREE.TorusGeometry(0.02, 0.006, 6, 10).rotateY(0), cup, nCup, (i, o) => o.position.set(cupX(i) + 0.052, 1.61, Z0 + 0.13));

  /* ----- the swan on the walnut panel, with an LED wash above ----- */
  const lock = ctx.logo('mark', { normal: true });
  if (lock) {
    const tx = (c, opt) => T.tex(c, opt || { color: false }), lh = 0.7;
    K.plane(lh * lock.aspect, lh, K.std('--color-gold-metal', { r: 0.35, m: 0.85, alphaMap: tx(lock.alpha), normalMap: lock.normal ? tx(lock.normal) : null, transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.2, envMapIntensity: 1.8 }), -1.1, 2.08, Z0 + 0.012, 's');
  }
  K.box(3.7, 0.014, 0.02, led, -0.35, 2.62, Z0 + 0.03); K.glowPlane(3.7, 0.55, -0.35, 2.4, Z0 + 0.02, 's', 0.3);
  [[-1.3, -0.8], [0.4, -0.5], [-0.4, 1.4], [1.3, 0.3]].forEach(([x, z]) => K.put(new THREE.CircleGeometry(0.06, 14), led, { x, y: H - 0.003, z, rx: PI / 2 }));

  /* ----- two low caramel bouclé chairs round a travertine table, pendant above ----- */
  const TX = 1.05, TZ = 1.55;
  const chair = (x, z) => {
    const ry = Math.atan2(TX - x, TZ - z), o = { x, z, ry };
    K.put(new THREE.CylinderGeometry(0.33, 0.3, 0.3, 24).translate(0, 0.15, 0), boucle, o);
    K.put(new THREE.CylinderGeometry(0.4, 0.4, 0.17, 24).translate(0, 0.385, 0), boucle, o);
    K.put(K.sector(0.28, 0.47, 190, 350, 0.78, 0, 0, 0.02, 0.03), boucle, o);
    K.shadow(1.15, 1.15, x, z, 0.4);
  };
  chair(0.25, 0.85); chair(1.85, 0.95);
  K.put(new THREE.CylinderGeometry(0.31, 0.31, 0.04, 28).translate(0, 0.43, 0), stone, { x: TX, z: TZ });
  K.put(new THREE.CylinderGeometry(0.17, 0.2, 0.41, 20).translate(0, 0.205, 0), stone, { x: TX, z: TZ }); K.shadow(0.8, 0.8, TX, TZ, 0.3);
  K.put(new THREE.CylinderGeometry(0.004, 0.004, 0.95, 6).translate(0, 2.2, 0), bronze, { x: TX, z: TZ });
  K.put(new THREE.SphereGeometry(0.13, 18, 12).scale(1, 0.82, 1).translate(0, 1.7, 0), lamp, { x: TX, z: TZ });
  K.glowPlane(0.8, 0.8, TX, 1.7, TZ, 's', 0.45); K.glowPlane(0.8, 0.8, TX, 1.7, TZ, 'e', 0.45);
  K.flush();

  /* ----- light (2700K): the pendant, a wash on the counter wall, one soft fill ----- */
  K.hemi('--color-led', '--color-caramel', 0.42);
  K.light('--color-light-warm', 2.6, 4.5, -0.6, 2.2, -1.6);
  K.light('--color-light-warm', 1.8, 3.6, TX, 1.6, TZ);
  K.light('--color-light-warm', 1.2, 4, -0.8, 2.4, 1.2, true);

  return {
    view: { pos: [-0.3, 1.6, 1.9], yaw: -6, pitch: -5 },
    exposure: 0.92,
    markers: [{ to: 'gym', at: [-1.0, 1.1, 2.45] }, { to: 'massage-room', at: [2.15, 1.1, -0.9] }],
  };
}
