/* Massage room (round 2 addition; look from .private/fal-renders/massage-room.png). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Interior 3.6 x 6.4 x 2.7 (x -1.8..1.8, z -3.2..3.2). North: the oak slatted wall with the gold swan. East: three cream-leather massage chairs with walnut sides stand against the wall
 * facing west, with gaps between them (instanced). West: a stone chimney breast with a flush linear fireplace (a gently animated flame and glow) and a large TV above it, facing the chairs.
 * Warm, low light with LED coves along both side walls. Doorways: south (back to the kitchenette), west near the north end (dry sauna, left), east near the north end (wet sauna, right). */

export async function build(scene, ctx) {
  const { THREE, K, T, S } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), wrap = { wrap: true };

  /* ----- maps (4 of our own, plus the flame) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 17, ao: 3, joint: S / 2, jointY: S / 2 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.travertine(S, { seed: 4, joint: S / 2, jointY: S / 4 }), wrap); await ctx.idle();
  const slatMap = T.tex(T.slats(S >> 1, { n: 32, tone: '--color-caramel' }), wrap);
  const walnutMap = T.tex(T.oak(S >> 1, { seed: 6, tone: '--color-walnut' }), wrap);
  scene.environment = ctx.env('--color-caramel');

  /* ----- materials ----- */
  const wall = K.std(WHITE, { r: 0.65, map: wallMap }), floor = K.std(WHITE, { r: 0.4, map: floorMap }), ceil = K.std('--color-cream', { r: 1 });
  const stone = K.std(new THREE.Color(0.82, 0.8, 0.78), { r: 0.7, map: wallMap }), slat = K.std(WHITE, { r: 0.7, map: slatMap }), walnut = K.std(WHITE, { r: 0.5, map: walnutMap });
  const leather = K.std('--color-cream', { r: 0.55 }), dark = K.std('--color-iron', { r: 0.3, m: 0.5 }), bronze = K.std('--color-glass-bronze', { r: 0.3, m: 0.9 });
  const led = K.basic('--color-led-warm'), ember = K.hot('--color-heater-glow', 1.5);
  const X0 = -1.8, X1 = 1.8, Z0 = -3.2, Z1 = 3.2, H = 2.7, DW = 0.9;

  /* ----- shell: floor, ceiling, slatted north wall, side walls with doorways, cove lights ----- */
  K.plane(3.6, 6.4, floor, 0, 0, 0, 'up', { tile: 2.4 }); K.plane(3.6, 6.4, ceil, 0, H, 0, 'down');
  K.plane(3.6, H, slat, 0, H / 2, Z0, 's', { tile: 0.8 });
  const wallDoor = (face, fixed, a, b, c) => {                                                  // a..b wall run, door centred on c: pieces and lintel
    const d0 = c - DW / 2, d1 = c + DW / 2, put = (u0, u1, y0, y1) => {
      const w = u1 - u0, h = y1 - y0, u = (u0 + u1) / 2, y = (y0 + y1) / 2;
      if (face === 'n') K.plane(w, h, wall, u, y, fixed, 'n', { tile: 2.4 }); else K.plane(w, h, wall, fixed, y, u, face, { tile: 2.4 });
    };
    put(a, d0, 0, H); put(d1, b, 0, H); put(d0, d1, 2.1, H);
  };
  wallDoor('e', X0, Z0, Z1, -2.1); wallDoor('w', X1, Z0, Z1, -2.4); wallDoor('n', Z1, X0, X1, -0.5);
  K.vista('--color-cedar', [X0, -2.1], 'w', DW, 2.1, 1.0); K.vista('--color-travertine', [X1, -2.4], 'e', DW, 2.1, 1.0); K.vista('--color-walnut', [-0.5, Z1], 's', DW, 2.1, 1.0);
  [[X0 + 0.01, -2.1, 0.012, DW], [X1 - 0.01, -2.4, 0.012, DW]].forEach(([x, z, w, d]) => K.box(w, 0.012, d, led, x, 2.1, z));
  K.box(DW, 0.012, 0.012, led, -0.5, 2.1, Z1 - 0.01);
  [X0 + 0.03, X1 - 0.03].forEach((x) => { K.box(0.03, 0.014, 6.3, led, x, H - 0.05, 0); K.glowPlane(0.6, 6.3, x < 0 ? x + 0.2 : x - 0.2, H - 0.01, 0, 'down', 0.3); });
  K.box(3.5, 0.014, 0.03, led, 0, H - 0.04, Z0 + 0.03); K.glowPlane(3.4, 0.5, 0, 2.45, Z0 + 0.02, 's', 0.3);

  /* ----- north wall: the gold swan ----- */
  const lock = ctx.logo('mark', { normal: true });
  if (lock) {
    const tx = (c, o) => T.tex(c, o || { color: false }), lh = 1.45;
    K.plane(lh * lock.aspect, lh, K.std('--color-gold-metal', { r: 0.35, m: 0.85, alphaMap: tx(lock.alpha), normalMap: lock.normal ? tx(lock.normal) : null, transparent: true, depthWrite: false, emissive: K.col('--color-gold-metal'), emissiveIntensity: 0.2, envMapIntensity: 1.8 }), 0, 1.5, Z0 + 0.015, 's');
  }

  /* ----- west wall: the chimney breast (stone, z -1.25..1.25), flush linear fireplace, TV above ----- */
  K.box(0.05, H, 2.5, stone, X0 + 0.025, H / 2, 0, { tile: 2.4 });
  const FX = X0 + 0.052;
  K.plane(1.56, 0.4, dark, FX, 0.55, 0, 'e');                                                  // the black opening, flush
  [[1.6, 0.025, 0.55 + 0.2], [1.6, 0.025, 0.55 - 0.2]].forEach(([w, h, y]) => K.box(0.01, h, w, bronze, FX, y, 0));
  [-0.8, 0.8].forEach((z) => K.box(0.01, 0.4, 0.025, bronze, FX, 0.55, z));
  K.box(0.012, 0.03, 1.5, ember, FX + 0.004, 0.37, 0);                                          // the ember bed
  {
    const c = document.createElement('canvas'); c.width = 256; c.height = 128; const g = c.getContext('2d'), r = T.rng(5);
    for (let i = 0; i < 18; i++) {
      const x = r() * 256, h = 45 + r() * 70, w = 10 + r() * 14;
      [-256, 0, 256].forEach((dx) => {
        const gr = g.createLinearGradient(0, 128, 0, 128 - h);
        gr.addColorStop(0, T.rgba('--color-light-warm', 0.95)); gr.addColorStop(0.3, T.rgba('--color-led-warm', 0.8)); gr.addColorStop(0.7, T.rgba('--color-heater-glow', 0.4)); gr.addColorStop(1, T.rgba('--color-heater-glow', 0));
        g.fillStyle = gr; g.beginPath(); g.moveTo(x + dx - w, 128); g.quadraticCurveTo(x + dx - w * 0.3, 128 - h * 0.5, x + dx + (r() - 0.5) * w, 128 - h); g.quadraticCurveTo(x + dx + w * 0.3, 128 - h * 0.5, x + dx + w, 128); g.fill();
      });
    }
    const mk = (rep) => { const t = T.tex(c, { wrap: true }); t.repeat.set(rep, 1); return new THREE.MeshBasicMaterial({ map: t, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.8 }); };
    var flames = [mk(1), mk(1.7)].map((m, i) => {
      const geo = new THREE.PlaneGeometry(1.5, 0.3 - i * 0.07); geo.translate(0, (0.3 - i * 0.07) / 2, 0);
      const f = new THREE.Mesh(geo, m); f.position.set(FX + 0.006 + i * 0.002, 0.38, 0); f.rotation.y = PI / 2; f.renderOrder = 3; scene.add(f); return f;
    });
  }
  const glow = K.glowPlane(2.2, 1.6, X0 + 0.9, 0.01, 0, 'up', 0.3, '--color-heater-glow');      // the glow on the floor in front
  K.glowPlane(1.9, 1.0, FX + 0.01, 0.6, 0, 'e', 0.3, '--color-heater-glow');
  {                                                                                             // the TV, 75 inch, dark screen with a faint warm sheen, facing the chairs
    const c = document.createElement('canvas'); c.width = 256; c.height = 144; const g = c.getContext('2d');
    g.fillStyle = T.mix('--color-iron', '--color-espresso', 0.5); g.fillRect(0, 0, 256, 144);
    const sh = g.createLinearGradient(0, 0, 256, 144); sh.addColorStop(0, T.rgba('--color-light-warm', 0)); sh.addColorStop(0.3, T.rgba('--color-light-warm', 0.14)); sh.addColorStop(1, T.rgba('--color-light-warm', 0));
    g.fillStyle = sh; g.fillRect(0, 0, 256, 144);
    K.box(0.04, 0.95, 1.65, dark, X0 + 0.07, 1.9, 0);
    K.plane(1.6, 0.9, K.basic(new THREE.Color(1, 1, 1), { map: T.tex(c) }), X0 + 0.092, 1.9, 0, 'e');
  }

  /* ----- the massage chairs: local x runs from the leg rest (-) to the back (+); one geometry per part, three instances each ----- */
  const CX = 1.0, CZ = [-0.9, 0.45, 1.8];
  const side = new THREE.Shape([[-0.74, 0.14], [-0.74, 0.34], [-0.3, 0.5], [0.05, 0.5], [0.45, 1.2], [0.62, 1.16], [0.76, 0.22], [0.6, 0.12]].map((p) => new THREE.Vector2(p[0], p[1])));
  const sideG = new THREE.ExtrudeGeometry(side, { depth: 0.07, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.012, bevelSegments: 1 }).translate(0, 0, -0.035);
  K.inst(sideG, walnut, 6, (i, o) => o.position.set(CX, 0, CZ[i >> 1] + (i & 1 ? 0.37 : -0.37)));
  const parts = [
    [K.rbox(0.5, 0.16, 0.44, 0.05, 0.03).translate(-0.12, 0.58, 0)],                                                          // seat
    [K.rbox(0.44, 0.74, 0.14, 0.05, 0.03).rotateY(PI / 2).rotateZ(-0.52).translate(0.19, 0.89, 0)],                           // back
    [K.rbox(0.6, 0.14, 0.44, 0.05, 0.03).rotateZ(0.35).translate(-0.52, 0.5, 0)],                                             // leg rest
    [K.rbox(0.22, 0.2, 0.3, 0.05, 0.03).rotateY(PI / 2).rotateZ(-0.52).translate(0.34, 1.22, 0)],                             // headrest
  ];
  parts.forEach(([g]) => K.inst(g, leather, 3, (i, o) => o.position.set(CX, 0, CZ[i])));
  K.inst(K.rbox(0.55, 0.09, 0.1, 0.03, 0.02).translate(-0.05, 0.68, 0), leather, 6, (i, o) => o.position.set(CX, 0, CZ[i >> 1] + (i & 1 ? 0.28 : -0.28)));   // arms
  K.inst(new THREE.BoxGeometry(1.5, 0.1, 0.62).translate(0.05, 0.07, 0), dark, 3, (i, o) => o.position.set(CX, 0, CZ[i]));
  CZ.forEach((z) => K.shadow(1.9, 0.95, CX, z, 0.4));
  K.flush();

  /* ----- light (2700K): low and warm; the fire is the moving one ----- */
  K.hemi('--color-led', '--color-caramel', 0.4);
  K.light('--color-light-warm', 2.2, 4.5, 0, 2.3, -2.5);
  K.light('--color-light-warm', 1.4, 4.5, 0.1, 2.4, 1.2);
  const fl = K.light('--color-heater-glow', 1.4, 3.4, X0 + 0.7, 0.7, 0), fl0 = fl ? fl.intensity : 0;

  function update(dt, t) {                                                                      // three sines out of step: a slow, uneven flicker, never a blink
    const f = 0.88 + 0.07 * Math.sin(t * 4.1) + 0.04 * Math.sin(t * 9.3 + 1) + 0.03 * Math.sin(t * 17.7 + 2);
    flames[0].material.map.offset.x = t * 0.035; flames[1].material.map.offset.x = -t * 0.05 + 0.3;
    flames[0].material.opacity = 0.85 * f; flames[1].material.opacity = 0.6 * f;
    flames[0].scale.y = 0.9 + 0.2 * Math.sin(t * 2.3) * Math.sin(t * 1.1 + 1); flames[1].scale.y = 0.9 + 0.2 * Math.sin(t * 3.1 + 2);
    glow.material.opacity = 0.3 * f; ember.color.setRGB(1, 1, 1).multiplyScalar(0.8 + (f - 0.88) * 2); ember.color.lerp(K.col('--color-heater-glow'), 0.5);
    if (fl) fl.intensity = fl0 * (0.85 + (f - 0.88) * 1.6);
  }
  update(0, 1);

  return {
    view: { pos: [0.1, 1.6, 2.6], yaw: -10, pitch: -6 },
    exposure: 0.9, ambient: true, update,
    markers: [{ to: 'kitchenette', at: [-0.5, 1.1, 3.15] }, { to: 'dry-sauna', at: [-1.75, 1.1, -2.1] }, { to: 'wet-sauna', at: [1.75, 1.1, -2.4] }],
  };
}
