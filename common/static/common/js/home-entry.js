/* The first journey question on the home page. Tapping a time saves the answer and opens the journey on screen 1
   with it selected. */
import { getJson, postWithRetry } from './api.js';

const root = document.querySelector('[data-home-entry]');
const status = root?.querySelector('[data-entry-status]');
const JOURNEY_FIRST = '/journey/your-time/';
let busy = false;

async function begin(button) {
  if (busy) return;
  busy = true;
  root.querySelectorAll('[data-entry-option]').forEach((b) => b.setAttribute('aria-disabled', 'true'));
  button.classList.add('is-chosen');
  if (status) { status.dataset.state = 'hint'; status.textContent = 'One moment'; }
  try {
    const params = new URLSearchParams();
    if (document.referrer) params.set('ref', document.referrer);
    new URLSearchParams(location.search).forEach((value, key) => { if (key.startsWith('utm_')) params.set(key, value); });
    await getJson(`/journey/state/?${params}`); // creates the session and sets the cookies
    const saved = await postWithRetry('/journey/answer/', { question: 'time', options: [button.dataset.entryOption] });
    if (saved.ok) await postWithRetry('/journey/step/', { step: 1 });
    // Even if saving failed, the journey opens: it saves again as he goes.
  } catch { /* the journey page boots on its own */ }
  location.assign(JOURNEY_FIRST);
}

root?.querySelectorAll('[data-entry-option]').forEach((button) => {
  button.addEventListener('click', () => begin(button));
});
