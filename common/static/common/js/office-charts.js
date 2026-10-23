/* Office Analytics charts (docs/design/OFFICE.md section 5, light). Chart.js 4.6.1 (self-hosted UMD) is loaded by the page; this module reads window.Chart.
 * - Data comes from the page's <script id="office-series"> (stored figures). Nothing is calculated here beyond layout: shares, rates and totals are the server's.
 * - Colours come from the Office tokens on <body> (getComputedStyle), never hard-coded.
 * - Each card's charts are created lazily when 15% of the card is in view, after the fonts are ready.
 * - A range switch (office-swap.js) replaces the JSON and fires 'office:series': every chart morphs in place with chart.update().
 * - Charts here: the hero area line, the centred funnel, the donuts (plans, journey answers) and the "where people stop" columns.
 *   Facilities, Gold, top pages and referrers are server-rendered bar lists (plain HTML, same colours). */
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

  // ---------- tokens (read from the body, where the Office tokens live) ----------
  const probe = document.createElement('canvas').getContext('2d');
  const cssVar = (name) => getComputedStyle(document.body).getPropertyValue(name).trim();
  const norm = (value) => { probe.fillStyle = '#000'; probe.fillStyle = value; return probe.fillStyle; }; // hex or rgba(), for any CSS colour syntax
  const rgb = (value) => {
    const m = String(norm(value));
    if (m.startsWith('#')) { const n = parseInt(m.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
    const parts = m.match(/[\d.]+/g) || [0, 0, 0];
    return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
  };
  const alpha = (value, a) => { const [r, g, b] = rgb(value); return `rgba(${r}, ${g}, ${b}, ${a})`; };
  const mixOver = (value, base, share) => { // `value` at `share` over `base`, as an opaque colour
    const [r, g, b] = rgb(value); const [r2, g2, b2] = rgb(base);
    const f = (a, c) => Math.round(a * share + c * (1 - share));
    return `rgb(${f(r, r2)}, ${f(g, g2)}, ${f(b, b2)})`;
  };
  const ms = (name) => { const v = cssVar(name); return v.endsWith('ms') ? parseFloat(v) : parseFloat(v) * 1000 || 0; };
  const tokens = () => {
    const t = {
      slate: norm(cssVar('--office-slate')), plum: norm(cssVar('--office-plum')), sage: norm(cssVar('--office-sage')), teal: norm(cssVar('--office-teal')),
      clay: norm(cssVar('--office-clay')), taupe: norm(cssVar('--office-taupe')),
      clayRamp: ['--office-clay', '--office-clay-2', '--office-clay-3', '--office-clay-4'].map((n) => norm(cssVar(n))),
      tealRamp: ['--office-teal', '--office-teal-2', '--office-teal-3', '--office-teal-4'].map((n) => norm(cssVar(n))),
      surface: norm(cssVar('--office-surface')), muted: norm(cssVar('--office-muted')), text: norm(cssVar('--office-text')),
      grid: norm(cssVar('--office-grid')), crosshair: norm(cssVar('--office-crosshair')),
      font: cssVar('--font-body').split(',')[0].replace(/["']/g, '') || 'Figtree',
      display: cssVar('--font-display').split(',')[0].replace(/["']/g, '') || 'Signika',
      ms: ms('--office-dur-chart'), morph: ms('--office-dur-morph'),
    };
    return t;
  };
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
    return lines;
  };

  // ---------- ordered categories: a ramp of the metric's own hue; the same fold as the server's legend (ramp_rows) ----------
  function rampRows(items, hue, valueKey) {
    const steps = hue === 'teal' ? T.tealRamp : T.clayRamp; const rows = []; let other = null; let none = null;
    items.forEach((item) => {
      const row = { label: item.label, value: item[valueKey], share_bp: item.share_bp };
      if (item.dimension === 'none') none = row;
      else if (rows.length < steps.length) { row.color = steps[rows.length]; rows.push(row); }
      else { other = other || { label: 'Other', value: 0, share_bp: 0 }; other.value += row.value; other.share_bp += row.share_bp; }
    });
    [other, none].forEach((extra) => { if (extra) { extra.color = T.taupe; rows.push(extra); } });
    return rows;
  }

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
  const funnelText = {   // a label left of each pill, its count right, and "74% carried on" between pills
    id: 'funnelText',
    afterDatasetsDraw(chart, _args, opts) {
      if (!opts?.steps) return;
      const { ctx, chartArea, width } = chart; const meta = chart.getDatasetMeta(0);
      const narrow = width < 520; const mid = (chartArea.left + chartArea.right) / 2;
      ctx.save(); ctx.textBaseline = 'middle';
      meta.data.forEach((bar, i) => {
        const step = opts.steps[i]; if (!step) return;
        ctx.textAlign = 'left'; ctx.fillStyle = T.muted; ctx.font = `500 12px ${T.font}`;
        const lines = wrap(step.name, narrow ? 11 : 26);
        lines.forEach((line, n) => ctx.fillText(line, 0, bar.y + (n - (lines.length - 1) / 2) * 14));
        ctx.textAlign = 'right'; ctx.fillStyle = T.text; ctx.font = `500 ${narrow ? 17 : 20}px ${T.display}`;
        ctx.fillText(nf.format(step.value), width, bar.y);
      });
      ctx.textAlign = 'center'; ctx.font = `500 12px ${T.font}`;
      meta.data.slice(0, -1).forEach((bar, i) => {
        const text = opts.between[i]; if (!text) return;
        const y = (bar.y + meta.data[i + 1].y) / 2;
        ctx.fillStyle = i === opts.drop ? T.text : T.muted;
        ctx.font = `${i === opts.drop ? 600 : 500} 12px ${T.font}`;
        ctx.fillText(text, mid, y);
      });
      ctx.restore();
    },
  };
  const topLabel = {   // "23 left here" above the tallest column
    id: 'topLabel',
    afterDatasetsDraw(chart, _args, opts) {
      if (!opts?.text || opts.index < 0) return;
      const bar = chart.getDatasetMeta(0).data[opts.index]; if (!bar) return;
      const { ctx } = chart;
      ctx.save(); ctx.font = `600 12px ${T.font}`; ctx.fillStyle = T.text; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
      ctx.fillText(opts.text, Math.min(Math.max(bar.x, 40), chart.width - 40), bar.y - 6);
      ctx.restore();
    },
  };

  // ---------- tooltip: one HTML element per chart, white, opacity only ----------
  function tipFor(box) {
    let el = box.querySelector('.o-tip');
    if (!el) { el = document.createElement('div'); el.className = 'o-tip'; el.setAttribute('role', 'presentation'); box.append(el); }
    return el;
  }
  function externalTip(key) {
    return ({ chart, tooltip }) => {
      const entry = charts.get(key); const box = entry?.box; if (!box) return;
      const el = tipFor(box);
      if (tooltip.opacity === 0 || !tooltip.dataPoints?.length) { el.removeAttribute('data-show'); return; }
      const content = entry.spec.tip(tooltip.dataPoints);
      el.replaceChildren();
      const title = document.createElement('div'); title.className = 'o-tip-title'; title.textContent = content.title; el.append(title);
      content.rows.forEach((row) => {
        const line = document.createElement('div'); line.className = 'o-tip-row';
        const swatch = document.createElement('span'); swatch.className = 'o-tip-key'; swatch.style.background = row.color;
        const name = document.createElement('span'); name.textContent = row.label;
        const value = document.createElement('span'); value.className = 'o-tip-val'; value.textContent = row.value;
        line.append(swatch, name, value); el.append(line);
      });
      const w = el.offsetWidth; const h = el.offsetHeight;
      const card = box.closest('.o-card') || box; const b = box.getBoundingClientRect(); const c = card.getBoundingClientRect();
      const min = c.left - b.left + 8; const max = c.right - b.left - w - 8;   // stay inside the card
      const left = Math.max(min, Math.min(tooltip.caretX - w / 2, max));
      const top = coarse.matches ? chart.chartArea.top - h - 6 : tooltip.caretY - h - 12;
      el.style.transform = `translate(${left}px, ${Math.max(top, -h - 8)}px)`;
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
  function base(key, extra = {}) {
    return {
      responsive: true, maintainAspectRatio: false, devicePixelRatio: window.devicePixelRatio,
      layout: { padding: { top: 8 } },
      animation: reducedQuery.matches ? false : { duration: T.ms, easing: 'easeOutQuint', delay: (ctx) => (ctx.type === 'data' && ctx.mode === 'default' ? (ctx.datasetIndex || 0) * 150 : 0) },
      transitions: { active: { animation: { duration: 120 } }, resize: { animation: { duration: 0 } } },
      plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip(key) } },
      ...extra,
    };
  }
  const xScale = (extra = {}) => ({ grid: { display: false }, border: { display: false }, ticks: { color: T.muted, maxRotation: 0, autoSkip: true, padding: 10 }, ...extra });
  const yScale = (extra = {}) => ({ beginAtZero: true, grid: { color: T.grid, lineWidth: 1, drawTicks: false }, border: { display: false }, ticks: { color: T.muted, padding: 10, maxTicksLimit: 4, callback: (v) => compact(v) }, ...extra });

  // ---------- chart specs: make(data) gives the Chart.js config; tip(points) the tooltip; empty(data) the empty test ----------
  const specs = {
    visitors: {
      empty: (d) => !d.series.visitors.total && !d.series.page_views.total,
      make(d) {
        const weekly = d.granularity === 'week'; const s = d.series[state.metric];
        const metric = state.metric === 'visitors' ? { name: 'Visitors', color: T.slate } : { name: 'Page views', color: T.plum };
        const days = d.labels.length;
        const datasets = [{
          label: metric.name, data: s.values, borderColor: metric.color, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 6, pointHoverBackgroundColor: metric.color,
          pointHoverBorderColor: T.surface, pointHoverBorderWidth: 2, cubicInterpolationMode: 'monotone', fill: 'origin',
          backgroundColor: (ctx) => {
            const { chart } = ctx; const a = chart.chartArea; if (!a) return 'transparent';
            const g = chart.ctx.createLinearGradient(0, a.top, 0, a.bottom);
            g.addColorStop(0, alpha(metric.color, 0.28)); g.addColorStop(1, alpha(metric.color, 0)); return g;
          },
        }];
        if (s.previous?.length) datasets.push({ label: `Previous ${days} days`, data: s.previous, borderColor: T.taupe, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: T.taupe, pointHoverBorderColor: T.surface, pointHoverBorderWidth: 2, cubicInterpolationMode: 'monotone', fill: false });
        return {
          type: 'line',
          data: { labels: d.labels.map((l) => label(l, weekly)), datasets },
          options: base('visitors', {
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 8, right: 8 } },
            scales: { x: xScale({ ticks: { color: T.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: coarse.matches ? 4 : 7, padding: 10 } }), y: yScale() },
          }),
          legend: datasets.length > 1 ? [{ text: metric.name, color: metric.color }, { text: datasets[1].label, color: T.taupe, dashed: true }] : [],
          tip: (pts) => ({
            title: weekly ? `w/c ${tipDay(d.labels[pts[0].dataIndex])}` : tipDay(d.labels[pts[0].dataIndex]),
            rows: pts.map((p) => ({ label: p.dataset.label, value: nf.format(p.parsed.y), color: p.dataset.borderColor })),
          }),
        };
      },
    },
    funnel: {
      empty: (d) => !d.funnel.some((s) => s.value > 0),
      make(d) {
        const steps = d.funnel; const colours = [T.slate, T.sage, T.teal, T.clay];
        let drop = -1; let low = Infinity;   // the largest drop is the step that carried on the smallest share
        steps.forEach((s, i) => { if (i && !s.partial && s.step_rate_bp !== null && s.step_rate_bp < low) { low = s.step_rate_bp; drop = i - 1; } });
        const between = steps.slice(1).map((s) => (s.partial || s.step_rate_bp === null ? '' : `${rate(s.step_rate_bp)} carried on`));
        const names = steps.map((s) => (s.key === 'completed' ? 'Finished it' : s.label));
        const top = Math.max(...steps.map((s) => s.value), 1);
        const narrow = (charts.get('funnel')?.box || root.querySelector('[data-chart="funnel"]')).clientWidth < 520;
        return {
          type: 'bar',
          data: { labels: names, datasets: [{ data: steps.map((s) => [-s.value / 2, s.value / 2]), backgroundColor: colours, borderRadius: 999, borderSkipped: false, barPercentage: 0.78, categoryPercentage: 1, minBarLength: 10 }] },
          options: base('funnel', {
            indexAxis: 'y', layout: { padding: { top: 0, left: narrow ? 84 : 170, right: narrow ? 56 : 80 } },
            interaction: { mode: 'nearest', intersect: true },
            scales: { x: { display: false, min: -top / 2, max: top / 2 }, y: { display: false } },
            plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip('funnel') }, funnelText: { steps: steps.map((s, i) => ({ name: names[i], value: s.value })), between, drop } },
          }),
          plugins: [funnelText],
          tip: (pts) => {
            const i = pts[0].dataIndex; const s = steps[i];
            return { title: names[i], rows: [{ label: 'People', value: nf.format(s.value), color: colours[i] }, ...(i && s.step_rate_bp !== null && !s.partial ? [{ label: 'Of the step before', value: rate(s.step_rate_bp), color: colours[i] }] : []), { label: 'Of visitors', value: rate(s.share_bp), color: colours[i] }] };
          },
        };
      },
    },
    plan: donut('plan', (d) => d.registrations_by_plan, 'value', 'clay', 'Registrations'),
    suggested: donut('suggested', (d) => d.suggested_plan, 'value', 'clay', 'Suggested'),
    'answers-time': donut('answers-time', (d) => d.journey_answers.time, 'count', 'teal', 'Answers'),
    'answers-frequency': donut('answers-frequency', (d) => d.journey_answers.frequency, 'count', 'teal', 'Answers'),
    'answers-company': donut('answers-company', (d) => d.journey_answers.company, 'count', 'teal', 'Answers'),
    dropoff: {
      empty: (d) => !d.drop_off.some((s) => s.reached > 0),
      make(d) {
        const screens = d.drop_off; let top = -1; let max = 0;
        screens.forEach((s, i) => { if (s.left > max) { max = s.left; top = i; } });
        const soft = mixOver(T.teal, T.surface, 0.48);
        const n = Math.max(screens.length, 1);
        return {
          type: 'bar',
          data: { labels: screens.map((s) => `Screen ${s.screen}`), datasets: [{ data: screens.map((s) => s.left), backgroundColor: screens.map((_s, i) => (i === top ? T.teal : soft)), borderRadius: 8, borderSkipped: 'start', maxBarThickness: 32, categoryPercentage: 0.8, barPercentage: 0.9 }] },
          options: base('dropoff', {
            layout: { padding: { top: 30 } }, interaction: { mode: 'nearest', axis: 'x', intersect: true },
            scales: {
              x: xScale({ ticks: { color: T.muted, maxRotation: 0, autoSkip: false, padding: 10, callback(_v, i) { const num = screens[i]?.screen; return this.chart.width / n < 56 ? [String(num)] : ['Screen', String(num)]; } } }),
              y: yScale({ ticks: { color: T.muted, padding: 10, maxTicksLimit: 4, precision: 0, callback: (v) => compact(v) } }),
            },
            plugins: { legend: { display: false }, tooltip: { enabled: false, external: externalTip('dropoff') }, topLabel: { index: top, text: top >= 0 ? `${nf.format(max)} left here` : '' } },
          }),
          plugins: [topLabel],
          tip: (pts) => { const s = screens[pts[0].dataIndex]; return { title: s.label, rows: [{ label: 'Reached', value: nf.format(s.reached), color: i0(pts) === top ? T.teal : soft }, { label: 'Left here', value: `${nf.format(s.left)} · ${s.left_percent}%`, color: i0(pts) === top ? T.teal : soft }] }; },
        };
      },
    },
  };
  const i0 = (pts) => pts[0].dataIndex;

  function donut(key, pick, field, hue, rowLabel) {
    return {
      empty: (d) => !pick(d).some((i) => i[field] > 0),
      make(d) {
        const rows = rampRows(pick(d), hue, field).filter((r) => r.value > 0);
        return {
          type: 'doughnut',
          data: { labels: rows.map((r) => r.label), datasets: [{ data: rows.map((r) => r.value), backgroundColor: rows.map((r) => r.color), borderWidth: 0, borderRadius: 8, spacing: 3, hoverOffset: 6 }] },
          options: base(key, {
            cutout: '76%', layout: { padding: 8 }, interaction: { mode: 'nearest', intersect: true },
            animation: reducedQuery.matches ? false : { duration: T.ms, easing: 'easeOutQuint', animateRotate: true, animateScale: false },
          }),
          plugins: [],
          tip: (pts) => { const r = rows[pts[0].dataIndex]; return { title: r.label, rows: [{ label: rowLabel, value: `${nf.format(r.value)} · ${rate(r.share_bp)}`, color: r.color }] }; },
        };
      },
    };
  }

  // ---------- create, update, legends ----------
  const readData = () => JSON.parse(document.getElementById('office-series').textContent);

  function legend(key, items) {
    if (!Array.isArray(items)) return;
    const el = root.querySelector(`[data-legend="${key}"]`);
    if (!el) return;
    el.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement('span'); row.className = 'o-legend-item';
      const mark = document.createElement('span');
      if (item.dashed) { mark.className = 'o-legend-line'; mark.style.borderTopColor = item.color; }
      else { mark.className = 'o-swatch'; mark.style.setProperty('--sw', item.color); }
      const text = document.createElement('span'); text.textContent = item.text;
      row.append(mark, text); el.append(row);
    });
  }

  function summaryFor(card, d) {
    const map = { visitors: 'visitors', funnel: 'funnel', plan: 'registrations_by_plan', suggested: 'suggested_plan', answers: 'journey_answers', dropoff: 'drop_off', gold: 'gold' };
    return d.summaries?.[map[card]] || '';
  }

  /** The hero's big number follows the toggle (both figures are rendered by the server; this only shows one). */
  function hero() {
    const card = root.querySelector('[data-chart-card="visitors"]'); if (!card) return;
    card.dataset.metric = state.metric;
    card.querySelectorAll('[data-hero-fig]').forEach((fig) => { fig.hidden = fig.dataset.heroFig !== state.metric; });
    const group = card.querySelector('[data-chart-toggle]');
    if (group) {
      const inputs = [...group.querySelectorAll('input[type="radio"]')];
      inputs.forEach((input) => { input.checked = input.value === state.metric; });
      group.style.setProperty('--i', String(Math.max(inputs.findIndex((i) => i.checked), 0)));
    }
  }

  /** Cards with no chart of their own keep their "View as table" in step with their data. */
  function tables(d) {
    const set = (card, empty) => { const t = root.querySelector(`[data-chart-card="${card}"] .o-table`); if (t) t.hidden = empty; };
    const a = d.journey_answers;
    set('answers', !['time', 'frequency', 'facilities', 'company'].some((q) => a[q].some((i) => i.count > 0)));
    set('gold', !d.gold.by_potential.some((i) => i.value > 0) && !d.gold.by_status_now.some((i) => i.value > 0));
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
    if (summary && (cardKey === key || cardKey === 'visitors' || cardKey === 'answers')) canvas.setAttribute('aria-label', summary);
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
    const d = readData(); const spec = specs[key]; if (!spec) return;
    box.toggleAttribute('data-empty', spec.empty(d));
    if (spec.empty(d)) return; // an empty range keeps its one-line state; a later range creates the chart
    const cfg = spec.make(d);
    const chart = new Chart(box.querySelector('canvas'), { type: cfg.type, data: cfg.data, options: cfg.options, plugins: cfg.plugins || [crosshair] });
    charts.set(key, { chart, box, spec: { tip: cfg.tip } });
    legend(key, cfg.legend);
    sync(key, d);
  }
  const keysIn = (card) => [...card.querySelectorAll('[data-chart]')].map((el) => el.dataset.chart);

  // visitors toggle (Visitors / Page views): the colour switches slate to plum with a morph
  const toggle = root.querySelector('[data-chart-toggle="visitors"]');
  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener('change', (event) => { state.metric = event.target.value; hero(); sync('visitors', readData()); });
  }

  document.addEventListener('office:series', () => {
    const d = readData();
    hero(); tables(d);
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
  reducedQuery.addEventListener('change', () => { const d = readData(); charts.forEach((_entry, key) => sync(key, d)); }); // sync rebuilds every option, so animation (and animateRotate) stay consistent

  // ---------- defaults, then lazily per card ----------
  document.fonts.ready.then(() => {
    T = tokens();
    Chart.defaults.font.family = T.font; Chart.defaults.font.size = 12; Chart.defaults.color = T.muted;
    Chart.defaults.responsive = true; Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.layout.padding = { top: 8 };
    const cards = [...root.querySelectorAll('[data-chart-card]')];
    const reveal = (card) => { created.add(card); keysIn(card).forEach(create); };
    if (!('IntersectionObserver' in window)) { cards.forEach(reveal); return; }
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { observer.unobserve(entry.target); reveal(entry.target); }
    }), { threshold: 0.15 });
    cards.forEach((card) => observer.observe(card));
  });
}
