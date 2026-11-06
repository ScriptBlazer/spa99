/* System > Revenue: the live example beside the two percentages (system/templates/system/revenue.html). Everything here is an enhancement: without it the page shows the saved figures in its tiles and the panel stays hidden.
   It works out, in the browser and from the stored approved figures in #rev-preview, what the two percentages do, exactly as office.counts._due_figures does:
   month n counts  months[n-1] x paying% x (1 - dropoff%)^(n-1);  the Gold Card fee counts  gold x paying%  with no drop-off.
   Money is pence, never rounded until it is shown, and the total is worked out from the exact figures, never added up from the rounded lines. Nothing is saved or sent. */
(function () {
  'use strict';
  const panel = document.querySelector('[data-revenue-live]');
  const source = document.getElementById('rev-preview');
  const paying = document.querySelector('[name="revenue_paying_percent"]');
  const dropoff = document.querySelector('[name="revenue_dropoff_percent"]');
  if (!panel || !source || !paying || !dropoff) return;

  const data = JSON.parse(source.textContent);
  const months = (data.months || []).map(Number);
  const gold = Number(data.gold_pence || 0);
  const real = Number(data.real_pence || 0);
  const grouped = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
  const pounds = (pence) => '£' + grouped.format(pence / 100);
  const percent = (value) => String(Number(value.toFixed(2)));
  const $ = (selector) => panel.querySelector(selector);
  const text = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };

  const monthRows = $('[data-live-months]');
  months.forEach((_, index) => {
    const row = document.createElement('tr');
    const head = document.createElement('th');
    head.scope = 'row';
    head.textContent = 'Month ' + (index + 1);
    const a = document.createElement('td');
    const b = document.createElement('td');
    a.className = b.className = 'sys-num';
    row.append(head, a, b);
    monthRows.append(row);
  });

  const asNumber = (input) => (input.value.trim() === '' ? NaN : Number(input.value));
  const inRange = (n) => Number.isFinite(n) && n >= 0 && n <= 100;

  function message(words) {
    $('[data-live-message]').textContent = words;
    $('[data-live-message]').hidden = false;
    $('[data-live-rows]').hidden = true;
    $('[data-live-table]').hidden = true;
    $('[data-live-round]').hidden = true;
  }

  function render() {
    const p = asNumber(paying);
    const d = asNumber(dropoff);
    if (!data.ready) return message('The figures will be ready after the next hourly update.');
    if (!inRange(p) || !inRange(d)) return message('Type a percentage from 0 to 100 to see the effect.');
    if (!real) return message('Nothing approved yet, so there is nothing to work out.');
    const share = p / 100;
    const stay = 1 - d / 100;
    $('[data-live-message]').hidden = true;
    $('[data-live-rows]').hidden = false;
    $('[data-live-table]').hidden = false;
    $('[data-live-round]').hidden = false;

    const assumedMonths = months.map((pence, index) => pence * share * Math.pow(stay, index));
    const assumedGold = gold * share;
    const assumed = assumedMonths.reduce((sum, value) => sum + value, assumedGold);
    const paid = real * share;
    const lost = real - assumed;
    const plain = p === 100 && d === 0;

    text('[data-live="real"]', pounds(real));
    text('[data-live-label="paying"]', 'If ' + percent(p) + '% actually pay');
    text('[data-live="paid"]', pounds(paid));
    text('[data-live-label="dropoff"]', 'And ' + percent(d) + '% leave each month');
    text('[data-live="less"]', pounds(paid - assumed) + ' less');
    text('[data-live="assumed"]', pounds(assumed));
    text('[data-live="difference"]', plain ? 'No difference. The Office shows only the real figure.' : pounds(lost) + ' less, ' + (lost / real * 100).toFixed(1) + '%');

    monthRows.querySelectorAll('tr').forEach((row, index) => {
      row.children[1].textContent = pounds(months[index]);
      row.children[2].textContent = pounds(assumedMonths[index]);
    });
    $('[data-live-gold]').hidden = !gold;
    text('[data-live="gold-real"]', pounds(gold));
    text('[data-live="gold-assumed"]', pounds(assumedGold));
    text('[data-live="all-real"]', pounds(real));
    text('[data-live="all-assumed"]', pounds(assumed));
  }

  ['input', 'change'].forEach((name) => { paying.addEventListener(name, render); dropoff.addEventListener(name, render); });
  paying.form?.addEventListener('reset', () => setTimeout(render, 0));
  panel.hidden = false;
  render();
})();
