/* Calls: the first real play of a voicemail marks it heard (POST once), then the "New" marker goes and the sidebar badge shows the new count.
   One player at a time. A failed POST is tried again on the next play. */
import { csrfToken } from './api.js';

const CAP = 100; // the server counts up to 100 and means "100 or more"

function badgeText(n) { return n >= CAP ? `${CAP}+` : String(n); }

function setBadges(n) {
  document.querySelectorAll('[data-calls-badge]').forEach((el) => {
    if (!n) { el.textContent = ''; return; }
    const shell = el.dataset.callsBadge === 'menu' ? Object.assign(document.createElement('span'), { className: 'o-count' }) : el;
    shell.textContent = badgeText(n);
    const hint = document.createElement('span');
    hint.className = 'sr-only';
    hint.textContent = ' unheard';
    shell.append(hint);
    if (shell !== el) el.replaceChildren(shell);
  });
}

function markShown(audio) {
  audio.removeAttribute('data-unheard');
  audio.closest('[data-call]')?.querySelectorAll('[data-call-new]').forEach((el) => el.remove());
  const line = document.querySelector('[data-call-heard]');
  if (line) line.textContent = 'Heard just now';
}

async function markHeard(audio) {
  if (!audio.hasAttribute('data-unheard') || audio.dataset.sending) return;
  audio.dataset.sending = '1';
  try {
    const token = csrfToken() || document.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
    const response = await fetch(audio.dataset.heardUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-Requested-With': 'fetch', 'X-CSRFToken': token },
    });
    if (!response.ok) return;
    const data = await response.json();
    markShown(audio);
    if (typeof data.unheard === 'number') setBadges(data.unheard);
  } catch (error) {
    /* offline or a blip: the next play tries again */
  } finally {
    delete audio.dataset.sending;
  }
}

// `playing` (sound really started, not just a press on a stalled player) does not bubble, so listen while it travels down.
document.addEventListener('playing', (event) => {
  const audio = event.target;
  if (!(audio instanceof HTMLAudioElement) || !audio.matches('[data-call-audio]')) return;
  document.querySelectorAll('[data-call-audio]').forEach((other) => { if (other !== audio && !other.paused) other.pause(); });
  markHeard(audio);
}, true);
