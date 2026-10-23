/* Lounge (docs/design/VIRTUAL-TOUR.md 2.1, with the 2026-10-23 layout corrections). Room module: no module statements, everything arrives in ctx (contract at the top of ../engine.js).
 * Shell 10.6 x 6.0 x 3.0 (x -7..3.6, z -3..3). North: the reef tank flush in a travertine slab, its long bench and the curved sofa, armchairs and table to the
 * RIGHT (east) of it, a frosted window and fluted panelling beyond, then a passage to the relaxing zone (east wall, z 2.0). To the LEFT (west): the reception
 * desk, curved cream stone that grows out of the west wall and runs straight down to the south wall (it sits in the south-west corner, the corner opposite the tank),
 * its front carrying the backlit gold stacked lockup, under a gold ceiling cove. In the SAME west wall, immediately north of the desk (between it and the tank-wall
 * corner), a long straight corridor (6 m, z -2.7..-1.1, running west parallel to the tank wall; warm cove, travertine, bench, doors) leads to the rooms; the gym marker
 * sits inside it. The north (tank) and south walls have no passage. */
const VS_REEF = 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';
const FS_REEF = `uniform sampler2D map; uniform sampler2D caus; uniform float uTime; uniform float uAmt; uniform float uGain; varying vec2 vUv;
void main(){
  vec3 base = texture2D(map, vUv).rgb * uGain;
  float c1 = texture2D(caus, vUv * vec2(3.0, 1.5) + vec2(uTime * 0.020, uTime * 0.011)).g;
  float c2 = texture2D(caus, vUv * vec2(2.4, 1.2) + vec2(-uTime * 0.014, uTime * 0.009)).g;
  float c = c1 * c2 * (0.35 + 0.65 * vUv.y);
  gl_FragColor = vec4(base + c * uAmt * vec3(0.7, 0.95, 1.0), 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;
const VS_FISH = `attribute vec4 aInfo; uniform float uTime; varying vec2 vUv; varying float vDim;
void main(){
  float f = floor(mod(uTime * 2.5 + aInfo.z, 2.0));
  vUv = vec2((aInfo.x + f + uv.x) / 4.0, ((3.0 - aInfo.y) + uv.y) / 4.0); vDim = aInfo.w;
  gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
}`;
const FS_FISH = `uniform sampler2D atlas; varying vec2 vUv; varying float vDim;
void main(){
  vec4 c = texture2D(atlas, vUv); if (c.a < 0.4) discard;
  gl_FragColor = vec4(c.rgb * vDim, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export async function build(scene, ctx) {
  const { THREE, K, T, S, tier } = ctx, PI = Math.PI, WHITE = new THREE.Color(1, 1, 1), r = T.rng(11);
  const wrap = { wrap: true };

  /* ----- maps (8, generated in idle slots) ----- */
  const wallMap = T.tex(T.travertine(S, { seed: 3, ao: 3 }), wrap); await ctx.idle();
  const floorMap = T.tex(T.oak(S, { seed: 9, tone: '--color-caramel', planks: 5, lift: 0.5 }), wrap); await ctx.idle();
  const mossMap = T.tex(T.moss(S >> 1), wrap);
  const reefMap = T.tex(T.reef(...ctx.reefSize)); await ctx.idle();
  const causMap = T.tex(T.caustics(128), { color: false, wrap: true });
  const fishMap = T.tex(T.fish());
  const lock = ctx.logo('stacked', { normal: false });                       // the real stacked lockup, from the page's own SVG
  scene.environment = ctx.env('--color-travertine');

  /* ----- materials ----- */
  const GREY = K.tint(WHITE, 0.74);                                          // pale surfaces sit under the light instead of clipping (kit.js defaults)
  const wall = K.std(GREY, { r: 0.6, map: wallMap }), floor = K.std(K.tint(WHITE, 0.68), { r: 0.42, map: floorMap }), ceil = K.std(K.tint('--color-cream', 0.7), { r: 1 });
  const sofa = K.std(K.tint('--color-cream-raised', 0.72), { r: 0.95 }), stone = K.std(K.tint('--color-cream-raised', 0.8), { r: 0.35 }), sage = K.std('--color-sage', { r: 0.95 }), oak = K.std('--color-caramel', { r: 0.6 });
  const walnut = K.std('--color-walnut', { r: 0.6 }), moss = K.std(WHITE, { r: 1, map: mossMap }), rug = K.std(K.tint('--color-cream', 0.7), { r: 1 });
  const gold = K.std('--color-gold-metal', { r: 0.28, m: 0.95, side: THREE.DoubleSide, envMapIntensity: 2.4 });
  const led = K.hot('--color-led-warm', 1.7), ledD = K.hot('--color-led-warm', 2.2, { side: THREE.DoubleSide });   // hot cores: clip to near white, warm edge
  const frost = K.basic(K.col('--color-cream').clone().lerp(K.col('--color-led-warm'), 0.3));
  const X0 = -7, XW = 10.6, XC = -1.7;                                     // west wall, shell width, shell centre

  /* ----- shell ----- */
  K.plane(XW, 6, floor, XC, 0, 0, 'up', { tile: 2.4 });
  K.plane(3.6, 3, wall, -5.2, 1.5, -3, 's', { tile: 3 });                                                                  // north, left of the tank slab: plain (no passage in the tank wall)
  K.plane(2.2, 3, wall, 2.5, 1.5, -3, 's', { tile: 3 });                                                                   // north, right of the tank slab
  K.plane(XW, 3, wall, XC, 1.5, 3, 'n', { tile: 3 });                                                                      // south: plain
  K.plane(4.5, 3, wall, 3.6, 1.5, -0.75, 'w', { tile: 3 }); K.plane(0.5, 3, wall, 3.6, 1.5, 2.75, 'w', { tile: 3 }); K.plane(1.0, 0.8, wall, 3.6, 2.6, 2.0, 'w', { tile: 3 });   // east, with the relaxing-zone passage at z 2.0
  K.plane(0.3, 3, wall, X0, 1.5, -2.85, 'e', { tile: 3 }); K.plane(4.1, 3, wall, X0, 1.5, 0.95, 'e', { tile: 3 }); K.plane(1.6, 0.6, wall, X0, 2.7, -1.9, 'e', { tile: 3 });   // west: the desk's wall, with the corridor opening at z -2.7..-1.1 (north of the desk, towards the tank wall), 2.4 high

  /* ceiling: dropped to 2.75 with a round recess (the gold cove) over reception, clipped by the walls, its roof gold leaf at 3.0 */
  const C = [-5.0, 1.0], R = 2.6, arc = [];
  for (let i = 0; i < 56; i++) { const a = i / 56 * PI * 2; arc.push([Math.min(3.58, Math.max(-6.98, C[0] + R * Math.cos(a))), Math.min(2.98, Math.max(-2.98, C[1] + R * Math.sin(a)))]); }
  const v2 = (pts) => pts.map((p) => new THREE.Vector2(p[0], p[1]));
  const outer = new THREE.Shape(v2([[X0, -3], [3.6, -3], [3.6, 3], [X0, 3]]));
  outer.holes.push(new THREE.Path(v2(arc)));
  const ceilG = new THREE.ShapeGeometry(outer); ceilG.rotateX(PI / 2);
  K.put(ceilG, ceil, { y: 2.75 });
  const roofG = new THREE.ShapeGeometry(new THREE.Shape(v2(arc))); roofG.rotateX(PI / 2);
  K.put(roofG, gold, { y: 3.0 });
  const lip = (pts, y0, y1) => {                                              // a vertical band round the recess, facing in
    const pos = [];
    pts.forEach((a, i) => { const b = pts[(i + 1) % pts.length]; pos.push(a[0], y0, a[1], b[0], y0, b[1], b[0], y1, b[1], a[0], y0, a[1], b[0], y1, b[1], a[0], y1, a[1]); });
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals(); return g;
  };
  K.put(lip(arc, 2.75, 3.0), gold);
  K.put(lip(arc.map((p) => [C[0] + (p[0] - C[0]) * 0.99, C[1] + (p[1] - C[1]) * 0.99]), 2.76, 2.8), ledD);   // the LED line along the lip
  [[-0.4, -0.9], [-0.3, 1.6], [1.4, 2.2], [3.0, 0.5], [-1.5, 2.2], [2.8, -2.0], [-2.6, 2.3]].forEach(([x, z]) => K.put(new THREE.CircleGeometry(0.05, 12), led, { x, y: 2.745, z, rx: PI / 2 }));

  /* ----- the tank wall: a slab flush with the glass, 3.4 x 1.5 opening, bottom at 0.55 ----- */
  K.box(0.7, 3, 0.25, wall, -3.05, 1.5, -2.875, { tile: 3 }); K.box(0.7, 3, 0.25, wall, 1.05, 1.5, -2.875, { tile: 3 });
  K.box(3.4, 0.55, 0.25, wall, -1.0, 0.275, -2.875, { tile: 3 }); K.box(3.4, 0.95, 0.25, wall, -1.0, 2.525, -2.875, { tile: 3 });
  const water = K.basic(new THREE.Color(T.REEF.mid));
  K.plane(0.62, 1.5, water, -2.7, 1.3, -3.06, 'e'); K.plane(0.62, 1.5, water, 0.7, 1.3, -3.06, 'w'); K.plane(3.4, 0.62, water, -1.0, 2.05, -3.06, 'down');

  const reefMat = (map, amt, extra) => new THREE.ShaderMaterial({ uniforms: { map: { value: map }, caus: { value: causMap }, uTime: { value: 0 }, uAmt: { value: amt }, uGain: { value: 1.3 } }, vertexShader: VS_REEF, fragmentShader: FS_REEF, ...extra });
  const back = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.5), reefMat(reefMap, 0.5)); back.position.set(-1.0, 1.3, -3.37); scene.add(back);
  const sandG = new THREE.PlaneGeometry(3.4, 0.62); sandG.rotateX(-PI / 2); const suv = sandG.attributes.uv; for (let i = 0; i < suv.count; i++) suv.setY(i, suv.getY(i) * 0.1);
  const sand = new THREE.Mesh(sandG, reefMat(reefMap, 0.5)); sand.position.set(-1.0, 0.55, -3.06); scene.add(sand);
  const glassM = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.5), K.std('--color-cream', { r: 0.05, transparent: true, opacity: 0.12, depthWrite: false }));
  glassM.position.set(-1.0, 1.3, -2.77); scene.add(glassM);
  const rays = [[-2.3, 0.28, 0.2], [-1.7, 0.2, 0.14], [-0.9, -0.2, 0.16], [-0.2, 0.3, 0.18], [0.3, -0.15, 0.12]].map(([x, rz, a]) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 1.6), new THREE.MeshBasicMaterial({ color: new THREE.Color('#9FD8FF'), map: T.shared('ray'), transparent: true, opacity: a, blending: THREE.AdditiveBlending, depthWrite: false }));
    m.position.set(x, 1.3, -3.2); m.rotation.z = rz; m.userData.x = x; return scene.add(m) && m;
  });

  /* fish: one InstancedMesh, 24 high / 12 mobile / 6 low (low can come later), lanes inside the opening */
  const N = tier === 'high' ? 24 : tier === 'mobile' ? 12 : 6, fishes = [], info = new Float32Array(N * 4), dummy = new THREE.Object3D();
  for (let i = 0; i < N; i++) {
    const sp = i % 6, depth = 0.1 + r() * 0.4;
    fishes.push({ x: -2.5 + r() * 3.0, y: 0.7 + r() * 1.2, z: -2.77 - depth, v: 0.08 + r() * 0.2, dir: r() > 0.5 ? 1 : -1, len: 0.11 + r() * 0.16, bob: 0.02 + r() * 0.02, per: 4 + r() * 3, ph: r() * 6.3, turn: 0, from: 1, sx: 1 });
    info.set([(sp & 1) * 2, sp >> 1, r() * 2, 1 - 0.3 * (depth / 0.5)], i * 4);
  }
  const fishG = new THREE.PlaneGeometry(1, 0.5); fishG.setAttribute('aInfo', new THREE.InstancedBufferAttribute(info, 4));
  const fishMat = new THREE.ShaderMaterial({ uniforms: { atlas: { value: fishMap }, uTime: { value: 0 } }, vertexShader: VS_FISH, fragmentShader: FS_FISH, side: THREE.DoubleSide });
  const school = new THREE.InstancedMesh(fishG, fishMat, N); school.frustumCulled = false; scene.add(school);
  await ctx.idle();

  /* ----- bench, cushion, pillows, then (east, to the right of the tank) the curved sofa, armchairs, table, rug ----- */
  K.box(3.6, 0.42, 0.7, wall, -1.0, 0.21, -2.4, { tile: 3 });
  K.led(3.6, 0.02, 0.02, -1.0, 0.03, -2.04, { w: 3.6, h: 0.55, x: -1.0, y: 0.006, z: -1.8, face: 'up', a: 0.5 }, led);
  K.put(K.rbox(3.5, 0.62, 0.10, 0.08, 0.03), sofa, { x: -1.0, y: 0.47, z: -2.4, rx: -PI / 2 });
  for (let i = 0; i < 6; i++) K.put(K.rbox(0.5, 0.4, 0.14, 0.08, 0.05), sage, { x: -2.5 + i * 0.55 + (r() - 0.5) * 0.04, y: 0.71, z: -2.58, rx: -15 * PI / 180, rz: (r() - 0.5) * 0.08 });
  K.put(K.sector(1.65, 2.35, -90, -20, 0.42, 0.8, -0.4, 0, 0), sofa);
  K.put(K.sector(1.7, 2.3, -90, -21, 0.12, 0.8, -0.4, 0.42, 0.03), sofa);
  K.put(K.sector(2.08, 2.35, -90, -20, 0.75, 0.8, -0.4, 0.42, 0.03), sofa);
  const chair = (x, z) => {                                                  // an armchair turned toward the table
    const th = Math.atan2(1.35 - x, -0.35 - z);
    K.put(K.rbox(0.8, 0.42, 0.8, 0.12, 0.04).translate(0, 0.21, 0), sofa, { x, z, ry: th });
    K.put(K.rbox(0.8, 0.5, 0.16, 0.1, 0.04).translate(0, 0.65, -0.34), sofa, { x, z, ry: th });
    K.shadow(1.1, 1.1, x, z, 0.4);
  };
  chair(2.7, 0.8); chair(0.0, 0.7);
  K.shadow(1.7, 1.2, 1.2, -2.35, 0.4); K.shadow(1.7, 1.2, 2.0, -2.0, 0.4); K.shadow(1.5, 1.4, 2.55, -1.4, 0.38); K.shadow(1.1, 1.1, 1.35, -0.35, 0.5);
  K.put(new THREE.CircleGeometry(1.1, 40), rug, { x: 1.35, y: 0.006, z: -0.35, rx: -PI / 2 });
  K.put(new THREE.CylinderGeometry(0.45, 0.45, 0.04, 28), wall, { x: 1.35, y: 0.40, z: -0.35, tile: 1.2 });
  K.put(new THREE.CylinderGeometry(0.3, 0.3, 0.38, 20), oak, { x: 1.35, y: 0.19, z: -0.35 });
  K.box(0.55, 2.6, 0.06, moss, 1.7, 1.3, -2.97, { tile: 1.2 });
  K.put(new THREE.TorusGeometry(0.35, 0.015, 6, 36), led, { x: 1.4, y: 2.2, z: -0.3, rx: PI / 2 });
  K.glowPlane(1.2, 1.2, 1.4, 2.2, -0.3, 'down', 0.3);

  /* east wall: fluted panelling (real flutes, merged), sconce, frosted window in a walnut frame (a window, no door) */
  for (let i = 0; i < 24; i++) { const z = 0.38 + i * 0.11; if (z < 1.45 || z > 2.55) K.box(0.04, 1.0, 0.07, oak, 3.57, 0.5, z); }   // flutes stop short of the passage
  K.put(new THREE.CylinderGeometry(0.03, 0.03, 0.3, 12), led, { x: 3.55, y: 1.7, z: 1.2 }); K.glowPlane(0.7, 1.0, 3.585, 1.7, 1.2, 'w', 0.35);
  K.plane(2.6, 1.7, frost, 3.59, 1.3, -1.2, 'w');
  K.glowPlane(3.6, 2.6, 3.5, 1.3, -1.2, 'w', 0.2, '--color-cream');
  [-2.5, -1.2, 0.1].forEach((z) => K.box(0.06, 1.8, 0.05, walnut, 3.57, 1.3, z));
  K.box(0.06, 0.05, 2.65, walnut, 3.57, 2.17, -1.2); K.box(0.06, 0.05, 2.65, walnut, 3.57, 0.43, -1.2);

  /* ----- reception (west, in the south-west corner): a quarter-round end curving out of the west wall, then a straight run to the south wall; the backlit gold lockup on its front ----- */
  const DC = [-7, 1.0], DR0 = 1.0, DR1 = 1.6, front = DC[0] + DR1, DL = 3 - DC[1], DZ = DC[1] + DL / 2;   // straight run z 1.0..3
  K.put(K.sector(DR0, DR1, -90, 0, 1.0, DC[0], DC[1], 0, 0.02), stone); K.box(DR1 - DR0, 1.0, DL, stone, front - (DR1 - DR0) / 2, 0.5, DZ);
  K.put(K.sector(DR0 - 0.05, DR1 + 0.05, -90, 0, 0.05, DC[0], DC[1], 1.0, 0.01), stone); K.box(DR1 - DR0 + 0.1, 0.05, DL, stone, front - (DR1 - DR0) / 2, 1.025, DZ);
  K.put(K.sector(DR1, DR1 + 0.02, -90, 0, 0.02, DC[0], DC[1], 0.04), led); K.box(0.02, 0.02, DL, led, front + 0.01, 0.05, DZ);   // the LED line under the desk's lip
  K.glowPlane(0.9, DL + 0.6, front + 0.3, 0.006, DZ, 'up', 0.4);
  K.shadow(1.6, DL + 0.8, front + 0.1, DZ, 0.35);
  if (lock) {                                                                  // the backlit lockup: a dark bronze inset on the straight front, the gold glowing on it
    const lh = 0.8, lw = lh * lock.aspect, tx = (c) => T.tex(c, { color: false }), at = { x: front + 0.04, y: 0.58, z: DZ, ry: PI / 2 };
    K.put(new THREE.PlaneGeometry(lw + 0.5, lh + 0.4), K.std('--color-iron', { r: 0.6, side: THREE.DoubleSide }), at);
    const mark = K.basic(K.col('--color-gold-metal').clone().multiplyScalar(2.2), { alphaMap: tx(lock.alpha), transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const m = new THREE.Mesh(new THREE.PlaneGeometry(lw, lh), mark); m.position.set(at.x + 0.012, at.y, at.z); m.rotation.y = at.ry; m.renderOrder = 3; scene.add(m);
    K.glowPlane(lw * 1.9, lh * 1.8, at.x + 0.03, 0.58, DZ, 'e', 0.7, '--color-led-warm');   // the halo round it
  }

  /* ----- the corridor (west wall, immediately north of the desk, between it and the tank-wall corner): runs away from the lounge along x, parallel to the tank wall.
   * 1.6 wide (z -2.7..-1.1), 2.4 high, 6 m long (x -7..-13). Travertine, gold-leaf ceiling with warm cove lines, bench, doors, lit door at the end ----- */
  const CZ = -1.9, CW = 1.6, CH = 2.4, CX0 = X0, CL = 6, CXm = CX0 - CL / 2, zn = CZ - CW / 2, zs = CZ + CW / 2;
  K.plane(CL, CW, wall, CXm, 0, CZ, 'up', { tile: 3 });                                                      // travertine floor
  K.plane(CL, CH, wall, CXm, CH / 2, zn, 's', { tile: 3 }); K.plane(CL, CH, wall, CXm, CH / 2, zs, 'n', { tile: 3 });
  K.plane(CW, CH, wall, CX0 - CL, CH / 2, CZ, 'e', { tile: 3 });
  K.plane(CL, CW, gold, CXm, CH, CZ, 'down');                                                                 // gold-leaf ceiling
  K.led(CL, 0.03, 0.05, CXm, CH - 0.03, zn + 0.04, null, ledD); K.led(CL, 0.03, 0.05, CXm, CH - 0.03, zs - 0.04, null, ledD);   // cove lines along both sides
  K.glowPlane(CL, CW, CXm, CH - 0.01, CZ, 'down', 0.4);
  K.led(CL, 0.02, 0.02, CXm, 0.03, zn + 0.01, { w: CL, h: 0.5, x: CXm, y: 0.006, z: zn + 0.25, face: 'up', a: 0.35 }, led);   // floor-level LED lines
  K.led(CL, 0.02, 0.02, CXm, 0.03, zs - 0.01, { w: CL, h: 0.5, x: CXm, y: 0.006, z: zs - 0.25, face: 'up', a: 0.35 }, led);
  K.edge(CX0, zn, -1, 0, CL, 0, 1, 0.4, 0.45); K.edge(CX0, zs, -1, 0, CL, 0, -1, 0.4, 0.45);
  [-0.07, 0, 0.07].forEach((d) => { K.box(0.045, 2.75, 0.025, gold, X0 + 0.04, 1.375, zn - 0.14 + d); K.box(0.045, 2.75, 0.025, gold, X0 + 0.04, 1.375, zs + 0.14 + d); });   // gold vertical fins at the mouth
  K.box(1.6, 0.42, 0.4, stone, X0 - 4.3, 0.21, zn + 0.2); K.put(K.rbox(1.5, 0.38, 0.1, 0.06, 0.03), sofa, { x: X0 - 4.3, y: 0.46, z: zn + 0.2, rx: -PI / 2 });   // the bench and its cushion
  K.put(new THREE.SphereGeometry(0.15, 16, 12), stone, { x: X0 - 3.6, y: 0.15, z: zn + 0.2 }); K.shadow(2.2, 0.9, X0 - 4.3, zn + 0.3, 0.45);
  [[zn + 0.02, 's', 2.0, walnut], [zn + 0.02, 's', 6.0, oak], [zs - 0.02, 'n', 4.6, walnut]].forEach(([z, f, d, m]) => {                  // doors: panel, frame, a gold pull
    const sg = f === 's' ? 1 : -1, x = X0 - d;
    K.plane(0.9, 2.1, m, x, 1.05, z, f); K.box(0.06, 2.16, 0.03, oak, x - 0.48, 1.08, z + 0.005 * sg); K.box(0.06, 2.16, 0.03, oak, x + 0.48, 1.08, z + 0.005 * sg); K.box(1.02, 0.06, 0.03, oak, x, 2.14, z + 0.005 * sg);
    K.box(0.03, 0.22, 0.03, gold, x + 0.34, 1.0, z + 0.03 * sg);
  });
  K.plane(0.9, 2.2, K.basic(K.col('--color-caramel').clone().multiplyScalar(1.15)), CX0 - CL + 0.02, 1.1, CZ, 'e');   // the lit door at the far end
  K.glowPlane(1.6, 2.4, CX0 - CL + 0.05, 1.2, CZ, 'e', 0.3, '--color-led-warm');

  /* doorway seen through: relaxing zone (travertine, east wall past the seating) */
  K.vista('--color-travertine', [3.6, 2.0], 'e', 1.0, 2.2, 1.0);           // relaxing zone, past the seating
  /* grounding: the dark line where floor meets wall, and under the bench */
  K.edge(X0, -3, 1, 0, XW, 0, 1, 0.55, 0.55); K.edge(X0, 3, 1, 0, XW, 0, -1, 0.55, 0.5); K.edge(3.6, -3, 0, 1, 6, -1, 0, 0.55, 0.5); K.edge(X0, -3, 0, 1, 0.3, 1, 0, 0.55, 0.5); K.edge(X0, -1.1, 0, 1, 4.1, 1, 0, 0.55, 0.5);
  K.shadow(4.0, 1.1, -1.0, -2.2, 0.55); K.shadow(2.2, 2.2, 1.9, -1.3, 0.35);
  [[1.4, 2.2], [-0.4, -0.9], [-1.5, 2.2]].forEach(([x, z]) => K.glowPlane(2.2, 2.2, x, 0.008, z, 'up', 0.16));   // downlight pools on the floor
  K.flush();

  /* ----- light (2700K) ----- */
  K.baseLight();                                                             // low, dark-footed ambient: the practicals do the lighting
  K.light('--color-light-warm', 3.4, 6, -5.0, 2.55, 1.0);                   // the cove over reception: pools on desk and floor
  K.light(new THREE.Color(T.REEF.top), 3.2, 4.5, -1.0, 1.4, -2.2);          // the tank's spill: blue on the bench, pillows and floor in front
  K.glowPlane(4.2, 2.6, -1.0, 0.007, -1.5, 'up', 0.22, new THREE.Color(T.REEF.mid));
  K.light('--color-light-warm', 2.4, 5, -10.0, 2.1, CZ);                       // the corridor's cove: warms the travertine, bench and doors (the lockup is self-lit, no separate backlight light: 4-light cap)
  K.light('--color-light-warm', 1.6, 3, 3.4, 1.7, 1.2, true);                // east sconce, dropped on the mobile tier (the self-lit sconce stays)

  /* ----- life: fish and caustics, 30 fps at rest ----- */
  let frozen = tier === 'low';
  function update(dt, t) {
    const time = frozen ? 0 : t;
    back.material.uniforms.uTime.value = sand.material.uniforms.uTime.value = time; fishMat.uniforms.uTime.value = t;
    for (let i = 0; i < school.count; i++) {
      const f = fishes[i];
      if (f.turn > 0) { f.turn -= dt; f.sx = f.from * (1 - 2 * (1 - Math.max(0, f.turn) / 0.6)); }
      else { f.x += f.dir * f.v * dt; f.sx = f.dir; if ((f.dir > 0 && f.x > 0.55) || (f.dir < 0 && f.x < -2.55)) { f.turn = 0.6; f.from = f.dir; f.dir = -f.dir; } }
      dummy.position.set(f.x, f.y + f.bob * Math.sin(t * 6.283 / f.per + f.ph), f.z); dummy.scale.set(f.len * f.sx, f.len * 0.5, 1); dummy.updateMatrix(); school.setMatrixAt(i, dummy.matrix);
    }
    school.instanceMatrix.needsUpdate = true;
    rays.forEach((m, i) => { m.position.x = m.userData.x + 0.04 * Math.sin(t * 6.283 / 24 + i * 2); });
  }
  update(0, 0);

  return {
    view: { pos: [2.9, 1.6, -0.8], yaw: -97, pitch: -5 },     // looks across the room to the desk in the corner and the corridor beside it
    arrive: { pos: [3.3, 1.6, -0.5], yaw: -93, pitch: -8, ms: 1400 },
    exposure: 0.8, ambient: true, update,
    markers: [{ to: 'gym', at: [X0 - 3.0, 1.1, CZ] }, { to: 'relaxing-zone', at: [3.55, 1.1, 2.0] }],
    tier(name) { if (name === 'low') { frozen = true; school.count = Math.min(school.count, 6); } },
  };
}
