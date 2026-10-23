/* The tour's own gate and loader (docs/design/VIRTUAL-TOUR.md 4.2 and 4.4). Loaded on every /tour/ page, about 1 KB, and the only tour script that is.
 * three.js and the engine are requested only when every check passes: WebGL2 on a real GPU, motion allowed, no Save-Data, data-webgl not off.
 * Otherwise nothing else is requested and the server-rendered photo page stays exactly as it is.
 * The early inline script in tour.html has already set html.tour-gl from the cheap checks (so the photo is not shown for a frame first);
 * this file removes it again if the WebGL probe fails or the engine cannot start. */
const html = document.documentElement;
const root = document.getElementById('tour');

function gate() {
  if (!root || html.dataset.webgl === 'off') return false;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  if (navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches) return false;
  const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
  if (!gl) return false;
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  return true;
}

const json = (id) => { try { return JSON.parse(document.getElementById(id).textContent); } catch { return null; } };

function fail(err) {
  if (err) console.error('virtual tour', err);
  html.classList.remove('tour-gl'); document.body.classList.remove('tour-3d');
}

if (!gate()) fail();
else {
  const go = () => {
    const config = json('tour-config'), modules = json('tour-modules');
    if (!config || !modules || !modules[config.current]) return fail();
    import(root.dataset.engine)
      .then((m) => m.start({ root, config, modules, icons: root.dataset.icons }))
      .catch(fail);
  };
  (window.requestIdleCallback || setTimeout)(go, { timeout: 600 });
}
