/* System > Sales: the preview link box, "Show all" on past sales, the sale form's Now switch, runs line and live preview panel. */
import { toast } from './feedback.js';
import { csrfToken } from './api.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/* ---------- preview link ---------- */
function initPreview() {
  const box = $('[data-ss-link]');
  if (!box) return;
  const input = $('[data-ss-link-url]', box);
  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('form[data-ss-preview]');
    if (!form) return;
    event.preventDefault();
    const button = $('button', form);
    button.disabled = true;
    try {
      const response = await fetch(form.action, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken() } });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.ok) throw new Error(data?.message || String(response.status));
      input.value = data.url;
      $('[data-ss-link-open]', box).href = data.url;
      $('[data-ss-link-minutes]', box).textContent = data.valid_minutes || 60;
      box.hidden = false;
      input.focus();
      input.select();
    } catch (error) {
      toast('Could not make the preview link. Please try again.', { kind: 'error' });
    } finally {
      button.disabled = false;
    }
  });
  $('[data-ss-link-copy]', box).addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(input.value); toast('Link copied.'); } catch (error) { input.focus(); input.select(); toast('Press Ctrl or Cmd C to copy.'); }
  });
}

/* ---------- past sales: latest 10, then Show all ---------- */
function initMore() {
  $$('[data-ss-more]').forEach((more) => {
    more.hidden = false;
    const button = $('[data-ss-show-all]', more);
    button.addEventListener('click', () => {
      $$('[data-ss-extra]', more.closest('section')).forEach((row) => row.setAttribute('data-open', ''));
      more.hidden = true;
    });
  });
}

/* ---------- the sale form ---------- */
const pad = (n) => String(n).padStart(2, '0');
const naive = (value) => { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value || ''); return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : NaN; };

function londonNow(addMinutes = 0) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(Date.now() + addMinutes * 60000)).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
function listed(names) { return names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names.at(-1)}` : names[0] || ''; }

function initForm() {
  const form = $('[data-sale-form]');
  if (!form) return;
  const prices = JSON.parse($('#ss-plan-prices')?.textContent || '[]');
  const field = (key) => $(`[data-ss="${key}"]`, form);
  const [name, percent, starts, ends, months] = ['name', 'percent', 'starts', 'ends', 'months'].map(field);
  const plans = $$('input[name="plans"]', form);
  const bar = $('[data-ss-bar]', form);
  const table = $('[data-ss-prices]', form);
  const runs = $('[data-ss-runs]', form);

  // "Now" (new or upcoming sale only): the start is the next minute in London. The real field stays in the form.
  const mode = $('[data-ss-start-mode]', form);
  if (mode && starts) {
    mode.hidden = false;
    const fields = $('[data-ss-start-fields]', form), note = $('[data-ss-start-now]', form);
    const apply = () => {
      const now = $('input[value="now"]', mode).checked;
      fields.hidden = now; note.hidden = !now;
      if (now) { starts.value = londonNow(1); starts.dispatchEvent(new Event('input', { bubbles: true })); }
    };
    $$('input', mode).forEach((radio) => radio.addEventListener('change', apply));
  }

  const chosen = () => plans.filter((p) => p.checked).map((p) => ({ pk: p.value, name: p.closest('label').textContent.trim() }));
  function draw() {
    const picked = chosen();
    const pct = Number(percent ? percent.value : form.dataset.percent);
    const left = naive(ends?.value) - naive(londonNow());
    if (runs) {
      const days = Math.floor(left / 86400000), hours = Math.floor((left % 86400000) / 3600000);
      runs.textContent = left > 0 ? `Runs ${days} ${days === 1 ? 'day' : 'days'}, ${hours} ${hours === 1 ? 'hour' : 'hours'}.` : '';
    }
    if (bar) {
      const total = Math.max(1, Math.ceil(left / 60000)), d = Math.floor(total / 1440), h = Math.floor((total % 1440) / 60), m = total % 60;
      const count = left > 0 ? (d ? `${d}d ${pad(h)}h ${pad(m)}m` : h ? `${h}h ${pad(m)}m` : `${m}m`) : '';
      const offer = [Number.isFinite(pct) && pct ? `${pct}% off` : '', listed(picked.map((p) => p.name))].filter(Boolean).join(' ');
      bar.textContent = [name?.value.trim(), offer, count && `ends in ${count}`].filter(Boolean).join(' · ');
    }
    if (table) {
      const n = Number(months ? months.value : form.dataset.months);
      const rows = prices.filter((p) => picked.some((c) => c.pk === p.pk));
      table.replaceChildren(...(rows.length ? rows.map((p) => {
        const tr = document.createElement('tr');
        const cells = [p.name, `£${Number(p.price).toFixed(2)}`, Number.isFinite(pct) && pct ? `£${(Math.round(Number(p.price) * (100 - pct)) / 100).toFixed(2)}` : '', n ? `${n} ${n === 1 ? 'month' : 'months'}` : ''];
        cells.forEach((text, i) => { const td = document.createElement('td'); td.textContent = text; if (i === 1 || i === 2) td.className = 'sys-num'; tr.append(td); });
        return tr;
      }) : [Object.assign(document.createElement('tr'), { innerHTML: '<td colspan="4" class="sys-muted">Tick a plan to see its sale price.</td>' })]));
    }
  }
  form.addEventListener('input', draw);
  form.addEventListener('change', draw);
  draw();

  // The panel is open from 64em and collapsed on a phone.
  const panel = $('[data-ss-preview-panel]');
  if (!panel) return;
  const wide = matchMedia('(min-width: 64em)');
  const sync = () => { panel.open = wide.matches; };
  sync();
  wide.addEventListener('change', sync);
}

initPreview();
initMore();
initForm();
