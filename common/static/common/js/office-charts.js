/* Office Analytics charts (docs/design/OFFICE.md section 4). Chart.js 4.6.1 (self-hosted UMD) is loaded by the page; this module reads window.Chart.
 * - Data comes from the page's <script id="office-series"> (stored figures). Nothing is calculated here: shares, rates and totals are the server's.
 * - Colours come from CSS tokens (getComputedStyle), never hard-coded.
 * - Each card's chart is created lazily when 15% of it is in view, after the fonts are ready.
 * - A range switch (office-swap.js) replaces the JSON and fires 'office:series': every chart morphs in place with chart.update().
 */
const Chart = window.Chart;
const root = document.querySelector('[data-office-charts]');
if (Chart && root) start();

function start() {
  const nf = new Intl.NumberFormat('en-GB');
  const zone = { timeZone: 'Europe/London' };
  const shortDay = new Intl.DateTimeFormat('en-GB', { ...zone, day: 'numeric', month: 'short' });
  const longDay = new Intl.DateTimeFormat('en-GB', { ...zone, weekday: 'short', day: 'numeric', month: 'short' });
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const coarse = window.matchMedia('(pointer: coarse)');
  const charts = new Map();   // key -> { chart, box, spec }
  const created = new Set();  // cards whose charts exist or are wanted
  const state = { metric: 'visitors' };

  // ---------- tokens ----------
  const probe = document.createElement('canvas').getContext('2d');
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const norm = (value) => { probe.fillStyle = '#000'; probe.fillStyle = value; return probe.fillStyle; }; // hex or rgba(), for any CSS colour syntax
  const alpha = (value, a) => {
    probe.fillStyle = value;
    const m = String(probe.fillStyle);
    if (m.startsWith('#')) { const n = parseInt(m.slice(1), 16); return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`; }
    return m.replace(/[\d.]+\)$/, `${a})`);
  };
  const tokens = () => ({
    gold: norm(cssVar('--color-gold')), caramel: norm(cssVar('--color-caramel')), cream: norm(cssVar('--color-cream')),
    muted: norm(cssVar('--color-text-muted-inverse')), card: norm(cssVar('--color-office-card')), grid: norm(cssVar('--color-grid')),
    crosshair: norm(cssVar('--color-crosshair')), areaTop: norm(cssVar('--color-area-top')), track: norm(cssVar('--color-ring-1-track')),
    compare: norm(cssVar('--color-compare')), text: norm(cssVar('--color-text-inverse')),
    font: cssVar('--font-body').split(',')[0].replace(/["']/g, '') || 'Figtree',
    ms: (() => { const v = cssVar('--duration-chart'); return v.endsWith('ms') ? parseFloat(v) : parseFloat(v) * 1000 || 0; })(),
    morph: (() => { const v = cssVar('--duration-morph'); return v.endsWith('ms') ? parseFloat(v) : parseFloat(v) * 1000 || 0; })(),
  });
  let T = tokens();

  // ---------- formatting (British) ----------
  const isoDate = (iso) => new Date(`${iso}T12:00:00Z`);
  const dayLabel = (iso) => shortDay.format(isoDate(iso));
  const tipDay = (iso) => longDay.format(isoDate(iso)).replace(',', '');
  const label = (iso, weekly) => (weekly ? `w/c ${dayLabel(iso)}` : dayLabel(iso));
  const compact = (v) => {
    if (v >= 1e6) return `${+(v / 1e6).toFixed(1)}m`;
    if (v >= 1e3) return `${+(v / 1e3).toFixed(1)}k`;
    return String(v);
  };
  const rate = (bp) => { const p = bp / 100; return p < 10 ? `${p.toFixed(1)}%` : `${Math.round(p)}%`; };
  const wrap = (text, max = 16) => {
    const lines = []; let line = '';
    String(text).split(' ').forEach((word) => {
      if (line && `${line} ${word}`.length > max) { lines.push(line); line = word; } else line = line ? `${line} ${word}` : word;
    });
    if (line) lines.push(line);
    return lines.length > 1 ? lines : lines[0] || '';
  };

  // ---------- plugins ----------
  const crosshair = {
    id: 'crosshair',
    afterDatasetsDraw(chart) {
      const active = chart.tooltip?.getActiveElements?.() || [];
      if (!active.length) return;
      const { ctx, chartArea } = chart; const x = active[0].element.x;
      ctx.save(); ctx.strokeStyle = T.crosshair; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke(); ctx.restore();
    },
  };
  const tracks = {   // the full-length track behind each funnel bar
    id: 'tracks',
    beforeDatasetsDraw(chart, _args, opts) {
      if (!opts?.on) return;
      const { ctx, scales } = chart; const meta = chart.getDatasetMeta(0);
      ctx.save(); ctx.fillStyle = T.track;
      meta.data.forEach((bar) => {
        const x0 = scales.x.getPixelForValue(0); const w = scales.x.right - x0; const h = bar.height;
        ctx.beginPath(); ctx.roundRect(x0, bar.y - h / 2, w, h, 4); ctx.fill();
      });
      ctx.restore();
    },
  };
  const directLabels = {   // values written at the bar end, so nothing lives only in a tooltip
    id: 'directLabels',
    afterDatasetsDraw(chart, _args, opts) {
      if (!opts?.texts) return;
      const { ctx } = chart; const meta = chart.getDatasetMeta(0);
      ctx.save(); ctx.font = `500 12px ${T.font}`; ctx.textBaseline = 'middle';
      meta.data.forEach((bar, i) => {
        const text = opts.texts[i]; if (!text) return;
        ctx.fillStyle = (opts.emphasis || []).includes(i) ? T.cream : T.muted;
        if (opts.horizontal) { ctx.textAlign = 'left'; ctx.fillText(text, Math.max(bar.x, bar.base) + 8, bar.y); }
        else { ctx.textAlign = 'center'; ctx.fillText(text, bar.x, bar.y - 10); }
      });
      ctx.restore();
    },
  };

  function hatch(colour) {
    const c = document.createElement('canvas'); c.width = c.height = 8;
    const g = c.getContext('2d'); g.strokeStyle = colour; g.lineWidth = 2;
    g.beginPath(); g.moveTo(-2, 10); g.lineTo(10, -2); g.moveTo(-2, 2); g.lineTo(2, -2); g.moveTo(6, 10); g.lineTo(10, 6); g.stroke();
    return probe.createPattern(c, 'repeat');
  }

  // ---------- tooltip: one HTML element per chart, cream, opacity only ----------
  function tipFor(box) {
    let el = box.querySelector('.o-tip');
    if (!el) { el = document.createElement('div'); el.className = 'o-tip'; el.setAttribute('role', 'presentation'); box.append(el); }
    return el;
  }
  function externalTip(key) {
    return ({ chart, tooltip }) => {
      const box = charts.get(key)?.box; if (!box) return;
      const el = tipFor(box);
      if (tooltip.opacity === 0 || !tooltip.dataPoints?.length) { el.removeAttribute('data-show'); return; }
      const content = charts.get(key).spec.tip(tooltip.dataPoints);
      el.replaceChildren();
      const title = document.createElement('div'); title.className = 'o-tip-title'; title.textContent = content.title; el.append(title);
      content.rows.forEach((row) => {
        const line = document.createElement('div'); line.className = 'o-tip-row';
        const swatch = document.createElement('span'); swatch.className = `o-tip-key${row.square ? ' o-tip-key--sq' : ''}`;
        swatch.style.background = row.dashed ? 'none' : row.color;
        if (row.dashed) { swatch.style.height = '0'; swatch.style.borderTop = `2px dashed ${row.color}`; }
        const name = document.createElement('span'); name.textContent = row.label;
        const value = document.createElement('span'); value.className = 'o-tip-val'; value.textContent = row.value;
        line.append(swatch, name, value); el.append(line);
      });
      const w = el.offsetWidth; const h = el.offsetHeight;
      const left = Math.min(Math.max(tooltip.caretX - w / 2, 0), chart.width - w);
      const top = coarse.matches ? chart.chartArea.top - h - 6 : Math.max(tooltip.caretY - h - 12, 0);
      el.style.transform = `translate(${left}px, ${top}px)`;
      el.setAttribute('data-show', '');
    };
  }
  document.addEventListener('pointerdown', (event) => {   // a tap outside hides the tooltip
    charts.forEach(({ chart, box }) => {
      if (box.contains(event.target)) return;
      if (chart.tooltip?.getActiveElements?.().length) { chart.setActiveElements([]); chart.tooltip.setActiveElements([], { x: 0, y: 0 }); chart.update('none'); }
    });
  });

  // ---------- shared options ----------
  const yTicks = { color: T.muted, padding: 8, maxTicksLimit: 5, callback: (v) => compact(v) };
  function base(key, extra = {}) {
    return {
      responsive: true, maintainAspectRatio: false, devicePixelRatio: window.devicePixelRatio,
      animation: reducedQuery.matches ? false : { duration: T.ms, easing: 'easeOutQuint', delay: (ctx) => (ctx.type === 'data' && ctx.mode === 'default' ? (ctx.datasetIndex || 0) * 150 : 0) },
      transitions: { active: { animation: { duration: 0 } }, resize: { animation: { duration: 0 } } },
      plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip(key) } },
      ...extra,
    };
  }
  const horizontal = (key, data, texts, emphasis = [], pad = 76) => base(key, {
    indexAxis: 'y',
    layout: { padding: { right: pad } },
    interaction: { mode: 'nearest', axis: 'y', intersect: false },
    scales: {
      x: { display: false, min: 0, ...(data.max ? { max: data.max } : {}) },
      y: { grid: { display: false }, border: { display: false }, ticks: { color: T.muted, autoSkip: false, padding: 8, callback(_v, i) { return wrap(data.labels[i]); } } },
    },
    plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip(key) }, directLabels: { texts, emphasis, horizontal: true }, tracks: { on: !!data.tracks } },
  });
  const barStyle = (colour) => ({ backgroundColor: colour, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 28, categoryPercentage: 0.7, barPercentage: 0.9 });
  const gridY = () => ({ beginAtZero: true, grid: { color: T.grid, lineWidth: 1, drawTicks: false }, border: { display: false }, ticks: yTicks });

  // ---------- chart specs: make(data) gives the Chart.js config; tip(points) the tooltip; empty(data) the empty test ----------
  const specs = {
    visitors: {
      empty: (d) => !d.series.visitors.total && !d.series.page_views.total,
      make(d) {
        const weekly = d.granularity === 'week'; const s = d.series[state.metric]; const name = state.metric === 'visitors' ? 'Visitors' : 'Page views';
        const days = d.labels.length;
        const datasets = [{
          label: name, data: s.values, borderColor: T.gold, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: T.gold,
          pointHoverBorderColor: T.card, pointHoverBorderWidth: 2, cubicInterpolationMode: 'monotone', fill: true,
          backgroundColor: (ctx) => {
            const area = ctx.chart.chartArea; if (!area) return null;
            const g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
            g.addColorStop(0, T.areaTop); g.addColorStop(1, alpha(T.areaTop, 0)); return g;
          },
        }];
        if (s.previous?.length) datasets.push({ label: `Previous ${days} days`, data: s.previous, borderColor: T.compare, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: T.compare, pointHoverBorderColor: T.card, pointHoverBorderWidth: 2, cubicInterpolationMode: 'monotone', fill: false });
        return {
          type: 'line',
          data: { labels: d.labels.map((l) => label(l, weekly)), datasets },
          options: base('visitors', {
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { right: 8 } },
            scales: {
              x: { grid: { display: false }, border: { display: false }, ticks: { color: T.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: coarse.matches ? 4 : 7, padding: 8 } },
              y: gridY(),
            },
          }),
          legend: datasets.length > 1 ? [{ text: name, line: T.gold }, { text: datasets[1].label, line: T.compare, dashed: true }] : [],
          tip: (pts) => ({
            title: weekly ? `w/c ${tipDay(d.labels[pts[0].dataIndex])}` : tipDay(d.labels[pts[0].dataIndex]),
            rows: pts.map((p) => ({ label: p.dataset.label, value: nf.format(p.parsed.y), color: p.dataset.borderColor, dashed: p.datasetIndex === 1 })),
          }),
        };
      },
    },
    funnel: {
      empty: (d) => !d.funnel.some((s) => s.value > 0),
      make(d) {
        const steps = d.funnel; let drop = -1; let low = Infinity;
        steps.forEach((s, i) => { if (i && s.step_rate_bp !== null && s.step_rate_bp < low) { low = s.step_rate_bp; drop = i; } });
        const texts = steps.map((s, i) => (i && s.step_rate_bp !== null ? `${nf.format(s.value)} · ${rate(s.step_rate_bp)}` : nf.format(s.value)));
        const data = { labels: steps.map((s) => s.label), max: steps[0].value || undefined, tracks: true };
        return {
          type: 'bar',
          data: { labels: data.labels, datasets: [{ data: steps.map((s) => s.value), ...barStyle(T.gold) }] },
          options: horizontal('funnel', data, texts, drop > 0 ? [drop] : [], 120),
          plugins: [tracks, directLabels],
          tip: (pts) => { const s = steps[pts[0].dataIndex]; return { title: s.label, rows: [{ label: 'People', value: nf.format(s.value), color: T.gold, square: true }, ...(s.step_rate_bp !== null ? [{ label: 'Of the step before', value: rate(s.step_rate_bp), color: T.gold, square: true }] : []), { label: 'Of visitors', value: rate(s.share_bp), color: T.gold, square: true }] }; },
        };
      },
    },
    plan: simpleBars('plan', (d) => d.registrations_by_plan, 'value', 'Registrations'),
    suggested: {
      empty: (d) => !d.suggested_plan.some((p) => p.value > 0),
      make(d) {
        const colours = [T.gold, T.caramel, T.cream, hatch(T.cream)];
        const items = d.suggested_plan;
        return {
          type: 'bar',
          data: { labels: [''], datasets: items.map((p, i) => ({ label: p.label, data: [p.value], backgroundColor: colours[Math.min(i, 3)], borderColor: T.card, borderWidth: 2, borderRadius: 0, borderSkipped: false, maxBarThickness: 28, barPercentage: 1, categoryPercentage: 1 })) },
          options: base('suggested', { indexAxis: 'y', layout: { padding: 0 }, interaction: { mode: 'nearest', intersect: true }, scales: { x: { stacked: true, display: false, min: 0 }, y: { stacked: true, display: false } } }),
          tip: (pts) => { const p = items[pts[0].datasetIndex]; return { title: p.label, rows: [{ label: 'Suggested', value: nf.format(p.value), color: T.gold, square: true }, { label: 'Share', value: rate(p.share_bp), color: T.gold, square: true }] }; },
        };
      },
    },
    'answers-time': answers('time'), 'answers-frequency': answers('frequency'), 'answers-facilities': answers('facilities'), 'answers-company': answers('company'),
    dropoff: {
      empty: (d) => !d.drop_off.some((s) => s.reached > 0),
      make(d) {
        const screens = d.drop_off; let top = -1; let max = -1;
        screens.forEach((s, i) => { if (s.left_percent > max) { max = s.left_percent; top = i; } });
        const texts = screens.map((s, i) => (i === top && s.left_percent > 0 ? `${s.left_percent}% left` : ''));
        return {
          type: 'bar',
          data: { labels: screens.map((s) => `Screen ${s.screen}`), datasets: [{ data: screens.map((s) => s.left_percent), ...barStyle(T.gold), borderSkipped: 'start' }] },
          options: base('dropoff', {
            layout: { padding: { top: 24 } }, interaction: { mode: 'nearest', axis: 'x', intersect: false },
            scales: { x: { grid: { display: false }, border: { display: false }, ticks: { color: T.muted, maxRotation: 0, autoSkip: false, padding: 8, callback(_v, i) { return wrap(`Screen ${screens[i]?.screen}`, 8); } } }, y: { ...gridY(), ticks: { ...yTicks, callback: (v) => `${v}%` } } },
            plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip('dropoff') }, directLabels: { texts, emphasis: [top], horizontal: false } },
          }),
          plugins: [directLabels],
          tip: (pts) => { const s = screens[pts[0].dataIndex]; return { title: s.label, rows: [{ label: 'Reached', value: nf.format(s.reached), color: T.gold, square: true }, { label: 'Left here', value: `${nf.format(s.left)} · ${s.left_percent}%`, color: T.gold, square: true }] }; },
        };
      },
    },
    'gold-potential': simpleBars('gold-potential', (d) => d.gold.by_potential, 'value', 'Applications'),
    'gold-status': {
      empty: (d) => !d.gold.by_status_now.some((s) => s.value > 0),
      make(d) {
        const colours = { approved: T.gold, waiting: T.cream, declined: hatch(T.caramel) };
        const items = d.gold.by_status_now;
        return {
          type: 'bar',
          data: { labels: [''], datasets: items.map((s) => ({ label: s.label, data: [s.value], backgroundColor: colours[s.dimension] || T.cream, borderColor: s.dimension === 'declined' ? T.caramel : T.card, borderWidth: s.dimension === 'declined' ? 1 : 2, borderSkipped: false, maxBarThickness: 28, barPercentage: 1, categoryPercentage: 1 })) },
          options: base('gold-status', { indexAxis: 'y', layout: { padding: 0 }, interaction: { mode: 'nearest', intersect: true }, scales: { x: { stacked: true, display: false, min: 0 }, y: { stacked: true, display: false } } }),
          legend: items.map((s) => ({ text: `${s.label} ${nf.format(s.value)}`, square: colours[s.dimension], hatch: s.dimension === 'declined' })),
          tip: (pts) => ({ title: items[pts[0].datasetIndex].label, rows: [{ label: 'Applications', value: nf.format(items[pts[0].datasetIndex].value), color: T.gold, square: true }] }),
        };
      },
    },
  };

  function simpleBars(key, pick, field, rowLabel) {
    return {
      empty: (d) => !pick(d).some((i) => i[field] > 0),
      make(d) {
        const items = pick(d);
        const texts = items.map((i) => (i.share_bp !== undefined ? `${nf.format(i[field])} · ${rate(i.share_bp)}` : nf.format(i[field])));
        const data = { labels: items.map((i) => i.label) };
        return {
          type: 'bar',
          data: { labels: data.labels, datasets: [{ data: items.map((i) => i[field]), ...barStyle(T.gold) }] },
          options: horizontal(key, data, texts, [], 96),
          plugins: [directLabels],
          tip: (pts) => { const i = items[pts[0].dataIndex]; return { title: i.label, rows: [{ label: rowLabel, value: nf.format(i[field]), color: T.gold, square: true }, ...(i.share_bp !== undefined ? [{ label: 'Share', value: rate(i.share_bp), color: T.gold, square: true }] : [])] }; },
        };
      },
    };
  }
  function answers(question) { return simpleBars(`answers-${question}`, (d) => d.journey_answers[question].map((a) => ({ label: a.label, value: a.count, share_bp: a.share_bp })), 'value', 'Answers'); }

  // ---------- create, update, legends ----------
  const readData = () => JSON.parse(document.getElementById('office-series').textContent);

  function legend(key, items) {
    if (!Array.isArray(items)) return;
    const el = root.querySelector(`[data-legend="${key}"]`);
    if (!el) return;
    el.replaceChildren();
    (items || []).forEach((item) => {
      const row = document.createElement('span'); row.className = 'o-legend-item';
      const mark = document.createElement('span');
      if (item.line) { mark.className = `o-legend-line${item.dashed ? ' o-legend-line--previous' : ''}`; }
      else { mark.className = 'o-legend-sq'; mark.style.background = item.hatch ? `repeating-linear-gradient(45deg, ${T.caramel} 0 2px, transparent 2px 4px)` : item.square; if (item.hatch) mark.style.boxShadow = `inset 0 0 0 1px ${T.caramel}`; }
      const text = document.createElement('span'); text.textContent = item.text;
      row.append(mark, text); el.append(row);
    });
  }

  function summaryFor(card, d) {
    const map = { visitors: 'visitors', funnel: 'funnel', plan: 'registrations_by_plan', suggested: 'suggested_plan', answers: 'journey_answers', dropoff: 'drop_off', gold: 'gold' };
    return d.summaries?.[map[card]] || '';
  }

  function sync(key, d) {
    const entry = charts.get(key); const spec = specs[key]; if (!entry && !spec) return;
    const box = entry?.box || root.querySelector(`[data-chart="${key}"]`);
    const empty = spec.empty(d);
    box.toggleAttribute('data-empty', empty);
    const card = box.closest('[data-chart-card]'); const cardKey = card?.dataset.chartCard;
    const table = card?.querySelector('.o-table');
    if (table && cardKey && !(cardKey === 'answers' || cardKey === 'gold')) table.hidden = empty;
    const canvas = box.querySelector('canvas'); const summary = summaryFor(cardKey, d);
    if (summary && (cardKey === key || cardKey === 'visitors')) canvas.setAttribute('aria-label', summary);
    if (!entry) return;
    if (empty) return;
    const cfg = spec.make(d);
    entry.spec = { tip: cfg.tip };
    const { chart } = entry;
    chart.data.labels = cfg.data.labels;
    chart.data.datasets = cfg.data.datasets;
    chart.options = cfg.options;
    chart.update();
    legend(key, cfg.legend);
  }

  function create(key) {
    if (charts.has(key)) return;
    const box = root.querySelector(`[data-chart="${key}"]`); if (!box) return;
    const d = readData(); const spec = specs[key];
    box.toggleAttribute('data-empty', spec.empty(d));
    if (spec.empty(d)) return; // an empty range keeps its one-line state; a later range creates the chart
    const cfg = spec.make(d);
    const chart = new Chart(box.querySelector('canvas'), { type: cfg.type, data: cfg.data, options: cfg.options, plugins: cfg.plugins || [crosshair] });
    charts.set(key, { chart, box, spec: { tip: cfg.tip } });
    legend(key, cfg.legend);
    sync(key, d);
  }
  const keysIn = (card) => [...card.querySelectorAll('[data-chart]')].map((el) => el.dataset.chart);

  // visitors toggle (Visitors / Page views): same morph
  const toggle = root.querySelector('[data-chart-toggle="visitors"]');
  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener('change', (event) => { state.metric = event.target.value; sync('visitors', readData()); });
  }

  document.addEventListener('office:series', () => {
    const d = readData();
    Object.keys(specs).forEach((key) => {
      if (charts.has(key)) sync(key, d);
      else {
        const box = root.querySelector(`[data-chart="${key}"]`); if (!box) return;
        const card = box.closest('[data-chart-card]');
        if (created.has(card)) create(key); // it was empty before and has data now
        else sync(key, d);
      }
    });
  });
  reducedQuery.addEventListener('change', () => charts.forEach(({ chart }) => { chart.options.animation = reducedQuery.matches ? false : { duration: T.ms, easing: 'easeOutQuint' }; }));

  // ---------- defaults, then lazily per card ----------
  document.fonts.ready.then(() => {
    T = tokens();
    Chart.defaults.font.family = T.font; Chart.defaults.font.size = 12; Chart.defaults.color = T.muted;
    Chart.defaults.maintainAspectRatio = false;
    const cards = [...root.querySelectorAll('[data-chart-card]')];
    const reveal = (card) => { created.add(card); keysIn(card).forEach(create); };
    if (!('IntersectionObserver' in window)) { cards.forEach(reveal); return; }
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { observer.unobserve(entry.target); reveal(entry.target); }
    }), { threshold: 0.15 });
    cards.forEach((card) => observer.observe(card));
  });
}
