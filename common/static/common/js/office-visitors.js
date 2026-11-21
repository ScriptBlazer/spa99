/* Analytics > Visitors (docs/features/analytics-design.md). Four small, separate jobs; the page itself is server-rendered.
 *   Live         "On the site now": polls /analytics/live.json every 15 s while the tab is visible (Page Visibility), backs off 15, 30, 60 s on
 *                trouble, then waits for "Try again". The count cross-fades; nothing counts up, pulses or flashes. No aria-live (it would speak every 15 s).
 *   Pages        the Most viewed / First page / Last page switch and "Show all" (all three tables are in the page).
 *   Heat map     the grid fades in once when 15% of it is visible; a tooltip on hover (mouse) or tap.
 *   Link maker   the address comes from the server (campaigns.build_link, the one place the cleaning rules live); Copy, and a QR code for flyers.
 * A range change (office-swap.js) replaces the [data-region] parts and fires 'office:series': what lives inside them is set up again here. */

const nf = new Intl.NumberFormat('en-GB');
const POLL_MS = 15000;
const BACKOFF_MS = [15000, 30000, 60000];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const pad = (n) => String(n).padStart(2, '0');
const fadeIn = (el) => { el.classList.remove('o-fade-in'); void el.offsetWidth; el.classList.add('o-fade-in'); };   // restarts the 240ms cross-fade

// ---------- Live ----------

function initLive(card) {
  const url = card.dataset.liveUrl;
  const labels = JSON.parse(document.getElementById('live-labels')?.textContent || '{}');
  const regions = typeof Intl.DisplayNames === 'function' ? new Intl.DisplayNames(['en-GB'], { type: 'region' }) : null;
  const countEl = card.querySelector('[data-live-count]');
  const lineEl = card.querySelector('[data-live-line]');
  const noteEl = card.querySelector('[data-live-note]');
  const retry = card.querySelector('[data-live-retry]');
  const NOTE = noteEl.textContent;
  let timer = 0; let fails = 0; let running = false;

  const cap = (text) => text.charAt(0).toUpperCase() + text.slice(1);
  const pretty = (key, raw) => {   // the same wording as the server's first paint (insights/office visitors_page.live_label)
    if (!raw || raw === 'unknown') return 'Unknown';
    if (key === 'by_country') {
      if (raw === 'other') return 'Other';
      try { return regions ? regions.of(raw.toUpperCase()) : raw.toUpperCase(); } catch { return raw.toUpperCase(); }
    }
    if (key === 'by_device' || key === 'by_channel') return labels[key]?.[raw] || cap(raw);
    return raw === 'home' ? 'Home' : cap(raw.replace(/[-_]/g, ' '));
  };

  function render(data) {
    const shown = nf.format(data.count);
    if (countEl.textContent !== shown) { countEl.textContent = shown; fadeIn(countEl); }
    lineEl.textContent = data.count ? 'in the last 5 minutes' : 'No one on the site right now.';
    card.toggleAttribute('data-empty', !data.count);
    card.querySelectorAll('[data-live-list]').forEach((list) => {
      const key = list.dataset.liveList;
      list.replaceChildren(...(data[key] || []).slice(0, 3).map((row) => {
        const item = document.createElement('li'); const name = document.createElement('span'); const num = document.createElement('span');
        const text = pretty(key, row.label);
        name.className = 'o-live-name'; name.textContent = text; name.title = text;
        num.className = 'o-live-num'; num.textContent = nf.format(row.value);
        item.append(name, num);
        return item;
      }));
    });
  }

  function note(state) {
    noteEl.textContent = state === 'ok' ? NOTE : (state === 'stopped' ? 'Live figures paused.' : 'Live figures paused. Trying again.');
    retry.hidden = state !== 'stopped';
  }

  async function poll() {
    clearTimeout(timer);
    if (document.hidden || running) return;
    running = true;
    try {
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) throw new Error(`GET ${url} ${response.status}`);
      render(await response.json());
      fails = 0; note('ok');
      timer = setTimeout(poll, POLL_MS);
    } catch {
      fails += 1;   // the figures stay as they were
      if (fails > BACKOFF_MS.length) note('stopped');
      else { note('trying'); timer = setTimeout(poll, BACKOFF_MS[fails - 1]); }
    } finally {
      running = false;
    }
  }

  retry.addEventListener('click', () => { fails = 0; note('trying'); poll(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearTimeout(timer);
    else if (fails <= BACKOFF_MS.length) poll();   // back on the tab: one poll at once, then every 15 s
  });
  timer = setTimeout(poll, POLL_MS);   // the server rendered the first figures
}

// ---------- Pages switch ----------

function initPages(card) {
  const sw = card.querySelector('[data-pages-switch]');
  const views = ['most', 'first', 'last'];
  let view = 'most'; let all = false;
  function apply(animate) {
    card.querySelectorAll('[data-pages-panel]').forEach((panel) => {
      const on = panel.dataset.pagesPanel === view;
      if (on && panel.hidden && animate) fadeIn(panel);
      panel.hidden = !on;
    });
    sw.style.setProperty('--i', String(views.indexOf(view)));
    sw.querySelectorAll('input').forEach((input) => { input.checked = input.value === view; });
    card.querySelectorAll('[data-extra]').forEach((row) => { row.hidden = !all; });
    card.querySelectorAll('[data-pages-all]').forEach((button) => { button.hidden = all; });
  }
  sw.addEventListener('change', (event) => { view = event.target.value; apply(true); });
  card.addEventListener('click', (event) => { if (event.target.closest('[data-pages-all]')) { all = true; apply(false); } });
  document.addEventListener('office:series', () => apply(false));   // a new range brought new tables: show the same view
}

// ---------- View as table: stays open through a range change ----------

function keepTablesOpen() {
  const open = new Map();
  document.addEventListener('toggle', (event) => { const key = event.target.dataset?.table; if (key) open.set(key, event.target.open); }, true);
  document.addEventListener('office:series', () => {
    document.querySelectorAll('details[data-table]').forEach((details) => { if (open.get(details.dataset.table)) details.open = true; });
  });
}

// ---------- Heat map ----------

function initHeat() {
  let revealed = false;
  function fade() {
    const grid = document.querySelector('.o-heat-grid');
    if (!grid) return;
    if (revealed || !('IntersectionObserver' in window)) { grid.classList.add('is-in'); return; }
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      revealed = true; grid.classList.add('is-in'); observer.disconnect();
    }, { threshold: 0.15 });
    observer.observe(grid);
  }
  fade();
  document.addEventListener('office:series', fade);

  let tip = null; let current = null;
  function hide() { tip?.removeAttribute('data-show'); current = null; }
  function show(cell) {
    const box = cell.closest('[data-heat]');
    if (!tip || tip.parentElement !== box) {
      tip = document.createElement('div'); tip.className = 'o-tip'; tip.setAttribute('role', 'presentation'); box.append(tip);
    }
    const d = Number(cell.dataset.d); const h = Number(cell.dataset.h); const v = Number(cell.dataset.v);
    const title = document.createElement('div'); title.className = 'o-tip-title'; title.textContent = `${DAYS[d]} ${pad(h)}:00 to ${pad((h + 1) % 24)}:00`;
    const row = document.createElement('div'); row.className = 'o-tip-row';
    const value = document.createElement('span'); value.textContent = `${nf.format(v)} ${v === 1 ? 'visit' : 'visits'}`;
    row.append(value); tip.replaceChildren(title, row);
    const b = box.getBoundingClientRect(); const c = cell.getBoundingClientRect();
    const w = tip.offsetWidth; const t = tip.offsetHeight;
    const left = Math.max(0, Math.min(c.left - b.left + c.width / 2 - w / 2, b.width - w));
    const above = c.top - b.top - t - 8;
    tip.style.transform = `translate(${left}px, ${above >= 0 ? above : c.bottom - b.top + 8}px)`;
    tip.setAttribute('data-show', '');
    current = cell;
  }
  const cellOf = (event) => event.target.closest?.('.o-heat-cell');
  document.addEventListener('pointerover', (event) => {
    if (event.pointerType !== 'mouse') return;
    const cell = cellOf(event);
    if (cell) show(cell); else if (current) hide();
  });
  document.addEventListener('click', (event) => {   // a tap shows it; a tap anywhere else closes it
    const cell = cellOf(event);
    if (cell && cell !== current) show(cell); else if (current) hide();
  });
  document.addEventListener('office:series', hide);
}

// ---------- Link maker ----------

function initLinkMaker(root) {
  const $ = (name) => root.querySelector(`[data-lm-${name}]`);
  const nameEl = $('name'); const pageEl = $('page'); const saved = $('saved'); const hint = $('hint'); const made = $('made');
  const urlEl = $('url'); const copy = $('copy'); const manual = $('manual'); const status = $('status');
  const qrBox = $('qr'); const qrImg = $('qrimg'); const download = $('download'); const qrError = $('qrerror');
  const COPY_LABEL = copy.textContent;
  let seq = 0; let debounce = 0; let current = ''; let savedName = ''; let qrFor = ''; let blobUrl = ''; let copied = 0;
  const placement = () => root.querySelector('[data-lm-placement]:checked')?.value || '';

  function reset() { clearTimeout(copied); copy.textContent = COPY_LABEL; manual.hidden = true; status.textContent = ''; }

  function showLink(url) {
    current = url;
    made.hidden = !url; hint.hidden = !!url;
    if (!url) { qrFor = ''; return; }
    if (urlEl.textContent !== url) { urlEl.textContent = url; reset(); }
    if (placement() === 'flyer-qr') makeQr(url); else { qrBox.hidden = true; qrFor = ''; }
  }

  async function update() {
    const mine = ++seq;
    const name = nameEl.value.trim();
    if (!name) { saved.textContent = ''; savedName = ''; showLink(''); return; }
    try {
      const query = new URLSearchParams({ placement: placement(), name, page: pageEl.value });
      const response = await fetch(`${root.dataset.linkUrl}?${query}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (mine !== seq) return;
      savedName = data.name; saved.textContent = data.name ? `Saved as ${data.name}` : '';
      hint.textContent = 'Choose a place, a name and a page to make the link.';
      showLink(data.url);
    } catch {
      if (mine !== seq) return;
      hint.textContent = 'Couldn’t make the link. Check your connection and change a choice to try again.';
      showLink('');
    }
  }

  async function makeQr(url) {
    if (url === qrFor) return;
    qrFor = url; qrBox.hidden = false; qrError.hidden = true; qrImg.hidden = true; download.hidden = true;
    try {
      const response = await fetch(`${root.dataset.qrUrl}?${new URLSearchParams({ url })}`, { credentials: 'same-origin' });
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      if (url !== current) return;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      blobUrl = URL.createObjectURL(blob);
      qrImg.src = blobUrl; download.href = blobUrl; download.download = `spa99-${savedName || 'link'}.svg`;
      qrImg.hidden = false; download.hidden = false;
    } catch {
      if (url !== current) return;
      qrFor = ''; qrError.hidden = false;
    }
  }

  root.querySelector('[data-lm-qrretry]').addEventListener('click', () => makeQr(current));
  root.addEventListener('change', (event) => { if (event.target.matches('[data-lm-placement], [data-lm-page]')) update(); });
  nameEl.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(update, 150); });

  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(current);
      copy.textContent = 'Copied'; status.textContent = 'Link copied'; manual.hidden = true;
      clearTimeout(copied); copied = setTimeout(reset, 2000);
    } catch {   // refused (no permission, or not a secure page): select the text so it can be copied by hand
      const range = document.createRange(); range.selectNodeContents(urlEl);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      manual.hidden = false;
    }
  });
}

function init() {
  const live = document.querySelector('[data-live]'); if (live) initLive(live);
  const pages = document.querySelector('[data-pages]'); if (pages) initPages(pages);
  const maker = document.querySelector('[data-linkmaker]'); if (maker) initLinkMaker(maker);
  keepTablesOpen();
  initHeat();
}
init();
